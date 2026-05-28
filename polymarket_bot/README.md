# Polymarket Arbitrage + Wallet Intelligence Bot

## ⚠️ Compliance & Risk Warning
Prediction market participation may be restricted in some jurisdictions. Do not bypass geoblocks, sanctions, or platform access controls. Do not use insider information. This software is provided for research/automation with **no profitability guarantees**.

## Design highlights
- Read-only first architecture with `DRY_RUN=true` default.
- Live execution gated by `LIVE_TRADING=true` and `PRIVATE_KEY` env var.
- Uses Gamma public API for market discovery and CLOB public API for order books.
- Modular Python 3.11+ codebase with Pydantic models and Typer CLI.

## Commands
- `polymarket-bot scan-markets`
- `polymarket-bot scan-arb`
- `polymarket-bot dry-run`
- `polymarket-bot live-run`
- `polymarket-bot init-db`

## Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
pytest
```

## Dry-run to live trading switch
1. Keep `DRY_RUN=true`, `LIVE_TRADING=false` while validating logs and opportunity quality.
2. Configure RPC/auth and risk limits.
3. Set `DRY_RUN=false`, `LIVE_TRADING=true`, and provide `PRIVATE_KEY` via environment only.
4. Enable kill switch file monitoring.

## Wallet intelligence outputs
- `sample_output/ranked_wallets.csv`
- `sample_output/wallet_report.json`
- `sample_output/top_wallets.md`
