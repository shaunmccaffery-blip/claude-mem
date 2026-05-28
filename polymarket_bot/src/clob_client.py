from __future__ import annotations

import time

import httpx
from cachetools import TTLCache
from tenacity import retry, stop_after_attempt, wait_exponential

from .market_models import OrderBookSnapshot, OrderLevel


class ClobClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=10.0)
        self.cache: TTLCache[str, OrderBookSnapshot] = TTLCache(maxsize=5000, ttl=5)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=0.5, max=5))
    def get_orderbook(self, token_id: str) -> OrderBookSnapshot:
        if token_id in self.cache:
            return self.cache[token_id]
        resp = self.client.get(f"{self.base_url}/book", params={"token_id": token_id})
        resp.raise_for_status()
        raw = resp.json()
        bids = [OrderLevel(price=float(x["price"]), size=float(x["size"])) for x in raw.get("bids", [])]
        asks = [OrderLevel(price=float(x["price"]), size=float(x["size"])) for x in raw.get("asks", [])]
        best_bid = bids[0].price if bids else None
        best_ask = asks[0].price if asks else None
        best_ask_size = asks[0].size if asks else 0.0
        ob = OrderBookSnapshot(token_id=token_id, best_bid=best_bid, best_ask=best_ask, best_ask_size=best_ask_size, bids=bids, asks=asks)
        self.cache[token_id] = ob
        time.sleep(0.05)
        return ob
