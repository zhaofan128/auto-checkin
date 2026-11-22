"""Points normalization.

The core never invents points. Unknown stays null and is labelled
api_unavailable with an explanatory message.
"""

from __future__ import annotations

from .models import PointsResult, PointsSource

Number = int | float


def _number(value: Number | None, field_name: str) -> Number | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a number or None")
    return value


def normalize_points(
    *,
    gained: Number | None,
    current: Number | None,
    unit: str | None,
    current_before: Number | None = None,
    current_after: Number | None = None,
    explicit_source: PointsSource | None = None,
    message: str | None = None,
) -> PointsResult:
    gained_value = _number(gained, "gained")
    current_value = _number(current, "current")
    before_value = _number(current_before, "current_before")
    after_value = _number(current_after, "current_after")
    normalized_unit = (unit or "").strip() or None

    if current_value is None and after_value is not None:
        current_value = after_value

    gained_source: str | None = None
    computed_by_diff = False
    if gained_value is not None:
        gained_source = explicit_source or "api_field"
    elif current_value is not None and before_value is not None:
        gained_value = current_value - before_value
        gained_source = "diff_before_after"
        computed_by_diff = True

    if current_value is None:
        source: PointsSource = explicit_source or "api_unavailable"
        reason = message or "平台未提供当前积分接口"
    elif computed_by_diff:
        source = "diff_before_after"
        reason = message
    elif gained_value is not None:
        source = explicit_source or "api_field"
        reason = message
    else:
        # Current points are available from an API field; only the gain is unknown.
        source = explicit_source or "api_field"
        reason = message or "平台未提供本次获得积分"

    return PointsResult(
        gained=gained_value,
        current=current_value,
        unit=normalized_unit,
        source=source,
        message=reason,
        gained_source=gained_source,
    )
