"""GitHub Secrets write-back through the gh CLI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess

from .errors import SecretWritebackUnavailable


class GhCliGitHubSecrets:
    """Uses `gh secret set/list` so the token never appears in argv.

    `set_secret` passes the value on stdin. Errors never include the value.
    """

    def __init__(
        self,
        repo: str,
        *,
        token: str | None = None,
        gh_binary: str = "gh",
        timeout_s: float = 30.0,
    ) -> None:
        self.repo = repo
        self.token = token
        self.gh_binary = gh_binary
        self.timeout_s = timeout_s

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self.token:
            env["GH_TOKEN"] = self.token
        return env

    def _run(self, args: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str] | None:
        if shutil.which(self.gh_binary) is None:
            return None
        try:
            return subprocess.run(
                [self.gh_binary, *args],
                input=input_text,
                text=True,
                capture_output=True,
                timeout=self.timeout_s,
                env=self._env(),
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

    def can_write(self) -> bool:
        result = self._run(
            ["secret", "list", "--repo", self.repo, "--json", "name", "--limit", "1"]
        )
        return bool(result is not None and result.returncode == 0)

    def set_secret(self, name: str, value: str) -> str | None:
        result = self._run(
            ["secret", "set", name, "--repo", self.repo],
            input_text=value,
        )
        if result is None or result.returncode != 0:
            raise SecretWritebackUnavailable(f"写入 Secret {name} 失败")
        return self.get_secret_updated_at(name)

    def get_secret_updated_at(self, name: str) -> str | None:
        result = self._run(
            ["secret", "list", "--repo", self.repo, "--json", "name,updatedAt"]
        )
        if result is None or result.returncode != 0:
            return None
        try:
            items = json.loads(result.stdout)
        except json.JSONDecodeError:
            return None
        for item in items:
            if isinstance(item, dict) and item.get("name") == name:
                return item.get("updatedAt")
        return None


class NullGitHubSecrets:
    def can_write(self) -> bool:
        return False

    def set_secret(self, name: str, value: str) -> str | None:
        raise SecretWritebackUnavailable("未配置 GH_PAT，无法写回 Secret")

    def get_secret_updated_at(self, name: str) -> str | None:
        return None
