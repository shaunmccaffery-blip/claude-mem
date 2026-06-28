#!/usr/bin/env python3
"""
CLI tying together Bybit (exchange) + Nansen (on-chain analytics).

All credentials come from env (.env, gitignored). Examples:
    python3 crypto_cli.py ticker BTCUSDT
    python3 crypto_cli.py balance
    python3 crypto_cli.py size --bankroll 5000 --edge 0.08 --odds 1.0
    python3 crypto_cli.py nansen smart-money --chain ethereum
"""

from __future__ import annotations

import argparse
import json
import sys

from trading_common import fractional_kelly_size, setup_logging


def cmd_ticker(args: argparse.Namespace) -> int:
    from bybit_client import BybitClient

    client = BybitClient()
    result = client.get_tickers(category=args.category, symbol=args.symbol)
    print(json.dumps(result, indent=2))
    return 0


def cmd_balance(args: argparse.Namespace) -> int:
    from bybit_client import BybitClient

    client = BybitClient()
    result = client.get_wallet_balance(account_type=args.account_type)
    # Compact summary of coin balances.
    for acct in result.get("list", []):
        print(f"account: {acct.get('accountType')}  equity: {acct.get('totalEquity')}")
        for coin in acct.get("coin", []):
            print(f"  {coin.get('coin'):>6}  bal={coin.get('walletBalance')}")
    return 0


def cmd_size(args: argparse.Namespace) -> int:
    usd = fractional_kelly_size(
        bankroll_usd=args.bankroll,
        edge=args.edge,
        odds=args.odds,
        kelly_fraction=args.kelly_fraction,
        max_position_pct=args.max_position_pct,
    )
    print(f"suggested position: ${usd}")
    return 0


def cmd_nansen(args: argparse.Namespace) -> int:
    from nansen_client import NansenClient

    client = NansenClient()
    if args.nansen_cmd == "screener":
        result = client.token_screener(
            chains=args.chains,
            timeframe=args.timeframe,
            only_smart_money=not args.all,
            order_by_field=args.order_by,
            per_page=args.per_page,
        )
        print(json.dumps(result, indent=2))
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    from crypto_strategy import review_log

    rows = review_log(path=args.log)
    if not rows:
        print(f"no logged picks found in {args.log}")
        return 0
    for r in rows:
        print(
            f"{r['ts'][:19]}  {r['side'].upper():>4} {r['symbol']:<12} "
            f"entry={r['entry_price']}  now={r['now_price']}  "
            f"return={r['return_pct']:+.2f}%"
        )
    returns = [r["return_pct"] for r in rows]
    wins = sum(1 for x in returns if x > 0)
    print(
        f"\n{len(returns)} picks | avg return {sum(returns)/len(returns):+.2f}% "
        f"| win rate {wins}/{len(returns)} ({100*wins/len(returns):.0f}%)"
    )
    print("(hypothetical — no money traded)")
    return 0


def cmd_signal(args: argparse.Namespace) -> int:
    from crypto_strategy import generate_proposals, place_proposals, log_proposals

    proposals = generate_proposals(
        bankroll_usd=args.bankroll,
        chains=args.chains,
        timeframe=args.timeframe,
        only_smart_money=not args.all,
        edge_per_signal=args.edge,
        kelly_fraction=args.kelly_fraction,
        max_position_pct=args.max_position_pct,
        top_n=args.top,
        use_claude=args.claude,
        min_confidence=args.min_confidence,
        full_send_confidence=args.full_send_confidence,
        all_in=args.all_in,
        allow_shorts=args.shorts,
        use_market_data=args.market,
    )
    if not proposals:
        print("no tradable proposals")
        return 0
    for p in proposals:
        line = (
            f"{p.side.upper():>4} {p.token:>8} -> {p.bybit_symbol:<12} "
            f"netflow={p.netflow}  px={p.last_price}  size=${p.suggested_usd}"
        )
        claude = p.extras.get("claude")
        if claude:
            line += f"  [claude {claude['confidence']:.2f}: {claude['rationale']}]"
        print(line)

    if not args.no_log:
        path = log_proposals(proposals, path=args.log)
        print(f"\nlogged {len(proposals)} picks to {path}")

    if not args.execute:
        print("\n(proposals only — no orders placed. Add --execute to trade.)")
        return 0

    # --- live execution path (double-gated) ---
    import os

    if os.getenv("BYBIT_EXECUTION_ENABLED", "false").lower() != "true":
        print(
            "\n--execute given but BYBIT_EXECUTION_ENABLED is not 'true' in .env.\n"
            "Orders will be DRY-RUN only (nothing placed). Set it to true to go live."
        )
    else:
        print(
            f"\n⚠️  About to place {len(proposals)} REAL orders with REAL money "
            f"on {'TESTNET' if os.getenv('BYBIT_TESTNET','true').lower()!='false' else 'MAINNET'}."
        )
        if not args.yes:
            confirm = input("Type 'yes' to confirm: ").strip().lower()
            if confirm != "yes":
                print("Aborted — no orders placed.")
                return 0

    results = place_proposals(
        proposals, leverage=args.leverage, tp_pct=args.tp, sl_pct=args.sl
    )
    print(json.dumps(results, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Bybit + Nansen crypto CLI")
    sub = p.add_subparsers(dest="command", required=True)

    t = sub.add_parser("ticker", help="Bybit ticker")
    t.add_argument("symbol")
    t.add_argument("--category", default="linear")
    t.set_defaults(func=cmd_ticker)

    b = sub.add_parser("balance", help="Bybit wallet balance")
    b.add_argument("--account-type", default="UNIFIED")
    b.set_defaults(func=cmd_balance)

    s = sub.add_parser("size", help="Fractional-Kelly position size")
    s.add_argument("--bankroll", type=float, required=True)
    s.add_argument("--edge", type=float, required=True)
    s.add_argument("--odds", type=float, default=1.0)
    s.add_argument("--kelly-fraction", type=float, default=0.25)
    s.add_argument("--max-position-pct", type=float, default=0.25)
    s.set_defaults(func=cmd_size)

    n = sub.add_parser("nansen", help="Nansen on-chain analytics")
    nsub = n.add_subparsers(dest="nansen_cmd", required=True)
    sc = nsub.add_parser("screener", help="Token screener by smart-money flow")
    sc.add_argument("--chains", nargs="+", default=["ethereum", "solana", "base"])
    sc.add_argument("--timeframe", default="24h")
    sc.add_argument("--order-by", default="netflow")
    sc.add_argument("--per-page", type=int, default=100)
    sc.add_argument("--all", action="store_true", help="Include non-smart-money")
    n.set_defaults(func=cmd_nansen)

    sg = sub.add_parser("signal", help="Nansen->Bybit sized proposals (dry, no orders)")
    sg.add_argument("--bankroll", type=float, required=True)
    sg.add_argument("--chains", nargs="+", default=["ethereum", "solana", "base"])
    sg.add_argument("--timeframe", default="24h")
    sg.add_argument("--edge", type=float, default=0.05)
    sg.add_argument("--kelly-fraction", type=float, default=0.25)
    sg.add_argument("--max-position-pct", type=float, default=0.25)
    sg.add_argument("--top", type=int, default=10)
    sg.add_argument("--all", action="store_true", help="Include non-smart-money")
    sg.add_argument("--shorts", action="store_true", help="Also short net-outflow tokens")
    sg.add_argument("--market", action="store_true", help="Enrich with CoinGecko/CMC/TradingView/LunarCrush")
    sg.add_argument("--claude", action="store_true", help="Filter candidates with the Claude analyst")
    sg.add_argument("--min-confidence", type=float, default=0.6, help="Min Claude confidence to keep")
    sg.add_argument("--execute", action="store_true", help="Place orders (needs BYBIT_EXECUTION_ENABLED=true)")
    sg.add_argument("--leverage", type=int, default=10, help="Contract leverage to set per symbol")
    sg.add_argument("--tp", type=float, default=20.0, help="Take-profit %% price move")
    sg.add_argument("--sl", type=float, default=10.0, help="Stop-loss %% price move")
    sg.add_argument("--full-send-confidence", type=float, default=1.1,
                    help="If a pick's Claude confidence >= this, bet the entire bankroll on it (default 1.1 = off)")
    sg.add_argument("--all-in", action="store_true",
                    help="Put the full bankroll on each pick (use with --top 1; no Claude needed)")
    sg.add_argument("--yes", action="store_true", help="Skip the live-order confirmation prompt")
    sg.add_argument("--log", default="logs/signals.jsonl", help="JSONL file to append picks to")
    sg.add_argument("--no-log", action="store_true", help="Don't log this run")
    sg.set_defaults(func=cmd_signal)

    rv = sub.add_parser("review", help="Re-price logged picks vs current price (paper P&L)")
    rv.add_argument("--log", default="logs/signals.jsonl", help="JSONL file to review")
    rv.set_defaults(func=cmd_review)

    return p


def main() -> int:
    logger = setup_logging("crypto_cli")
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except Exception as exc:  # surface a clean error, not a traceback
        logger.error("%s: %s", type(exc).__name__, exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
