"""Configuration: config.yaml (see config.example.yaml) with environment overrides for secrets."""
from __future__ import annotations

import copy
import os
from pathlib import Path

import yaml

DEFAULT = {
    "var_dir": "var",
    "ibkr": {"host": "127.0.0.1", "port": 7497, "client_id": 17, "market_data_type": 1},
    "universe": {"file": "universe.txt", "index": "SPY", "watchlist": []},
    "premarket_scan": {"enabled": True, "scan_codes": ["TOP_PERC_GAIN", "HOT_BY_VOLUME"], "above_price": 3.0,
                       "above_volume": 100000, "rows": 25, "refresh_min": 5},
    "intraday": {"enabled": True, "setups": ["orb", "vwap_pullback", "gap_and_go"], "max_watch": 40, "top_k": 20,
                 "history_days": 15},
    "swing": {"enabled": True, "setups": ["earnings_gap", "trend_pullback", "base_breakout", "rsi2_reversion"],
              "run_at": "16:10"},
    "strategies": {},
    "meta": {"enabled": True, "min_prob": None, "folds": 5, "live_weight": 3.0, "min_trades": 300},
    "health": {"window": 30, "min_trades": 20, "mute_below_r": -0.05},
    "risk": {"account": 100000, "risk_pct": 0.5, "max_position_pct": 25, "max_open_intraday": 3, "max_open_swing": 8,
             "daily_loss_r": 3.0},
    "costs": {"slippage_bps": 5.0},
    "telegram": {"token": None, "chat_id": None},
}


def _merge(a: dict, b: dict) -> dict:
    out = copy.deepcopy(a)
    for k, v in (b or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load(path: str | Path | None = None) -> dict:
    cfg = copy.deepcopy(DEFAULT)
    p = Path(path) if path else Path("config.yaml")
    if p.exists():
        cfg = _merge(cfg, yaml.safe_load(p.read_text()) or {})
    cfg["telegram"]["token"] = os.environ.get("TRADEKIT_TELEGRAM_TOKEN", cfg["telegram"]["token"])
    cfg["telegram"]["chat_id"] = os.environ.get("TRADEKIT_TELEGRAM_CHAT", cfg["telegram"]["chat_id"])
    cfg["_root"] = str(p.parent.resolve())
    return cfg


def var(cfg: dict, *parts: str) -> Path:
    base = Path(cfg["var_dir"])
    if not base.is_absolute():
        base = Path(cfg.get("_root", ".")) / base
    return base.joinpath(*parts)


def universe(cfg: dict) -> list[str]:
    f = Path(cfg["universe"]["file"])
    if not f.is_absolute():
        f = Path(cfg.get("_root", ".")) / f
    syms = []
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.split("#")[0].strip().upper()
            if line:
                syms.append(line)
    syms += [s.upper() for s in cfg["universe"].get("watchlist", [])]
    return list(dict.fromkeys(syms))
