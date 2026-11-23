from src.browser.playwright_runtime import BrowserCheckinResult
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


def test_kk_without_manual_token_uses_browser_fallback(tmp_path, monkeypatch):
    import src.platforms.kk.adapter as module

    monkeypatch.setattr(
        module,
        "browser_checkin",
        lambda *args, **kwargs: BrowserCheckinResult(
            ok=True,
            status=200,
            payload={"success": True, "data": {"quota_awarded": 10}},
            turnstile_result="solved",
            attempts=1,
            clicks=0,
            duration_ms=100,
            token_present=True,
        ),
    )
    http = FakeHttp(handler())
    ctx = make_context(tmp_path, http, KK_ACCOUNT, {"KK_TOKEN": "kk-token"})
    adapter = KKAdapter()
    creds = adapter.resolve_credentials(ctx)
    result = adapter.checkin(ctx, creds)

    assert result.status == "success"
    assert result.points is not None
    assert result.points.gained == 10
    assert result.points.current == 1000
    assert result.turnstile is not None
    assert result.turnstile["mode"] == "browser_fallback"
    assert result.turnstile["result"] == "solved"
    assert result.turnstile["token_present"] is True


def test_kk_browser_timeout_is_failed_without_fake_points(tmp_path, monkeypatch):
    import src.platforms.kk.adapter as module

    monkeypatch.setattr(
        module,
        "browser_checkin",
        lambda *args, **kwargs: BrowserCheckinResult(
            ok=False,
            status=0,
            payload={},
            turnstile_result="timeout",
            attempts=3,
            clicks=2,
            duration_ms=90000,
            error="Turnstile 验证超时",
            token_present=False,
        ),
    )
    http = FakeHttp(handler())
    ctx = make_context(tmp_path, http, KK_ACCOUNT, {"KK_TOKEN": "kk-token"})
    adapter = KKAdapter()
    creds = adapter.resolve_credentials(ctx)
    result = adapter.checkin(ctx, creds)

    assert result.status == "failed"
    assert result.error_type == "turnstile_timeout"
    assert result.manual_required is True
    assert result.points is not None
    assert result.points.gained is None
    assert result.points.current == 1000
    assert result.points.source == "turnstile_unavailable"
    assert "Turnstile 验证超时" in result.message


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
