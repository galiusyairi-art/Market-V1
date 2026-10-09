"""Synthetic market for demos and tests (no network, no broker).

The generator plants a weak, *learnable* regularity so the whole pipeline can be checked end to end:
strong-volume gap days and days that open on heavy relative volume tend to continue. Results on this data say
nothing about real markets.
"""
from __future__ import annotations

import zlib

import numpy as np
import pandas as pd

TZ = "America/New_York"


def daily(symbol: str, days: int = 900, seed: int | None = None, start: str = "2023-01-02", drift: float = 0.0004) -> pd.DataFrame:
    rng = np.random.default_rng(seed if seed is not None else zlib.crc32(symbol.encode()))
    idx = pd.bdate_range(start, periods=days)
    vol = 0.018 * np.exp(rng.normal(0, 0.25))
    regime = np.cumsum(rng.normal(0, 0.02, days))
    rets = drift + 0.0006 * np.sign(np.sin(regime)) + rng.standard_t(4, days) * vol / 1.4
    gaps = np.zeros(days)
    shock = rng.random(days) < 0.015
    gaps[shock] = rng.normal(0.02, 0.07, shock.sum())
    follow = np.zeros(days)
    for i in np.flatnonzero(shock):
        follow[i + 1:i + 11] += np.sign(gaps[i]) * 0.0025  # post-gap drift
    close = 50 * np.exp(np.cumsum(rets + gaps + follow[:days]))
    open_ = np.r_[close[0], close[:-1]] * np.exp(gaps + rng.normal(0, vol / 4, days))
    hi = np.maximum(open_, close) * np.exp(np.abs(rng.normal(0, vol / 2, days)))
    lo = np.minimum(open_, close) * np.exp(-np.abs(rng.normal(0, vol / 2, days)))
    base_vol = rng.uniform(1e6, 2e7)
    v = base_vol * np.exp(rng.normal(0, 0.3, days)) * (1 + 4 * shock)
    return pd.DataFrame({"open": open_, "high": hi, "low": lo, "close": close, "volume": v.round()}, index=idx)


def intraday(symbol: str, days: int = 120, seed: int | None = None, start: str = "2026-03-02",
             with_premarket: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (1-minute bars incl. premarket, matching daily bars that start 60 sessions earlier)."""
    rng = np.random.default_rng(seed if seed is not None else zlib.crc32(symbol.encode()) + 7)
    warm = 60
    d = daily(symbol, days + warm, seed=rng.integers(1 << 31), start=(pd.Timestamp(start) - pd.offsets.BDay(warm)).strftime("%Y-%m-%d"))
    sessions = d.index[warm:]
    frames = []
    prev_close = d["close"].iloc[warm - 1]
    for day in sessions:
        in_play = rng.random() < 0.15
        gap = rng.normal(0.0, 0.01) + (rng.choice([-1, 1]) * rng.uniform(0.03, 0.09) if in_play and rng.random() < 0.5 else 0)
        o = prev_close * (1 + gap)
        sig = 0.0011 * (1.8 if in_play else 1.0)
        trend = (np.sign(gap) if abs(gap) > 0.025 else rng.choice([-1, 1])) * (0.00012 if in_play else 0.0)
        n = 390
        r = trend + rng.normal(0, sig, n)
        c = o * np.exp(np.cumsum(r))
        op = np.r_[o, c[:-1]]
        h = np.maximum(op, c) * np.exp(np.abs(rng.normal(0, sig / 2, n)))
        l = np.minimum(op, c) * np.exp(-np.abs(rng.normal(0, sig / 2, n)))
        u = np.linspace(-1, 1, n)
        shape = 1 + 2.5 * u ** 2
        v = 3000 * shape * np.exp(rng.normal(0, 0.4, n)) * (4 if in_play else 1)
        ix = pd.date_range(pd.Timestamp(day).tz_localize(TZ) + pd.Timedelta(minutes=570), periods=n, freq="1min")
        frames.append(pd.DataFrame({"open": op, "high": h, "low": l, "close": c, "volume": v.round()}, index=ix))
        if with_premarket:
            m = 90
            pr = prev_close * np.exp(np.cumsum(rng.normal(gap / m, sig / 2, m)))
            pop = np.r_[prev_close, pr[:-1]]
            pix = pd.date_range(ix[0] - pd.Timedelta(minutes=m), periods=m, freq="1min")
            frames.append(pd.DataFrame({"open": pop, "high": np.maximum(pop, pr) * 1.0005, "low": np.minimum(pop, pr) * 0.9995,
                                        "close": pr, "volume": (300 * (5 if in_play else 1) * np.exp(rng.normal(0, 0.5, m))).round()}, index=pix))
        prev_close = c[-1]
    m1 = pd.concat(frames).sort_index()
    from ..indicators import daily_from_intraday
    dd = daily_from_intraday(m1)
    dd.index = dd.index.tz_localize(None)
    hist = d.iloc[:warm].copy()
    return m1, pd.concat([hist, dd])
