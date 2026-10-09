"""Run setups over history, label every signal with the triple barrier, and summarise results in R."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .labeling import simulate
from .signals import INTRADAY, Signal
from .strategies import intraday as intra
from .strategies import swing


@dataclass
class Trade:
    signal: Signal
    r: float
    exit_reason: str
    exit_ts: pd.Timestamp
    bars_held: int
    mfe_r: float
    mae_r: float


def run_swing(daily_by_symbol: dict[str, pd.DataFrame], params: dict | None = None, setups: list[str] | None = None,
              slippage_bps: float = 5.0) -> list[Trade]:
    trades = []
    for sym, d in daily_by_symbol.items():
        for s in swing.scan_all(sym, d, params, setups):
            fut = d[d.index > s.ts]
            o = simulate(s, fut, slippage_bps)
            if o is not None and o.bars_held > 0:
                trades.append(Trade(s, o.r_multiple, o.exit_reason, o.exit_ts, o.bars_held, o.mfe_r, o.mae_r))
    return trades


def run_intraday(m1_by_symbol: dict[str, pd.DataFrame], daily_by_symbol: dict[str, pd.DataFrame],
                 params: dict | None = None, setups: list[str] | None = None, top_k: int = 20,
                 slippage_bps: float = 5.0) -> list[Trade]:
    """`top_k`: per day keep only the K signals per setup with the highest relative volume (the "stocks in play")."""
    sigs: list[Signal] = []
    for sym, m1 in m1_by_symbol.items():
        d = daily_by_symbol.get(sym)
        if d is None or m1.empty:
            continue
        for name, fn in intra.ALL.items():
            if setups and name not in setups:
                continue
            sigs += fn(sym, m1, d, (params or {}).get(name))
    sigs = rank_in_play(sigs, top_k)
    trades = []
    for s in sigs:
        m1 = m1_by_symbol[s.symbol]
        fut = m1[m1.index > s.ts]
        o = simulate(s, fut, slippage_bps)
        if o is not None:
            trades.append(Trade(s, o.r_multiple, o.exit_reason, o.exit_ts, o.bars_held, o.mfe_r, o.mae_r))
    return trades


def rank_in_play(sigs: list[Signal], top_k: int) -> list[Signal]:
    if not sigs or not top_k:
        return sigs
    df = pd.DataFrame({"i": range(len(sigs)), "day": [pd.Timestamp(s.ts).normalize() for s in sigs],
                       "setup": [s.setup for s in sigs], "rvol": [s.features.get("rvol", 0) for s in sigs]})
    keep = df.sort_values("rvol", ascending=False).groupby(["day", "setup"]).head(top_k)["i"]
    return [sigs[i] for i in sorted(keep)]


def trades_frame(trades: list[Trade]) -> pd.DataFrame:
    rows = []
    for t in trades:
        s = t.signal
        rows.append({"ts": pd.Timestamp(s.ts), "symbol": s.symbol, "setup": s.setup, "horizon": s.horizon,
                     "side": s.side, "entry": s.entry, "stop": s.stop, "target": s.target, "r": t.r,
                     "exit_reason": t.exit_reason, "bars_held": t.bars_held, "mfe_r": t.mfe_r, "mae_r": t.mae_r})
    return pd.DataFrame(rows)


def stats(r: pd.Series) -> dict:
    r = pd.Series(r, dtype=float).dropna()
    if r.empty:
        return {"trades": 0}
    eq = r.cumsum()
    dd = (eq - eq.cummax()).min()
    wins, losses = r[r > 0], r[r <= 0]
    return {
        "trades": int(len(r)),
        "win_rate": float((r > 0).mean()),
        "avg_r": float(r.mean()),
        "total_r": float(r.sum()),
        "profit_factor": float(wins.sum() / -losses.sum()) if losses.sum() < 0 else float("inf"),
        "avg_win_r": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss_r": float(losses.mean()) if len(losses) else 0.0,
        "max_dd_r": float(dd),
        "sqn": float(np.sqrt(min(len(r), 100)) * r.mean() / r.std()) if len(r) > 1 and r.std() > 0 else 0.0,
    }


def report(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    rows = {"ALL": stats(df["r"])}
    for k, g in df.groupby("setup"):
        rows[k] = stats(g["r"])
    return pd.DataFrame(rows).T
