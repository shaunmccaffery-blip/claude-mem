#!/usr/bin/env python3
"""
Market-data providers: enrich a candidate token with price, technicals, and
social signals from CoinGecko, CoinMarketCap, TradingView, and LunarCrush.

Design: every provider is FAIL-SOFT. A missing API key, a network error, or an
unexpected response returns {} and is logged at debug level — it never raises
into the strategy. So you can wire all four and only the ones you have keys for
contribute. The aggregated bundle is fed to the Claude analyst as extra context.

Keys (env / .env, gitignored):
  COINMARKETCAP_API_KEY   - CoinMarketCap (free tier available)
  LUNARCRUSH_API_KEY      - LunarCrush (paid)
  COINGECKO_API_KEY       - optional; only for CoinGecko Pro

NOTE: external API shapes change. The endpoints below match each provider's
documented v-current API at time of writing; verify against current docs if a
provider starts returning {}. TradingView has no official API — technicals come
from the community `tradingview-ta` package (optional import).
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import requests

from trading_common import setup_logging

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

logger = setup_logging("market_data")

_TIMEOUT = 15


class MarketData:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.cmc_key = os.getenv("COINMARKETCAP_API_KEY") or None
        self.lunar_key = os.getenv("LUNARCRUSH_API_KEY") or None
        self.coingecko_key = os.getenv("COINGECKO_API_KEY") or None

    # -- CoinGecko (free) --------------------------------------------------

    def coingecko(self, symbol: str) -> Dict[str, Any]:
        try:
            base = "https://api.coingecko.com/api/v3"
            params = {
                "vs_currency": "usd",
                "symbols": symbol.lower(),
                "price_change_percentage": "24h",
            }
            headers = {}
            if self.coingecko_key:
                base = "https://pro-api.coingecko.com/api/v3"
                headers["x-cg-pro-api-key"] = self.coingecko_key
            resp = self.session.get(
                f"{base}/coins/markets", params=params, headers=headers, timeout=_TIMEOUT
            )
            resp.raise_for_status()
            rows = resp.json()
            if not rows:
                return {}
            r = rows[0]
            return {
                "price": r.get("current_price"),
                "market_cap": r.get("market_cap"),
                "volume_24h": r.get("total_volume"),
                "change_24h_pct": r.get("price_change_percentage_24h"),
            }
        except Exception as exc:
            logger.debug("coingecko failed for %s: %s", symbol, exc)
            return {}

    # -- CoinMarketCap (key) ----------------------------------------------

    def coinmarketcap(self, symbol: str) -> Dict[str, Any]:
        if not self.cmc_key:
            return {}
        try:
            resp = self.session.get(
                "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest",
                params={"symbol": symbol.upper(), "convert": "USD"},
                headers={"X-CMC_PRO_API_KEY": self.cmc_key},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {}).get(symbol.upper())
            if isinstance(data, list):
                data = data[0] if data else None
            if not data:
                return {}
            quote = data.get("quote", {}).get("USD", {})
            return {
                "price": quote.get("price"),
                "volume_24h": quote.get("volume_24h"),
                "change_24h_pct": quote.get("percent_change_24h"),
                "change_7d_pct": quote.get("percent_change_7d"),
                "market_cap": quote.get("market_cap"),
            }
        except Exception as exc:
            logger.debug("coinmarketcap failed for %s: %s", symbol, exc)
            return {}

    # -- LunarCrush (key) — social sentiment ------------------------------

    def lunarcrush(self, symbol: str) -> Dict[str, Any]:
        if not self.lunar_key:
            return {}
        try:
            resp = self.session.get(
                f"https://lunarcrush.com/api4/public/coins/{symbol.upper()}/v1",
                headers={"Authorization": f"Bearer {self.lunar_key}"},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            d = resp.json().get("data", {})
            return {
                "galaxy_score": d.get("galaxy_score"),
                "alt_rank": d.get("alt_rank"),
                "sentiment": d.get("sentiment"),
                "social_volume_24h": d.get("social_volume_24h"),
                "interactions_24h": d.get("interactions_24h"),
            }
        except Exception as exc:
            logger.debug("lunarcrush failed for %s: %s", symbol, exc)
            return {}

    # -- TradingView (unofficial lib) — technicals ------------------------

    def tradingview(self, bybit_symbol: str, interval: str = "1h") -> Dict[str, Any]:
        try:
            from tradingview_ta import TA_Handler, Interval
        except ImportError:
            logger.debug("tradingview_ta not installed; skipping technicals")
            return {}
        intervals = {
            "1h": Interval.INTERVAL_1_HOUR,
            "4h": Interval.INTERVAL_4_HOURS,
            "1d": Interval.INTERVAL_1_DAY,
        }
        try:
            handler = TA_Handler(
                symbol=bybit_symbol.upper(),
                screener="crypto",
                exchange="BYBIT",
                interval=intervals.get(interval, Interval.INTERVAL_1_HOUR),
            )
            summary = handler.get_analysis().summary
            return {
                "recommendation": summary.get("RECOMMENDATION"),
                "buy": summary.get("BUY"),
                "sell": summary.get("SELL"),
                "neutral": summary.get("NEUTRAL"),
            }
        except Exception as exc:
            logger.debug("tradingview failed for %s: %s", bybit_symbol, exc)
            return {}

    # -- aggregate ---------------------------------------------------------

    def enrich(self, token_symbol: str, bybit_symbol: Optional[str] = None) -> Dict[str, Any]:
        """Gather every available signal for a token. Empty providers are omitted."""
        out: Dict[str, Any] = {}
        for name, data in (
            ("coingecko", self.coingecko(token_symbol)),
            ("coinmarketcap", self.coinmarketcap(token_symbol)),
            ("lunarcrush", self.lunarcrush(token_symbol)),
            ("tradingview", self.tradingview(bybit_symbol or f"{token_symbol}USDT")),
        ):
            if data:
                out[name] = data
        return out


def _demo() -> None:
    md = MarketData()
    print(md.enrich("BTC", "BTCUSDT"))


if __name__ == "__main__":
    _demo()
