#!/usr/bin/env python3
"""
Nansen -> Bybit signal glue.

Pulls smart-money / flow signals from Nansen's token-screener, matches each
token to a tradable Bybit perp symbol, and proposes a fractional-Kelly position.

SAFETY: This only PROPOSES. It never places orders. Execution stays behind
bybit_client's BYBIT_EXECUTION_ENABLED gate, which you invoke separately.

Extensibility: Nansen exposes many endpoints. Rather than hardcode paths that
may 404 against your plan/version, extra signals are merged via a generic
NansenClient.request(...) in `enrich_with_endpoint()`. Add typed wrappers in
nansen_client.py once you confirm the exact paths from your Nansen API docs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from bybit_client import BybitClient
from nansen_client import NansenClient
from trading_common import fractional_kelly_size, setup_logging

logger = setup_logging("crypto_strategy")


@dataclass
class Proposal:
    token: str
    bybit_symbol: str
    netflow: Optional[float]
    last_price: Optional[float]
    suggested_usd: float
    extras: Dict[str, Any] = field(default_factory=dict)


def _to_bybit_symbol(token_symbol: str, quote: str = "USDT") -> str:
    return f"{token_symbol.upper()}{quote}"


def _bybit_symbol_tradable(bybit: BybitClient, symbol: str) -> Optional[float]:
    """Return last price if the symbol trades on Bybit linear perps, else None."""
    try:
        result = bybit.get_tickers(category="linear", symbol=symbol)
        rows = result.get("list", [])
        if rows:
            return float(rows[0].get("lastPrice", 0)) or None
    except Exception as exc:  # symbol not found / transient
        logger.debug("ticker lookup failed for %s: %s", symbol, exc)
    return None


def generate_proposals(
    bankroll_usd: float,
    chains: Optional[List[str]] = None,
    timeframe: str = "24h",
    only_smart_money: bool = True,
    edge_per_signal: float = 0.05,
    kelly_fraction: float = 0.25,
    max_position_pct: float = 0.25,
    top_n: int = 10,
    nansen: Optional[NansenClient] = None,
    bybit: Optional[BybitClient] = None,
) -> List[Proposal]:
    """
    Rank tokens by Nansen net-inflow, keep those tradable on Bybit, and size them.

    edge_per_signal is a flat assumed edge per qualifying signal — deliberately
    conservative. Tune it (or replace with a calibrated model) before trusting size.
    """
    nansen = nansen or NansenClient()
    bybit = bybit or BybitClient()

    screened = nansen.token_screener(
        chains=chains,
        timeframe=timeframe,
        only_smart_money=only_smart_money,
        order_by_field="netflow",
        order_by_direction="DESC",
        per_page=max(top_n * 3, 30),
    )
    rows = screened.get("data", screened.get("result", screened)) if isinstance(screened, dict) else screened
    if not isinstance(rows, list):
        logger.warning("Unexpected screener shape; got %s", type(rows).__name__)
        rows = []

    proposals: List[Proposal] = []
    for row in rows:
        symbol = (row.get("symbol") or row.get("token_symbol") or "").strip()
        if not symbol:
            continue
        bybit_symbol = _to_bybit_symbol(symbol)
        last_price = _bybit_symbol_tradable(bybit, bybit_symbol)
        if last_price is None:
            continue  # not tradable on Bybit perps; skip
        usd = fractional_kelly_size(
            bankroll_usd=bankroll_usd,
            edge=edge_per_signal,
            odds=1.0,
            kelly_fraction=kelly_fraction,
            max_position_pct=max_position_pct,
        )
        proposals.append(
            Proposal(
                token=symbol,
                bybit_symbol=bybit_symbol,
                netflow=row.get("netflow"),
                last_price=last_price,
                suggested_usd=usd,
            )
        )
        if len(proposals) >= top_n:
            break
    return proposals


def enrich_with_endpoint(
    proposals: List[Proposal],
    path: str,
    body_for: Optional[Any] = None,
    nansen: Optional[NansenClient] = None,
    method: str = "POST",
) -> List[Proposal]:
    """
    Fold an arbitrary Nansen endpoint's data into each proposal's `extras`.

    `body_for(proposal) -> dict` builds the request body per token. Use this to
    attach any Nansen endpoint (flows, holders, PnL, TGM, etc.) without waiting
    for a typed wrapper. Failures per-token are logged and skipped, not fatal.
    """
    nansen = nansen or NansenClient()
    for p in proposals:
        try:
            body = body_for(p) if callable(body_for) else (body_for or {})
            p.extras[path] = nansen.request(method, path, json_body=body)
        except Exception as exc:
            logger.debug("enrich %s failed for %s: %s", path, p.token, exc)
    return proposals
