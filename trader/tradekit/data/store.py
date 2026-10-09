"""Local bar cache: one CSV per symbol and timeframe under var/bars/<tf>/<SYMBOL>.csv.

Anything that can write OHLCV CSVs (IBKR fetch, a vendor export, a broker download) can feed the backtester.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

TZ = "America/New_York"
COLS = ["open", "high", "low", "close", "volume"]


class BarStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def path(self, symbol: str, tf: str) -> Path:
        return self.root / tf / f"{symbol.upper()}.csv"

    def symbols(self, tf: str) -> list[str]:
        d = self.root / tf
        return sorted(p.stem for p in d.glob("*.csv")) if d.exists() else []

    def load(self, symbol: str, tf: str) -> pd.DataFrame:
        p = self.path(symbol, tf)
        if not p.exists():
            return pd.DataFrame(columns=COLS)
        df = pd.read_csv(p, index_col=0)
        idx = pd.to_datetime(df.index, utc=(tf != "1d"))
        df.index = idx.tz_convert(TZ) if tf != "1d" else idx
        return normalize(df)

    def save(self, symbol: str, tf: str, df: pd.DataFrame, merge: bool = True) -> None:
        p = self.path(symbol, tf)
        p.parent.mkdir(parents=True, exist_ok=True)
        df = normalize(df)
        if merge and p.exists():
            old = self.load(symbol, tf)
            df = pd.concat([old, df])
            df = df[~df.index.duplicated(keep="last")].sort_index()
        out = df.copy()
        if tf != "1d":
            out.index = out.index.tz_convert("UTC")
        out.to_csv(p)


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=str.lower)
    df = df[[c for c in COLS if c in df.columns]].astype(float)
    return df[~df.index.duplicated(keep="last")].sort_index()
