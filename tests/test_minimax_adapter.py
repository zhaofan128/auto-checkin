import json

from src.platforms.minimax.adapter import MM_ACCOUNT, MiniMaxAdapter
from tests.fakes import FakeHttp, make_context, response


def test_minimax_claim_returns_today_points_without_total(tmp_path):
    def handler(method, url, **kwargs):
        if "/signin/status" in url:
            return response(
                {
                    "data": {
                        "days": [
                            {
                                "is_today": True,
                                "points": 100,
                                "day_no": 1,
                                "status": 2,
                            }
                        ]
                    }
                }
            )
        if "/signin/claim" in url:
            return response({"data": {"claim_result": 1}})
        return response({}, 404)

    http = FakeHttp(handler)
    ctx = make_context(
        tmp_path,
        http,
        MM_ACCOUNT,
        {"MM_CREDS": json.dumps({"access_token": "at", "refresh_token": "rt"})},
    )
    adapter = MiniMaxAdapter()
    creds = adapter.resolve_credentials(ctx)
    result = adapter.checkin(ctx, creds)

    assert result.status == "success"
    assert result.points is not None
    assert result.points.gained == 100
    assert result.points.current is None
    assert result.points.source == "api_unavailable"
    assert result.points.message == "平台未返回总积分"


def test_minimax_already_checked_does_not_fake_gained(tmp_path):
    def handler(method, url, **kwargs):
        if "/signin/status" in url:
            return response(
                {"data": {"days": [{"is_today": True, "points": 100, "status": 3}]}}
            )
        raise AssertionError("already checked must not claim")

    http = FakeHttp(handler)
    ctx = make_context(
        tmp_path,
        http,
        MM_ACCOUNT,
        {"MM_CREDS": json.dumps({"access_token": "at", "refresh_token": "rt"})},
    )
    adapter = MiniMaxAdapter()
    creds = adapter.resolve_credentials(ctx)
    result = adapter.checkin(ctx, creds)

    assert result.status == "already_checked"
    assert result.points is not None
    assert result.points.gained is None
    assert result.points.current is None
    assert result.points.source == "api_unavailable"
    assert result.points.message == "平台未返回总积分"


def test_minimax_resolve_does_not_overwrite_refreshed_token(tmp_path):
    http = FakeHttp(lambda method, url, **kwargs: response({}))
    ctx = make_context(
        tmp_path,
        http,
        MM_ACCOUNT,
        {"MM_CREDS": json.dumps({"access_token": "old-at", "refresh_token": "rt"})},
    )
    adapter = MiniMaxAdapter()
    adapter._access_tokens["minimax:default"] = "new-at"
    adapter.resolve_credentials(ctx)
    assert adapter._access_tokens["minimax:default"] == "new-at"


def test_minimax_refresh_returns_rotation(tmp_path):
    def handler(method, url, **kwargs):
        if "/oauth2/token" in url:
            return response({"access_token": "new-at", "refresh_token": "rt2"})
        return response({}, 404)

    http = FakeHttp(handler)
    ctx = make_context(
        tmp_path,
        http,
        MM_ACCOUNT,
        {"MM_CREDS": json.dumps({"refresh_token": "rt1"})},
    )
    adapter = MiniMaxAdapter()
    creds = adapter.resolve_credentials(ctx)
    rotation = adapter.refresh(ctx, creds)

    assert rotation is not None
    assert json.loads(rotation.new_value)["access_token"] == "new-at"
    assert adapter._access_tokens["minimax:default"] == "new-at"
