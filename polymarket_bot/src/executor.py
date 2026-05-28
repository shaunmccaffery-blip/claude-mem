from __future__ import annotations

from .config import Settings
from .market_models import Opportunity
from .risk import kill_switch_triggered


class Executor:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def execute(self, opp: Opportunity) -> str:
        if kill_switch_triggered(self.settings):
            return "kill_switch_triggered"
        if self.settings.dry_run or not self.settings.live_trading:
            return f"dry_run_only: {opp.market_id}"
        if not self.settings.private_key:
            return "live_trading_enabled_but_missing_private_key"
        return f"live_execution_not_implemented_safely_yet: {opp.market_id}"
