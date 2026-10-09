"""Triple-barrier simulation: what happened to a signal after it fired.

Conservative fill rules:
- Entry is the signal's entry price plus slippage, filled on the bar after the signal bar.
- If one bar touches both stop and target, the stop is assumed to have hit first.
- A gap through the stop/target fills at the bar's open (worse for stops, no extra credit for targets).
- Intraday signals are always flat by the session close.
"""
from __future__ import annotations

import pandas as pd

from .signals import INTRADAY, Outcome, Signal


def simulate(sig: Signal, future: pd.DataFrame, slippage_bps: float = 5.0, commission_r: float = 0.0) -> Outcome | None:
    """`future` = bars strictly after the signal bar (same timeframe as the setup)."""
    if future is None or future.empty or not sig.valid():
        return None
    if sig.horizon == INTRADAY:
        day = pd.Timestamp(sig.ts).normalize()
        future = future[future.index.normalize() == day]
        t = future.index.hour * 60 + future.index.minute
        future = future[t < 960]
        if future.empty:
            return None
    bars = future.iloc[: sig.max_bars]
    slip = sig.entry * slippage_bps / 1e4
    entry = sig.entry + sig.side * slip
    risk = abs(sig.entry - sig.stop)
    s = sig.side
    mfe = mae = 0.0
    exit_px, reason, ts, n = None, "time", bars.index[-1], len(bars)
    for i, (ts_i, b) in enumerate(bars.iterrows(), start=1):
        hi, lo, op = b["high"], b["low"], b["open"]
        fav = (hi - entry) if s > 0 else (entry - lo)
        adv = (entry - lo) if s > 0 else (hi - entry)
        mfe, mae = max(mfe, fav / risk), max(mae, adv / risk)
        hit_stop = lo <= sig.stop if s > 0 else hi >= sig.stop
        hit_tgt = hi >= sig.target if s > 0 else lo <= sig.target
        if hit_stop:
            gap_through = (op <= sig.stop) if s > 0 else (op >= sig.stop)
            exit_px, reason, ts, n = (op if gap_through else sig.stop), "stop", ts_i, i
            break
        if hit_tgt:
            exit_px, reason, ts, n = sig.target, "target", ts_i, i
            break
    if exit_px is None:
        exit_px = bars["close"].iloc[-1]
    exit_px = exit_px - s * exit_px * slippage_bps / 1e4
    r = s * (exit_px - entry) / risk - commission_r
    return Outcome(exit_ts=ts, exit_price=float(exit_px), exit_reason=reason, r_multiple=float(r),
                   bars_held=n, mfe_r=float(mfe), mae_r=float(mae))
