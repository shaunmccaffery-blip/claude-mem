from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    dry_run: bool = True
    live_trading: bool = False
    min_net_edge: float = 0.01
    min_trade_size: float = 20.0
    safety_buffer: float = 0.003
    estimated_fees: float = 0.002
    estimated_slippage: float = 0.003
    max_position_per_market: float = 200.0
    max_daily_loss: float = 100.0
    max_total_exposure: float = 1000.0
    kill_switch_file: str = "./KILL_SWITCH"
    database_url: str = "./bot.db"

    gamma_api_base: str = "https://gamma-api.polymarket.com"
    clob_api_base: str = "https://clob.polymarket.com"

    bitquery_api_key: str = ""
    dune_api_key: str = ""
    polygon_rpc_url: str = ""
    private_key: str = ""
    telegram_bot_token: str = ""
    discord_webhook_url: str = ""


def get_settings() -> Settings:
    return Settings()
