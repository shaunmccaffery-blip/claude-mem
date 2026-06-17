#!/usr/bin/env python3
"""
Nansen API client (on-chain analytics).

Same safety stance as bybit_client:
- API key read ONLY from env (NANSEN_API_KEY), never hardcoded or pasted in chat.
- Read-only analytics; no funds are ever moved by this client.

NOTE ON ENDPOINTS: Nansen's API surface evolves and access depends on your plan.
The base URL and auth header below match Nansen's documented scheme (apiKey
header), and a generic request() method lets you hit any endpoint. The named
helpers are convenience wrappers for commonly used paths — verify the exact
paths/params against your current Nansen API docs and adjust if they 404.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

NANSEN_BASE = os.getenv("NANSEN_BASE_URL", "https://api.nansen.ai/api/v1")


class NansenError(RuntimeError):
    pass


@dataclass
class NansenConfig:
    api_key: Optional[str] = None

    @classmethod
    def from_env(cls) -> "NansenConfig":
        return cls(api_key=os.getenv("NANSEN_API_KEY") or None)


class NansenClient:
    def __init__(self, config: Optional[NansenConfig] = None) -> None:
        self.config = config or NansenConfig.from_env()
        self.base_url = NANSEN_BASE.rstrip("/")
        self.session = requests.Session()

    def _require_auth(self) -> None:
        if not self.config.api_key:
            raise NansenError(
                "NANSEN_API_KEY not set. Add it to your .env file (gitignored) "
                "— never hardcode it."
            )

    def _headers(self) -> Dict[str, str]:
        self._require_auth()
        return {"apiKey": self.config.api_key, "Content-Type": "application/json"}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
    def request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Generic Nansen request. path is appended to the base URL."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        resp = self.session.request(
            method.upper(),
            url,
            headers=self._headers(),
            params=params,
            json=json_body,
            timeout=20,
        )
        if resp.status_code >= 400:
            raise NansenError(f"Nansen {resp.status_code} on {path}: {resp.text[:300]}")
        return resp.json()

    # -- convenience wrappers (verify paths against current Nansen docs) ----

    def smart_money_holdings(self, chain: str = "ethereum", **params: Any) -> Any:
        """Smart-money token holdings for a chain."""
        return self.request(
            "POST", "smart-money/holdings", json_body={"chain": chain, **params}
        )

    def token_flows(self, token_address: str, chain: str = "ethereum", **params: Any) -> Any:
        """Inflow/outflow analytics for a token."""
        return self.request(
            "POST",
            "token/flows",
            json_body={"chain": chain, "tokenAddress": token_address, **params},
        )

    def wallet_pnl(self, address: str, chain: str = "ethereum", **params: Any) -> Any:
        """Profit/loss profile for a wallet address."""
        return self.request(
            "POST",
            "profiler/pnl",
            json_body={"chain": chain, "walletAddress": address, **params},
        )


def _demo() -> None:
    client = NansenClient()
    if not client.config.api_key:
        print("(no NANSEN_API_KEY set — set it in .env to test)")
        return
    print("smart money (ethereum):", client.smart_money_holdings())


if __name__ == "__main__":
    _demo()
