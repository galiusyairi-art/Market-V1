"""Intraday setups on 1-minute bars (New York time, premarket included).

Every function looks only at data available at the bar it signals on, so the same code
drives both the backtest (all days) and the live scanner (latest day).

- orb:          5-minute Opening Range Breakout on "stocks in play" (Zarattini, Barbon & Aziz 2024).
- vwap_pullback: trend day, first orderly pullback to session VWAP that holds.
- gap_and_go:   premarket gapper breaking its premarket high in the first half hour.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..indicators import atr, cumulative_rvol, premarket, rth, session_vwap
from ..signals import INTRADAY, Signal

DEFAULTS = {
    "orb": {"or_minutes": 5, "min_rvol": 1.0, "min_price": 5.0, "stop_atr": 0.10, "target_r": 5.0,
            "entry_until": 660, "allow_short": True, "lookback": 14},
    "vwap_pullback": {"min_rvol": 1.5, "start": 600, "until": 900, "trend_bars": 30, "above_frac": 0.8,
                      "tol": 0.001, "target_r": 2.0, "min_price": 5.0, "allow_short": True},
    "gap_and_go": {"min_gap": 0.04, "min_price": 3.0, "min_rvol": 2.0, "window": 30, "max_risk_atr": 0.6,
                   "target_r": 2.0},
}


def _minutes(idx: pd.DatetimeIndex) -> np.ndarray:
    return (idx.hour * 60 + idx.minute).to_numpy()


def _prior_atr(daily: pd.DataFrame) -> pd.Series:
    return atr(daily, 14).shift(1)


def _to_close(ts: pd.Timestamp) -> int:
    """Bars left until the 16:00 close (time barrier); independent of how much of the day has been seen."""
    return max(1, 960 - (ts.hour * 60 + ts.minute) - 1)


def _base_features(day, g, daily, datr):
    dn = day.tz_localize(None) if day.tzinfo else day  # daily bars are tz-naive dates
    prev = daily[daily.index < dn]
    if len(prev) < 21:
        return None
    a = datr.get(dn, np.nan)
    if pd.isna(a):  # today's daily bar may not exist yet (live): ATR as of the last completed day
        a = atr(prev, 14).iloc[-1]
    if pd.isna(a) or a <= 0:
        return None
    pc = prev["close"]
    a = float(a)
    return {
        "atr": a,
        "atr_pct": a / pc.iloc[-1],
        "gap_pct": g["open"].iloc[0] / pc.iloc[-1] - 1,
        "prev_ret": pc.iloc[-1] / pc.iloc[-2] - 1,
        "ret_5d": pc.iloc[-1] / pc.iloc[-6] - 1,
        "ret_20d": pc.iloc[-1] / pc.iloc[-21] - 1,
    }


def orb(symbol: str, m1: pd.DataFrame, daily: pd.DataFrame, p: dict | None = None) -> list[Signal]:
    p = {**DEFAULTS["orb"], **(p or {})}
    r = rth(m1)
    if r.empty:
        return []
    n = p["or_minutes"]
    datr = _prior_atr(daily)
    days = r.index.normalize()
    or_vol = r.groupby(days)["volume"].apply(lambda v: v.iloc[:n].sum())
    or_base = or_vol.shift(1).rolling(p["lookback"], min_periods=5).mean()
    vwap = session_vwap(r)
    out = []
    for day, g in r.groupby(days):
        if len(g) <= n or pd.isna(or_base.get(day)) or or_base[day] <= 0:
            continue
        f = _base_features(day, g, daily, datr)
        if f is None or g["open"].iloc[0] < p["min_price"]:
            continue
        rv = or_vol[day] / or_base[day]
        if rv < p["min_rvol"]:
            continue
        first = g.iloc[:n]
        d = np.sign(first["close"].iloc[-1] - first["open"].iloc[0])
        if d == 0 or (d < 0 and not p["allow_short"]):
            continue
        level = first["high"].max() if d > 0 else first["low"].min()
        rest = g.iloc[n:]
        rest = rest[_minutes(rest.index) < p["entry_until"]]
        trig = rest[rest["high"] >= level] if d > 0 else rest[rest["low"] <= level]
        if trig.empty:
            continue
        ts = trig.index[0]
        entry = float(trig["close"].iloc[0])
        a = f["atr"]
        stop = entry - d * p["stop_atr"] * a
        risk = abs(entry - stop)
        tgt = entry + d * p["target_r"] * risk
        feats = {**f, "rvol": rv, "or_range_atr": (first["high"].max() - first["low"].min()) / a,
                 "minute": int(ts.hour * 60 + ts.minute), "dist_vwap_atr": (entry - vwap[ts]) / a,
                 "side": int(d)}
        out.append(Signal(symbol, ts, "orb", INTRADAY, int(d), entry, float(stop), float(tgt), _to_close(ts),
                          take_profit=float(entry + d * 2 * risk),
                          note=f"פריצת טווח {n} דק׳ · RVOL {rv:.1f}", features=feats))
    return out


def vwap_pullback(symbol: str, m1: pd.DataFrame, daily: pd.DataFrame, p: dict | None = None) -> list[Signal]:
    p = {**DEFAULTS["vwap_pullback"], **(p or {})}
    r = rth(m1)
    if r.empty:
        return []
    datr = _prior_atr(daily)
    vw = session_vwap(r)
    rv = cumulative_rvol(m1)
    out = []
    for day, g in r.groupby(r.index.normalize()):
        f = _base_features(day, g, daily, datr)
        if f is None or g["open"].iloc[0] < p["min_price"]:
            continue
        a = f["atr"]
        v = vw.loc[g.index]
        above = (g["close"] > v).astype(float).rolling(p["trend_bars"]).mean()
        mins = _minutes(g.index)
        for i in range(p["trend_bars"], len(g)):
            if mins[i] < p["start"] or mins[i] >= p["until"]:
                continue
            rvi = rv.get(g.index[i], np.nan)
            if not (rvi >= p["min_rvol"]):
                continue
            b, vi = g.iloc[i], v.iloc[i]
            slope = vi - v.iloc[i - p["trend_bars"]]
            for d in (1, -1):
                if d < 0 and not p["allow_short"]:
                    continue
                trend = above.iloc[i - 1] >= p["above_frac"] if d > 0 else above.iloc[i - 1] <= 1 - p["above_frac"]
                if not trend or d * slope <= 0:
                    continue
                touched = b["low"] <= vi * (1 + p["tol"]) if d > 0 else b["high"] >= vi * (1 - p["tol"])
                held = (b["close"] > vi and b["close"] > b["open"]) if d > 0 else (b["close"] < vi and b["close"] < b["open"])
                if not (touched and held):
                    continue
                entry = float(b["close"])
                swing = g["low"].iloc[i - 2:i + 1].min() if d > 0 else g["high"].iloc[i - 2:i + 1].max()
                stop = (min(swing, vi) - 0.05 * a) if d > 0 else (max(swing, vi) + 0.05 * a)
                risk = abs(entry - stop)
                if risk < 0.05 * a or risk > 0.5 * a:
                    continue
                ts = g.index[i]
                feats = {**f, "rvol": float(rvi), "minute": int(mins[i]), "dist_vwap_atr": (entry - vi) / a,
                         "vwap_slope_atr": slope / a, "day_ret": entry / g["open"].iloc[0] - 1, "side": d}
                out.append(Signal(symbol, ts, "vwap_pullback", INTRADAY, d, entry, float(stop),
                                  float(entry + d * p["target_r"] * risk), _to_close(ts),
                                  take_profit=float(entry + d * risk), note=f"פולבק ל-VWAP ביום מגמה · RVOL {rvi:.1f}",
                                  features=feats))
                break
            if out and out[-1].ts.normalize() == day:
                break
    return out


def gap_and_go(symbol: str, m1: pd.DataFrame, daily: pd.DataFrame, p: dict | None = None) -> list[Signal]:
    p = {**DEFAULTS["gap_and_go"], **(p or {})}
    r = rth(m1)
    if r.empty:
        return []
    datr = _prior_atr(daily)
    pm_all = premarket(m1)
    rv = cumulative_rvol(m1)
    vw = session_vwap(r)
    out = []
    for day, g in r.groupby(r.index.normalize()):
        f = _base_features(day, g, daily, datr)
        if f is None or f["gap_pct"] < p["min_gap"] or g["open"].iloc[0] < p["min_price"]:
            continue
        pm = pm_all[pm_all.index.normalize() == day]
        level = pm["high"].max() if not pm.empty else g["high"].iloc[0]
        win = g[_minutes(g.index) < 570 + p["window"]]
        a = f["atr"]
        for i in range(1, len(win)):
            b = win.iloc[i]
            if b["high"] < level or b["close"] <= level * 0.998:
                continue
            ts = win.index[i]
            rvi = rv.get(ts, np.nan)
            if not (rvi >= p["min_rvol"]):
                continue
            entry = float(b["close"])
            stop = float(max(win["low"].iloc[max(0, i - 5):i + 1].min(), vw[ts] if vw[ts] < entry else -np.inf))
            stop = min(stop, entry - 0.15 * a)  # floor: a stop inside the noise just pays the spread
            risk = entry - stop
            if risk > p["max_risk_atr"] * a:
                continue
            feats = {**f, "rvol": float(rvi), "minute": int(ts.hour * 60 + ts.minute),
                     "pm_vol": float(pm["volume"].sum()) if not pm.empty else 0.0,
                     "dist_vwap_atr": (entry - vw[ts]) / a, "side": 1}
            out.append(Signal(symbol, ts, "gap_and_go", INTRADAY, 1, entry, stop, float(entry + p["target_r"] * risk),
                              _to_close(ts), take_profit=float(entry + risk),
                              note=f"גאפ {f['gap_pct']:.0%} ופריצת שיא הפרה-מרקט", features=feats))
            break
    return out


ALL = {"orb": orb, "vwap_pullback": vwap_pullback, "gap_and_go": gap_and_go}
