"""Market Data Ingestion Engine - Real-time & Historical via yfinance"""
import yfinance as yf
import pandas as pd
import numpy as np
import threading
import time
import logging
import os
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class MarketDataCache:
    def __init__(self, ttl_seconds: int = 30):
        self._cache: Dict[str, Tuple[datetime, any]] = {}
        self._lock = threading.RLock()
        self.ttl = ttl_seconds

    def get(self, key: str):
        with self._lock:
            if key in self._cache:
                ts, val = self._cache[key]
                if (datetime.utcnow() - ts).total_seconds() < self.ttl:
                    return val
        return None

    def set(self, key: str, value) -> None:
        with self._lock:
            self._cache[key] = (datetime.utcnow(), value)


class MarketDataIngestion:
    def __init__(self, cache_ttl: int = 30):
        self._cache = MarketDataCache(ttl_seconds=cache_ttl)
        self._subscriptions: Dict[str, dict] = {}
        self._polling = False
        self._poll_thread: Optional[threading.Thread] = None
        self._callbacks: List = []
        self._lock = threading.RLock()
        self.DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
        if not os.path.exists(self.DATA_DIR):
            os.makedirs(self.DATA_DIR, exist_ok=True)

        # Mapping for your specific uploaded files
        self.SYMBOL_MAP = {
            "EQUITY": {"file": "equity_dataset.csv", "price_col": "Price", "vol_col": "Volume"},
            "OIL": {"file": "oil_dataset.csv", "price_col": "Price", "vol_col": "Volume"},
            "GOLD": {"file": "multi_asset_dataset.csv", "price_col": "Gold", "vol_col": None},
            "BONDS": {"file": "multi_asset_dataset.csv", "price_col": "Bonds", "vol_col": None},
            "OIL_MULTI": {"file": "multi_asset_dataset.csv", "price_col": "Oil", "vol_col": None},
            "INFLATION": {"file": "macro_dataset (1).csv", "price_col": "Inflation", "vol_col": None},
            "INTEREST_RATE": {"file": "macro_dataset (1).csv", "price_col": "Interest_Rate", "vol_col": None},
            "USD_INDEX": {"file": "macro_dataset (1).csv", "price_col": "USD_Index", "vol_col": None},
        }

    def get_historical(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        symbol = symbol.upper()
        key = f"hist_{symbol}_{period}_{interval}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        # Check mapping first
        if symbol in self.SYMBOL_MAP:
            m = self.SYMBOL_MAP[symbol]
            local_path = os.path.join(self.DATA_DIR, m["file"])
            if os.path.exists(local_path):
                try:
                    df = pd.read_csv(local_path)
                    df.columns = [c.strip() for c in df.columns]
                    df['Date'] = pd.to_datetime(df['Date'])
                    df.set_index('Date', inplace=True)
                    
                    price_col = m["price_col"]
                    vol_col = m.get("vol_col")
                    
                    result = pd.DataFrame(index=df.index)
                    result['close'] = df[price_col]
                    result['open'] = result['close'] # Approximated
                    result['high'] = result['close']
                    result['low'] = result['close']
                    result['volume'] = df[vol_col] if vol_col and vol_col in df.columns else 0.0
                    
                    self._cache.set(key, result)
                    return result
                except Exception as e:
                    logger.error(f"Error loading mapped data for {symbol}: {e}")

        # Fallback to symbol-named CSV
        local_path = os.path.join(self.DATA_DIR, f"{symbol}.csv")
        if os.path.exists(local_path):
            try:
                df = pd.read_csv(local_path)
                df.columns = [c.lower() for c in df.columns]
                if 'date' in df.columns:
                    df['date'] = pd.to_datetime(df['date'])
                    df.set_index('date', inplace=True)
                
                mapping = {"timestamp": "date", "price": "close", "last": "close"}
                for k, v in mapping.items():
                    if k in df.columns and v not in df.columns:
                        df.rename(columns={k: v}, inplace=True)

                cols = ["open", "high", "low", "close", "volume"]
                for c in cols:
                    if c not in df.columns:
                        if c == 'close' and 'price' in df.columns: df['close'] = df['price']
                        else: df[c] = df['close'] if 'close' in df.columns else 0.0
                
                df = df[cols].dropna()
                self._cache.set(key, df)
                return df
            except Exception as e:
                logger.error(f"Error loading symbol CSV for {symbol}: {e}")

        # Fallback to yfinance
        for attempt in range(2):
            try:
                df = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=True)
                if not df.empty:
                    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
                    df.columns = ["open", "high", "low", "close", "volume"]
                    self._cache.set(key, df)
                    return df
            except:
                time.sleep(1)
        return pd.DataFrame()

    def get_multi_historical(self, symbols: List[str], period: str = "1y", interval: str = "1d") -> Dict[str, pd.DataFrame]:
        results = {}
        threads = []
        def _fetch(sym):
            results[sym] = self.get_historical(sym, period, interval)
        for sym in symbols:
            t = threading.Thread(target=_fetch, args=(sym,), daemon=True)
            threads.append(t)
            t.start()
        for t in threads:
            t.join(timeout=30)
        return results

    def get_returns(self, symbol: str, period: str = "1y") -> pd.Series:
        df = self.get_historical(symbol, period=period)
        if df.empty:
            return pd.Series(dtype=float)
        return np.log(df["close"] / df["close"].shift(1)).dropna()

    def get_multi_returns(self, symbols: List[str], period: str = "1y") -> pd.DataFrame:
        all_data = self.get_multi_historical(symbols, period=period)
        series = {sym: np.log(df["close"] / df["close"].shift(1)).dropna()
                  for sym, df in all_data.items() if not df.empty}
        return pd.DataFrame(series).dropna() if series else pd.DataFrame()

    def get_quote(self, symbol: str) -> dict:
        symbol = symbol.upper()
        key = f"quote_{symbol}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        # Check local data first
        df = self.get_historical(symbol, period="5d")
        if not df.empty:
            last_row = df.iloc[-1]
            prev_row = df.iloc[-2] if len(df) > 1 else last_row
            price = float(last_row["close"])
            prev = float(prev_row["close"])
            change = round(price - prev, 4)
            change_pct = round((change / prev) * 100, 4) if prev != 0 else 0.0
            
            q = {
                "symbol": symbol, "price": price, "prev_close": prev,
                "change": change, "change_pct": change_pct,
                "day_high": float(last_row.get("high", price)),
                "day_low": float(last_row.get("low", price)),
                "volume": int(last_row.get("volume", 0)),
                "source": "local"
            }
            self._cache.set(key, q)
            return q

        # Fallback to yfinance
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            price = getattr(info, "last_price", None) or getattr(info, "previous_close", None)
            prev = getattr(info, "previous_close", None)
            change = round(price - prev, 4) if price and prev else 0.0
            change_pct = round((change / prev) * 100, 4) if prev else 0.0
            q = {
                "symbol": symbol, "price": price, "prev_close": prev,
                "change": change, "change_pct": change_pct,
                "day_high": getattr(info, "day_high", None),
                "day_low": getattr(info, "day_low", None),
                "volume": getattr(info, "last_volume", 0),
                "source": "yfinance"
            }
            self._cache.set(key, q)
            return q
        except Exception as e:
            logger.error(f"Error fetching quote for {symbol}: {e}")
            return {"symbol": symbol, "price": 0.0, "error": str(e)}

    def get_ticker_info(self, symbol: str) -> dict:
        symbol = symbol.upper()
        if symbol in self.SYMBOL_MAP:
            return {"symbol": symbol, "shortName": symbol, "sector": "Local Dataset", "quoteType": "CSV"}
        try:
            return yf.Ticker(symbol).info
        except:
            return {"symbol": symbol, "shortName": symbol}

    def get_multi_quotes(self, symbols: List[str]) -> Dict[str, dict]:
        results = {}
        threads = []
        def _fetch(sym):
            results[sym] = self.get_quote(sym)
        for sym in symbols:
            t = threading.Thread(target=_fetch, args=(sym,), daemon=True)
            threads.append(t)
            t.start()
        for t in threads:
            t.join(timeout=15)
        return results

    def get_prices(self, symbols: List[str]) -> Dict[str, float]:
        quotes = self.get_multi_quotes(symbols)
        return {sym: (q.get("price") or 0.0) for sym, q in quotes.items()}

    def get_market_overview(self) -> dict:
        indices = {
            "S&P 500": "^GSPC", "NASDAQ": "^IXIC", "DOW": "^DJI",
            "VIX": "^VIX", "10Y Treasury": "^TNX",
            "Gold": "GC=F", "Oil (WTI)": "CL=F", "BTC-USD": "BTC-USD",
        }
        quotes = self.get_multi_quotes(list(indices.values()))
        return {
            name: {"symbol": sym, "price": quotes.get(sym, {}).get("price"),
                   "change_pct": quotes.get(sym, {}).get("change_pct", 0)}
            for name, sym in indices.items()
        }

    def subscribe(self, symbol: str) -> None:
        with self._lock:
            self._subscriptions[symbol] = {"added_at": datetime.utcnow()}

    def add_callback(self, fn) -> None:
        self._callbacks.append(fn)

    def start_polling(self, interval: int = 15) -> None:
        if self._polling:
            return
        self._polling = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def stop_polling(self) -> None:
        self._polling = False

    def _poll_loop(self) -> None:
        while self._polling:
            try:
                with self._lock:
                    symbols = list(self._subscriptions.keys())
                if symbols:
                    quotes = self.get_multi_quotes(symbols)
                    for cb in self._callbacks:
                        try:
                            cb(quotes)
                        except Exception:
                            pass
            except Exception:
                pass
            time.sleep(15)
