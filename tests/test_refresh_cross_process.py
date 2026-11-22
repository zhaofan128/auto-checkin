"""Cross-process refresh serialization test.

This validates the POSIX file lock + generation CAS path. It is intentionally
skipped on Windows because the test uses POSIX process semantics.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import time
from pathlib import Path

import pytest

from src.core.locks import FileLock
from src.core.models import AccountRef, RotationResult
from src.core.refresh import RefreshCoordinator
from src.core.secrets import SecretResolver, SecretSpec
from src.core.state import AccountStateStore


class FileGitHub:
    """A file-backed fake GitHub Secrets store shared by processes."""

    def __init__(self, path: Path, lock_path: Path) -> None:
        self.path = Path(path)
        self.lock_path = Path(lock_path)

    def _read(self) -> dict:
        if not self.path.exists():
            return {"values": {}, "versions": {}, "writes": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def can_write(self) -> bool:
        return True

    def set_secret(self, name: str, value: str) -> str | None:
        with FileLock(self.lock_path, timeout_s=10):
            data = self._read()
            data.setdefault("values", {})[name] = value
            data.setdefault("writes", []).append({"name": name, "pid": os.getpid()})
            version = f"v{len(data['writes'])}"
            data.setdefault("versions", {})[name] = version
            self._write(data)
            return version

    def get_secret_updated_at(self, name: str) -> str | None:
        with FileLock(self.lock_path, timeout_s=10):
            return self._read().get("versions", {}).get(name)


def _worker(
    state_dir: str,
    secret_file: str,
    secret_lock: str,
    start_event,
    queue,
) -> None:
    try:
        start_event.wait(timeout=10)
        state = AccountStateStore(Path(state_dir))
        github = FileGitHub(Path(secret_file), Path(secret_lock))
        secrets = SecretResolver({"WB_RT": "old"}, github=github)
        coordinator = RefreshCoordinator(state, secrets, github)
        account = AccountRef(
            platform="workbuddy",
            platform_name="WorkBuddy",
            account_id="default",
            account_key="workbuddy:default",
            account_label="workbuddy",
        )
        spec = SecretSpec(
            logical_name="workbuddy_rt",
            primary="CHECKIN_WORKBUDDY_RT",
            legacy=("WB_RT",),
            rolling=True,
        )

        def refresh_fn(raw: str) -> RotationResult:
            time.sleep(0.2)
            return RotationResult(new_value=f"new-{os.getpid()}", reason="cross-process-test")

        outcome = coordinator.refresh(
            account,
            spec,
            refresh_fn,
            timeout_s=10,
            expected_generation=0,
        )
        queue.put(
            {
                "pid": os.getpid(),
                "changed": outcome.changed,
                "generation": outcome.generation,
                "skipped_reason": outcome.skipped_reason,
            }
        )
    except Exception as exc:  # noqa: BLE001 - report child failures to the parent
        queue.put({"pid": os.getpid(), "error": type(exc).__name__, "detail": str(exc)})


@pytest.mark.skipif(os.name == "nt", reason="POSIX cross-process lock test")
def test_two_processes_do_not_refresh_twice(tmp_path: Path):
    ctx = mp.get_context("spawn")
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    secret_file = tmp_path / "secrets.json"
    secret_lock = tmp_path / "secrets.lock"
    secret_file.write_text(
        json.dumps({"values": {"WB_RT": "old"}, "versions": {"WB_RT": "v0"}, "writes": []}),
        encoding="utf-8",
    )

    start = ctx.Event()
    queue = ctx.Queue()
    args = (str(state_dir), str(secret_file), str(secret_lock), start, queue)
    processes = [ctx.Process(target=_worker, args=args) for _ in range(2)]
    for process in processes:
        process.start()
    start.set()
    for process in processes:
        process.join(timeout=20)

    for process in processes:
        assert process.exitcode == 0

    results = [queue.get(timeout=5) for _ in range(2)]
    for result in results:
        assert "error" not in result, result

    changed = [result for result in results if result["changed"]]
    assert len(changed) == 1, results

    data = json.loads(secret_file.read_text(encoding="utf-8"))
    assert len(data["writes"]) == 1
    assert data["values"]["WB_RT"].startswith("new-")

    state_file = state_dir / "workbuddy" / "workbuddy_default.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["generation"] == 1
    assert state["secret_version"] == "v1"
