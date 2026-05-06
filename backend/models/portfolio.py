"""
Portfolio and Position data models for the hedge fund system.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
import uuid


@dataclass
class Position:
    symbol: str
    quantity: float
    avg_cost: float
    current_price: float = 0.0
    asset_class: str = "equity"
    sector: str = "unknown"
    currency: str = "USD"
    position_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    opened_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def cost_basis(self) -> float:
        return self.quantity * self.avg_cost

    @property
    def unrealized_pnl(self) -> float:
        return self.market_value - self.cost_basis

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.cost_basis == 0:
            return 0.0
        return (self.unrealized_pnl / self.cost_basis) * 100

    @property
    def weight(self) -> float:
        return 0.0  # Set externally by portfolio

    def to_dict(self) -> dict:
        return {
            "position_id": self.position_id,
            "symbol": self.symbol,
            "quantity": self.quantity,
            "avg_cost": self.avg_cost,
            "current_price": self.current_price,
            "market_value": round(self.market_value, 2),
            "cost_basis": round(self.cost_basis, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "unrealized_pnl_pct": round(self.unrealized_pnl_pct, 2),
            "asset_class": self.asset_class,
            "sector": self.sector,
            "currency": self.currency,
            "opened_at": self.opened_at.isoformat(),
        }


@dataclass
class Order:
    symbol: str
    side: str          # 'buy' or 'sell'
    quantity: float
    order_type: str    # 'market', 'limit', 'stop'
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    status: str = "pending"   # pending, filled, cancelled, rejected
    filled_price: Optional[float] = None
    filled_at: Optional[datetime] = None
    order_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: datetime = field(default_factory=datetime.utcnow)
    strategy: str = "manual"
    notes: str = ""

    def fill(self, price: float) -> None:
        self.status = "filled"
        self.filled_price = price
        self.filled_at = datetime.utcnow()

    def cancel(self) -> None:
        self.status = "cancelled"

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "order_type": self.order_type,
            "limit_price": self.limit_price,
            "stop_price": self.stop_price,
            "status": self.status,
            "filled_price": self.filled_price,
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
            "created_at": self.created_at.isoformat(),
            "strategy": self.strategy,
            "notes": self.notes,
        }


class Portfolio:
    def __init__(self, name: str = "Main Portfolio", initial_cash: float = 1_000_000.0):
        self.name = name
        self.cash = initial_cash
        self.initial_cash = initial_cash
        self.positions: Dict[str, Position] = {}
        self.order_history: List[Order] = []
        self.created_at = datetime.utcnow()
        self._realized_pnl = 0.0

    @property
    def total_market_value(self) -> float:
        return sum(p.market_value for p in self.positions.values())

    @property
    def total_nav(self) -> float:
        return self.cash + self.total_market_value

    @property
    def total_unrealized_pnl(self) -> float:
        return sum(p.unrealized_pnl for p in self.positions.values())

    @property
    def total_pnl(self) -> float:
        return self.total_unrealized_pnl + self._realized_pnl

    @property
    def total_pnl_pct(self) -> float:
        if self.initial_cash == 0:
            return 0.0
        return (self.total_pnl / self.initial_cash) * 100

    def get_weights(self) -> Dict[str, float]:
        nav = self.total_nav
        if nav == 0:
            return {}
        return {sym: pos.market_value / nav for sym, pos in self.positions.items()}

    def add_position(self, position: Position) -> None:
        if position.symbol in self.positions:
            existing = self.positions[position.symbol]
            total_qty = existing.quantity + position.quantity
            existing.avg_cost = (
                (existing.quantity * existing.avg_cost + position.quantity * position.avg_cost)
                / total_qty
            )
            existing.quantity = total_qty
        else:
            self.positions[position.symbol] = position

    def remove_position(self, symbol: str, quantity: float, price: float) -> float:
        """Remove quantity from position, return realized PnL."""
        if symbol not in self.positions:
            return 0.0
        pos = self.positions[symbol]
        realized = (price - pos.avg_cost) * quantity
        self._realized_pnl += realized
        pos.quantity -= quantity
        if pos.quantity <= 1e-6:
            del self.positions[symbol]
        return realized

    def update_prices(self, prices: Dict[str, float]) -> None:
        for sym, price in prices.items():
            if sym in self.positions:
                self.positions[sym].current_price = price

    def to_dict(self) -> dict:
        weights = self.get_weights()
        positions = []
        for sym, pos in self.positions.items():
            d = pos.to_dict()
            d["weight_pct"] = round(weights.get(sym, 0) * 100, 2)
            positions.append(d)
        return {
            "name": self.name,
            "cash": round(self.cash, 2),
            "total_market_value": round(self.total_market_value, 2),
            "total_nav": round(self.total_nav, 2),
            "total_unrealized_pnl": round(self.total_unrealized_pnl, 2),
            "realized_pnl": round(self._realized_pnl, 2),
            "total_pnl": round(self.total_pnl, 2),
            "total_pnl_pct": round(self.total_pnl_pct, 2),
            "positions": positions,
            "num_positions": len(self.positions),
            "created_at": self.created_at.isoformat(),
        }
