import pytest

from src.platforms.newapi import newapi_platforms
from tests.fakes import FakeHttp, make_context, response

PASSWORD_SITES = ("dgb", "aiaiai", "helpcoder", "kemeng")
TOKEN_SITES = ("seekai", "benst")


def platform_map():
    return {platform.platform: platform for platform in newapi_platforms()}


def password_env() -> dict[str, str]:
    return {"CHECKIN_USERNAME": "user", "CHECKIN_PASSWORD": "pass"}


def token_env(site_code: str) -> dict[str, str]:
    return {"SEEKAI_TOKEN": "seekai-token"} if site_code == "seekai" else {"BENST_TOKEN": "benst-token"}


def handler_for(checked: bool = False, current_data=None):
    current_data = current_data or {"quota": 1000}

    def handler(method, url, **kwargs):
        if "/api/user/login" in url:
            return response(
                {"success": True, "data": {"access_token": "at", "user": {"id": 1}}}
            )
        if "/api/user/checkin" in url:
            if method == "GET":
                return response(
                    {
                        "success": True,
                        "data": {"stats": {"checked_in_today": checked, "total_checkins": 5}},
                    }
                )
            return response(
                {"success": True, "data": {"quota_awarded": 10}}
            )
        if "/api/user/self" in url or "/api/data/self" in url:
            return response({"success": True, "data": current_data})
        return response({}, 404)

    return handler


@pytest.mark.parametrize("site_code", PASSWORD_SITES)
def test_password_site_success(tmp_path, site_code):
    platform = platform_map()[site_code]
    adapter = platform.account_adapter("default")
    http = FakeHttp(handler_for())
    ctx = make_context(tmp_path, http, adapter.account, password_env())
    creds = adapter.resolve_credentials(ctx)
    result = adapter.checkin(ctx, creds)

    assert result.status == "success"
    assert result.points is not None
    assert result.points.gained == 10
    assert result.points.current == 1000
    assert result.points.unit == "quota"
    assert result.points.source == "api_field"


@pytest.mark.parametrize("site_code", TOKEN_SITES)
def test_token_site_success(tmp_path, site_code):
    platform = platform_map()[site_code]
    adapter = platform.account_adapter("default")
    http = FakeHttp(handler_for())
    ctx = make_context(tmp_path, http, adapter.account, token_env(site_code))
    creds = adapter.resolve_credentials(ctx)
    result = adapter.checkin(ctx, creds)

    assert result.status == "success"
    assert result.points is not None
    assert result.points.gained == 10
    assert result.points.current == 1000
    assert result.points.source == "api_field"


def test_newapi_already_checked_reads_current_but_not_gained(tmp_path):
    platform = platform_map()["dgb"]
    adapter = platform.account_adapter("default")
    http = FakeHttp(handler_for(checked=True))
    ctx = make_context(tmp_path, http, adapter.account, password_env())
    creds = adapter.resolve_credentials(ctx)
    result = adapter.checkin(ctx, creds)

    assert result.status == "already_checked"
    assert result.points is not None
    assert result.points.gained is None
    assert result.points.current == 1000
    assert result.points.source == "api_unavailable"


def test_newapi_total_quota_is_not_current_balance(tmp_path):
    platform = platform_map()["dgb"]
    adapter = platform.account_adapter("default")
    http = FakeHttp(handler_for(current_data={"total_quota": 9999, "used_quota": 1}))
    ctx = make_context(tmp_path, http, adapter.account, password_env())
    creds = adapter.resolve_credentials(ctx)
    result = adapter.checkin(ctx, creds)

    assert result.points is not None
    assert result.points.gained == 10
    assert result.points.current is None
    assert result.points.source == "api_unavailable"
    assert result.points.current != 9999


def test_newapi_usage_token_fallback_after_user_self_401(tmp_path):
    def handler(method, url, **kwargs):
        if "/api/user/login" in url:
            return response({"success": True, "data": {"access_token": "at", "user": {"id": 1}}})
        if "/api/user/checkin" in url:
            if method == "GET":
                return response({"success": True, "data": {"stats": {"checked_in_today": False}}})
            return response({"success": True, "data": {"quota_awarded": 10}})
        if "/api/usage/token/" in url:
            return response({"success": True, "data": {"quota": 123}})
        if "/api/user/self" in url or "/api/data/self" in url:
            return response({"success": False}, 401)
        return response({}, 404)

    platform = platform_map()["dgb"]
    adapter = platform.account_adapter("default")
    http = FakeHttp(handler)
    ctx = make_context(tmp_path, http, adapter.account, password_env())
    creds = adapter.resolve_credentials(ctx)
    result = adapter.checkin(ctx, creds)

    assert result.status == "success"
    assert result.points is not None
    assert result.points.gained == 10
    assert result.points.current == 123
    assert result.points.source == "api_field"


def test_newapi_total_available_is_accepted(tmp_path):
    platform = platform_map()["aiaiai"]
    adapter = platform.account_adapter("default")
    http = FakeHttp(handler_for(current_data={"total_available": 777}))
    ctx = make_context(tmp_path, http, adapter.account, password_env())
    creds = adapter.resolve_credentials(ctx)
    result = adapter.checkin(ctx, creds)

    assert result.points is not None
    assert result.points.current == 777
    assert result.points.source == "api_field"
