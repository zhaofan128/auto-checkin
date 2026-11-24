from pathlib import Path

from src.core.logging import EventLogger
from src.core.models import AccountRef, AccountResult, CheckinResult, PointsResult, RunReport
from src.core.state import AccountStateStore, default_state


def qoder_account(platform: str, account_id: str) -> AccountRef:
    return AccountRef(
        platform=platform,
        platform_name=f"Qoder {account_id.upper()}",
        account_id=account_id,
        account_key=f"qoder:{account_id}",
        account_label=f"qoder-{account_id}",
    )


def test_qoder_cn_and_global_do_not_share_state_or_logs(tmp_path: Path):
    store = AccountStateStore(tmp_path / "state")
    logger = EventLogger(tmp_path / "history", run_id="run-qoder")
    cn = qoder_account("qoder_cn", "cn")
    global_account = qoder_account("qoder_global", "global")

    store.save(default_state(cn))
    store.save(default_state(global_account))
    assert store.path_for(cn) != store.path_for(global_account)
    assert store.lock(cn).path != store.lock(global_account).path
    with store.lock(cn, timeout_s=0.2):
        with store.lock(global_account, timeout_s=0.2):
            pass

    logger.account_result(
        cn,
        CheckinResult(
            status="success",
            message="CN ok",
            points=PointsResult(gained=100, current=1000, unit="credits", source="api_field"),
            duration_ms=1,
        ),
        run_profile="manual",
    )
    logger.account_result(
        global_account,
        CheckinResult(
            status="failed",
            message="Global failed",
            error_type="auth_failed",
            duration_ms=1,
        ),
        run_profile="manual",
    )
    report = RunReport(run_id="run-qoder", profile="manual")
    report.results.extend(
        [
            AccountResult(
                account=cn,
                result=CheckinResult(status="success", message="CN ok"),
            ),
            AccountResult(
                account=global_account,
                result=CheckinResult(status="failed", message="Global failed"),
            ),
        ]
    )
    logger.summary(report)

    events = logger.read_events()
    platforms = {event["platform"] for event in events}
    assert platforms == {"qoder_cn", "qoder_global"}
    assert all("qoder" in event["account_key"] for event in events)
    text = (tmp_path / "history" / "run.log").read_text(encoding="utf-8")
    assert len(text.splitlines()) == 1
    assert "qoder_cn:成功" in text
    assert "qoder_global:失败" in text
