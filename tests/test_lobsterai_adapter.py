import json

from src.platforms.lobsterai.adapter import (
    API_BASE,
    LOBSTER_ACCOUNT,
    VERSION_API,
    LobsterAIAdapter,
)
from tests.fakes import FakeHttp, make_context, response


def lobster_env() -> dict[str, str]:
    return {
        "LOBSTER_CREDS": json.dumps(
            {
                "access_token": "at",
                "refresh_token": "rt",
                "first_keyfrom": "f",
                "latest_keyfrom": "l",
                "uuid": "u",
            }
        )
    }


def test_lobster_first_login_reset_is_not_gained(tmp_path):
    def handler(method, url, **kwargs):
        if VERSION_API in url:
            return response({"data": {"value": {"version": "1.0"}}})
        if "/api/client-activities/slot" in url:
            return response(
                {
                    "data": {
                        "slotState": "available",
                        "activity": {"activityCode": "act", "configRevision": 1},
                    }
                }
            )
        if "/context" in url:
            return response(
                {
                    "data": {
                        "claimedToday": True,
                        "state": {"rewardCredits": 20},
                        "actions": ["check_in"],
                    }
                }
            )
        return response({}, 404)

    http = FakeHttp(handler)
    ctx = make_context(tmp_path, http, LOBSTER_ACCOUNT, lobster_env())
    adapter = LobsterAIAdapter()
    creds = adapter.resolve_credentials(ctx)
    result = adapter.checkin(ctx, creds)

    assert result.status == "already_checked"
    assert result.points is not None
    assert result.points.gained is None
    assert result.points.source == "idempotent_reset"
    assert result.points.message == "平台返回额度重置，非签到获得积分"


def test_lobster_explicit_credits_become_gained(tmp_path):
    def handler(method, url, **kwargs):
        if VERSION_API in url:
            return response({"data": {"value": {"version": "1.0"}}})
        if "/api/client-activities/slot" in url:
            return response(
                {
                    "data": {
                        "slotState": "available",
                        "activity": {"activityCode": "act", "configRevision": 1},
                    }
                }
            )
        if "/context" in url:
            return response(
                {
                    "data": {
                        "claimedToday": False,
                        "state": {},
                        "actions": ["check_in"],
                    }
                }
            )
        if "/actions/check_in" in url:
            return response({"data": {"result": {"creditsGranted": 30}}})
        return response({}, 404)

    http = FakeHttp(handler)
    ctx = make_context(tmp_path, http, LOBSTER_ACCOUNT, lobster_env())
    adapter = LobsterAIAdapter()
    creds = adapter.resolve_credentials(ctx)
    result = adapter.checkin(ctx, creds)

    assert result.status == "success"
    assert result.points is not None
    assert result.points.gained == 30
    assert result.points.current is None
    assert result.points.source == "api_unavailable"
