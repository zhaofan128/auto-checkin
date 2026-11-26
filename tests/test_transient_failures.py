"""Transient upstream failures must not fail the whole workflow run."""

from src.core.models import AccountRef, AccountResult, CheckinResult, RunReport


def _account(key: str = "demo") -> AccountRef:
    return AccountRef("demo", "Demo", key, f"demo:{key}", key)


def _report(message: str, *, error_type: str | None = "api_error") -> RunReport:
    report = RunReport(run_id="run-test", profile="manual")
    report.results.append(
        AccountResult(
            account=_account(),
            result=CheckinResult(status="failed", message=message, error_type=error_type),
        )
    )
    return report


def test_upstream_5xx_is_transient():
    report = _report("失败: KK 签到状态查询失败: HTTP 503")
    assert report.counts["failed"] == 1
    assert report.transient_failed == 1
    assert report.exit_code == 0


def test_network_failure_is_transient():
    report = _report("失败: 网络请求失败: connection reset", error_type="http_error")
    assert report.exit_code == 0


def test_auth_failure_still_fails():
    report = _report("失败: 登录失败: HTTP 401", error_type="api_error")
    assert report.transient_failed == 0
    assert report.exit_code == 1


def test_turnstile_timeout_still_fails():
    report = _report("失败: Turnstile 验证超时", error_type="turnstile_timeout")
    assert report.exit_code == 1
