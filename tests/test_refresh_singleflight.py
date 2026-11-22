import threading
from pathlib import Path

import pytest

from src.core.errors import SecretWritebackFailed
from src.core.models import AccountRef, RotationResult
from src.core.refresh import RefreshCoordinator
from src.core.secrets import SecretResolver, SecretSpec
from src.core.state import AccountStateStore


class FakeGitHub:
    def __init__(self) -> None:
        self.versions: dict[str, str] = {"WB_RT": "v0"}
        self.values: dict[str, str] = {"WB_RT": "old"}
        self.writes: list[tuple[str, str]] = []

    def can_write(self) -> bool:
        return True

    def set_secret(self, name: str, value: str) -> str | None:
        self.writes.append((name, value))
        self.values[name] = value
        self.versions[name] = f"v{len(self.writes)}"
        return self.versions[name]

    def get_secret_updated_at(self, name: str) -> str | None:
        return self.versions.get(name)


def account() -> AccountRef:
    return AccountRef(
        platform="workbuddy",
        platform_name="WorkBuddy",
        account_id="default",
        account_key="workbuddy:default",
        account_label="workbuddy",
    )


def spec() -> SecretSpec:
    return SecretSpec(
        logical_name="workbuddy_rt",
        primary="CHECKIN_WORKBUDDY_RT",
        legacy=("WB_RT",),
        rolling=True,
    )


def test_concurrent_refresh_runs_only_once(tmp_path: Path):
    github = FakeGitHub()
    resolver = SecretResolver({"WB_RT": "old"}, github=github)
    store = AccountStateStore(tmp_path)
    coordinator = RefreshCoordinator(store, resolver, github)
    ref = account()
    calls = 0
    lock = threading.Lock()

    def refresh_fn(raw: str) -> RotationResult:
        nonlocal calls
        with lock:
            calls += 1
        assert raw == "old"
        return RotationResult(new_value="new", reason="test")

    barrier = threading.Barrier(2)
    outcomes = []

    def worker() -> None:
        barrier.wait()
        outcomes.append(
            coordinator.refresh(
                ref,
                spec(),
                refresh_fn,
                timeout_s=5,
                expected_generation=0,
            )
        )

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert calls == 1
    assert len(outcomes) == 2
    assert all(outcome.changed for outcome in outcomes)
    assert store.load(ref).generation == 1
    assert github.values["WB_RT"] == "new"


def test_stale_generation_does_not_refresh_again(tmp_path: Path):
    github = FakeGitHub()
    resolver = SecretResolver({"WB_RT": "old"}, github=github)
    store = AccountStateStore(tmp_path)
    coordinator = RefreshCoordinator(store, resolver, github)
    ref = account()
    calls = 0

    def refresh_fn(raw: str) -> RotationResult:
        nonlocal calls
        calls += 1
        return RotationResult(new_value="new", reason="test")

    first = coordinator.refresh(ref, spec(), refresh_fn, expected_generation=0)
    assert first.changed is True
    second = coordinator.refresh(ref, spec(), refresh_fn, expected_generation=0)

    assert second.changed is False
    assert calls == 1
    assert store.load(ref).generation == 1


def test_writeback_failure_is_not_reported_as_skip(tmp_path: Path):
    class FailingWriteGitHub(FakeGitHub):
        def set_secret(self, name: str, value: str) -> str | None:
            raise RuntimeError("write failed")

    github = FailingWriteGitHub()
    resolver = SecretResolver({"WB_RT": "old"}, github=github)
    store = AccountStateStore(tmp_path)
    coordinator = RefreshCoordinator(store, resolver, github)
    ref = account()

    with pytest.raises(SecretWritebackFailed):
        coordinator.refresh(
            ref,
            spec(),
            lambda raw: RotationResult(new_value="new", reason="test"),
            expected_generation=0,
        )


def test_writeback_unavailable_skips_refresh(tmp_path: Path):
    class NoWriteGitHub(FakeGitHub):
        def can_write(self) -> bool:
            return False

    github = NoWriteGitHub()
    resolver = SecretResolver({"WB_RT": "old"}, github=github)
    store = AccountStateStore(tmp_path)
    coordinator = RefreshCoordinator(store, resolver, github)
    ref = account()
    calls = 0

    def refresh_fn(raw: str) -> RotationResult:
        nonlocal calls
        calls += 1
        return RotationResult(new_value="new", reason="test")

    outcome = coordinator.refresh(ref, spec(), refresh_fn, expected_generation=0)
    assert outcome.changed is False
    assert outcome.skipped_reason == "secret_writeback_unavailable"
    assert calls == 0
    assert github.writes == []
