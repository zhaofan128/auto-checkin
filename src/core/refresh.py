"""Refresh single-flight with per-account lock and generation CAS."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field, replace
from typing import Callable

from .errors import (
    LockTimeout,
    SecretMissing,
    SecretWritebackFailed,
    StateConflict,
)
from .models import AccountRef, RotationResult
from .secrets import GitHubSecrets, SecretResolver, SecretSpec
from .state import AccountStateStore, utc_now_iso


@dataclass(frozen=True)
class RefreshOutcome:
    changed: bool
    generation: int
    secret_version: str | None
    skipped_reason: str | None = None


@dataclass
class _Flight:
    event: threading.Event = field(default_factory=threading.Event)
    outcome: RefreshOutcome | None = None
    error: BaseException | None = None


class RefreshCoordinator:
    """Guarantees at most one refresh in flight per account.

    In-process callers share a single flight. Cross-process callers serialize
    on a per-account file lock and re-check the state generation before writing.
    """

    def __init__(
        self,
        state: AccountStateStore,
        secrets: SecretResolver,
        github: GitHubSecrets,
    ) -> None:
        self.state = state
        self.secrets = secrets
        self.github = github
        self._guard = threading.Lock()
        self._inflight: dict[str, _Flight] = {}

    def refresh(
        self,
        account: AccountRef,
        spec: SecretSpec,
        refresh_fn: Callable[[str], RotationResult],
        *,
        timeout_s: float = 90.0,
        expected_generation: int | None = None,
        force: bool = False,
    ) -> RefreshOutcome:
        key = account.account_key
        with self._guard:
            flight = self._inflight.get(key)
            if flight is None:
                flight = _Flight()
                self._inflight[key] = flight
                leader = True
            else:
                leader = False

        if not leader:
            if not flight.event.wait(timeout=timeout_s):
                raise LockTimeout(f"等待同账户刷新超时: {key}")
            if flight.error is not None:
                raise flight.error
            if flight.outcome is None:
                raise LockTimeout(f"同账户刷新未返回结果: {key}")
            return flight.outcome

        try:
            outcome = self._do_refresh(
                account,
                spec,
                refresh_fn,
                timeout_s=timeout_s,
                expected_generation=expected_generation,
                force=force,
            )
            flight.outcome = outcome
            return outcome
        except BaseException as exc:
            flight.error = exc
            raise
        finally:
            flight.event.set()
            with self._guard:
                self._inflight.pop(key, None)

    def _do_refresh(
        self,
        account: AccountRef,
        spec: SecretSpec,
        refresh_fn: Callable[[str], RotationResult],
        *,
        timeout_s: float,
        expected_generation: int | None,
        force: bool,
    ) -> RefreshOutcome:
        with self.state.lock(account, timeout_s=timeout_s):
            current = self.state.load(account)
            if expected_generation is not None and current.generation != expected_generation:
                return RefreshOutcome(
                    changed=False,
                    generation=current.generation,
                    secret_version=current.secret_version,
                )

            resolved = self.secrets.resolve(spec)
            if resolved is None:
                names = ", ".join(spec.candidates())
                raise SecretMissing(f"缺少 Secret 键: {names}")

            current_version = self.github.get_secret_updated_at(resolved.source_key)
            if (
                not force
                and current.secret_version
                and current_version
                and current.secret_version != current_version
            ):
                # Another process already rotated the secret; do not refresh again.
                return RefreshOutcome(
                    changed=False,
                    generation=current.generation,
                    secret_version=current.secret_version,
                )

            if not self.github.can_write():
                return RefreshOutcome(
                    changed=False,
                    generation=current.generation,
                    secret_version=current.secret_version,
                    skipped_reason="secret_writeback_unavailable",
                )

            rotation = refresh_fn(resolved.value)
            if rotation is None:
                return RefreshOutcome(
                    changed=False,
                    generation=current.generation,
                    secret_version=current.secret_version,
                )

            writeback = self.secrets.write_back(spec, rotation.new_value, resolved.source_key)
            if not writeback.ok:
                if writeback.error == "secret_writeback_unavailable":
                    return RefreshOutcome(
                        changed=False,
                        generation=current.generation,
                        secret_version=current.secret_version,
                        skipped_reason="secret_writeback_unavailable",
                    )
                raise SecretWritebackFailed(writeback.error or "secret_writeback_failed")

            new_state = replace(
                current,
                generation=current.generation + 1,
                secret_version=writeback.updated_at,
                updated_at=utc_now_iso(),
            )
            try:
                self.state.save(new_state, expected_generation=current.generation)
            except StateConflict:
                latest = self.state.load(account)
                return RefreshOutcome(
                    changed=False,
                    generation=latest.generation,
                    secret_version=latest.secret_version,
                )
            return RefreshOutcome(
                changed=True,
                generation=new_state.generation,
                secret_version=new_state.secret_version,
            )
