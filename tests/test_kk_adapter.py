from src.platforms.kk.adapter import KK_ACCOUNT, KKAdapter
from tests.fakes import FakeHttp, make_context, response


def base_env() -> dict[str, str]:
    return {"KK_TOKEN": "kk-token", "KK_TURNSTILE_TOKEN": "turnstile-secret"}


def handler(checked: bool = False):
    def inner(method, url, **kwargs):
        if "/api/user/checkin" in url:
            if method == "GET":
                return response(
                    {"success": True, "data": {"stats": {"checked_in_today": checked}}}
                )
            return response({"success": True, "data": {"quota_awarded": 10}})
        if "/api/user/self" in url or "/api/data/self" in url:
            return response({"success": True, "data": {"quota": 1000}})
        return response({}, 404)

    return inner


def test_kk_manual_token_success(tmp_path):
    http = FakeHttp(handler())
    ctx = make_context(tmp_path, http, KK_ACCOUNT, base_env())
    adapter = KKAdapter()
    creds = adapter.resolve_credentials(ctx)
    result = adapter.checkin(ctx, creds)

    assert result.status == "success"
    assert result.points is not None
    assert result.points.gained == 10
    assert result.points.current == 1000
    assert result.points.source == "api_field"
    assert result.turnstile is not None
    assert result.turnstile["mode"] == "manual_token"
    assert result.turnstile["token_present"] is True
    assert "turnstile-secret" not in result.message
    assert "turnstile-secret" not in str(result.turnstile)


def test_kk_without_manual_token_skips_with_turnstile_unavailable(tmp_path):
    http = FakeHttp(handler())
    ctx = make_context(
        tmp_path,
        http,
        KK_ACCOUNT,
        {"KK_TOKEN": "kk-token"},
    )
    adapter = KKAdapter()
    creds = adapter.resolve_credentials(ctx)
    result = adapter.checkin(ctx, creds)

    assert result.status == "skipped"
    assert result.skipped_reason == "turnstile_unavailable"
    assert result.points is not None
    assert result.points.gained is None
    assert result.points.current == 1000
    assert result.points.source == "turnstile_unavailable"
    assert "KK_TURNSTILE_TOKEN 未配置" in result.message
    assert result.turnstile is not None
    assert result.turnstile["mode"] == "browser_fallback"
    assert result.turnstile["token_present"] is False


def test_kk_already_checked_does_not_need_turnstile(tmp_path):
    http = FakeHttp(handler(checked=True))
    ctx = make_context(tmp_path, http, KK_ACCOUNT, {"KK_TOKEN": "kk-token"})
    adapter = KKAdapter()
    creds = adapter.resolve_credentials(ctx)
    result = adapter.checkin(ctx, creds)

    assert result.status == "already_checked"
    assert result.points is not None
    assert result.points.gained is None
    assert result.points.current == 1000
