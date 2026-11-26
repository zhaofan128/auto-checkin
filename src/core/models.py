"""Shared dataclasses for the unified check-in core."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

CheckinStatus = Literal["success", "already_checked", "failed", "skipped", "unknown"]
PointsSource = Literal[
    "api_field",
    "diff_before_after",
    "api_unavailable",
    "idempotent_reset",
    "turnstile_unavailable",
]


@dataclass(frozen=True)
class AccountRef:
    platform: str
    platform_name: str
    account_id: str
    account_key: str
    account_label: str
    enabled: bool = True


@dataclass(frozen=True)
class PointsResult:
    gained: int | float | None
    current: int | float | None
    unit: str | None
    source: PointsSource
    message: str | None = None
    gained_source: str | None = None


@dataclass
class CheckinResult:
    status: CheckinStatus
    message: str
    points: PointsResult | None = None
    error_type: str | None = None
    error_detail: str | None = None
    duration_ms: int = 0
    manual_required: bool = False
    skipped_reason: str | None = None
    turnstile: dict[str, Any] | None = None


@dataclass(frozen=True, repr=False)
class RotationResult:
    new_value: str
    reason: str

    def __repr__(self) -> str:
        return f"RotationResult(new_value=<redacted>, reason={self.reason!r})"


@dataclass(frozen=True)
class CheckinEvent:
    schema_version: int
    timestamp: str
    run_id: str
    platform: str
    platform_name: str
    account: str
    account_key: str
    checkin_status: CheckinStatus
    points_gained: int | float | None
    points_current: int | float | None
    points_unit: str | None
    points_source: PointsSource
    message: str
    error_type: str | None
    error_detail: str | None
    duration_ms: int
    run_profile: str
    attempt: int = 1
    manual_required: bool = False
    skipped_reason: str | None = None
    turnstile: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AccountResult:
    account: AccountRef
    result: CheckinResult


_TRANSIENT_PATTERN = re.compile(
    r"HTTP\s*5\d{2}|error code:\s*5\d{2}|网络请求失败|timed?\s*out|timeout",
    re.IGNORECASE,
)


def is_transient_failure(result: CheckinResult) -> bool:
    """上游 5xx / 网络超时属于临时故障，不应让整次任务失败（后续定时任务会自动重试）。"""

    if result.status != "failed":
        return False
    if result.error_type == "transient_error":
        return True
    text = f"{result.message or ''} {result.error_detail or ''}"
    return bool(_TRANSIENT_PATTERN.search(text))


@dataclass
class RunReport:
    run_id: str
    profile: str
    results: list[AccountResult] = field(default_factory=list)
    duration_ms: int = 0

    @property
    def counts(self) -> dict[str, int]:
        counts = {key: 0 for key in ("success", "already_checked", "failed", "skipped", "unknown")}
        for item in self.results:
            counts[item.result.status] = counts.get(item.result.status, 0) + 1
        return counts

    @property
    def transient_failed(self) -> int:
        return sum(1 for item in self.results if is_transient_failure(item.result))

    @property
    def skipped_reasons(self) -> dict[str, int]:
        reasons: dict[str, int] = {}
        for item in self.results:
            reason = item.result.skipped_reason
            if reason:
                reasons[reason] = reasons.get(reason, 0) + 1
        return reasons

    @property
    def failed(self) -> bool:
        return self.counts.get("failed", 0) > 0

    @property
    def exit_code(self) -> int:
        blocking = self.counts.get("failed", 0) - self.transient_failed
        return 1 if blocking > 0 else 0
