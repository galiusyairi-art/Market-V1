"""tradekit command line.

  tradekit demo                       full pipeline on synthetic data (no broker needed)
  tradekit fetch [--intraday-days N]  download/cache bars from IBKR for the universe
  tradekit backtest [--horizon H]     backtest all setups on cached bars, report in R
  tradekit train                      backtest + journal → retrain meta-models and setup health
  tradekit live                       run the live session scanner (premarket → close → swing scan)
  tradekit swing                      one-off end-of-day swing scan
  tradekit resolve                    label open alerts with what happened since
  tradekit journal [--open]           list alerts; tradekit mark KEY taken|skipped [--r R]
  tradekit health                     per-setup backtest/live edge and mute status
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

import pandas as pd

from . import backtest as bt
from . import config as C
from .alerts import Notifier
from .data.store import BarStore
from .engine import AlertEngine
from .features import market_frame
from .journal import Journal
from .learn import backtest_all, load_history, load_models, train

pd.set_option("display.width", 160)
pd.set_option("display.float_format", lambda v: f"{v:,.3f}")


def _store(cfg) -> BarStore:
    return BarStore(C.var(cfg, "bars"))


def _ib(cfg):
    from .data.ibkr import IBKR
    i = cfg["ibkr"]
    return IBKR(i["host"], i["port"], i["client_id"], i["market_data_type"]).connect()


def _engine(cfg, store) -> AlertEngine:
    models, health = load_models(cfg)
    idx = cfg["universe"]["index"]
    return AlertEngine(cfg, Journal(C.var(cfg, "journal.db")), Notifier(cfg["telegram"]["token"], cfg["telegram"]["chat_id"]),
                       models, health, market_frame(store.load(idx, "1d")))


def cmd_demo(cfg, a):
    from .data import synthetic as syn
    cfg["var_dir"] = str(C.var(cfg, "demo"))
    store = _store(cfg)
    n_sw, n_in = a.symbols, max(6, a.symbols // 3)
    print(f"building synthetic market: {n_sw} symbols daily, {n_in} symbols 1-minute …")
    store.save("SPY", "1d", syn.daily("SPY", 900, seed=1, drift=0.0003), merge=False)
    for i in range(n_sw):
        store.save(f"S{i:03d}", "1d", syn.daily(f"S{i:03d}", 900, seed=100 + i), merge=False)
    for i in range(n_in):
        m1, d = syn.intraday(f"I{i:03d}", a.days, seed=500 + i)
        store.save(f"I{i:03d}", "1m", m1, merge=False)
        store.save(f"I{i:03d}", "1d", d, merge=False)
    daily, m1 = load_history(store)
    trades = backtest_all(cfg, daily, m1)
    for hz, ts in trades.items():
        print(f"\n=== backtest · {hz} ===")
        print(bt.report(bt.trades_frame(ts)).to_string())
    print("\n=== meta-model (walk-forward) ===")
    cfg["meta"]["min_trades"] = min(cfg["meta"]["min_trades"], 200)
    train(cfg, store, Journal(C.var(cfg, "journal.db")), trades)
    eng = _engine(cfg, store)
    recent = sorted((t.signal for t in trades["swing"]), key=lambda s: s.ts)[-12:]
    sigs = list({s.symbol: s for s in recent}.values())[-5:]
    print(f"\n=== sample alerts (latest swing signals, filtered by the meta-model) ===")
    eng.handle(sigs)
    print("\n(synthetic data: these numbers only prove the pipeline works, not that any setup has an edge)")


def cmd_fetch(cfg, a):
    store = _store(cfg)
    ib = _ib(cfg)
    syms = [cfg["universe"]["index"]] + C.universe(cfg)
    for i, s in enumerate(dict.fromkeys(syms)):
        try:
            store.save(s, "1d", ib.daily(s, a.daily))
            print(f"[{i + 1}/{len(syms)}] {s} daily ok")
        except Exception as e:
            print(f"{s}: {e}")
    for s in (a.intraday_symbols.split(",") if a.intraday_symbols else []):
        ib.fetch_minutes_history(store, s.strip().upper(), a.intraday_days)
    ib.disconnect()


def cmd_backtest(cfg, a):
    store = _store(cfg)
    daily, m1 = load_history(store)
    if not daily:
        sys.exit("no cached bars: run `tradekit fetch` first (or `tradekit demo`)")
    trades = backtest_all(cfg, daily, m1)
    for hz, ts in trades.items():
        if a.horizon and hz != a.horizon:
            continue
        df = bt.trades_frame(ts)
        print(f"\n=== {hz}: {len(df)} trades ===")
        print(bt.report(df).to_string())
        if not df.empty:
            out = C.var(cfg, f"trades_{hz}.csv")
            df.to_csv(out, index=False)
            print(f"trades → {out}")


def cmd_train(cfg, a):
    store = _store(cfg)
    print(json.dumps(train(cfg, store, Journal(C.var(cfg, "journal.db"))), indent=1, default=str))


def cmd_live(cfg, a):
    from .scanner import LiveScanner
    store = _store(cfg)
    ib = _ib(cfg)
    idx = cfg["universe"]["index"]
    store.save(idx, "1d", ib.daily(idx, "2 Y"))
    LiveScanner(cfg, ib, store, _engine(cfg, store), C.universe(cfg)).run()
    ib.disconnect()


def cmd_swing(cfg, a):
    from .scanner import LiveScanner
    store = _store(cfg)
    ib = _ib(cfg)
    sent = LiveScanner(cfg, ib, store, _engine(cfg, store), C.universe(cfg)).swing_scan()
    print(f"{len(sent)} swing alerts")
    ib.disconnect()


def cmd_resolve(cfg, a):
    store = _store(cfg)
    j = Journal(C.var(cfg, "journal.db"))
    n = j.resolve(lambda s, hz: store.load(s, "1m" if hz == "intraday" else "1d"))
    print(f"resolved {n} alerts")


def cmd_journal(cfg, a):
    df = Journal(C.var(cfg, "journal.db")).frame("open" if a.open else None)
    cols = ["key", "prob", "entry", "stop", "target", "status", "exit_reason", "r", "action", "my_r"]
    print(df[cols].tail(a.n).to_string(index=False) if not df.empty else "journal is empty")
    if not df.empty and df["r"].notna().any():
        print("\nresolved:", bt.stats(df["r"].dropna()))


def cmd_mark(cfg, a):
    Journal(C.var(cfg, "journal.db")).mark(a.key, a.action, a.r, a.comment or "")
    print("ok")


def cmd_health(cfg, a):
    _, health = load_models(cfg)
    print(pd.DataFrame(health).T.to_string() if health else "no health file yet: run `tradekit train`")


def main(argv=None):
    p = argparse.ArgumentParser(prog="tradekit", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-c", "--config", default="config.yaml")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo"); d.add_argument("--symbols", type=int, default=40); d.add_argument("--days", type=int, default=120)
    f = sub.add_parser("fetch"); f.add_argument("--daily", default="3 Y"); f.add_argument("--intraday-symbols", default="")
    f.add_argument("--intraday-days", type=int, default=60)
    b = sub.add_parser("backtest"); b.add_argument("--horizon", choices=["intraday", "swing"])
    sub.add_parser("train"); sub.add_parser("live"); sub.add_parser("swing"); sub.add_parser("resolve"); sub.add_parser("health")
    j = sub.add_parser("journal"); j.add_argument("--open", action="store_true"); j.add_argument("-n", type=int, default=30)
    m = sub.add_parser("mark"); m.add_argument("key"); m.add_argument("action", choices=["taken", "skipped"])
    m.add_argument("--r", type=float); m.add_argument("--comment")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(asctime)s %(name)s %(message)s")
    cfg = C.load(a.config)
    globals()[f"cmd_{a.cmd}"](cfg, a)


if __name__ == "__main__":
    main()
