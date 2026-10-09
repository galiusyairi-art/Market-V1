"""Technical indicators on pandas Series/DataFrames (OHLCV, lowercase columns)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    prev = df["close"].shift(1)
    return pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Wilder ATR."""
    return true_range(df).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    """Wilder RSI."""
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = up / dn.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.where(dn != 0, 100.0)


def session_dates(idx: pd.DatetimeIndex) -> pd.Index:
    return idx.normalize()


def session_vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP that resets every session (intraday bars)."""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    day = session_dates(df.index)
    pv = (tp * df["volume"]).groupby(day).cumsum()
    vv = df["volume"].groupby(day).cumsum()
    return pv / vv.replace(0, np.nan)


def rth(df: pd.DataFrame) -> pd.DataFrame:
    """Regular trading hours (09:30–16:00 New York) slice of intraday bars."""
    t = df.index.hour * 60 + df.index.minute
    return df[(t >= 570) & (t < 960)]


def premarket(df: pd.DataFrame) -> pd.DataFrame:
    t = df.index.hour * 60 + df.index.minute
    return df[(t >= 240) & (t < 570)]


def cumulative_rvol(df: pd.DataFrame, lookback: int = 14) -> pd.Series:
    """Relative volume by time of day: today's cumulative RTH volume up to each minute
    divided by the average cumulative volume at the same minute over the prior `lookback` sessions."""
    r = rth(df)
    if r.empty:
        return pd.Series(dtype=float)
    day = session_dates(r.index)
    minute = r.index.hour * 60 + r.index.minute
    cum = r["volume"].groupby(day).cumsum()
    tab = pd.DataFrame({"day": day, "minute": minute, "cum": cum.values}, index=r.index)
    piv = tab.pivot_table(index="day", columns="minute", values="cum", aggfunc="last").sort_index()
    piv = piv.ffill(axis=1)
    base = piv.shift(1).rolling(lookback, min_periods=max(3, lookback // 3)).mean()
    rel = (piv / base).stack(future_stack=True)
    rel.index.names = ["day", "minute"]
    keys = pd.MultiIndex.from_arrays([tab["day"], tab["minute"]])
    return pd.Series(rel.reindex(keys).values, index=r.index)


def daily_from_intraday(df: pd.DataFrame) -> pd.DataFrame:
    r = rth(df)
    g = r.groupby(session_dates(r.index))
    return pd.DataFrame({
        "open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
        "close": g["close"].last(), "volume": g["volume"].sum(),
    })
