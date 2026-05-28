from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Outcome(BaseModel):
    name: str
    token_id: str


class Market(BaseModel):
    market_id: str
    event_id: str | None = None
    question: str
    slug: str | None = None
    outcomes: list[Outcome]
    end_date: datetime | None = None
    volume: float = 0.0
    liquidity: float = 0.0
    tags: list[str] = Field(default_factory=list)
    status: str = "unknown"


class OrderLevel(BaseModel):
    price: float
    size: float


class OrderBookSnapshot(BaseModel):
    token_id: str
    best_bid: float | None = None
    best_ask: float | None = None
    best_ask_size: float = 0.0
    bids: list[OrderLevel] = Field(default_factory=list)
    asks: list[OrderLevel] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    def cumulative_ask_depth(self, target_price: float) -> float:
        return sum(level.size for level in self.asks if level.price <= target_price)


class Opportunity(BaseModel):
    market_id: str
    question: str
    outcomes: list[str]
    token_ids: list[str]
    best_asks: list[float]
    available_sizes: list[float]
    total_cost: float
    gross_edge: float
    net_edge: float
    max_safe_size: float
    expected_profit: float
    warnings: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class WalletTrade(BaseModel):
    wallet: str
    market_id: str
    outcome: str
    side: str
    price: float
    size: float
    timestamp: datetime
    resolved: bool = False
    pnl: float | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class WalletScore(BaseModel):
    wallet: str
    realized_pnl: float
    unrealized_pnl: float
    total_volume: float
    resolved_markets: int
    win_rate: float
    avg_roi: float
    median_roi: float
    profit_factor: float
    max_drawdown: float
    stability_score: float
    avg_hold_hours: float
    market_diversity: float
    category_concentration: float
    pnl_top_trade_pct: float
    pnl_unresolved_pct: float
    entry_timing_score: float
    copy_lag_sensitivity: float
    suspicious_activity_score: float
    copyworthiness: float
