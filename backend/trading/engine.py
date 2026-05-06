"""
Signal Generator & Semi-Automated Trading Engine
Strategies: Momentum, Mean Reversion, RSI, MACD, Bollinger Bands
"""
import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Optional
from datetime import datetime
from backend.models.portfolio import Order

logger = logging.getLogger(__name__)


class TechnicalIndicators:
    """Utility class for computing technical indicators."""

    @staticmethod
    def sma(series: pd.Series, window: int) -> pd.Series:
        return series.rolling(window=window).mean()

    @staticmethod
    def ema(series: pd.Series, window: int) -> pd.Series:
        return series.ewm(span=window, adjust=False).mean()

    @staticmethod
    def rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    @staticmethod
    def bollinger_bands(series: pd.Series, window: int = 20, num_std: float = 2.0):
        mid = series.rolling(window).mean()
        std = series.rolling(window).std()
        upper = mid + num_std * std
        lower = mid - num_std * std
        return upper, mid, lower

    @staticmethod
    def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        return tr.rolling(period).mean()


class SignalGenerator:
    """
    Generates trading signals for each symbol using multiple strategies.
    Each strategy returns: 'BUY', 'SELL', or 'HOLD'
    """

    def momentum_signal(self, df: pd.DataFrame, fast: int = 20, slow: int = 50) -> str:
        if len(df) < slow + 5:
            return "HOLD"
        close = df["close"]
        sma_fast = TechnicalIndicators.sma(close, fast).iloc[-1]
        sma_slow = TechnicalIndicators.sma(close, slow).iloc[-1]
        prev_fast = TechnicalIndicators.sma(close, fast).iloc[-2]
        prev_slow = TechnicalIndicators.sma(close, slow).iloc[-2]
        if prev_fast <= prev_slow and sma_fast > sma_slow:
            return "BUY"
        if prev_fast >= prev_slow and sma_fast < sma_slow:
            return "SELL"
        return "HOLD"

    def rsi_signal(self, df: pd.DataFrame, period: int = 14, oversold: int = 30, overbought: int = 70) -> str:
        if len(df) < period + 5:
            return "HOLD"
        rsi = TechnicalIndicators.rsi(df["close"], period)
        current_rsi = rsi.iloc[-1]
        if current_rsi < oversold:
            return "BUY"
        if current_rsi > overbought:
            return "SELL"
        return "HOLD"

    def macd_signal(self, df: pd.DataFrame) -> str:
        if len(df) < 40:
            return "HOLD"
        macd, signal, hist = TechnicalIndicators.macd(df["close"])
        if hist.iloc[-2] <= 0 and hist.iloc[-1] > 0:
            return "BUY"
        if hist.iloc[-2] >= 0 and hist.iloc[-1] < 0:
            return "SELL"
        return "HOLD"

    def bollinger_signal(self, df: pd.DataFrame) -> str:
        if len(df) < 25:
            return "HOLD"
        upper, mid, lower = TechnicalIndicators.bollinger_bands(df["close"])
        close = df["close"].iloc[-1]
        if close < lower.iloc[-1]:
            return "BUY"
        if close > upper.iloc[-1]:
            return "SELL"
        return "HOLD"

    def mean_reversion_signal(self, df: pd.DataFrame, window: int = 20, z_threshold: float = 2.0) -> str:
        if len(df) < window + 5:
            return "HOLD"
        close = df["close"]
        roll_mean = close.rolling(window).mean()
        roll_std = close.rolling(window).std()
        z_score = (close - roll_mean) / roll_std
        z = z_score.iloc[-1]
        if z < -z_threshold:
            return "BUY"
        if z > z_threshold:
            return "SELL"
        return "HOLD"

    def aggregate_signal(self, df: pd.DataFrame, symbol: str) -> dict:
        """Run all strategies, majority-vote the final signal."""
        if df.empty:
            return {"symbol": symbol, "signal": "HOLD", "confidence": 0, "signals": {}}

        signals = {
            "momentum": self.momentum_signal(df),
            "rsi": self.rsi_signal(df),
            "macd": self.macd_signal(df),
            "bollinger": self.bollinger_signal(df),
            "mean_reversion": self.mean_reversion_signal(df),
        }

        buy_count = sum(1 for s in signals.values() if s == "BUY")
        sell_count = sum(1 for s in signals.values() if s == "SELL")
        total = len(signals)

        if buy_count > sell_count and buy_count >= 2:
            final = "BUY"
            confidence = round(buy_count / total * 100, 1)
        elif sell_count > buy_count and sell_count >= 2:
            final = "SELL"
            confidence = round(sell_count / total * 100, 1)
        else:
            final = "HOLD"
            confidence = round(max(buy_count, sell_count) / total * 100, 1)

        # Technical values
        close = df["close"]
        rsi_val = TechnicalIndicators.rsi(close).iloc[-1] if len(df) > 14 else None
        macd_val, sig_val, _ = TechnicalIndicators.macd(close) if len(df) > 30 else (pd.Series(), pd.Series(), pd.Series())
        upper, mid, lower = TechnicalIndicators.bollinger_bands(close) if len(df) > 20 else (pd.Series(), pd.Series(), pd.Series())

        return {
            "symbol": symbol,
            "signal": final,
            "confidence": confidence,
            "signals": signals,
            "current_price": round(float(close.iloc[-1]), 4),
            "rsi": round(float(rsi_val), 2) if rsi_val is not None else None,
            "macd": round(float(macd_val.iloc[-1]), 4) if not macd_val.empty else None,
            "macd_signal": round(float(sig_val.iloc[-1]), 4) if not sig_val.empty else None,
            "bb_upper": round(float(upper.iloc[-1]), 4) if not upper.empty else None,
            "bb_lower": round(float(lower.iloc[-1]), 4) if not lower.empty else None,
            "sma_20": round(float(TechnicalIndicators.sma(close, 20).iloc[-1]), 4) if len(df) > 20 else None,
            "sma_50": round(float(TechnicalIndicators.sma(close, 50).iloc[-1]), 4) if len(df) > 50 else None,
            "generated_at": datetime.utcnow().isoformat(),
        }


class OrderManager:
    """
    Semi-automated order management.
    - Generates orders from signals
    - Paper trading simulation
    - Risk controls (position sizing, max position limits)
    """

    def __init__(
        self,
        max_position_pct: float = 0.10,
        max_orders_per_day: int = 10,
        auto_execute: bool = False,
    ):
        self.max_position_pct = max_position_pct
        self.max_orders_per_day = max_orders_per_day
        self.auto_execute = auto_execute
        self.pending_orders: List[Order] = []
        self.filled_orders: List[Order] = []

    def size_position(self, nav: float, price: float, signal_confidence: float) -> float:
        """Kelly-inspired position sizing adjusted by confidence."""
        base_pct = self.max_position_pct * (signal_confidence / 100)
        dollar_value = nav * base_pct
        if price <= 0:
            return 0.0
        qty = dollar_value / price
        return round(qty, 4)

    def create_order_from_signal(
        self,
        signal: dict,
        nav: float,
        current_weights: Dict[str, float],
    ) -> Optional[Order]:
        sym = signal["symbol"]
        action = signal["signal"]
        confidence = signal["confidence"]
        price = signal.get("current_price", 0)

        if action == "HOLD" or price <= 0:
            return None

        side = "buy" if action == "BUY" else "sell"
        qty = self.size_position(nav, price, confidence)
        if qty <= 0:
            return None

        order = Order(
            symbol=sym,
            side=side,
            quantity=qty,
            order_type="market",
            strategy="signal_engine",
            notes=f"Confidence: {confidence}% | Strategies: {signal.get('signals', {})}",
        )
        self.pending_orders.append(order)
        return order

    def execute_paper_order(self, order: Order, fill_price: float) -> Order:
        """Simulate a fill at the given price."""
        order.fill(fill_price)
        self.pending_orders = [o for o in self.pending_orders if o.order_id != order.order_id]
        self.filled_orders.append(order)
        return order

    def get_pending_orders(self) -> List[dict]:
        return [o.to_dict() for o in self.pending_orders]

    def get_filled_orders(self) -> List[dict]:
        return [o.to_dict() for o in self.filled_orders[-50:]]
