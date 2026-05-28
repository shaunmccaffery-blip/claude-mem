from __future__ import annotations

from .config import Settings
from .market_models import Market, Opportunity, OrderBookSnapshot


def scan_market_for_arb(market: Market, books: dict[str, OrderBookSnapshot], settings: Settings) -> list[Opportunity]:
    opportunities: list[Opportunity] = []
    asks: list[float] = []
    sizes: list[float] = []
    names: list[str] = []
    token_ids: list[str] = []
    for outcome in market.outcomes:
        book = books.get(outcome.token_id)
        if not book or book.best_ask is None:
            return opportunities
        asks.append(book.best_ask)
        sizes.append(book.best_ask_size)
        names.append(outcome.name)
        token_ids.append(outcome.token_id)

    total_cost = sum(asks)
    gross_edge = 1.0 - total_cost
    net_edge = gross_edge - settings.estimated_fees - settings.estimated_slippage - settings.safety_buffer
    max_safe_size = min(sizes)
    if net_edge >= settings.min_net_edge and max_safe_size >= settings.min_trade_size:
        opportunities.append(Opportunity(
            market_id=market.market_id,
            question=market.question,
            outcomes=names,
            token_ids=token_ids,
            best_asks=asks,
            available_sizes=sizes,
            total_cost=total_cost,
            gross_edge=gross_edge,
            net_edge=net_edge,
            max_safe_size=max_safe_size,
            expected_profit=net_edge * max_safe_size,
            warnings=[],
        ))
    return opportunities
