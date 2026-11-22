"""Secret compatibility layer.

Read order: new unified key first, then legacy keys.
Write-back: always keep the legacy key fresh for rollback compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from .errors import SecretMissing


@dataclass(frozen=True)
class SecretSpec:
    logical_name: str
    primary: str
    legacy: tuple[str, ...] = ()
    rolling: bool = False

    def candidates(self) -> tuple[str, ...]:
        return (self.primary, *self.legacy)


@dataclass(frozen=True, repr=False)
class SecretValue:
    value: str
    source_key: str

    def __repr__(self) -> str:
        return f"SecretValue(source_key={self.source_key!r}, present={bool(self.value)})"


@dataclass(frozen=True, repr=False)
class PasswordCredentials:
    username: str
    password: str
    source: str

    def __repr__(self) -> str:
        return f"PasswordCredentials(source={self.source!r}, present=true)"


@dataclass(frozen=True)
class WriteBackResult:
    ok: bool
    primary_key: str
    mirrored_keys: tuple[str, ...] = ()
    updated_at: str | None = None
    error: str | None = None


class GitHubSecrets(Protocol):
    def can_write(self) -> bool: ...

    def set_secret(self, name: str, value: str) -> str | None: ...

    def get_secret_updated_at(self, name: str) -> str | None: ...


class SecretResolver:
    def __init__(self, env: Mapping[str, str], github: GitHubSecrets | None = None) -> None:
        self.env = env
        self.github = github

    def resolve(self, spec: SecretSpec) -> SecretValue | None:
        for key in spec.candidates():
            value = (self.env.get(key) or "").strip()
            if value:
                return SecretValue(value=value, source_key=key)
        return None

    def require(self, spec: SecretSpec) -> SecretValue:
        value = self.resolve(spec)
        if value is None:
            names = ", ".join(spec.candidates())
            raise SecretMissing(f"缺少 Secret 键: {names}")
        return value

    def write_back(self, spec: SecretSpec, value: str, source_key: str) -> WriteBackResult:
        if self.github is None or not self.github.can_write():
            return WriteBackResult(
                ok=False,
                primary_key=source_key,
                error="secret_writeback_unavailable",
            )

        keys = [source_key]
        if spec.rolling:
            for legacy in spec.legacy:
                if legacy not in keys:
                    keys.append(legacy)
            # Only mirror the new alias when it already exists; never create it implicitly.
            if source_key != spec.primary and self.github.get_secret_updated_at(spec.primary) is not None:
                keys.append(spec.primary)

        updated_at: str | None = None
        mirrored: list[str] = []
        try:
            updated_at = self.github.set_secret(source_key, value)
        except Exception as exc:  # noqa: BLE001 - write-back failure must be a value, not a crash
            return WriteBackResult(
                ok=False,
                primary_key=source_key,
                mirrored_keys=(),
                error=type(exc).__name__,
            )

        mirror_errors: list[str] = []
        for key in keys[1:]:
            try:
                self.github.set_secret(key, value)
                mirrored.append(key)
            except Exception as exc:  # noqa: BLE001 - mirror failure is a warning
                mirror_errors.append(f"{key}:{type(exc).__name__}")

        return WriteBackResult(
            ok=True,
            primary_key=source_key,
            mirrored_keys=tuple(mirrored),
            updated_at=updated_at,
            error=("mirror_failed:" + ",".join(mirror_errors)) if mirror_errors else None,
        )

    def resolve_password(self, site_code: str) -> PasswordCredentials | None:
        """Resolve password credentials with per-site override then global default."""

        site = site_code.upper()
        site_user_key = f"CHECKIN_USERNAME_{site}"
        site_pass_key = f"CHECKIN_PASSWORD_{site}"
        site_user = (self.env.get(site_user_key) or "").strip()
        site_pass = self.env.get(site_pass_key) or ""
        global_user = (self.env.get("CHECKIN_USERNAME") or "").strip()
        global_pass = self.env.get("CHECKIN_PASSWORD") or ""

        username = site_user or global_user
        password = site_pass or global_pass
        if not username or not password:
            return None
        source = "site_override" if (site_user or site_pass) else "global"
        return PasswordCredentials(username=username, password=password, source=source)
