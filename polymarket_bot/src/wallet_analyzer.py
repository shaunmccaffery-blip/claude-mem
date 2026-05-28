from __future__ import annotations

import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

from .market_models import WalletScore, WalletTrade


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def score_wallet(trades: list[WalletTrade]) -> WalletScore:
    wallet = trades[0].wallet if trades else "unknown"
    pnls = [t.pnl or 0.0 for t in trades]
    realized = sum((t.pnl or 0.0) for t in trades if t.resolved)
    unrealized = sum((t.pnl or 0.0) for t in trades if not t.resolved)
    volume = sum(t.price * t.size for t in trades)
    wins = [p for p in pnls if p > 0]
    losses = [abs(p) for p in pnls if p < 0]
    rois = [((t.pnl or 0.0) / (t.price * t.size)) for t in trades if t.price * t.size > 0]
    pnl_top_trade_pct = _safe_div(max(pnls) if pnls else 0.0, realized if realized else 1.0)
    copyworthiness = (
        realized * 0.25 + _safe_div(len(wins), len(trades)) * 25 - (max(losses) if losses else 0) * 0.05
        + len({t.market_id for t in trades}) * 0.5 - max(0.0, pnl_top_trade_pct - 0.5) * 20
    )
    return WalletScore(
        wallet=wallet,
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        total_volume=volume,
        resolved_markets=len({t.market_id for t in trades if t.resolved}),
        win_rate=_safe_div(len(wins), len(trades)),
        avg_roi=statistics.mean(rois) if rois else 0.0,
        median_roi=statistics.median(rois) if rois else 0.0,
        profit_factor=_safe_div(sum(wins), sum(losses)),
        max_drawdown=max(losses) if losses else 0.0,
        stability_score=1.0 / (statistics.pstdev(rois) + 1e-6) if len(rois) > 2 else 0.0,
        avg_hold_hours=0.0,
        market_diversity=len({t.market_id for t in trades}),
        category_concentration=0.0,
        pnl_top_trade_pct=pnl_top_trade_pct,
        pnl_unresolved_pct=_safe_div(unrealized, realized + unrealized if realized + unrealized else 1.0),
        entry_timing_score=0.0,
        copy_lag_sensitivity=0.0,
        suspicious_activity_score=0.0,
        copyworthiness=copyworthiness,
    )


def rank_wallets(wallet_trades: list[WalletTrade], out_dir: str) -> list[WalletScore]:
    grouped: dict[str, list[WalletTrade]] = defaultdict(list)
    for trade in wallet_trades:
        grouped[trade.wallet].append(trade)
    scores = sorted((score_wallet(v) for v in grouped.values()), key=lambda x: x.copyworthiness, reverse=True)

    p = Path(out_dir)
    p.mkdir(parents=True, exist_ok=True)
    with (p / "ranked_wallets.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(scores[0].model_dump().keys()) if scores else ["wallet"])
        writer.writeheader()
        for s in scores:
            writer.writerow(s.model_dump())
    (p / "wallet_report.json").write_text(json.dumps([s.model_dump() for s in scores], indent=2))
    (p / "top_wallets.md").write_text("\n".join([f"- {s.wallet}: {s.copyworthiness:.2f}" for s in scores[:10]]))
    return scores
