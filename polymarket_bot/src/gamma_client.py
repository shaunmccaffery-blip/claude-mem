from __future__ import annotations

from datetime import datetime

import httpx
from dateutil.parser import isoparse

from .market_models import Market, Outcome


class GammaClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=15.0)

    def fetch_active_markets(self, limit: int = 200) -> list[Market]:
        params = {"limit": limit, "active": True, "closed": False}
        resp = self.client.get(f"{self.base_url}/markets", params=params)
        resp.raise_for_status()
        data = resp.json()
        out: list[Market] = []
        for row in data:
            status = str(row.get("status") or "open").lower()
            if status in {"closed", "resolved", "paused"}:
                continue
            liq = float(row.get("liquidity", 0) or 0)
            if liq < 100:
                continue
            outcomes = [Outcome(name=o.get("name", ""), token_id=str(o.get("token_id", ""))) for o in row.get("outcomes", []) if o.get("token_id")]
            if len(outcomes) < 2:
                continue
            out.append(Market(
                market_id=str(row.get("id")),
                event_id=str(row.get("event_id")) if row.get("event_id") else None,
                question=str(row.get("question", "")),
                slug=row.get("slug"),
                outcomes=outcomes,
                end_date=isoparse(row["end_date_iso"]) if row.get("end_date_iso") else None,
                volume=float(row.get("volume", 0) or 0),
                liquidity=liq,
                tags=[str(t) for t in row.get("tags", [])],
                status=status,
            ))
        return out
