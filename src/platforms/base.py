"""Adapter interfaces. No concrete platform implementations live here."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from src.core.http import HttpClient
from src.core.logging import EventLogger
from src.core.models import AccountRef, CheckinResult, PointsResult, RotationResult
from src.core.secrets import SecretResolver, SecretSpec
from src.core.state import AccountStateStore


@dataclass(frozen=True, repr=False)
class Credentials:
    raw: str
    source_key: str
    data: Mapping[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"Credentials(source_key={self.source_key!r}, present={bool(self.raw)})"


@dataclass(frozen=True)
class AccountSpec:
    platform: str
    platform_name: str
    account_id: str
    account_key: str
    secret_specs: tuple[SecretSpec, ...] = ()
    rolling: bool = False
    schedule_profiles: frozenset[str] = frozenset({"manual"})
    enabled_flag: str | None = None
    account_label: str | None = None


@dataclass
class AccountContext:
    run_id: str
    profile: str
    account: AccountRef
    http: HttpClient
    secrets: SecretResolver
    state: AccountStateStore
    logger: EventLogger
    dry_run: bool = False
    force: bool = False


class AccountAdapter(Protocol):
    account: AccountRef

    def resolve_credentials(self, ctx: AccountContext) -> Credentials: ...

    def refresh(self, ctx: AccountContext, creds: Credentials) -> RotationResult | None: ...

    def checkin(self, ctx: AccountContext, creds: Credentials) -> CheckinResult: ...

    def fetch_points(self, ctx: AccountContext, creds: Credentials) -> PointsResult: ...


class PlatformAdapter(Protocol):
    platform: str
    accounts: tuple[AccountSpec, ...]

    def account_adapter(self, account_id: str) -> AccountAdapter: ...
