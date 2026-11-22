from pathlib import Path

from src.core.logging import EventLogger, new_run_id
from src.core.models import AccountRef, CheckinResult, PointsResult, RunReport, AccountResult


def make_account(platform: str, account_id: str, key: str) -> AccountRef:
    return AccountRef(
        platform=platform,
        platform_name=platform.replace("_", " ").title(),
        account_id=account_id,
        account_key=key,
        account_label="q***n",
    )


def test_events_jsonl_is_append_only(tmp_path: Path):
    logger = EventLogger(tmp_path, run_id="run-1")
    account = make_account("qoder_cn", "cn", "qoder:cn")
    result = CheckinResult(
        status="success",
        message="签到成功",
        points=PointsResult(gained=100, current=1200, unit="credits", source="api_field"),
        duration_ms=12,
    )
    logger.account_result(account, result, run_profile="manual")
    logger.account_result(account, result, run_profile="manual")

    lines = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert (tmp_path / "run.log").read_text(encoding="utf-8").count("\n") == 2


def test_existing_run_log_is_preserved(tmp_path: Path):
    host_log = tmp_path / "run.log"
    host_log.write_text("2026-10-31 01:36 UTC  daily-checkin 运行一次\n", encoding="utf-8")

    logger = EventLogger(tmp_path, run_id="run-2")
    account = make_account("workbuddy", "default", "workbuddy:default")
    logger.account_result(
        account,
        CheckinResult(status="already_checked", message="今日已签到", duration_ms=5),
        run_profile="morning",
    )

    content = host_log.read_text(encoding="utf-8")
    assert content.startswith("2026-10-31 01:36 UTC  daily-checkin 运行一次\n")
    assert len(content.splitlines()) == 2


def test_run_log_is_not_truncated_over_many_events(tmp_path: Path):
    logger = EventLogger(tmp_path, run_id="run-3")
    account = make_account("kk", "default", "kk:default")
    for index in range(200):
        logger.account_result(
            account,
            CheckinResult(status="success", message=f"ok {index}", duration_ms=index),
            run_profile="manual",
        )
    assert len((tmp_path / "run.log").read_text(encoding="utf-8").splitlines()) == 200


def test_summary_emits_skipped_reason_for_human_readability(tmp_path: Path):
    logger = EventLogger(tmp_path, run_id="run-4")
    account = make_account("traework", "cn", "traework:cn")
    report = RunReport(run_id="run-4", profile="morning")
    report.results.append(
        AccountResult(
            account=account,
            result=CheckinResult(
                status="skipped",
                message="GH_PAT 不可写，跳过刷新以保护登录态",
                skipped_reason="secret_writeback_unavailable",
                duration_ms=1,
            ),
        )
    )
    logger.summary(report)
    text = (tmp_path / "run.log").read_text(encoding="utf-8")
    assert "skipped_reason=secret_writeback_unavailable" in text


def test_logging_failure_does_not_raise(tmp_path: Path):
    logger = EventLogger(tmp_path, run_id="run-5")

    def boom(*args, **kwargs):
        raise OSError("disk full")

    logger._append_text = boom  # type: ignore[method-assign]
    account = make_account("minimax", "default", "minimax:default")
    logger.account_result(
        account,
        CheckinResult(status="success", message="ok", duration_ms=1),
        run_profile="manual",
    )
    assert logger.last_errors


def test_duplicate_checkin_is_logged_with_current_points(tmp_path: Path):
    logger = EventLogger(tmp_path, run_id="run-duplicate")
    account = make_account("dgb", "dgb", "dgb:dgb")
    logger.account_result(
        account,
        CheckinResult(
            status="already_checked",
            message="今日已签到，跳过",
            points=PointsResult(
                gained=None,
                current=500,
                unit="quota",
                source="api_unavailable",
                message="平台未提供当前积分接口",
            ),
            duration_ms=3,
        ),
        run_profile="manual",
    )
    events = logger.read_events()
    assert events[0]["checkin_status"] == "already_checked"
    assert events[0]["points_current"] == 500
    assert events[0]["points_source"] == "api_unavailable"
    text = (tmp_path / "run.log").read_text(encoding="utf-8")
    assert "status=already_checked" in text
    assert "current=500" in text


def test_manual_turnstile_mode_is_logged_without_token(tmp_path: Path):
    logger = EventLogger(tmp_path, run_id="run-turnstile")
    account = make_account("kk", "default", "kk:default")
    logger.account_result(
        account,
        CheckinResult(
            status="success",
            message="签到成功",
            duration_ms=1,
            turnstile={
                "mode": "manual_token",
                "result": "manual_token",
                "token": "secret-turnstile-token",
                "token_present": True,
            },
        ),
        run_profile="manual",
    )
    text = (tmp_path / "run.log").read_text(encoding="utf-8")
    assert "turnstile=manual_token/manual_token" in text
    assert "secret-turnstile-token" not in text
    assert "secret-turnstile-token" not in (tmp_path / "events.jsonl").read_text(encoding="utf-8")


def test_browser_fallback_mode_is_logged_without_token(tmp_path: Path):
    logger = EventLogger(tmp_path, run_id="run-turnstile-fallback")
    account = make_account("kk", "default", "kk:default")
    logger.account_result(
        account,
        CheckinResult(
            status="failed",
            message="Turnstile 验证超时",
            error_type="turnstile_timeout",
            duration_ms=90,
            manual_required=True,
            turnstile={
                "mode": "browser_fallback",
                "result": "timeout",
                "token": "secret-browser-token",
                "manual_required": True,
            },
        ),
        run_profile="manual",
    )
    text = (tmp_path / "run.log").read_text(encoding="utf-8")
    assert "turnstile=browser_fallback/timeout" in text
    assert "secret-browser-token" not in text
    assert "secret-browser-token" not in (tmp_path / "events.jsonl").read_text(encoding="utf-8")


def test_sensitive_values_are_redacted_in_logs(tmp_path: Path):
    logger = EventLogger(tmp_path, run_id="run-6")
    account = make_account("newapi_dgb", "dgb", "newapi:dgb")
    logger.account_result(
        account,
        CheckinResult(
            status="failed",
            message="login failed password=supersecret token=nap_abcdefghijklmnopqrstuvwxyz",
            error_detail="Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnop",
            duration_ms=7,
        ),
        run_profile="manual",
    )
    text = (tmp_path / "run.log").read_text(encoding="utf-8")
    assert "supersecret" not in text
    assert "nap_abcdefghijklmnopqrstuvwxyz" not in text
    assert "eyJhbGciOiJIUzI1NiJ9" not in text


def test_new_run_id_is_unique():
    assert new_run_id() != new_run_id()
