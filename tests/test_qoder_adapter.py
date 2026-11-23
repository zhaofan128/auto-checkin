import json

from src.platforms.qoder.adapter import (
    CAMPAIGNS_PATH,
    CN_ACCOUNT,
    GLOBAL_ACCOUNT,
    JOB_REFRESH_PATH,
    USAGE_PATH,
    qoder_platform,
)
from tests.fakes import FakeHttp, make_context, response


def test_qoder_cn_claim_and_current_points(tmp_path):
    def handler(method, url, **kwargs):
        if "/claim" in url:
            return response({"credits": 100})
        if CAMPAIGNS_PATH in url:
            return response(
                {
                    "campaigns": [
                        {
                            "actionType": "CLAIM_BENEFIT",
                            "claimStatus": "CLAIMABLE",
                            "campaignId": "campaign-1",
                        }
                    ]
                }
            )
        if USAGE_PATH in url:
            return response({"data": {"total_credits": 1200}})
        return response({}, 404)

    http = FakeHttp(handler)
    ctx = make_context(tmp_path, http, CN_ACCOUNT, {"QODER_CN_TOKEN": "dt-cn"})
    adapter = qoder_platform().account_adapter("cn")
    creds = adapter.resolve_credentials(ctx)
    result = adapter.checkin(ctx, creds)

    assert result.status == "success"
    assert result.points is not None
    assert result.points.gained == 100
    assert result.points.current == 1200
    assert result.points.source == "api_field"


def test_qoder_global_already_checked_is_separate(tmp_path):
    def handler(method, url, **kwargs):
        if CAMPAIGNS_PATH in url:
            return response(
                {
                    "campaigns": [
                        {
                            "actionType": "CLAIM_BENEFIT",
                            "claimStatus": "DONE",
                            "campaignId": "campaign-2",
                        }
                    ]
                }
            )
        if USAGE_PATH in url:
            return response({"data": {"total_credits": 800}})
        return response({}, 404)

    http = FakeHttp(handler)
    ctx = make_context(tmp_path, http, GLOBAL_ACCOUNT, {"QODER_GLOBAL_TOKEN": "dt-global"})
    adapter = qoder_platform().account_adapter("global")
    creds = adapter.resolve_credentials(ctx)
    result = adapter.checkin(ctx, creds)

    assert result.status == "already_checked"
    assert result.points is not None
    assert result.points.gained is None
    assert result.points.current == 800
    assert result.points.source == "api_unavailable"
    assert ctx.account.platform == "qoder_global"


def test_qoder_cn_device_refresh_uses_device_token(tmp_path):
    def handler(method, url, **kwargs):
        if url.endswith("/api/v1/deviceToken/refresh"):
            return response({"token": "dt-new", "refresh_token": "dr2"})
        if CAMPAIGNS_PATH in url:
            return response({"campaigns": []})
        if USAGE_PATH in url:
            return response({"qoderUsage": {"userQuota": {"remaining": 42}}})
        return response({}, 404)

    http = FakeHttp(handler)
    ctx = make_context(
        tmp_path,
        http,
        CN_ACCOUNT,
        {"QODER_CN_TOKEN": json.dumps({"refresh_token": "dr1"})},
    )
    adapter = qoder_platform().account_adapter("cn")
    creds = adapter.resolve_credentials(ctx)
    rotation = adapter.refresh(ctx, creds)

    assert rotation is not None
    assert json.loads(rotation.new_value)["refresh_token"] == "dr2"
    assert adapter._device_tokens["qoder:cn"] == "dt-new"
    result = adapter.checkin(ctx, creds)
    assert result.status == "skipped"
    assert result.points is not None
    assert result.points.current == 42


def test_qoder_cn_refresh_writes_new_credential(tmp_path):
    def handler(method, url, **kwargs):
        if JOB_REFRESH_PATH in url:
            return response({"token": "job-token", "refresh_token": "r2"})
        return response({}, 404)

    http = FakeHttp(handler)
    ctx = make_context(
        tmp_path,
        http,
        CN_ACCOUNT,
        {"QODER_CN_TOKEN": json.dumps({"refresh_token": "r1"})},
    )
    adapter = qoder_platform().account_adapter("cn")
    creds = adapter.resolve_credentials(ctx)
    rotation = adapter.refresh(ctx, creds)

    assert rotation is not None
    assert json.loads(rotation.new_value)["refresh_token"] == "r2"
    assert adapter._job_tokens["qoder:cn"] == "job-token"


def test_qoder_cn_and_global_have_distinct_platforms():
    platform = qoder_platform()
    assert [account.account_key for account in platform.accounts] == ["qoder:cn", "qoder:global"]
    assert [account.platform for account in platform.accounts] == ["qoder_cn", "qoder_global"]
