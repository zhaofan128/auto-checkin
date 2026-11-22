"""Orchestrator for isolated per-account check-ins."""

from __future__ import annotations

import time
from dataclasses import replace

from src.config.registry import PlatformRegistry
from src.config.settings import Settings
from src.core.errors import (
    CheckinError,
    LockTimeout,
    RefreshRequired,
    SecretMissing,
    SecretWritebackFailed,
    SecretWritebackUnavailable,
    StateConflict,
)
from src.core.http import HttpClient
from src.core.logging import EventLogger
from src.core.models import AccountRef, AccountResult, CheckinResult, PointsResult, RunReport
from src.core.refresh import RefreshCoordinator
from src.core.secrets import SecretResolver
from src.core.state import AccountStateStore, utc_now_iso
from src.platforms.base import AccountContext, AccountSpec


class Runner:
    def __init__(
        self,
        registry: PlatformRegistry,
        secrets: SecretResolver,
        state: AccountStateStore,
        logger: EventLogger,
        refresher: RefreshCoordinator,
        http: HttpClient,
        settings: Settings,
    ) -> None:
        self.registry = registry
        self.secrets = secrets
        self.state = state
        self.logger = logger
        self.refresher = refresher
        self.http = http
        self.settings = settings

    def run(
        self,
        *,
        profile: str,
        platforms: set[str] | None = None,
        dry_run: bool = False,
        force: bool = False,
    ) -> RunReport:
        started = time.monotonic()
        report = RunReport(run_id=self.logger.run_id, profile=profile)
        for spec in self.registry.select(profile, platforms):
            account = self._account_from_spec(spec)
            result = self.run_account(account, profile=profile, dry_run=dry_run, force=force)
            self._persist_state(account, result)
            report.results.append(AccountResult(account=account, result=result))
            self.logger.account_result(account, result, run_profile=profile)
        report.duration_ms = int((time.monotonic() - started) * 1000)
        self.logger.summary(report)
        return report

    def run_account(
        self,
        account: AccountRef,
        *,
        profile: str,
        dry_run: bool,
        force: bool,
    ) -> CheckinResult:
        started = time.monotonic()
        spec = self.registry.get_spec(account.account_key)
        adapter = self.registry.adapter_for(account.account_key).account_adapter(account.account_id)
        ctx = AccountContext(
            run_id=self.logger.run_id,
            profile=profile,
            account=account,
            http=self.http,
            secrets=self.secrets,
            state=self.state,
            logger=self.logger,
            dry_run=dry_run,
            force=force,
        )

        try:
            creds = adapter.resolve_credentials(ctx)
            if spec.rolling and spec.secret_specs:
                before = self.state.load(account)
                outcome = self.refresher.refresh(
                    account,
                    spec.secret_specs[0],
                    lambda raw: adapter.refresh(ctx, replace(creds, raw=raw)),
                    timeout_s=self.settings.timeout_s,
                    expected_generation=before.generation,
                )
                if outcome.skipped_reason:
                    return self._skipped(
                        account,
                        outcome.skipped_reason,
                        started,
                        message=(
                            "GH_PAT 不可写，跳过刷新以保护登录态"
                            if outcome.skipped_reason == "secret_writeback_unavailable"
                            else f"跳过刷新: {outcome.skipped_reason}"
                        ),
                        error_type=outcome.skipped_reason,
                    )
                if outcome.changed:
                    creds = adapter.resolve_credentials(ctx)

            result = self._checkin_with_retry(adapter, ctx, creds, account, spec, started)
            result.duration_ms = int((time.monotonic() - started) * 1000)
            if result.points is None:
                try:
                    points = adapter.fetch_points(ctx, creds)
                    if points is not None:
                        result.points = points
                except Exception as exc:  # noqa: BLE001 - points lookup must not lose the check-in result
                    result.points = PointsResult(
                        gained=None,
                        current=None,
                        unit=None,
                        source="api_unavailable",
                        message=f"积分查询失败: {exc}",
                    )
            return result
        except SecretMissing as exc:
            return self._skipped(
                account,
                "secret_missing",
                started,
                message=f"Secret 缺失，未真实探测：{exc}",
                error_type="secret_missing",
            )
        except SecretWritebackUnavailable as exc:
            return self._skipped(
                account,
                "secret_writeback_unavailable",
                started,
                message="GH_PAT 不可写，跳过刷新以保护登录态",
                error_type="secret_writeback_unavailable",
            )
        except SecretWritebackFailed as exc:
            return self._failed(account, "secret_writeback_failed", started, str(exc))
        except LockTimeout as exc:
            return self._failed(account, "lock_timeout", started, str(exc))
        except StateConflict as exc:
            return self._failed(account, "state_conflict", started, str(exc))
        except CheckinError as exc:
            return self._failed(account, getattr(exc, "error_type", "checkin_error"), started, str(exc))
        except Exception as exc:  # noqa: BLE001 - one account must never stop the run
            return self._failed(account, "unknown_error", started, str(exc))

    def _checkin_with_retry(
        self,
        adapter: object,
        ctx: object,
        creds: object,
        account: AccountRef,
        spec: AccountSpec,
        started: float,
    ) -> CheckinResult:
        """Retry once after a cross-process generation race.

        WorkBuddy (and similar adapters) cache the accessToken obtained during
        refresh. If another process won the refresh and this process skipped it,
        checkin raises RefreshRequired. Force one serialized refresh, then retry.
        """

        try:
            return adapter.checkin(ctx, creds)  # type: ignore[attr-defined]
        except RefreshRequired:
            if not (spec.rolling and spec.secret_specs):
                raise
            latest = self.state.load(account)
            outcome = self.refresher.refresh(
                account,
                spec.secret_specs[0],
                lambda raw: adapter.refresh(ctx, replace(creds, raw=raw)),  # type: ignore[attr-defined]
                timeout_s=self.settings.timeout_s,
                expected_generation=latest.generation,
                force=True,
            )
            if outcome.skipped_reason:
                return self._skipped(
                    account,
                    outcome.skipped_reason,
                    started,
                    message=(
                        "GH_PAT 不可写，跳过刷新以保护登录态"
                        if outcome.skipped_reason == "secret_writeback_unavailable"
                        else f"跳过刷新: {outcome.skipped_reason}"
                    ),
                    error_type=outcome.skipped_reason,
                )
            fresh = adapter.resolve_credentials(ctx)  # type: ignore[attr-defined]
            return adapter.checkin(ctx, fresh)  # type: ignore[attr-defined]

    def _persist_state(self, account: AccountRef, result: CheckinResult) -> None:
        """Persist non-sensitive per-account state without touching generation."""

        try:
            with self.state.lock(account, timeout_s=self.settings.timeout_s):
                current = self.state.load(account)
                points = result.points
                now = utc_now_iso()
                updated = replace(
                    current,
                    last_run_id=self.logger.run_id,
                    last_checkin_status=result.status,
                    last_points_gained=points.gained if points else None,
                    last_points_current=points.current if points else None,
                    last_points_unit=points.unit if points else None,
                    last_points_source=points.source if points else None,
                    last_success_at=now
                    if result.status in ("success", "already_checked")
                    else current.last_success_at,
                    last_error_type=result.error_type,
                    updated_at=now,
                )
                self.state.save(updated)
        except Exception as exc:  # noqa: BLE001 - state persistence must not lose the check-in log
            self.logger.last_errors.append(f"state_persist_failed:{type(exc).__name__}")

    @staticmethod
    def _account_from_spec(spec: AccountSpec) -> AccountRef:
        return AccountRef(
            platform=spec.platform,
            platform_name=spec.platform_name,
            account_id=spec.account_id,
            account_key=spec.account_key,
            account_label=spec.account_label or spec.account_id,
        )

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return int((time.monotonic() - started) * 1000)

    def _skipped(
        self,
        account: AccountRef,
        reason: str,
        started: float,
        *,
        message: str,
        error_type: str,
    ) -> CheckinResult:
        return CheckinResult(
            status="skipped",
            message=message,
            error_type=error_type,
            skipped_reason=reason,
            duration_ms=self._elapsed_ms(started),
        )

    def _failed(self, account: AccountRef, error_type: str, started: float, detail: str) -> CheckinResult:
        return CheckinResult(
            status="failed",
            message=f"失败: {detail}",
            error_type=error_type,
            error_detail=detail,
            duration_ms=self._elapsed_ms(started),
        )
