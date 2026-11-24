from pathlib import Path

from src.config.registry import build_default_registry
from src.config.settings import Settings
from src.core.github import NullGitHubSecrets
from src.core.http import HttpClient
from src.core.logging import EventLogger
from src.core.refresh import RefreshCoordinator
from src.core.runner import Runner
from src.core.secrets import SecretResolver
from src.core.state import AccountStateStore


def test_all_13_accounts_degrade_without_secrets(tmp_path: Path):
    registry = build_default_registry()
    secrets = SecretResolver({})
    github = NullGitHubSecrets()
    state = AccountStateStore(tmp_path / "state")
    logger = EventLogger(tmp_path / "history", run_id="degraded-all")
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

    assert len(report.results) == 13
    assert report.counts["skipped"] == 13
    assert report.counts["success"] == 0
    assert report.skipped_reasons == {"secret_missing": 13}

    events = logger.read_events()
    assert len(events) == 13
    for event in events:
        assert event["checkin_status"] == "skipped"
        assert event["points_gained"] is None
        assert event["points_current"] is None
        assert event["points_source"] == "api_unavailable"
        assert event["message"].startswith("Secret 缺失，未真实探测")

    text = (tmp_path / "history" / "run.log").read_text(encoding="utf-8")
    assert len(text.splitlines()) == 1
    assert text.count(":跳过") == 13
    assert len(list((tmp_path / "state").rglob("*.json"))) == 13
