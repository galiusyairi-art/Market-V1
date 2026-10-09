"""Live session loop against IBKR.

04:00–09:30  premarket: IBKR scanners (top % gainers, hot by volume) build the watchlist of stocks in play.
09:30–16:00  regular: every completed 1-minute bar re-runs the intraday setups for that symbol; new signals go
             through the AlertEngine (meta-model, setup health, risk) and out to Telegram/console.
16:10        swing scan over the universe on fresh daily bars, then resolve open alerts and retrain if due.
"""
from __future__ import annotations

import logging

import pandas as pd

from .data.ibkr import IBKR
from .data.store import TZ, BarStore
from .engine import AlertEngine
from .indicators import daily_from_intraday
from .strategies import intraday as intra
from .strategies import swing

log = logging.getLogger("tradekit.scanner")


def now_ny() -> pd.Timestamp:
    return pd.Timestamp.now(tz=TZ)


def minute_of_day(t: pd.Timestamp) -> int:
    return t.hour * 60 + t.minute


class LiveScanner:
    def __init__(self, cfg: dict, ib: IBKR, store: BarStore, engine: AlertEngine, universe: list[str]):
        self.cfg, self.ib, self.store, self.engine, self.universe = cfg, ib, store, engine, universe
        self.watch: dict[str, object] = {}
        self.daily: dict[str, pd.DataFrame] = {}
        self.history: dict[str, pd.DataFrame] = {}
        self.last_scan = 0
        self.swing_done = False

    # ---------- watchlist ----------
    def refresh_watchlist(self) -> None:
        ps = self.cfg["premarket_scan"]
        found: list[str] = []
        for code in ps["scan_codes"]:
            try:
                found += self.ib.scanner(code, ps["above_price"], ps["above_volume"], ps["rows"])
            except Exception as e:
                log.warning("scanner %s failed: %s", code, e)
        found += self.cfg["universe"].get("watchlist", [])
        for sym in dict.fromkeys(found):
            if len(self.watch) >= self.cfg["intraday"]["max_watch"]:
                break
            if sym not in self.watch:
                self.add(sym)

    def add(self, sym: str) -> None:
        try:
            d = self.store.load(sym, "1d")
            if len(d) < 30 or d.index[-1] < (now_ny().tz_localize(None).normalize() - pd.offsets.BDay(3)):
                d = self.ib.daily(sym, "1 Y")
                self.store.save(sym, "1d", d)
            self.daily[sym] = self.store.load(sym, "1d")
            hist = self.store.load(sym, "1m")
            need = self.cfg["intraday"]["history_days"]
            if hist.empty or hist.index.normalize().nunique() < need:
                self.ib.fetch_minutes_history(self.store, sym, need)
                hist = self.store.load(sym, "1m")
            self.history[sym] = hist
            self.watch[sym] = self.ib.stream_minutes(sym, self.on_bars)
            log.info("watching %s", sym)
        except Exception as e:
            log.warning("cannot watch %s: %s", sym, e)

    # ---------- bar handler ----------
    def on_bars(self, sym: str, live: pd.DataFrame) -> None:
        t = now_ny()
        if not (570 <= minute_of_day(t) < 960) or live.empty:
            return
        m1 = pd.concat([self.history.get(sym, live.iloc[:0]), live])
        m1 = m1[~m1.index.duplicated(keep="last")].sort_index()
        today = t.normalize()
        daily = self.daily.get(sym)
        if daily is None:
            return
        # daily history must stop before today (today's bar comes from the minutes)
        d = daily[daily.index < today.tz_localize(None)]
        sigs = []
        for name in self.cfg["intraday"]["setups"]:
            fn = intra.ALL[name]
            sigs += [s for s in fn(sym, m1, d, self.cfg.get("strategies", {}).get(name))
                     if s.ts.normalize() == today and s.ts >= live.index[-1] - pd.Timedelta(minutes=2)]
        if sigs:
            self.engine.handle(sigs)

    # ---------- end of day ----------
    def swing_scan(self) -> list[dict]:
        sigs = []
        for i, sym in enumerate(self.universe):
            try:
                d = self.ib.daily(sym, "2 Y")
                self.store.save(sym, "1d", d)
                d = self.store.load(sym, "1d")
            except Exception as e:
                log.warning("daily %s failed: %s", sym, e)
                continue
            last = d.index[-1]
            sigs += [s for s in swing.scan_all(sym, d, self.cfg.get("strategies"), self.cfg["swing"]["setups"]) if s.ts == last]
            if i % 20 == 19:
                self.ib.sleep(1)
        return self.engine.handle(sigs)

    def resolve(self) -> int:
        def bars_for(sym, hz):
            return self.store.load(sym, "1m" if hz == "intraday" else "1d")
        for sym, b in self.watch.items():
            df = self.ib._df(b, intraday=True)
            if not df.empty:
                self.store.save(sym, "1m", df)
        return self.engine.journal.resolve(bars_for)

    # ---------- main loop ----------
    def run(self) -> None:
        hh, mm = map(int, self.cfg["swing"]["run_at"].split(":"))
        swing_at = hh * 60 + mm
        log.info("scanner started; Ctrl+C to stop")
        while True:
            t = now_ny()
            m = minute_of_day(t)
            weekday = t.weekday() < 5
            if weekday and self.cfg["intraday"]["enabled"] and 240 <= m < 930:
                if m - self.last_scan >= self.cfg["premarket_scan"]["refresh_min"] or m < self.last_scan:
                    if self.cfg["premarket_scan"]["enabled"]:
                        self.refresh_watchlist()
                    self.last_scan = m
            if weekday and m >= swing_at and not self.swing_done:
                if self.cfg["swing"]["enabled"]:
                    sent = self.swing_scan()
                    log.info("swing scan: %d alerts", len(sent))
                n = self.resolve()
                log.info("resolved %d alerts", n)
                self.swing_done = True
                for b in self.watch.values():
                    self.ib.cancel_stream(b)
                self.watch.clear()
                return
            self.ib.sleep(5)


def update_daily_from_minutes(store: BarStore, sym: str) -> None:
    m1 = store.load(sym, "1m")
    if not m1.empty:
        d = daily_from_intraday(m1)
        d.index = d.index.tz_localize(None)
        store.save(sym, "1d", d)
