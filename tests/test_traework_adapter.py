import json

import pytest

from src.core.errors import RefreshRequired
from src.core.secrets import SecretResolver
from src.platforms.traework.adapter import (
    TRAE_ACCOUNT,
    STATUS_PATH,
    CLAIM_PATH,
    TraeWorkAdapter,
)
from src.platforms.traework.crypto import ExchangeResult
from tests.fakes import FakeHttp, make_context, response


def creds_json() -> str:
    return json.dumps(
        {
            "refresh_token": "rt-old",
            "device_id": "device",
            "machine_id": "machine",
            "uid": "uid",
            "device_key_pem": "pem",
            "device_pub_pem": "pub",
        }
    )


def context(tmp_path, http):
    return make_context(
        tmp_path,
        http,
        TRAE_ACCOUNT,
        {"TRAE_CREDS": creds_json()},
    )


def test_traework_success_uses_explicit_credits(tmp_path):
    def handler(method, url, **kwargs):
        if STATUS_PATH in url:
            return response({"code": 0, "data": {"checked_in": False, "credits": 1000}})
        if CLAIM_PATH in url:
            return response(
                {
                    "code": 0,
                    "data": {
                        "credits_earned_today": 50,
                        "total_credits": 1050,
                    },
                }
            )
        return response({"code": 404}, 404)

    http = FakeHttp(handler)
    ctx = context(tmp_path, http)
    adapter = TraeWorkAdapter()
    creds = adapter.resolve_credentials(ctx)
    adapter._access_tokens["traework:cn"] = "at"
    result = adapter.checkin(ctx, creds)

    assert result.status == "success"
    assert result.points is not None
    assert result.points.gained == 50
    assert result.points.current == 1050
    assert result.points.source == "api_field"


def test_traework_success_uses_diff_when_gained_missing(tmp_path):
    def handler(method, url, **kwargs):
        if STATUS_PATH in url:
            return response({"code": 0, "data": {"checked_in": False, "credits": 1000}})
        if CLAIM_PATH in url:
            return response({"code": 0, "data": {"total_credits": 1050}})
        return response({"code": 404}, 404)

    http = FakeHttp(handler)
    ctx = context(tmp_path, http)
    adapter = TraeWorkAdapter()
    creds = adapter.resolve_credentials(ctx)
    adapter._access_tokens["traework:cn"] = "at"
    result = adapter.checkin(ctx, creds)

    assert result.points is not None
    assert result.points.gained == 50
    assert result.points.current == 1050
    assert result.points.source == "diff_before_after"


def test_traework_already_checked_does_not_fake_gained(tmp_path):
    def handler(method, url, **kwargs):
        if STATUS_PATH in url:
            return response({"code": 0, "data": {"checked_in": True, "credits": 1000}})
        raise AssertionError("already checked must not claim")

    http = FakeHttp(handler)
    ctx = context(tmp_path, http)
    adapter = TraeWorkAdapter()
    creds = adapter.resolve_credentials(ctx)
    adapter._access_tokens["traework:cn"] = "at"
    result = adapter.checkin(ctx, creds)

    assert result.status == "already_checked"
    assert result.points is not None
    assert result.points.gained is None
    assert result.points.current == 1000
    assert result.points.source == "api_unavailable"


def test_traework_refresh_returns_rotation(tmp_path, monkeypatch):
    import src.platforms.traework.adapter as module

    monkeypatch.setattr(
        module,
        "exchange_token",
        lambda creds, http: ExchangeResult("at-new", "rt-new", "ok"),
    )
    http = FakeHttp(lambda method, url, **kwargs: response({}))
    ctx = context(tmp_path, http)
    adapter = TraeWorkAdapter()
    creds = adapter.resolve_credentials(ctx)
    rotation = adapter.refresh(ctx, creds)

    assert rotation is not None
    updated = json.loads(rotation.new_value)
    assert updated["refresh_token"] == "rt-new"
    assert adapter._access_tokens["traework:cn"] == "at-new"


def test_traework_requires_access_token(tmp_path):
    http = FakeHttp(lambda method, url, **kwargs: response({}))
    ctx = context(tmp_path, http)
    adapter = TraeWorkAdapter()
    creds = adapter.resolve_credentials(ctx)
    with pytest.raises(RefreshRequired):
        adapter.checkin(ctx, creds)
