"""Swing setups on daily bars. A signal fires at a day's close; entry is that close.

- earnings_gap:  big gap up on heavy volume that holds into the close (post-earnings/news drift).
- trend_pullback: established uptrend, pullback to the 20 EMA that turns back up.
- base_breakout: tight base (volatility contraction) breaking to a 50-day high near the 52-week high.
- rsi2_reversion: Connors RSI(2) oversold dip inside a long-term uptrend.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..indicators import atr, ema, rsi, sma
from ..signals import SWING, Signal

DEFAULTS = {
    "earnings_gap": {"min_gap": 0.05, "min_vol_ratio": 2.0, "min_close_pos": 0.5, "target_r": 2.5, "max_bars": 20,
                     "min_price": 5.0},
    "trend_pullback": {"touch": 0.01, "rsi_lo": 40, "rsi_hi": 60, "stop_atr": 0.25, "target_r": 2.0, "max_bars": 15,
                       "min_price": 5.0},
    "base_breakout": {"high_n": 50, "near_52w": 0.15, "contraction": 0.8, "min_vol_ratio": 1.5, "stop_atr": 1.5,
                      "target_r": 3.0, "max_bars": 30, "min_price": 5.0},
    "rsi2_reversion": {"rsi_max": 10, "stop_atr": 2.0, "max_bars": 7, "min_price": 5.0},
}


def frame(daily: pd.DataFrame) -> pd.DataFrame:
    d = daily.copy()
    c = d["close"]
    d["atr"] = atr(d, 14)
    d["atr10"], d["atr50"] = atr(d, 10), atr(d, 50)
    d["ema20"], d["sma5"], d["sma50"], d["sma200"] = ema(c, 20), sma(c, 5), sma(c, 50), sma(c, 200)
    d["rsi14"], d["rsi2"] = rsi(c, 14), rsi(c, 2)
    d["vol50"] = d["volume"].rolling(50).mean().shift(1)
    d["hi52"] = d["high"].rolling(252, min_periods=120).max()
    d["gap"] = d["open"] / c.shift(1) - 1
    rng = (d["high"] - d["low"]).replace(0, np.nan)
    d["close_pos"] = (c - d["low"]) / rng
    return d


def _features(d: pd.DataFrame, i: int) -> dict:
    r = d.iloc[i]
    c = d["close"]
    return {
        "atr_pct": r["atr"] / r["close"], "rsi14": r["rsi14"], "rsi2": r["rsi2"],
        "ret_5d": r["close"] / c.iloc[i - 5] - 1, "ret_20d": r["close"] / c.iloc[i - 20] - 1,
        "dist_ema20_atr": (r["close"] - r["ema20"]) / r["atr"], "dist_sma50": r["close"] / r["sma50"] - 1,
        "dist_sma200": r["close"] / r["sma200"] - 1 if pd.notna(r["sma200"]) else 0.0,
        "vol_ratio": r["volume"] / r["vol50"], "gap_pct": r["gap"], "close_pos": r["close_pos"],
        "dist_52w": r["close"] / r["hi52"] - 1, "contraction": r["atr10"] / r["atr50"], "side": 1,
    }


def _emit(symbol, d, mask, build, cooldown=5) -> list[Signal]:
    out, last = [], -10**9
    for i in np.flatnonzero(mask.fillna(False).to_numpy()):
        if i < 60 or i - last < cooldown:
            continue
        s = build(i)
        if s is not None and s.valid():
            out.append(s)
            last = i
    return out


def earnings_gap(symbol: str, daily: pd.DataFrame, p: dict | None = None, d: pd.DataFrame | None = None) -> list[Signal]:
    p = {**DEFAULTS["earnings_gap"], **(p or {})}
    d = frame(daily) if d is None else d
    m = (d["gap"] >= p["min_gap"]) & (d["volume"] >= p["min_vol_ratio"] * d["vol50"]) & \
        (d["close_pos"] >= p["min_close_pos"]) & (d["close"] >= p["min_price"])

    def build(i):
        r = d.iloc[i]
        entry, stop = float(r["close"]), float(r["low"])
        if entry - stop < 0.3 * r["atr"]:
            stop = entry - 0.3 * r["atr"]
        risk = entry - stop
        return Signal(symbol, d.index[i], "earnings_gap", SWING, 1, entry, stop, entry + p["target_r"] * risk,
                      p["max_bars"], take_profit=entry + risk, note=f"גאפ {r['gap']:.0%} בנפח ×{r['volume'] / r['vol50']:.1f}",
                      features=_features(d, i))
    return _emit(symbol, d, m, build)


def trend_pullback(symbol: str, daily: pd.DataFrame, p: dict | None = None, d: pd.DataFrame | None = None) -> list[Signal]:
    p = {**DEFAULTS["trend_pullback"], **(p or {})}
    d = frame(daily) if d is None else d
    up = (d["close"] > d["sma50"]) & (d["sma50"] > d["sma200"]) & (d["sma50"] > d["sma50"].shift(10))
    touch = d["low"] <= d["ema20"] * (1 + p["touch"])
    turn = (d["close"] > d["open"]) & (d["close"] > d["ema20"])
    m = up & touch & turn & d["rsi14"].between(p["rsi_lo"], p["rsi_hi"]) & (d["close"] >= p["min_price"])

    def build(i):
        r = d.iloc[i]
        entry = float(r["close"])
        stop = float(d["low"].iloc[i - 2:i + 1].min() - p["stop_atr"] * r["atr"])
        risk = entry - stop
        return Signal(symbol, d.index[i], "trend_pullback", SWING, 1, entry, stop, entry + p["target_r"] * risk,
                      p["max_bars"], take_profit=entry + risk, note="פולבק ל-EMA20 במגמת עלייה", features=_features(d, i))
    return _emit(symbol, d, m, build)


def base_breakout(symbol: str, daily: pd.DataFrame, p: dict | None = None, d: pd.DataFrame | None = None) -> list[Signal]:
    p = {**DEFAULTS["base_breakout"], **(p or {})}
    d = frame(daily) if d is None else d
    prior_hi = d["high"].rolling(p["high_n"]).max().shift(1)
    m = (d["close"] > prior_hi) & (d["close"] >= d["hi52"] * (1 - p["near_52w"])) & \
        (d["atr10"].shift(1) <= p["contraction"] * d["atr50"].shift(1)) & \
        (d["volume"] >= p["min_vol_ratio"] * d["vol50"]) & (d["close"] >= p["min_price"])

    def build(i):
        r = d.iloc[i]
        entry = float(r["close"])
        stop = float(max(entry - p["stop_atr"] * r["atr"], d["low"].iloc[i - 10:i].min()))
        if stop >= entry:
            return None
        risk = entry - stop
        return Signal(symbol, d.index[i], "base_breakout", SWING, 1, entry, stop, entry + p["target_r"] * risk,
                      p["max_bars"], take_profit=entry + 1.5 * risk, note="פריצת בסיס צר לשיא 50 יום", features=_features(d, i))
    return _emit(symbol, d, m, build)


def rsi2_reversion(symbol: str, daily: pd.DataFrame, p: dict | None = None, d: pd.DataFrame | None = None) -> list[Signal]:
    p = {**DEFAULTS["rsi2_reversion"], **(p or {})}
    d = frame(daily) if d is None else d
    m = (d["close"] > d["sma200"]) & (d["rsi2"] < p["rsi_max"]) & (d["close"] >= p["min_price"])

    def build(i):
        r = d.iloc[i]
        entry = float(r["close"])
        stop = entry - p["stop_atr"] * float(r["atr"])
        # Connors exits on a close above the 5-day SMA; as a fixed barrier use the SMA5 level now (at least 0.5R away)
        target = max(float(r["sma5"]), entry + 0.5 * (entry - stop))
        return Signal(symbol, d.index[i], "rsi2_reversion", SWING, 1, entry, stop, target, p["max_bars"],
                      take_profit=target, note=f"RSI(2)={r['rsi2']:.0f} מעל ממוצע 200", features=_features(d, i))
    return _emit(symbol, d, m, build, cooldown=3)


ALL = {"earnings_gap": earnings_gap, "trend_pullback": trend_pullback, "base_breakout": base_breakout,
       "rsi2_reversion": rsi2_reversion}


def scan_all(symbol: str, daily: pd.DataFrame, params: dict | None = None, setups: list[str] | None = None) -> list[Signal]:
    if len(daily) < 220:
        return []
    d = frame(daily)
    out = []
    for name, fn in ALL.items():
        if setups and name not in setups:
            continue
        out += fn(symbol, daily, (params or {}).get(name), d=d)
    return out
