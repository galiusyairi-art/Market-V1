"""Feature matrix for the meta-model: per-signal features + market regime + setup one-hot."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import atr, sma
from .signals import INTRADAY, Signal

SIGNAL_FEATURES = [
    "atr_pct", "gap_pct", "ret_5d", "ret_20d", "rvol", "minute", "dist_vwap_atr", "or_range_atr", "prev_ret",
    "vwap_slope_atr", "day_ret", "pm_vol_log", "rsi14", "rsi2", "dist_ema20_atr", "dist_sma50", "dist_sma200",
    "vol_ratio", "close_pos", "dist_52w", "contraction", "side", "reward_r",
]
MARKET_FEATURES = ["mkt_above_50", "mkt_ret_5d", "mkt_ret_20d", "mkt_atr_pct"]


def market_frame(index_daily: pd.DataFrame | None) -> pd.DataFrame | None:
    if index_daily is None or index_daily.empty:
        return None
    c = index_daily["close"]
    return pd.DataFrame({
        "mkt_above_50": (c > sma(c, 50)).astype(float),
        "mkt_ret_5d": c / c.shift(5) - 1,
        "mkt_ret_20d": c / c.shift(20) - 1,
        "mkt_atr_pct": atr(index_daily, 14) / c,
    })


def market_row(mkt: pd.DataFrame | None, sig: Signal) -> dict:
    if mkt is None:
        return {}
    day = pd.Timestamp(sig.ts).normalize().tz_localize(None) if pd.Timestamp(sig.ts).tzinfo else pd.Timestamp(sig.ts).normalize()
    idx = mkt.index.tz_localize(None) if getattr(mkt.index, "tz", None) else mkt.index
    # intraday signals only know yesterday's close; swing signals fire at today's close
    pos = idx.searchsorted(day, side="left" if sig.horizon == INTRADAY else "right") - 1
    if pos < 0:
        return {}
    return mkt.iloc[pos].to_dict()


def signal_row(sig: Signal, setups: list[str], mkt: pd.DataFrame | None = None) -> dict:
    f = dict(sig.features)
    f["reward_r"] = sig.reward_r
    if "pm_vol" in f:
        f["pm_vol_log"] = float(np.log1p(f["pm_vol"]))
    row = {k: f.get(k, np.nan) for k in SIGNAL_FEATURES}
    m = market_row(mkt, sig)
    row.update({k: m.get(k, np.nan) for k in MARKET_FEATURES})
    for s in setups:
        row[f"setup_{s}"] = 1.0 if sig.setup == s else 0.0
    return row


def matrix(signals: list[Signal], setups: list[str], mkt: pd.DataFrame | None = None) -> pd.DataFrame:
    return pd.DataFrame([signal_row(s, setups, mkt) for s in signals], dtype=float)
