"""Meta-labeling: a second model that learns which signals of each setup tend to work.

The setups decide *what* and *where* (entry/stop/target). The meta-model only answers
"given everything we know at signal time, what is the chance this one reaches its target first?".
Alerts below a probability threshold are suppressed, so the stream gets cleaner as more history accumulates.

Training is walk-forward with a purge gap so the model is always scored on trades that happened after the data
it learned from. Live alert outcomes from the journal are appended to the backtest history and weighted higher.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score


@dataclass
class MetaReport:
    folds: int
    auc: float
    base_win_rate: float
    base_avg_r: float
    by_threshold: list[dict] = field(default_factory=list)
    chosen_threshold: float = 0.5

    def to_dict(self) -> dict:
        return self.__dict__


def _model() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=250, min_samples_leaf=40,
                                          l2_regularization=1.0, early_stopping=False, random_state=7)


def _fit(X: pd.DataFrame, y: np.ndarray, w: np.ndarray | None):
    X = X.copy()
    X[X.columns[X.isna().all()]] = 0.0  # a feature this setup never produces: constant, so the model ignores it
    return _model().fit(X, y, sample_weight=w)


def walk_forward(X: pd.DataFrame, y: np.ndarray, r: np.ndarray, ts: pd.Series, folds: int = 5, purge_days: int = 30,
                 weights: np.ndarray | None = None, min_train: int = 150) -> tuple[np.ndarray, MetaReport]:
    """Out-of-sample probabilities for every trade after the first training window."""
    order = np.argsort(pd.to_datetime(ts).to_numpy())
    X, y, r = X.iloc[order].reset_index(drop=True), y[order], r[order]
    t = pd.to_datetime(ts).iloc[order].reset_index(drop=True)
    t = t.dt.tz_localize(None) if t.dt.tz is not None else t
    w = None if weights is None else weights[order]
    oos = np.full(len(y), np.nan)
    edges = np.linspace(0, len(y), folds + 2).astype(int)[1:]
    done = 0
    for k in range(len(edges) - 1):
        lo, hi = edges[k], edges[k + 1]
        cutoff = t.iloc[lo] - pd.Timedelta(days=purge_days)
        tr = np.flatnonzero((t < cutoff).to_numpy())
        if len(tr) < min_train or len(np.unique(y[tr])) < 2:
            continue
        m = _fit(X.iloc[tr], y[tr], None if w is None else w[tr])
        oos[lo:hi] = m.predict_proba(X.iloc[lo:hi])[:, 1]
        done += 1
    mask = ~np.isnan(oos)
    rep = MetaReport(folds=done, auc=float("nan"), base_win_rate=float(y[mask].mean()) if mask.any() else float("nan"),
                     base_avg_r=float(r[mask].mean()) if mask.any() else float("nan"))
    if mask.sum() > 30 and len(np.unique(y[mask])) == 2:
        rep.auc = float(roc_auc_score(y[mask], oos[mask]))
        best = (rep.base_avg_r, 0.0)
        for th in np.round(np.arange(0.30, 0.75, 0.05), 2):
            sel = mask & (oos >= th)
            n = int(sel.sum())
            if n == 0:
                continue
            row = {"threshold": float(th), "trades": n, "kept": n / mask.sum(), "win_rate": float(y[sel].mean()),
                   "avg_r": float(r[sel].mean()), "total_r": float(r[sel].sum())}
            rep.by_threshold.append(row)
            # prefer the threshold with the best expectancy that still keeps >= 25% of trades
            if row["kept"] >= 0.25 and row["avg_r"] > best[0]:
                best = (row["avg_r"], th)
        rep.chosen_threshold = float(best[1])
    out = np.full(len(y), np.nan)
    out[order] = oos
    return out, rep


class MetaModel:
    def __init__(self, model=None, columns: list[str] | None = None, threshold: float = 0.0, report: dict | None = None):
        self.model, self.columns, self.threshold, self.report = model, columns or [], threshold, report or {}

    @classmethod
    def train(cls, X: pd.DataFrame, y: np.ndarray, r: np.ndarray, ts: pd.Series, weights: np.ndarray | None = None,
              folds: int = 5, purge_days: int = 30) -> "MetaModel":
        _, rep = walk_forward(X, y, r, ts, folds=folds, purge_days=purge_days, weights=weights)
        model = _fit(X, y, weights) if len(np.unique(y)) == 2 else None
        return cls(model, list(X.columns), rep.chosen_threshold, rep.to_dict())

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.model is None or X.empty:
            return np.full(len(X), np.nan)
        X = X.reindex(columns=self.columns)
        return self.model.predict_proba(X)[:, 1]

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": self.model, "columns": self.columns, "threshold": self.threshold, "report": self.report}, path)
        path.with_suffix(".json").write_text(json.dumps({"threshold": self.threshold, "report": self.report}, indent=1, default=str))

    @classmethod
    def load(cls, path: str | Path) -> "MetaModel | None":
        path = Path(path)
        if not path.exists():
            return None
        d = joblib.load(path)
        return cls(d["model"], d["columns"], d["threshold"], d["report"])
