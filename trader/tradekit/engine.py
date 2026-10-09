"""Decides which fresh signals become alerts: meta-model probability, setup health, risk limits, de-duplication."""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from .alerts import SETUP_HE, Notifier, render
from .config import var
from .features import matrix
from .journal import Journal
from .learn import SETUPS
from .risk import RiskConfig, shares_for
from .signals import INTRADAY, Signal

log = logging.getLogger("tradekit.engine")


class AlertEngine:
    def __init__(self, cfg: dict, journal: Journal, notifier: Notifier, models: dict, health: dict, mkt: pd.DataFrame | None):
        self.cfg, self.journal, self.notifier = cfg, journal, notifier
        self.models, self.health, self.mkt = models, health, mkt
        self.risk = RiskConfig(**cfg["risk"])

    def score(self, sigs: list[Signal]) -> np.ndarray:
        probs = np.full(len(sigs), np.nan)
        for hz in {s.horizon for s in sigs}:
            m = self.models.get(hz)
            ix = [i for i, s in enumerate(sigs) if s.horizon == hz]
            if m is not None and ix and self.cfg["meta"]["enabled"]:
                probs[ix] = m.predict(matrix([sigs[i] for i in ix], SETUPS[hz], self.mkt))
        return probs

    def threshold(self, hz: str) -> float:
        if self.cfg["meta"]["min_prob"] is not None:
            return float(self.cfg["meta"]["min_prob"])
        m = self.models.get(hz)
        return m.threshold if m is not None else 0.0

    def today_r(self) -> float:
        df = self.journal.frame()
        if df.empty:
            return 0.0
        today = pd.Timestamp.now(tz="America/New_York").date().isoformat()
        d = df[(df["horizon"] == INTRADAY) & df["ts"].str.startswith(today) & df["r"].notna()]
        return float(d["r"].sum())

    def open_count(self, hz: str) -> int:
        df = self.journal.frame("open")
        if df.empty:
            return 0
        df = df[df["horizon"] == hz]
        if hz == INTRADAY:
            today = pd.Timestamp.now(tz="America/New_York").date().isoformat()
            df = df[df["ts"].str.startswith(today)]
        return len(df)

    def handle(self, sigs: list[Signal]) -> list[dict]:
        sigs = [s for s in sigs if s.valid() and not self.journal.has(s.key)]
        if not sigs:
            return []
        probs = self.score(sigs)
        sent = []
        for s, p in sorted(zip(sigs, probs), key=lambda x: -(x[1] if x[1] == x[1] else 0)):
            h = self.health.get(s.setup, {})
            if h.get("muted"):
                log.info("skip %s: setup %s muted", s.symbol, s.setup)
                continue
            if p == p and p < self.threshold(s.horizon):
                log.info("skip %s %s: p=%.2f below threshold", s.symbol, s.setup, p)
                continue
            if s.horizon == INTRADAY and self.today_r() <= -self.risk.daily_loss_r:
                log.info("daily loss limit reached; intraday alerts paused")
                continue
            if self.open_count(s.horizon) >= (self.risk.max_open_intraday if s.horizon == INTRADAY else self.risk.max_open_swing):
                log.info("skip %s: max open %s alerts reached", s.symbol, s.horizon)
                continue
            prob = None if p != p else float(p)
            shares = shares_for(s, self.risk, prob)
            if not self.journal.add(s, prob, shares):
                continue
            self.notifier.send(render(s, prob, shares))
            sent.append({**s.to_dict(), "prob": prob, "shares": shares})
        if sent:
            self.export_dashboard()
        return sent

    def export_dashboard(self) -> None:
        """Open alerts in the cockpit dashboard's picks format (var/dashboard/alerts.json)."""
        df = self.journal.frame("open")
        rows = []
        for i, a in enumerate(df.sort_values("created_at", ascending=False).head(20).itertuples(), start=1):
            pct = (a.target / a.entry - 1) * 100
            rows.append({"rank": i, "symbol": a.symbol, "name": SETUP_HE.get(a.setup, a.setup), "prev_close": a.entry,
                         "pre_price": None, "pre_pct": None, "reg_price": None, "reg_pct": None,
                         "entry": a.entry, "stop": a.stop, "take_profit": a.take_profit, "target": a.target,
                         "target_pct": round(pct, 2), "confidence": None if a.prob is None or a.prob != a.prob else round(a.prob * 100),
                         "thesis": a.note, "catalyst": SETUP_HE.get(a.setup, a.setup), "setup": a.horizon, "ts": a.ts})
        p = var(self.cfg, "dashboard", "alerts.json")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rows, ensure_ascii=False, indent=1, default=str))
