#!/usr/bin/env python3
"""
Bybit V5 API client (2026-safe baseline).

Design goals:
- Secrets NEVER live in code or git. Credentials are read from environment
  variables (BYBIT_API_KEY / BYBIT_API_SECRET), typically loaded from a
  gitignored .env file.
- Public market-data endpoints need no auth.
- Authenticated reads (wallet balance, positions) require the env credentials.
- Order placement is gated: it is a no-op dry run unless BYBIT_EXECUTION_ENABLED
  is explicitly "true". Mirrors the manual-review-first stance of polymarket_bot.py.

Reference: https://bybit-exchange.github.io/docs/v5/intro
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv optional; env vars may be set elsewhere
    pass

MAINNET_BASE = "https://api.bybit.com"
TESTNET_BASE = "https://api-testnet.bybit.com"

RECV_WINDOW = os.getenv("BYBIT_RECV_WINDOW", "5000")


class BybitError(RuntimeError):
    """Raised when Bybit returns a non-zero retCode or transport fails."""


@dataclass
class BybitConfig:
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    private_key_path: Optional[str] = None
    testnet: bool = True
    execution_enabled: bool = False

    @classmethod
    def from_env(cls) -> "BybitConfig":
        return cls(
            api_key=os.getenv("BYBIT_API_KEY") or None,
            api_secret=os.getenv("BYBIT_API_SECRET") or None,
            private_key_path=os.getenv("BYBIT_PRIVATE_KEY_PATH") or None,
            # Default to testnet so a misconfigured run can't touch real funds.
            testnet=os.getenv("BYBIT_TESTNET", "true").lower() != "false",
            execution_enabled=os.getenv("BYBIT_EXECUTION_ENABLED", "false").lower()
            == "true",
        )

    @property
    def use_rsa(self) -> bool:
        return bool(self.private_key_path)


class BybitClient:
    def __init__(self, config: Optional[BybitConfig] = None) -> None:
        self.config = config or BybitConfig.from_env()
        self.base_url = TESTNET_BASE if self.config.testnet else MAINNET_BASE
        self.session = requests.Session()
        self._private_key = None  # lazily loaded RSA key

    # -- internals ---------------------------------------------------------

    def _require_auth(self) -> None:
        if not self.config.api_key:
            raise BybitError(
                "BYBIT_API_KEY not set. Add it to your .env file (gitignored)."
            )
        if not (self.config.api_secret or self.config.private_key_path):
            raise BybitError(
                "Set BYBIT_API_SECRET (HMAC) or BYBIT_PRIVATE_KEY_PATH (RSA) "
                "in your .env file — never hardcode credentials."
            )

    def _load_private_key(self):
        if self._private_key is None:
            try:
                from cryptography.hazmat.primitives.serialization import (
                    load_pem_private_key,
                )
            except ImportError as exc:  # pragma: no cover
                raise BybitError(
                    "RSA auth needs the 'cryptography' package "
                    "(pip install cryptography)."
                ) from exc
            with open(self.config.private_key_path, "rb") as fh:
                self._private_key = load_pem_private_key(fh.read(), password=None)
        return self._private_key

    def _sign(self, timestamp: str, payload: str) -> str:
        # Origin string is identical for both schemes.
        origin = f"{timestamp}{self.config.api_key}{RECV_WINDOW}{payload}"
        if self.config.use_rsa:
            # RSA: PKCS1v15 over SHA256, base64-encoded.
            import base64

            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding

            signature = self._load_private_key().sign(
                origin.encode(), padding.PKCS1v15(), hashes.SHA256()
            )
            return base64.b64encode(signature).decode()
        # HMAC-SHA256 with the API secret.
        return hmac.new(
            self.config.api_secret.encode(),
            origin.encode(),
            hashlib.sha256,
        ).hexdigest()

    def _auth_headers(self, payload: str) -> Dict[str, str]:
        self._require_auth()
        timestamp = str(int(time.time() * 1000))
        return {
            "X-BAPI-API-KEY": self.config.api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": RECV_WINDOW,
            "X-BAPI-SIGN": self._sign(timestamp, payload),
            "X-BAPI-SIGN-TYPE": "2",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _unwrap(data: Dict[str, Any]) -> Dict[str, Any]:
        if data.get("retCode") != 0:
            raise BybitError(
                f"Bybit retCode={data.get('retCode')}: {data.get('retMsg')}"
            )
        return data.get("result", {})

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=10),
        retry=retry_if_exception_type(requests.RequestException),
        reraise=True,
    )
    def _get(self, path: str, params: Dict[str, Any], auth: bool = False) -> Dict[str, Any]:
        query = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        headers = self._auth_headers(query) if auth else {}
        resp = self.session.get(
            f"{self.base_url}{path}", params=params, headers=headers, timeout=15
        )
        resp.raise_for_status()
        return self._unwrap(resp.json())

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=10),
        retry=retry_if_exception_type(requests.RequestException),
        reraise=True,
    )
    def _post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        payload = json.dumps(body, separators=(",", ":"))
        headers = self._auth_headers(payload)
        resp = self.session.post(
            f"{self.base_url}{path}", data=payload, headers=headers, timeout=15
        )
        resp.raise_for_status()
        return self._unwrap(resp.json())

    # -- public market data (no auth) -------------------------------------

    def get_server_time(self) -> Dict[str, Any]:
        return self._get("/v5/market/time", {})

    def get_tickers(self, category: str = "linear", symbol: Optional[str] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {"category": category}
        if symbol:
            params["symbol"] = symbol
        return self._get("/v5/market/tickers", params)

    def get_orderbook(self, symbol: str, category: str = "linear", limit: int = 25) -> Dict[str, Any]:
        return self._get(
            "/v5/market/orderbook",
            {"category": category, "symbol": symbol, "limit": limit},
        )

    def get_klines(
        self, symbol: str, interval: str = "60", category: str = "linear", limit: int = 200
    ) -> Dict[str, Any]:
        return self._get(
            "/v5/market/kline",
            {"category": category, "symbol": symbol, "interval": interval, "limit": limit},
        )

    # -- authenticated reads ----------------------------------------------

    def get_wallet_balance(self, account_type: str = "UNIFIED") -> Dict[str, Any]:
        return self._get(
            "/v5/account/wallet-balance", {"accountType": account_type}, auth=True
        )

    def get_positions(self, category: str = "linear", settle_coin: str = "USDT") -> Dict[str, Any]:
        return self._get(
            "/v5/position/list",
            {"category": category, "settleCoin": settle_coin},
            auth=True,
        )

    # -- trading (gated) ---------------------------------------------------

    def place_order(
        self,
        symbol: str,
        side: str,
        qty: str,
        category: str = "linear",
        order_type: str = "Market",
        price: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Place an order. No-op dry run unless BYBIT_EXECUTION_ENABLED=true."""
        self._require_auth()
        body: Dict[str, Any] = {
            "category": category,
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": qty,
        }
        if price is not None:
            body["price"] = price

        if not self.config.execution_enabled:
            return {"dryRun": True, "wouldSend": body}
        return self._post("/v5/order/create", body)


def _demo() -> None:
    client = BybitClient()
    print("network:", "testnet" if client.config.testnet else "MAINNET")
    print("server time:", client.get_server_time())
    print("BTCUSDT ticker:", client.get_tickers(symbol="BTCUSDT"))
    if client.config.api_key:
        print("wallet:", client.get_wallet_balance())
    else:
        print("(no credentials set — skipping authenticated calls)")


if __name__ == "__main__":
    _demo()
