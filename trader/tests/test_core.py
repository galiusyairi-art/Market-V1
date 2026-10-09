import numpy as np
import pandas as pd
import pytest

from tradekit import backtest as bt
from tradekit.data import synthetic as syn
from tradekit.data.store import BarStore
from tradekit.indicators import rsi, session_vwap
from tradekit.labeling import simulate
from tradekit.meta import MetaModel
from tradekit.signals import INTRADAY, SWING, Signal
from tradekit.strategies import intraday as intra
from tradekit.strategies import swing


def bars(rows, start="2026-01-05 09:30", freq="1min", tz="America/New_York"):
    idx = pd.date_range(pd.Timestamp(start, tz=tz), periods=len(rows), freq=freq)
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"], index=idx, dtype=float)


def test_vwap_resets_each_session():
    a = bars([[10, 10, 10, 10, 100]] * 3)
    b = bars([[20, 20, 20, 20, 100]] * 3, start="2026-01-06 09:30")
    v = session_vwap(pd.concat([a, b]))
    assert v.iloc[2] == pytest.approx(10) and v.iloc[3] == pytest.approx(20)


def test_rsi_bounds():
    r = rsi(pd.Series(np.cumsum(np.random.default_rng(0).normal(size=300)) + 100), 2).dropna()
    assert r.between(0, 100).all()


def test_stop_wins_when_bar_hits_both_barriers():
    s = Signal("X", pd.Timestamp("2026-01-05 09:30", tz="America/New_York"), "t", INTRADAY, 1, 100, 99, 102, 10)
    fut = bars([[100, 103, 98, 101, 1]], start="2026-01-05 09:31")
    o = simulate(s, fut, slippage_bps=0)
    assert o.exit_reason == "stop" and o.r_multiple == pytest.approx(-1)


def test_target_and_time_exit():
    s = Signal("X", pd.Timestamp("2026-01-05"), "t", SWING, 1, 100, 95, 110, 3)
    fut = bars([[100, 104, 99, 103, 1], [103, 111, 102, 110, 1]], start="2026-01-06", freq="D", tz=None)
    assert simulate(s, fut, 0).exit_reason == "target"
    fut2 = bars([[100, 101, 99, 100, 1]] * 5, start="2026-01-06", freq="D", tz=None)
    o = simulate(s, fut2, 0)
    assert o.exit_reason == "time" and o.bars_held == 3


def test_short_gap_through_stop_fills_at_open():
    s = Signal("X", pd.Timestamp("2026-01-05"), "t", SWING, -1, 100, 105, 90, 5)
    fut = bars([[108, 109, 107, 108, 1]], start="2026-01-06", freq="D", tz=None)
    o = simulate(s, fut, 0)
    assert o.exit_reason == "stop" and o.r_multiple == pytest.approx(-8 / 5)


def test_swing_signals_have_no_lookahead():
    d = syn.daily("LA", 700, seed=3)
    full = {s.key: s for s in swing.scan_all("LA", d)}
    cut = d.index[500]
    part = {s.key: s for s in swing.scan_all("LA", d[d.index <= cut])}
    for k, s in part.items():
        assert k in full and full[k].entry == pytest.approx(s.entry) and full[k].stop == pytest.approx(s.stop)
    assert all(s.ts <= cut for s in part.values())


def test_intraday_signals_have_no_lookahead():
    m1, d = syn.intraday("IA", 40, seed=11)
    days = m1.index.normalize().unique()
    cut = days[30] + pd.Timedelta(hours=12)
    for fn in intra.ALL.values():
        full = {s.key: s for s in fn("IA", m1, d)}
        part = fn("IA", m1[m1.index <= cut], d[d.index < days[30].tz_localize(None)])
        for s in part:
            assert s.key in full and full[s.key].ts == s.ts and full[s.key].entry == pytest.approx(s.entry)


def test_signals_are_valid_and_respect_side():
    m1, d = syn.intraday("IV", 60, seed=5)
    sigs = [s for fn in intra.ALL.values() for s in fn("IV", m1, d)] + swing.scan_all("SV", syn.daily("SV", 800, seed=9))
    assert sigs
    for s in sigs:
        assert s.valid(), s


def test_store_roundtrip(tmp_path):
    st = BarStore(tmp_path)
    m1, d = syn.intraday("RT", 5, seed=1)
    st.save("RT", "1m", m1)
    st.save("RT", "1d", d)
    back = st.load("RT", "1m")
    assert len(back) == len(m1) and str(back.index.tz) == "America/New_York"
    assert np.allclose(back["close"].values, m1["close"].values)
    assert len(st.load("RT", "1d")) == len(d)


def test_meta_model_learns_a_planted_rule():
    rng = np.random.default_rng(0)
    n = 1500
    X = pd.DataFrame({"a": rng.normal(size=n), "b": rng.normal(size=n)})
    y = (X["a"] + rng.normal(scale=0.7, size=n) > 0).astype(int).to_numpy()
    r = np.where(y == 1, 1.5, -1.0)
    ts = pd.Series(pd.date_range("2020-01-01", periods=n, freq="D"))
    m = MetaModel.train(X, y, r, ts, folds=4, purge_days=5)
    assert m.report["auc"] > 0.75
    hi = [row for row in m.report["by_threshold"] if row["threshold"] >= 0.6]
    assert hi and hi[0]["avg_r"] > m.report["base_avg_r"]


def test_backtest_runs_end_to_end():
    m1, d = syn.intraday("E1", 60, seed=2)
    tr = bt.run_intraday({"E1": m1}, {"E1": d}, top_k=5)
    sw = bt.run_swing({"E2": syn.daily("E2", 800, seed=4)})
    rep = bt.report(bt.trades_frame(tr + sw))
    assert "ALL" in rep.index and rep.loc["ALL", "trades"] == len(tr) + len(sw)
