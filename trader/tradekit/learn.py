"""The learning loop.

1. Backtest every setup over cached history → triple-barrier outcome for each historical signal.
2. Add the journal's resolved live alerts (weighted higher: they are the conditions you actually trade in).
3. Train one meta-model per horizon, walk-forward, and pick the probability threshold that maximises expectancy.
4. Track each setup's recent live expectancy; mute a setup whose edge has faded until it recovers in backtests.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import backtest as bt
from .config import var
from .data.store import BarStore
from .features import market_frame, matrix
from .journal import Journal
from .meta import MetaModel
from .signals import INTRADAY, SWING

SETUPS = {INTRADAY: ["orb", "vwap_pullback", "gap_and_go"],
          SWING: ["earnings_gap", "trend_pullback", "base_breakout", "rsi2_reversion"]}


def load_history(store: BarStore, symbols: list[str] | None = None):
    daily = {s: store.load(s, "1d") for s in (symbols or store.symbols("1d"))}
    daily = {s: d for s, d in daily.items() if len(d) > 60}
    m1 = {s: store.load(s, "1m") for s in (symbols or store.symbols("1m"))}
    m1 = {s: d for s, d in m1.items() if not d.empty and s in daily}
    return daily, m1


def backtest_all(cfg: dict, daily: dict, m1: dict) -> dict[str, list[bt.Trade]]:
    slip = cfg["costs"]["slippage_bps"]
    p = cfg.get("strategies", {})
    out = {SWING: bt.run_swing(daily, p, cfg["swing"]["setups"], slip)}
    out[INTRADAY] = bt.run_intraday(m1, daily, p, cfg["intraday"]["setups"], cfg["intraday"]["top_k"], slip) if m1 else []
    return out


def train(cfg: dict, store: BarStore, journal: Journal | None = None, trades: dict | None = None, log=print) -> dict:
    daily, m1 = load_history(store)
    idx = cfg["universe"]["index"]
    mkt = market_frame(daily.get(idx, store.load(idx, "1d")))
    trades = trades or backtest_all(cfg, daily, m1)
    live_sigs, live_r = journal.resolved_signals() if journal else ([], [])
    summary = {}
    for hz in (INTRADAY, SWING):
        sigs = [t.signal for t in trades[hz]]
        rs = [t.r for t in trades[hz]]
        w = [1.0] * len(sigs)
        ls = [(s, r) for s, r in zip(live_sigs, live_r) if s.horizon == hz]
        sigs += [s for s, _ in ls]
        rs += [r for _, r in ls]
        w += [cfg["meta"]["live_weight"]] * len(ls)
        log(f"[{hz}] {len(sigs)} labelled signals ({len(ls)} live)")
        if len(sigs) < cfg["meta"]["min_trades"]:
            log(f"[{hz}] not enough history to train (need {cfg['meta']['min_trades']}); alerts will use setup stats only")
            summary[hz] = {"trained": False, "signals": len(sigs)}
            continue
        X = matrix(sigs, SETUPS[hz], mkt)
        r = np.asarray(rs, float)
        y = (r > 0).astype(int)
        ts = pd.Series([pd.Timestamp(s.ts).tz_localize(None) if pd.Timestamp(s.ts).tzinfo else pd.Timestamp(s.ts) for s in sigs])
        purge = 2 if hz == INTRADAY else 45
        model = MetaModel.train(X, y, r, ts, weights=np.asarray(w), folds=cfg["meta"]["folds"], purge_days=purge)
        model.save(var(cfg, "models", f"{hz}.joblib"))
        rep = model.report
        log(f"[{hz}] walk-forward AUC {rep.get('auc', float('nan')):.3f} · base avg {rep.get('base_avg_r', float('nan')):+.3f}R · threshold {model.threshold:.2f}")
        for row in rep.get("by_threshold", []):
            log(f"    p≥{row['threshold']:.2f}: {row['trades']:>5} trades ({row['kept']:.0%}) win {row['win_rate']:.0%} avg {row['avg_r']:+.3f}R")
        summary[hz] = {"trained": True, "signals": len(sigs), **{k: rep.get(k) for k in ("auc", "base_avg_r", "base_win_rate")},
                       "threshold": model.threshold}
    health = setup_health(cfg, trades, journal)
    var(cfg, "models").mkdir(parents=True, exist_ok=True)
    var(cfg, "models", "health.json").write_text(json.dumps(health, indent=1))
    summary["health"] = health
    return summary


def setup_health(cfg: dict, trades: dict, journal: Journal | None) -> dict:
    """Backtest edge per setup + rolling live edge. A setup is muted when its last `window` live alerts
    average below `mute_below_r` (with at least `min_trades`), or when its backtest expectancy is negative."""
    h = cfg["health"]
    out = {}
    live = journal.frame("resolved") if journal else pd.DataFrame()
    for hz, ts in trades.items():
        df = bt.trades_frame(ts)
        for setup in SETUPS[hz]:
            b = df[df["setup"] == setup]["r"] if not df.empty else pd.Series(dtype=float)
            lv = live[live["setup"] == setup].sort_values("exit_ts")["r"].tail(h["window"]) if not live.empty else pd.Series(dtype=float)
            bt_avg = float(b.mean()) if len(b) else None
            live_avg = float(lv.mean()) if len(lv) else None
            muted = (bt_avg is not None and len(b) >= 50 and bt_avg < 0) or \
                    (live_avg is not None and len(lv) >= h["min_trades"] and live_avg < h["mute_below_r"])
            out[setup] = {"horizon": hz, "backtest_trades": int(len(b)), "backtest_avg_r": bt_avg,
                          "backtest_win_rate": float((b > 0).mean()) if len(b) else None,
                          "live_trades": int(len(lv)), "live_avg_r": live_avg, "muted": bool(muted)}
    return out


def load_models(cfg: dict) -> tuple[dict, dict]:
    models = {hz: MetaModel.load(var(cfg, "models", f"{hz}.joblib")) for hz in (INTRADAY, SWING)}
    p = var(cfg, "models", "health.json")
    health = json.loads(p.read_text()) if Path(p).exists() else {}
    return models, health
