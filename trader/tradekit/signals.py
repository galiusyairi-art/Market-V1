"""Signal model shared by strategies, backtester, scanner and journal."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

INTRADAY = "intraday"
SWING = "swing"


@dataclass
class Signal:
    symbol: str
    ts: pd.Timestamp            # bar close at which the setup triggered (entry is filled after this)
    setup: str
    horizon: str                # INTRADAY or SWING
    side: int                   # +1 long, -1 short
    entry: float
    stop: float
    target: float               # profit barrier (full objective)
    max_bars: int               # time barrier, in bars of the horizon's timeframe
    take_profit: float | None = None   # partial-exit level shown in alerts (not a barrier)
    note: str = ""
    features: dict[str, Any] = field(default_factory=dict)

    @property
    def risk(self) -> float:
        return abs(self.entry - self.stop)

    @property
    def reward_r(self) -> float:
        return abs(self.target - self.entry) / self.risk if self.risk else 0.0

    @property
    def key(self) -> str:
        return f"{self.symbol}|{self.setup}|{pd.Timestamp(self.ts).date()}"

    def valid(self) -> bool:
        if self.risk <= 0 or self.entry <= 0:
            return False
        if self.side > 0:
            return self.stop < self.entry < self.target
        return self.target < self.entry < self.stop

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ts"] = pd.Timestamp(self.ts).isoformat()
        d["risk"] = self.risk
        d["reward_r"] = round(self.reward_r, 2)
        return d


@dataclass
class Outcome:
    exit_ts: pd.Timestamp
    exit_price: float
    exit_reason: str            # target | stop | time
    r_multiple: float           # net of costs
    bars_held: int
    mfe_r: float                # max favourable excursion in R
    mae_r: float                # max adverse excursion in R
