from __future__ import annotations

import typer

from .arb_scanner import scan_market_for_arb
from .clob_client import ClobClient
from .config import get_settings
from .executor import Executor
from .gamma_client import GammaClient
from .notifications import notify_console
from .storage import init_db

app = typer.Typer(help="Polymarket arbitrage and wallet intelligence bot")


@app.command("scan-markets")
def scan_markets() -> None:
    s = get_settings()
    gamma = GammaClient(s.gamma_api_base)
    markets = gamma.fetch_active_markets()
    notify_console(f"fetched {len(markets)} markets")


@app.command("scan-arb")
def scan_arb() -> None:
    s = get_settings()
    gamma = GammaClient(s.gamma_api_base)
    clob = ClobClient(s.clob_api_base)
    executor = Executor(s)
    markets = gamma.fetch_active_markets()
    for m in markets[:100]:
        books = {o.token_id: clob.get_orderbook(o.token_id) for o in m.outcomes}
        opps = scan_market_for_arb(m, books, s)
        for opp in opps:
            notify_console(f"opportunity: {opp.market_id} net_edge={opp.net_edge:.4f}")
            notify_console(executor.execute(opp))


@app.command("dry-run")
def dry_run() -> None:
    scan_arb()


@app.command("live-run")
def live_run() -> None:
    s = get_settings()
    if not s.live_trading:
        raise typer.BadParameter("LIVE_TRADING must be true to run live-run")
    scan_arb()


@app.command("init-db")
def init_db_cmd() -> None:
    init_db(get_settings().database_url)


if __name__ == "__main__":
    app()
