from __future__ import annotations

from pathlib import Path

from .config import Settings


def kill_switch_triggered(settings: Settings) -> bool:
    return Path(settings.kill_switch_file).exists()


def validate_risk_limits(settings: Settings, current_exposure: float, daily_loss: float, position_size: float) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if current_exposure + position_size > settings.max_total_exposure:
        issues.append("max_total_exposure breached")
    if position_size > settings.max_position_per_market:
        issues.append("max_position_per_market breached")
    if daily_loss <= -settings.max_daily_loss:
        issues.append("max_daily_loss breached")
    return (len(issues) == 0, issues)
