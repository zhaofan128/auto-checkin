"""Dual append-only logging: events.jsonl (source of truth) and run.log (readable)."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from zoneinfo import ZoneInfo

    _TZ = ZoneInfo("Asia/Shanghai")
except Exception:  # pragma: no cover - minimal environments
    _TZ = timezone(timedelta(hours=8))

from .models import AccountRef, CheckinEvent, CheckinResult, PointsResult, RunReport
from .redact import mask_account, redact_text, redact_turnstile


def now_shanghai() -> datetime:
    return datetime.now(_TZ)


def new_run_id(clock: Callable[[], datetime] | None = None) -> str:
    stamp = (clock or now_shanghai)().strftime("%Y%m%dT%H%M%S")
    return f"{stamp}-{uuid.uuid4().hex[:6]}"


def sanitize_event(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result["account"] = mask_account(str(result.get("account") or ""))
    result["message"] = redact_text(str(result.get("message") or ""))
    if result.get("error_detail") is not None:
        result["error_detail"] = redact_text(str(result["error_detail"]))
    if result.get("turnstile") is not None:
        result["turnstile"] = redact_turnstile(result["turnstile"])
    return result


class EventLogger:
    def __init__(
        self,
        history_dir: Path,
        run_id: str,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.history_dir = Path(history_dir)
        self.run_id = run_id
        self.events_path = self.history_dir / "events.jsonl"
        self.run_log_path = self.history_dir / "run.log"
        self.last_errors: list[str] = []
        self._clock = clock or now_shanghai
        self._lock = threading.Lock()

    def emit(self, event: CheckinEvent) -> None:
        payload = sanitize_event(event.to_dict())
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self._safe_append(self.events_path, line)

    def account_result(
        self,
        account: AccountRef,
        result: CheckinResult,
        *,
        run_profile: str,
        attempt: int = 1,
    ) -> None:
        points = result.points or PointsResult(
            gained=None,
            current=None,
            unit=None,
            source="api_unavailable",
            message="平台未返回积分结果",
        )
        message = result.message
        if points.message and points.message not in message:
            message = f"{message}；{points.message}"
        event = CheckinEvent(
            schema_version=1,
            timestamp=self._clock().isoformat(timespec="seconds"),
            run_id=self.run_id,
            platform=account.platform,
            platform_name=account.platform_name,
            account=mask_account(account.account_label or account.account_id),
            account_key=account.account_key,
            checkin_status=result.status,
            points_gained=points.gained,
            points_current=points.current,
            points_unit=points.unit,
            points_source=points.source,
            message=redact_text(message),
            error_type=result.error_type,
            error_detail=redact_text(result.error_detail) if result.error_detail else None,
            duration_ms=result.duration_ms,
            run_profile=run_profile,
            attempt=attempt,
            manual_required=result.manual_required,
            skipped_reason=result.skipped_reason,
            turnstile=redact_turnstile(result.turnstile),
        )
        self.emit(event)

    def summary(self, report: RunReport) -> None:
        labels = {
            "success": "成功",
            "already_checked": "已签到",
            "failed": "失败",
            "skipped": "跳过",
            "unknown": "未知",
        }
        parts = [
            f"{item.account.platform}:{labels.get(item.result.status, item.result.status)}"
            for item in report.results
        ]
        line = f"{self._clock().isoformat(timespec='seconds')} | " + " ".join(parts)
        counts = report.counts
        counts_line = " ".join(
            f"{key}={counts[key]}"
            for key in ("success", "already_checked", "failed", "skipped", "unknown")
        )
        with self._lock:
            self._safe_append(self.run_log_path, line)
            try:
                (self.history_dir / "last-summary.txt").write_text(
                    counts_line + "\n", encoding="utf-8"
                )
            except Exception as exc:  # noqa: BLE001 - logging must never block check-in
                self.last_errors.append(f"last-summary.txt: {exc}")

    def read_events(self) -> list[dict[str, Any]]:
        if not self.events_path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in self.events_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
        return events

    def _safe_append(self, path: Path, text: str) -> None:
        try:
            self._append_text(path, text)
        except Exception as exc:  # noqa: BLE001 - logging must never block check-in
            self.last_errors.append(f"{path.name}: {exc}")

    def _append_text(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
        try:
            os.write(fd, (text.rstrip("\n") + "\n").encode("utf-8"))
        finally:
            os.close(fd)
