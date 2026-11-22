"""Per-account state storage with atomic writes and generation CAS."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime, timezone
from pathlib import Path

from .errors import StateConflict, StateCorrupt
from .locks import FileLock
from .models import AccountRef


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class AccountState:
    schema_version: int
    account_key: str
    platform: str
    account_label: str
    generation: int
    secret_version: str | None
    last_run_id: str | None
    last_checkin_status: str | None
    last_points_gained: float | None
    last_points_current: float | None
    last_points_unit: str | None
    last_points_source: str | None
    last_success_at: str | None
    last_error_type: str | None
    updated_at: str


def default_state(account: AccountRef) -> AccountState:
    return AccountState(
        schema_version=1,
        account_key=account.account_key,
        platform=account.platform,
        account_label=account.account_label,
        generation=0,
        secret_version=None,
        last_run_id=None,
        last_checkin_status=None,
        last_points_gained=None,
        last_points_current=None,
        last_points_unit=None,
        last_points_source=None,
        last_success_at=None,
        last_error_type=None,
        updated_at=utc_now_iso(),
    )


def _safe_key(account: AccountRef) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", account.account_key)


def _group(account: AccountRef) -> str:
    return account.account_key.split(":", 1)[0] or account.platform


class AccountLock(FileLock):
    """A file lock scoped to a single account key."""


class AccountStateStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def path_for(self, account: AccountRef) -> Path:
        return self.root / _group(account) / f"{_safe_key(account)}.json"

    def lock(self, account: AccountRef, *, timeout_s: float = 30.0) -> AccountLock:
        path = self.root / ".locks" / f"{_safe_key(account)}.lock"
        return AccountLock(path, timeout_s=timeout_s)

    def load(self, account: AccountRef) -> AccountState:
        path = self.path_for(account)
        if not path.exists():
            return default_state(account)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StateCorrupt(f"状态文件损坏: {path}") from exc
        if not isinstance(raw, dict):
            raise StateCorrupt(f"状态文件格式错误: {path}")
        base = asdict(default_state(account))
        allowed = {item.name for item in fields(AccountState)}
        base.update({key: value for key, value in raw.items() if key in allowed})
        return AccountState(**base)

    def save(self, state: AccountState, *, expected_generation: int | None = None) -> None:
        account = self._account_from_state(state)
        if expected_generation is not None:
            current = self.load(account)
            if current.generation != expected_generation:
                raise StateConflict(
                    f"状态 generation 冲突: expected={expected_generation}, actual={current.generation}"
                )

        path = self.path_for(account)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(asdict(state), handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    def bump_generation(self, account: AccountRef, *, expected_generation: int) -> AccountState:
        current = self.load(account)
        if current.generation != expected_generation:
            raise StateConflict(
                f"状态 generation 冲突: expected={expected_generation}, actual={current.generation}"
            )
        updated = replace(current, generation=current.generation + 1, updated_at=utc_now_iso())
        self.save(updated, expected_generation=expected_generation)
        return updated

    @staticmethod
    def _account_from_state(state: AccountState) -> AccountRef:
        account_id = state.account_key.split(":", 1)[-1] if ":" in state.account_key else state.platform
        return AccountRef(
            platform=state.platform,
            platform_name=state.platform,
            account_id=account_id,
            account_key=state.account_key,
            account_label=state.account_label,
        )
