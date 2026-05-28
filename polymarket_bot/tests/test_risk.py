from src.config import Settings
from src.risk import validate_risk_limits


def test_risk_limits_breach():
    s = Settings(max_total_exposure=100)
    ok, issues = validate_risk_limits(s, 90, 0, 20)
    assert not ok
    assert issues
