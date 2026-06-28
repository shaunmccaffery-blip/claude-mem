#!/usr/bin/env python3
"""
Claude-powered analyst: judges a candidate token and returns a structured verdict.

Uses the official Anthropic SDK. Reads ANTHROPIC_API_KEY from the environment
(.env, gitignored) — never hardcode it. Model defaults to claude-opus-4-8.

IMPORTANT: Claude has no real-time market data and cannot predict prices. This
layer adds a skeptical second opinion on top of the Nansen signal to FILTER OUT
weak candidates — it is not a source of alpha. Treat every verdict as opinion,
not a guarantee.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import anthropic

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-8")

SYSTEM = """You are a cautious crypto trading analyst reviewing one candidate \
perpetual-futures token at a time. You are given a token symbol, its Nansen \
smart-money net flow over a recent window, its last price, and a proposed \
direction (LONG when smart money is net buying, SHORT when net selling), and \
optionally extra market signals (price momentum, technical-indicator \
recommendation, social sentiment).

Reason about whether opening that position in that direction is reasonable, then \
return a verdict.

Use any extra signals for SELECTIVITY, not justification:
- Require corroboration: the trade is attractive only if independent signals AGREE
  with the direction (a LONG wants positive flow AND non-bearish technicals).
- Treat a clear conflict as a veto (skip), not something to explain away.
- Social sentiment is often lagging/contrarian — extreme bullishness is a caution.
- Do not let the mere quantity of signals inflate confidence.

Be skeptical and default to "skip":
- Smart-money net flow is a weak, noisy signal, not a guarantee.
- You have NO real-time order-book or news context — acknowledge that uncertainty.
- Only choose "trade" when signals align and you can give a concrete reason.
- Express confidence honestly (0.0-1.0). Most candidates should score below 0.5.
- Keep the rationale to one or two plain sentences."""

_VERDICT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["trade", "skip"]},
        "confidence": {"type": "number", "description": "0.0 (no) to 1.0 (strong)"},
        "rationale": {"type": "string", "description": "One or two sentences."},
    },
    "required": ["decision", "confidence", "rationale"],
    "additionalProperties": False,
}


@dataclass
class Verdict:
    decision: str  # "trade" | "skip"
    confidence: float
    rationale: str


class ClaudeAnalyst:
    def __init__(self, model: str = MODEL) -> None:
        self.model = model
        # Reads ANTHROPIC_API_KEY from the environment.
        self.client = anthropic.Anthropic()

    def evaluate(
        self,
        symbol: str,
        netflow: Optional[float],
        last_price: Optional[float],
        side: str = "Buy",
        chain: str = "",
        signals: Optional[Dict[str, Any]] = None,
    ) -> Verdict:
        direction = "LONG" if side == "Buy" else "SHORT"
        extra = ""
        if signals:
            extra = "\nExtra market signals:\n" + json.dumps(signals, indent=2) + "\n"
        prompt = (
            f"Token symbol: {symbol}\n"
            f"Chain: {chain or 'unknown'}\n"
            f"Nansen smart-money net flow (recent window): {netflow} "
            f"({'inflow' if (netflow or 0) >= 0 else 'outflow'})\n"
            f"Last price (USD): {last_price}\n"
            f"Proposed direction: {direction}\n"
            f"{extra}\n"
            f"Should this {direction} position be opened (small speculative size)? "
            "Decide trade or skip."
        )
        response = self.client.messages.create(
            model=self.model,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": _VERDICT_SCHEMA}},
        )
        # Safety classifiers may decline — treat a refusal as "skip".
        if response.stop_reason == "refusal":
            return Verdict("skip", 0.0, "Analyst declined to assess this candidate.")

        text = next((b.text for b in response.content if b.type == "text"), "")
        data = json.loads(text)
        return Verdict(
            decision=data["decision"],
            confidence=float(data["confidence"]),
            rationale=data["rationale"],
        )


def _demo() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("(set ANTHROPIC_API_KEY in .env to test the analyst)")
        return
    analyst = ClaudeAnalyst()
    v = analyst.evaluate("ZKUSDT", 7701.0, 0.011418, chain="ethereum")
    print(v)


if __name__ == "__main__":
    _demo()
