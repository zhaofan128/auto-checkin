from pathlib import Path

from src.config.registry import PlatformRegistry
from src.config.settings import Settings
from src.core.github import NullGitHubSecrets
from src.core.http import HttpClient
from src.core.logging import EventLogger
from src.core.models import AccountRef, CheckinResult, PointsResult, RotationResult
from src.core.refresh import RefreshCoordinator
from src.core.runner import Runner
from src.core.secrets import SecretResolver
from src.core.state import AccountStateStore
from src.platforms.base import AccountContext, AccountSpec, Credentials


class FakeAccountAdapter:
    def __init__(self, account: AccountRef, *, fail: bool = False) -> None:
        self.account = account
        self.fail = fail

    def resolve_credentials(self, ctx: AccountContext) -> Credentials:
        return Credentials(raw="raw", source_key="TEST_SECRET")

    def refresh(self, ctx: AccountContext, creds: Credentials) -> RotationResult | None:
        return None

    def checkin(self, ctx: AccountContext, creds: Credentials) -> CheckinResult:
        if self.fail:
            raise RuntimeError("adapter exploded")
        return CheckinResult(status="success", message="ok", duration_ms=1)

    def fetch_points(self, ctx: AccountContext, creds: Credentials) -> PointsResult:
        return PointsResult(gained=10, current=20, unit="credits", source="api_field")


class FakePlatformAdapter:
    def __init__(self) -> None:
        self.platform = "fake"
        self.accounts = (
            AccountSpec(
                platform="fake_good",
                platform_name="Fake Good",
                account_id="good",
                account_key="fake:good",
                schedule_profiles=frozenset({"manual"}),
            ),
            AccountSpec(
                platform="fake_bad",
                platform_name="Fake Bad",
                account_id="bad",
                account_key="fake:bad",
                schedule_profiles=frozenset({"manual"}),
            ),
        )
        self._adapters = {
            "good": FakeAccountAdapter(
                AccountRef("fake_good", "Fake Good", "good", "fake:good", "good")
            ),
            "bad": FakeAccountAdapter(
                AccountRef("fake_bad", "Fake Bad", "bad", "fake:bad", "bad"),
                fail=True,
            ),
        }

    def account_adapter(self, account_id: str) -> FakeAccountAdapter:
        return self._adapters[account_id]


def test_one_account_failure_does_not_stop_others(tmp_path: Path):
    registry = PlatformRegistry([FakePlatformAdapter()])
    secrets = SecretResolver({})
    github = NullGitHubSecrets()
    state = AccountStateStore(tmp_path / "state")
    logger = EventLogger(tmp_path / "history", run_id="run-runner")
    refresher = RefreshCoordinator(state, secrets, github)
    runner = Runner(
        registry=registry,
        secrets=secrets,
        state=state,
        logger=logger,
        refresher=refresher,
        http=HttpClient(),
        settings=Settings(history_dir=tmp_path / "history", state_dir=tmp_path / "state"),
    )

    report = runner.run(profile="manual")

    assert len(report.results) == 2
    assert report.counts["success"] == 1
    assert report.counts["failed"] == 1
    assert report.exit_code == 1
    events = logger.read_events()
    assert {event["platform"] for event in events} == {"fake_good", "fake_bad"}
    text = (tmp_path / "history" / "run.log").read_text(encoding="utf-8")
    assert len(text.splitlines()) == 1
    assert "fake_good:成功" in text
    assert "fake_bad:失败" in text

    state = AccountStateStore(tmp_path / "state")
    good = state.load(
        AccountRef("fake_good", "Fake Good", "good", "fake:good", "good")
    )
    bad = state.load(
        AccountRef("fake_bad", "Fake Bad", "bad", "fake:bad", "bad")
    )
    assert good.last_checkin_status == "success"
    assert bad.last_checkin_status == "failed"
    assert good.generation == 0
    assert bad.generation == 0
