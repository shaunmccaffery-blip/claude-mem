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

import datetime as dt
import json
import os
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
    side: str = "Buy"  # "Buy" (long) when net inflow, "Sell" (short) when net outflow
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
    use_claude: bool = False,
    min_confidence: float = 0.6,
    allow_shorts: bool = False,
    use_market_data: bool = False,
    nansen: Optional[NansenClient] = None,
    bybit: Optional[BybitClient] = None,
) -> List[Proposal]:
    """
    Rank tokens by Nansen net-inflow, keep those tradable on Bybit, and size them.

    edge_per_signal is a flat assumed edge per qualifying signal — deliberately
    conservative. Tune it (or replace with a calibrated model) before trusting size.

    If use_claude is True, each candidate is also run past the Claude analyst and
    dropped unless it returns "trade" with confidence >= min_confidence. Size is
    then scaled by the analyst's confidence. The analyst is a skeptical filter,
    not a source of alpha.
    """
    nansen = nansen or NansenClient()
    bybit = bybit or BybitClient()

    analyst = None
    if use_claude:
        from claude_analyst import ClaudeAnalyst

        analyst = ClaudeAnalyst()

    market = None
    if use_market_data:
        from market_data import MarketData

        market = MarketData()

    def _rows(direction: str) -> List[Dict[str, Any]]:
        screened = nansen.token_screener(
            chains=chains,
            timeframe=timeframe,
            only_smart_money=only_smart_money,
            order_by_field="netflow",
            order_by_direction=direction,
            per_page=max(top_n * 3, 30),
        )
        data = (
            screened.get("data", screened.get("result", screened))
            if isinstance(screened, dict)
            else screened
        )
        return data if isinstance(data, list) else []

    # DESC = biggest net inflows (long candidates); ASC = biggest net outflows
    # (short candidates). Merge and rank by absolute flow so the strongest
    # signals in either direction win.
    rows = _rows("DESC")
    if allow_shorts:
        rows = rows + _rows("ASC")
    rows.sort(key=lambda r: abs(float(r.get("netflow") or 0)), reverse=True)
    if not rows:
        logger.warning("Screener returned no rows")

    proposals: List[Proposal] = []
    for row in rows:
        symbol = (row.get("symbol") or row.get("token_symbol") or "").strip()
        if not symbol:
            continue
        bybit_symbol = _to_bybit_symbol(symbol)
        last_price = _bybit_symbol_tradable(bybit, bybit_symbol)
        if last_price is None:
            continue  # not tradable on Bybit perps; skip

        netflow_val = float(row.get("netflow") or 0)
        # Net inflow -> long (Buy); net outflow -> short (Sell).
        side = "Sell" if netflow_val < 0 else "Buy"
        usd = fractional_kelly_size(
            bankroll_usd=bankroll_usd,
            edge=edge_per_signal,
            odds=1.0,
            kelly_fraction=kelly_fraction,
            max_position_pct=max_position_pct,
        )

        extras: Dict[str, Any] = {}

        signals = None
        if market is not None:
            signals = market.enrich(symbol, bybit_symbol)
            if signals:
                extras["market"] = signals

        if analyst is not None:
            try:
                verdict = analyst.evaluate(
                    symbol=symbol,
                    netflow=row.get("netflow"),
                    last_price=last_price,
                    side=side,
                    chain=row.get("chain", ""),
                    signals=signals,
                )
            except Exception as exc:
                logger.warning("Claude analyst failed for %s: %s", symbol, exc)
                continue
            extras["claude"] = {
                "decision": verdict.decision,
                "confidence": verdict.confidence,
                "rationale": verdict.rationale,
            }
            if verdict.decision != "trade" or verdict.confidence < min_confidence:
                logger.info(
                    "Claude skipped %s (%.2f): %s",
                    symbol, verdict.confidence, verdict.rationale,
                )
                continue
            # Scale size by the analyst's confidence.
            usd = round(usd * verdict.confidence, 2)

        proposals.append(
            Proposal(
                token=symbol,
                bybit_symbol=bybit_symbol,
                netflow=row.get("netflow"),
                last_price=last_price,
                suggested_usd=usd,
                side=side,
                extras=extras,
            )
        )
        if len(proposals) >= top_n:
            break
    return proposals


def place_proposals(
    proposals: List[Proposal],
    leverage: int = 10,
    bybit: Optional[BybitClient] = None,
) -> List[Dict[str, Any]]:
    """
    Set leverage and place a market order (side per proposal) for each candidate.

    SAFETY: both set_leverage and place_order are no-op dry runs unless
    BYBIT_EXECUTION_ENABLED=true. Quantity is sized from suggested_usd /
    last_price; Bybit may reject orders below a symbol's minimum quantity or with
    the wrong step size — those errors are logged per-token, not fatal.
    """
    bybit = bybit or BybitClient()
    results: List[Dict[str, Any]] = []
    for p in proposals:
        if not p.last_price:
            continue
        try:
            bybit.set_leverage(p.bybit_symbol, leverage, category="linear")
        except Exception as exc:
            logger.warning("set_leverage failed for %s: %s", p.bybit_symbol, exc)
        qty = str(round(p.suggested_usd / p.last_price, 6))
        try:
            res = bybit.place_order(
                symbol=p.bybit_symbol, side=p.side, qty=qty, category="linear"
            )
            results.append(
                {"symbol": p.bybit_symbol, "side": p.side, "qty": qty,
                 "leverage": leverage, "result": res}
            )
            logger.info(
                "order %s %s qty=%s lev=%sx -> %s",
                p.bybit_symbol, p.side, qty, leverage, res,
            )
        except Exception as exc:
            logger.warning("order failed for %s: %s", p.bybit_symbol, exc)
            results.append({"symbol": p.bybit_symbol, "qty": qty, "error": str(exc)})
    return results


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


DEFAULT_LOG_PATH = "logs/signals.jsonl"


def log_proposals(proposals: List[Proposal], path: str = DEFAULT_LOG_PATH) -> str:
    """Append each proposal (with entry price + signals + UTC timestamp) as JSONL.

    This is the record you review later to see whether the picks made money,
    BEFORE risking real funds. Logged on every run, dry or live.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    ts = dt.datetime.now(dt.timezone.utc).isoformat()
    with open(path, "a") as fh:
        for p in proposals:
            fh.write(
                json.dumps(
                    {
                        "ts": ts,
                        "token": p.token,
                        "symbol": p.bybit_symbol,
                        "side": p.side,
                        "netflow": p.netflow,
                        "entry_price": p.last_price,
                        "suggested_usd": p.suggested_usd,
                        "claude": p.extras.get("claude"),
                        "market": p.extras.get("market"),
                    }
                )
                + "\n"
            )
    return path


def review_log(
    path: str = DEFAULT_LOG_PATH, bybit: Optional[BybitClient] = None
) -> List[Dict[str, Any]]:
    """Re-price each logged pick against the CURRENT Bybit price.

    Returns a list of {ts, symbol, side, entry_price, now_price, return_pct}
    where return_pct is the hypothetical return in the picked direction (longs
    gain when price rises, shorts when it falls). No money is involved.
    """
    bybit = bybit or BybitClient()
    out: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        return out
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            entry = rec.get("entry_price")
            now = _bybit_symbol_tradable(bybit, rec["symbol"])
            if not entry or not now:
                continue
            move = (now - entry) / entry
            ret = move if rec.get("side", "Buy") == "Buy" else -move
            out.append(
                {
                    "ts": rec.get("ts"),
                    "symbol": rec["symbol"],
                    "side": rec.get("side", "Buy"),
                    "entry_price": entry,
                    "now_price": now,
                    "return_pct": round(ret * 100, 2),
                }
            )
    return out
