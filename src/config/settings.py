"""Runtime configuration, loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    repo: str | None = None
    gh_token: str | None = field(default=None, repr=False)
    history_dir: Path = Path("history")
    state_dir: Path = Path("state")
    timezone: str = "Asia/Shanghai"
    default_profile: str = "manual"
    timeout_s: float = 30.0

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        values = env if env is not None else dict(os.environ)
        repo = values.get("CHECKIN_GITHUB_REPO") or values.get("GITHUB_REPOSITORY")
        token = values.get("GH_PAT") or values.get("GH_TOKEN") or values.get("GITHUB_TOKEN")
        try:
            timeout_s = float(values.get("CHECKIN_TIMEOUT_S", "30"))
        except ValueError:
            timeout_s = 30.0
        return cls(
            repo=repo or None,
            gh_token=token or None,
            history_dir=Path(values.get("CHECKIN_HISTORY_DIR", "history")),
            state_dir=Path(values.get("CHECKIN_STATE_DIR", "state")),
            timezone=values.get("CHECKIN_TZ", "Asia/Shanghai"),
            default_profile=values.get("CHECKIN_PROFILE", "manual"),
            timeout_s=timeout_s,
        )

    def ensure_dirs(self) -> None:
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
