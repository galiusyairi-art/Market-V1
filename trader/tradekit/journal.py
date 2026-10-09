"""Alert journal (SQLite). Every alert is stored with its features; `resolve` fills in what actually happened.
Resolved alerts are the live feedback the meta-model retrains on."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

from .labeling import simulate
from .signals import Signal

SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
  key TEXT PRIMARY KEY, created_at TEXT, ts TEXT, symbol TEXT, setup TEXT, horizon TEXT, side INTEGER,
  entry REAL, stop REAL, take_profit REAL, target REAL, max_bars INTEGER, prob REAL, shares INTEGER, note TEXT,
  features TEXT, status TEXT DEFAULT 'open', exit_ts TEXT, exit_price REAL, exit_reason TEXT, r REAL,
  action TEXT, my_r REAL, comment TEXT
);
"""


class Journal:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as c:
            c.executescript(SCHEMA)

    def _db(self):
        return sqlite3.connect(self.path)

    def has(self, key: str) -> bool:
        with self._db() as c:
            return c.execute("SELECT 1 FROM alerts WHERE key=?", (key,)).fetchone() is not None

    def add(self, sig: Signal, prob: float | None, shares: int | None) -> bool:
        if self.has(sig.key):
            return False
        with self._db() as c:
            c.execute("""INSERT INTO alerts (key, created_at, ts, symbol, setup, horizon, side, entry, stop, take_profit,
                         target, max_bars, prob, shares, note, features) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (sig.key, pd.Timestamp.now(tz="UTC").isoformat(), pd.Timestamp(sig.ts).isoformat(), sig.symbol,
                       sig.setup, sig.horizon, sig.side, sig.entry, sig.stop, sig.take_profit, sig.target, sig.max_bars,
                       None if prob is None else float(prob), shares, sig.note, json.dumps(sig.features, default=float)))
        return True

    def mark(self, key: str, action: str, my_r: float | None = None, comment: str = "") -> None:
        """Record what you did with an alert: taken / skipped, and your own result in R."""
        with self._db() as c:
            c.execute("UPDATE alerts SET action=?, my_r=?, comment=? WHERE key=?", (action, my_r, comment, key))

    def frame(self, status: str | None = None) -> pd.DataFrame:
        q = "SELECT * FROM alerts" + (" WHERE status=?" if status else "")
        with self._db() as c:
            return pd.read_sql_query(q, c, params=(status,) if status else ())

    def resolve(self, bars_for) -> int:
        """`bars_for(symbol, horizon)` -> bars DataFrame covering the period after the alert. Returns count resolved."""
        n = 0
        for _, a in self.frame("open").iterrows():
            sig = to_signal(a)
            bars = bars_for(sig.symbol, sig.horizon)
            if bars is None or bars.empty:
                continue
            fut = bars[bars.index > pd.Timestamp(sig.ts)]
            if sig.horizon == "swing" and len(fut) < sig.max_bars:
                o = simulate(sig, fut)
                if o is None or o.exit_reason == "time":
                    continue  # still running
            else:
                o = simulate(sig, fut)
            if o is None:
                continue
            with self._db() as c:
                c.execute("UPDATE alerts SET status='resolved', exit_ts=?, exit_price=?, exit_reason=?, r=? WHERE key=?",
                          (pd.Timestamp(o.exit_ts).isoformat(), o.exit_price, o.exit_reason, o.r_multiple, a["key"]))
            n += 1
        return n

    def resolved_signals(self) -> tuple[list[Signal], list[float]]:
        df = self.frame("resolved")
        return [to_signal(a) for _, a in df.iterrows()], df["r"].tolist()


def to_signal(a) -> Signal:
    return Signal(a["symbol"], pd.Timestamp(a["ts"]), a["setup"], a["horizon"], int(a["side"]), float(a["entry"]),
                  float(a["stop"]), float(a["target"]), int(a["max_bars"]),
                  take_profit=None if pd.isna(a["take_profit"]) else float(a["take_profit"]), note=a["note"] or "",
                  features=json.loads(a["features"] or "{}"))
