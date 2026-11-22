from src.core.points import normalize_points


def test_api_field_points():
    result = normalize_points(gained=100, current=1200, unit="credits")
    assert result.gained == 100
    assert result.current == 1200
    assert result.unit == "credits"
    assert result.source == "api_field"


def test_diff_before_after_points():
    result = normalize_points(gained=None, current=None, unit="points", current_before=100, current_after=150)
    assert result.gained == 50
    assert result.current == 150
    assert result.source == "diff_before_after"


def test_unavailable_current_points():
    result = normalize_points(gained=None, current=None, unit=None, message="无积分接口")
    assert result.current is None
    assert result.source == "api_unavailable"
    assert result.message == "无积分接口"


def test_missing_gained_is_not_zero():
    result = normalize_points(gained=None, current=500, unit="quota")
    assert result.gained is None
    assert result.current == 500
    assert result.source == "api_field"
    assert result.message == "平台未提供本次获得积分"


def test_zero_gained_is_preserved():
    result = normalize_points(gained=0, current=0, unit="credits")
    assert result.gained == 0
    assert result.source == "api_field"


def test_unit_is_not_invented():
    result = normalize_points(gained=10, current=20, unit=None)
    assert result.unit is None


def test_idempotent_reset_source_is_supported():
    result = normalize_points(
        gained=None,
        current=None,
        unit="credits",
        explicit_source="idempotent_reset",
        message="alreadyProcessed:额度已重置，未返回本次 gained",
    )
    assert result.gained is None
    assert result.current is None
    assert result.source == "idempotent_reset"
