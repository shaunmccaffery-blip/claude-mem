#!/usr/bin/env python3
"""
Shared helpers for the crypto trading tools (logging + position sizing).

Kept dependency-light so bybit_client / nansen_client / crypto_cli can all
import it without pulling in the heavier Polymarket stack.
"""

from __future__ import annotations

import logging
import sys


def setup_logging(name: str = "crypto", level: int = logging.INFO) -> logging.Logger:
    """Stream logger matching polymarket_bot's format."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def fractional_kelly_size(
    bankroll_usd: float,
    edge: float,
    odds: float,
    kelly_fraction: float = 0.25,
    max_position_pct: float = 0.25,
) -> float:
    """
    Position size (USD) using fractional Kelly, capped by max_position_pct.

    edge: expected edge as a fraction (e.g. 0.08 for 8%)
    odds: net odds received on a win (b in Kelly; e.g. 1.0 for even money)
    """
    if bankroll_usd <= 0 or odds <= 0:
        return 0.0
    # Kelly fraction of bankroll: f* = edge / odds (simplified favorable-bet form)
    raw_fraction = max(0.0, edge / odds)
    sized_fraction = min(raw_fraction * kelly_fraction, max_position_pct)
    return round(bankroll_usd * sized_fraction, 2)
