import json

import pytest

from src.core.errors import RefreshFailed, RefreshRequired
from src.core.http import HttpResponse
from src.core.logging import EventLogger
from src.core.secrets import SecretResolver
from src.core.state import AccountStateStore
from src.platforms.base import AccountContext
from src.platforms.workbuddy.adapter import (
    BILLING,
    CHECKIN,
    PLUGIN,
    REFRESH,
    STATUS,
    TRAVEL,
    T_STATUS,
    WORKBUDDY_ACCOUNT,
    WorkBuddyAdapter,
)


def response(payload: dict, status: int = 200) -> HttpResponse:
    return HttpResponse(status, {}, json.dumps(payload).encode("utf-8"))


class FakeHttp:
    def __init__(self, handler):
        self.handler = handler
        self.calls: list[tuple[str, str]] = []

    def request(self, method, url, *, headers=None, json_body=None, **kwargs):
        self.calls.append((method, url))
        return self.handler(method, url)


def make_ctx(tmp_path, http, *, dry_run: bool = False) -> AccountContext:
    return AccountContext(
        run_id="run-workbuddy",
        profile="manual",
        account=WORKBUDDY_ACCOUNT,
        http=http,  # type: ignore[arg-type]
        secrets=SecretResolver({"WB_RT": "old-rt"}),
        state=AccountStateStore(tmp_path / "state"),
        logger=EventLogger(tmp_path / "history", run_id="run-workbuddy"),
        dry_run=dry_run,
    )


def test_workbuddy_success_parses_gained_and_current(tmp_path):
    def handler(method, url):
        if PLUGIN + REFRESH in url:
            return response({"code": 0, "data": {"accessToken": "at-123", "refreshToken": "new-rt"}})
        if BILLING + STATUS in url:
            return response(
                {
                    "code": 0,
                    "data": {
                        "today_checked_in": False,
                        "total_credits": 1200,
                        "streak_days": 2,
                    },
                }
            )
        if BILLING + CHECKIN in url:
            return response({"code": 0, "data": {"credit": 100, "total_credits": 1300}})
        if TRAVEL + T_STATUS in url:
            return response({"code": 0, "data": {"state": "traveling"}})
        return response({"code": 404}, 404)

    http = FakeHttp(handler)
    ctx = make_ctx(tmp_path, http)
    adapter = WorkBuddyAdapter()
    creds = adapter.resolve_credentials(ctx)
    rotation = adapter.refresh(ctx, creds)
    assert rotation is not None
    assert rotation.new_value == "new-rt"

    result = adapter.checkin(ctx, creds)
    assert result.status == "success"
    assert result.points is not None
    assert result.points.gained == 100
    assert result.points.current == 1300
    assert result.points.unit == "credits"
    assert result.points.source == "api_field"
    assert "travel=traveling" in result.message
    assert "at-123" not in result.message
    assert "new-rt" not in result.message


def test_workbuddy_already_checked_still_reads_current_points(tmp_path):
    def handler(method, url):
        if PLUGIN + REFRESH in url:
            return response({"code": 0, "data": {"accessToken": "at-123", "refreshToken": "new-rt"}})
        if BILLING + STATUS in url:
            return response({"code": 0, "data": {"today_checked_in": True, "total_credits": 1200}})
        if BILLING + CHECKIN in url:
            raise AssertionError("already checked must not call checkin")
        if TRAVEL + T_STATUS in url:
            return response({"code": 0, "data": {"state": "traveling"}})
        return response({"code": 404}, 404)

    http = FakeHttp(handler)
    ctx = make_ctx(tmp_path, http)
    adapter = WorkBuddyAdapter()
    creds = adapter.resolve_credentials(ctx)
    adapter.refresh(ctx, creds)
    result = adapter.checkin(ctx, creds)

    assert result.status == "already_checked"
    assert result.points is not None
    assert result.points.gained is None
    assert result.points.current == 1200
    assert result.points.source == "api_unavailable"
    assert result.points.message == "签到响应未返回本次积分"
    assert result.points.unit == "credits"


def test_workbuddy_checkin_failure_keeps_current_points(tmp_path):
    def handler(method, url):
        if PLUGIN + REFRESH in url:
            return response({"code": 0, "data": {"accessToken": "at-123", "refreshToken": "new-rt"}})
        if BILLING + STATUS in url:
            return response({"code": 0, "data": {"today_checked_in": False, "total_credits": 1200}})
        if BILLING + CHECKIN in url:
            return response({"code": 500, "msg": "server busy"})
        if TRAVEL + T_STATUS in url:
            return response({"code": 0, "data": {"state": "traveling"}})
        return response({"code": 404}, 404)

    http = FakeHttp(handler)
    ctx = make_ctx(tmp_path, http)
    adapter = WorkBuddyAdapter()
    creds = adapter.resolve_credentials(ctx)
    adapter.refresh(ctx, creds)
    result = adapter.checkin(ctx, creds)

    assert result.status == "failed"
    assert result.error_type == "api_error"
    assert "server busy" in result.message
    assert result.points is not None
    assert result.points.gained is None
    assert result.points.current == 1200
    assert result.points.source == "api_unavailable"


def test_workbuddy_success_uses_diff_when_credit_missing(tmp_path):
    def handler(method, url):
        if PLUGIN + REFRESH in url:
            return response({"code": 0, "data": {"accessToken": "at-123", "refreshToken": "new-rt"}})
        if BILLING + STATUS in url:
            return response({"code": 0, "data": {"today_checked_in": False, "total_credits": 1000}})
        if BILLING + CHECKIN in url:
            return response({"code": 0, "data": {"total_credits": 1050}})
        if TRAVEL + T_STATUS in url:
            return response({"code": 0, "data": {"state": "traveling"}})
        return response({"code": 404}, 404)

    http = FakeHttp(handler)
    ctx = make_ctx(tmp_path, http)
    adapter = WorkBuddyAdapter()
    creds = adapter.resolve_credentials(ctx)
    adapter.refresh(ctx, creds)
    result = adapter.checkin(ctx, creds)

    assert result.status == "success"
    assert result.points is not None
    assert result.points.gained == 50
    assert result.points.current == 1050
    assert result.points.source == "diff_before_after"


def test_workbuddy_status_only_does_not_use_today_credit(tmp_path):
    def handler(method, url):
        if PLUGIN + REFRESH in url:
            return response({"code": 0, "data": {"accessToken": "at-123", "refreshToken": "new-rt"}})
        if BILLING + STATUS in url:
            return response(
                {
                    "code": 0,
                    "data": {
                        "today_checked_in": False,
                        "total_credits": 1000,
                        "today_credit": 20,
                    },
                }
            )
        if BILLING + CHECKIN in url:
            return response({"code": 0, "data": {}})
        if TRAVEL + T_STATUS in url:
            return response({"code": 0, "data": {"state": "traveling"}})
        return response({"code": 404}, 404)

    http = FakeHttp(handler)
    ctx = make_ctx(tmp_path, http)
    adapter = WorkBuddyAdapter()
    creds = adapter.resolve_credentials(ctx)
    adapter.refresh(ctx, creds)
    result = adapter.checkin(ctx, creds)

    assert result.status == "success"
    assert result.points is not None
    assert result.points.gained is None
    assert result.points.current == 1000
    assert result.points.source == "api_unavailable"
    assert result.points.message == "签到响应未返回本次积分"
    assert result.points.gained != 20


def test_workbuddy_travel_failure_does_not_fail_checkin(tmp_path):
    def handler(method, url):
        if PLUGIN + REFRESH in url:
            return response({"code": 0, "data": {"accessToken": "at-123", "refreshToken": "new-rt"}})
        if BILLING + STATUS in url:
            return response({"code": 0, "data": {"today_checked_in": False, "total_credits": 0}})
        if BILLING + CHECKIN in url:
            return response({"code": 0, "data": {"credit": 10, "total_credits": 10}})
        if TRAVEL + T_STATUS in url:
            return response({"code": 1, "msg": "travel unavailable"})
        return response({"code": 404}, 404)

    http = FakeHttp(handler)
    ctx = make_ctx(tmp_path, http)
    adapter = WorkBuddyAdapter()
    creds = adapter.resolve_credentials(ctx)
    adapter.refresh(ctx, creds)
    result = adapter.checkin(ctx, creds)

    assert result.status == "success"
    assert result.points is not None
    assert result.points.gained == 10
    assert "travel=unavailable" in result.message


def test_workbuddy_requires_refresh_before_checkin(tmp_path):
    http = FakeHttp(lambda method, url: response({"code": 404}, 404))
    ctx = make_ctx(tmp_path, http)
    adapter = WorkBuddyAdapter()
    creds = adapter.resolve_credentials(ctx)
    with pytest.raises(RefreshRequired):
        adapter.checkin(ctx, creds)


def test_workbuddy_refresh_failure_is_typed(tmp_path):
    http = FakeHttp(lambda method, url: response({"code": 1, "msg": "bad token"}))
    ctx = make_ctx(tmp_path, http)
    adapter = WorkBuddyAdapter()
    creds = adapter.resolve_credentials(ctx)
    with pytest.raises(RefreshFailed):
        adapter.refresh(ctx, creds)


def test_workbuddy_dry_run_does_not_claim(tmp_path):
    def handler(method, url):
        if PLUGIN + REFRESH in url:
            return response({"code": 0, "data": {"accessToken": "at-123", "refreshToken": "new-rt"}})
        if BILLING + STATUS in url:
            return response({"code": 0, "data": {"today_checked_in": False, "total_credits": 1200}})
        raise AssertionError("dry-run must not call checkin or travel")

    http = FakeHttp(handler)
    ctx = make_ctx(tmp_path, http, dry_run=True)
    adapter = WorkBuddyAdapter()
    creds = adapter.resolve_credentials(ctx)
    adapter.refresh(ctx, creds)
    result = adapter.checkin(ctx, creds)

    assert result.status == "skipped"
    assert result.skipped_reason == "dry_run"
    assert result.points is not None
    assert result.points.current == 1200
