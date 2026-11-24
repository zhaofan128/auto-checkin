from pathlib import Path

from src.config.registry import PlatformRegistry
from src.config.settings import Settings
from src.core.github import NullGitHubSecrets
from src.core.http import HttpClient
from src.core.logging import EventLogger
from src.core.models import AccountRef, CheckinResult, PointsResult, RotationResult
from src.core.refresh import RefreshCoordinator
from src.core.runner import Runner
from src.core.secrets import SecretResolver, SecretSpec
from src.core.state import AccountStateStore
from src.platforms.base import AccountContext, AccountSpec, Credentials


WB_SPEC = SecretSpec(
    logical_name="workbuddy_rt",
    primary="CHECKIN_WORKBUDDY_RT",
    legacy=("WB_RT",),
    rolling=True,
)


class RollingAdapter:
    def __init__(self) -> None:
        self.account = AccountRef("workbuddy", "WorkBuddy", "default", "workbuddy:default", "wb")
        self.checkin_called = False

    def resolve_credentials(self, ctx: AccountContext) -> Credentials:
        return Credentials(raw="old", source_key="WB_RT")

    def refresh(self, ctx: AccountContext, creds: Credentials) -> RotationResult | None:
        return RotationResult(new_value="new", reason="test")

    def checkin(self, ctx: AccountContext, creds: Credentials) -> CheckinResult:
        self.checkin_called = True
        return CheckinResult(status="success", message="should not run")

    def fetch_points(self, ctx: AccountContext, creds: Credentials) -> PointsResult:
        return PointsResult(gained=None, current=None, unit=None, source="api_unavailable")


class RollingPlatform:
    def __init__(self, adapter: RollingAdapter) -> None:
        self.platform = "workbuddy"
        self.accounts = (
            AccountSpec(
                platform="workbuddy",
                platform_name="WorkBuddy",
                account_id="default",
                account_key="workbuddy:default",
                secret_specs=(WB_SPEC,),
                rolling=True,
                schedule_profiles=frozenset({"manual"}),
                account_label="wb",
            ),
        )
        self._adapter = adapter

    def account_adapter(self, account_id: str) -> RollingAdapter:
        return self._adapter


def test_pat_unavailable_skip_is_visible_in_human_log(tmp_path: Path):
    adapter = RollingAdapter()
    registry = PlatformRegistry([RollingPlatform(adapter)])
    github = NullGitHubSecrets()
    secrets = SecretResolver({"WB_RT": "old"}, github=github)
    state = AccountStateStore(tmp_path / "state")
    logger = EventLogger(tmp_path / "history", run_id="run-skip")
    runner = Runner(
        registry=registry,
        secrets=secrets,
        state=state,
        logger=logger,
        refresher=RefreshCoordinator(state, secrets, github),
        http=HttpClient(),
        settings=Settings(history_dir=tmp_path / "history", state_dir=tmp_path / "state"),
    )

    report = runner.run(profile="manual")

    assert report.counts["skipped"] == 1
    assert report.results[0].result.skipped_reason == "secret_writeback_unavailable"
    assert adapter.checkin_called is False

    event_line = (tmp_path / "history" / "events.jsonl").read_text(encoding="utf-8")
    assert '"skipped_reason":"secret_writeback_unavailable"' in event_line

    human = (tmp_path / "history" / "run.log").read_text(encoding="utf-8")
    assert len(human.splitlines()) == 1
    assert "workbuddy:跳过" in human
