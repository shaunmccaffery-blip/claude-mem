from src.arb_scanner import scan_market_for_arb
from src.config import Settings
from src.market_models import Market, OrderBookSnapshot, Outcome


def test_binary_arb_positive():
    m = Market(market_id="1", question="Q", outcomes=[Outcome(name="YES", token_id="a"), Outcome(name="NO", token_id="b")])
    books = {
        "a": OrderBookSnapshot(token_id="a", best_ask=0.48, best_ask_size=100),
        "b": OrderBookSnapshot(token_id="b", best_ask=0.49, best_ask_size=100),
    }
    s = Settings(min_net_edge=0.0, estimated_fees=0.0, estimated_slippage=0.0, safety_buffer=0.0)
    opps = scan_market_for_arb(m, books, s)
    assert len(opps) == 1
    assert opps[0].gross_edge == 0.03
