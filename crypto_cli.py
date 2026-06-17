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
    if args.nansen_cmd == "smart-money":
        print(json.dumps(client.smart_money_holdings(chain=args.chain), indent=2))
    elif args.nansen_cmd == "flows":
        print(json.dumps(client.token_flows(args.token, chain=args.chain), indent=2))
    elif args.nansen_cmd == "pnl":
        print(json.dumps(client.wallet_pnl(args.address, chain=args.chain), indent=2))
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
    sm = nsub.add_parser("smart-money")
    sm.add_argument("--chain", default="ethereum")
    fl = nsub.add_parser("flows")
    fl.add_argument("token")
    fl.add_argument("--chain", default="ethereum")
    pn = nsub.add_parser("pnl")
    pn.add_argument("address")
    pn.add_argument("--chain", default="ethereum")
    n.set_defaults(func=cmd_nansen)

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
