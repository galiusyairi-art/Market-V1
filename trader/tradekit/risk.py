"""Position sizing and daily guard rails."""
from __future__ import annotations

from dataclasses import dataclass

from .signals import Signal


@dataclass
class RiskConfig:
    account: float = 100_000.0
    risk_pct: float = 0.5           # % of account risked per trade (distance entry→stop)
    max_position_pct: float = 25.0  # cap on notional per position, % of account
    max_open_intraday: int = 3
    max_open_swing: int = 8
    daily_loss_r: float = 3.0       # stop sending intraday alerts after this many R lost today


def shares_for(sig: Signal, cfg: RiskConfig, prob: float | None = None) -> int:
    """Fixed-fractional sizing; scaled down when the meta-model is lukewarm (prob < 0.5)."""
    if sig.risk <= 0:
        return 0
    risk_cash = cfg.account * cfg.risk_pct / 100
    if prob is not None and prob == prob:
        risk_cash *= min(1.0, max(0.5, 0.5 + (prob - 0.4)))
    by_risk = risk_cash / sig.risk
    by_cap = cfg.account * cfg.max_position_pct / 100 / sig.entry
    return int(max(0, min(by_risk, by_cap)))
