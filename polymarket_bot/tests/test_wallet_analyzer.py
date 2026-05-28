from datetime import datetime

from src.market_models import WalletTrade
from src.wallet_analyzer import score_wallet


def test_score_wallet():
    trades = [WalletTrade(wallet="0x1", market_id="m1", outcome="YES", side="buy", price=0.4, size=100, timestamp=datetime.utcnow(), resolved=True, pnl=10)]
    score = score_wallet(trades)
    assert score.realized_pnl == 10
