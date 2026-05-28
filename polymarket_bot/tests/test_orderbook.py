from src.market_models import OrderBookSnapshot, OrderLevel
from src.orderbook import executable_size


def test_executable_size():
    ob = OrderBookSnapshot(token_id="a", asks=[OrderLevel(price=0.4, size=10), OrderLevel(price=0.5, size=15)])
    assert executable_size(ob, 0.5) == 25
