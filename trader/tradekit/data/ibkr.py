"""Interactive Brokers data via ib_async (TWS or IB Gateway must be running with the API enabled).

Market data needed (non-professional, ≈$10–15/month): "US Securities Snapshot and Futures Value Bundle"
plus "US Equity and Options Add-On Streaming Bundle". IBKR waives the base bundle above $30 monthly commissions.

Pacing: IBKR allows about 60 historical requests per 10 minutes for small bars, so bulk intraday downloads are
throttled; daily bars are fetched faster. Everything fetched is cached in the BarStore so it is downloaded once.
"""
from __future__ import annotations

import logging
import time

import pandas as pd

from .store import TZ, BarStore, normalize

log = logging.getLogger("tradekit.ibkr")


class IBKR:
    def __init__(self, host: str = "127.0.0.1", port: int = 7497, client_id: int = 17, market_data_type: int = 1):
        from ib_async import IB  # imported lazily so backtests run without the package
        self.ib = IB()
        self.host, self.port, self.client_id, self.mdt = host, port, client_id, market_data_type
        self._contracts: dict = {}
        self._last_small = 0.0

    def connect(self) -> "IBKR":
        self.ib.connect(self.host, self.port, clientId=self.client_id, timeout=20)
        self.ib.reqMarketDataType(self.mdt)
        return self

    def disconnect(self) -> None:
        self.ib.disconnect()

    def sleep(self, sec: float) -> None:
        self.ib.sleep(sec)

    def contract(self, symbol: str):
        from ib_async import Stock
        c = self._contracts.get(symbol)
        if c is None:
            c = Stock(symbol, "SMART", "USD")
            q = self.ib.qualifyContracts(c)
            if not q:
                raise ValueError(f"unknown symbol {symbol}")
            self._contracts[symbol] = c = q[0]
        return c

    @staticmethod
    def _df(bars, intraday: bool) -> pd.DataFrame:
        from ib_async import util
        df = util.df(bars)
        if df is None or df.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        idx = pd.to_datetime(df["date"], utc=intraday)
        df.index = idx.dt.tz_convert(TZ) if intraday else idx
        return normalize(df)

    def _pace(self) -> None:
        wait = 10.5 - (time.time() - self._last_small)
        if wait > 0:
            self.ib.sleep(wait)
        self._last_small = time.time()

    def daily(self, symbol: str, duration: str = "2 Y") -> pd.DataFrame:
        bars = self.ib.reqHistoricalData(self.contract(symbol), endDateTime="", durationStr=duration, barSizeSetting="1 day",
                                         whatToShow="TRADES", useRTH=True, formatDate=1)
        return self._df(bars, intraday=False)

    def minutes(self, symbol: str, days: int = 5, end: pd.Timestamp | None = None) -> pd.DataFrame:
        """1-minute bars including pre/after-market, `days` sessions ending at `end` (default now)."""
        self._pace()
        end_s = "" if end is None else pd.Timestamp(end).tz_convert("UTC").strftime("%Y%m%d %H:%M:%S UTC")
        bars = self.ib.reqHistoricalData(self.contract(symbol), endDateTime=end_s, durationStr=f"{days} D",
                                         barSizeSetting="1 min", whatToShow="TRADES", useRTH=False, formatDate=2)
        return self._df(bars, intraday=True)

    def fetch_minutes_history(self, store: BarStore, symbol: str, days: int, chunk: int = 5) -> None:
        end = None
        got = 0
        while got < days:
            df = self.minutes(symbol, chunk, end)
            if df.empty:
                break
            store.save(symbol, "1m", df)
            end = df.index[0]
            got += chunk
            log.info("%s: %d/%d days of 1-min bars", symbol, min(got, days), days)

    def scanner(self, scan_code: str = "TOP_PERC_GAIN", above_price: float = 3.0, above_volume: int = 100000,
                rows: int = 25) -> list[str]:
        from ib_async import ScannerSubscription
        sub = ScannerSubscription(instrument="STK", locationCode="STK.US.MAJOR", scanCode=scan_code,
                                  abovePrice=above_price, aboveVolume=above_volume, numberOfRows=rows)
        data = self.ib.reqScannerData(sub)
        return [d.contractDetails.contract.symbol for d in data]

    def stream_minutes(self, symbol: str, on_update, days: int = 2):
        """Keep-up-to-date 1-min bars; calls on_update(symbol, df) whenever a bar completes."""
        bars = self.ib.reqHistoricalData(self.contract(symbol), endDateTime="", durationStr=f"{days} D",
                                         barSizeSetting="1 min", whatToShow="TRADES", useRTH=False, formatDate=2,
                                         keepUpToDate=True)

        def _upd(b, has_new_bar):
            if has_new_bar:
                df = self._df(b, intraday=True)
                on_update(symbol, df.iloc[:-1])  # last bar is still forming
        bars.updateEvent += _upd
        return bars

    def cancel_stream(self, bars) -> None:
        self.ib.cancelHistoricalData(bars)
