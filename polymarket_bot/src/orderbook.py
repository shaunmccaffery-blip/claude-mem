from .market_models import OrderBookSnapshot


def executable_size(snapshot: OrderBookSnapshot, max_price: float) -> float:
    return snapshot.cumulative_ask_depth(max_price)
