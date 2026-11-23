"""TraeWork CN platform adapter."""

from __future__ import annotations

import json
from typing import Any, Mapping

from src.core.errors import ApiError, RefreshFailed, RefreshRequired
from src.core.models import AccountRef, CheckinResult, PointsResult, RotationResult
from src.core.points import normalize_points
from src.core.secrets import SecretSpec
from src.platforms.base import AccountContext, AccountSpec, Credentials
from src.platforms.util import as_dict, first_number, response_json
from src.platforms.traework.crypto import (
    checkin_headers,
    exchange_token,
    extract_credits,
)

TRAE_SECRET = SecretSpec(
    logical_name="traework_creds",
    primary="CHECKIN_TRAEWORK_CREDS",
    legacy=("TRAE_CREDS",),
    rolling=True,
)

TRAE_ACCOUNT = AccountRef(
    platform="traework",
    platform_name="TraeWork CN",
    account_id="cn",
    account_key="traework:cn",
    account_label="traework",
)

TRAE_SPEC = AccountSpec(
    platform="traework",
    platform_name="TraeWork CN",
    account_id="cn",
    account_key="traework:cn",
    secret_specs=(TRAE_SECRET,),
    rolling=True,
    schedule_profiles=frozenset({"morning", "midmorning", "afternoon", "manual"}),
    enabled_flag="TRAE_ENABLED",
    account_label="traework",
)

STATUS_PATH = "/trae/api/v2/ug/checkin_credits/status"
CLAIM_PATH = "/trae/api/v2/ug/checkin_credits/claim"
UG_HOST = "https://api.trae.cn"


class TraeWorkAdapter:
    def __init__(self, account: AccountRef = TRAE_ACCOUNT) -> None:
        self.account = account
        self._access_tokens: dict[str, str] = {}

    def resolve_credentials(self, ctx: AccountContext) -> Credentials:
        secret = ctx.secrets.require(TRAE_SECRET)
        try:
            data = json.loads(secret.value)
        except json.JSONDecodeError as exc:
            raise ApiError("TRAE_CREDS 不是合法 JSON") from exc
        if not isinstance(data, dict):
            raise ApiError("TRAE_CREDS 不是 JSON 对象")
        return Credentials(raw=secret.value, source_key=secret.source_key, data=data)

    def refresh(self, ctx: AccountContext, creds: Credentials) -> RotationResult | None:
        result = exchange_token(creds.data, ctx.http)
        if not result.token:
            raise RefreshFailed("TraeWork 刷新失败: " + result.note)
        self._access_tokens[ctx.account.account_key] = result.token
        if result.refresh_token and result.refresh_token != creds.data.get("refresh_token"):
            updated = dict(creds.data)
            updated["refresh_token"] = result.refresh_token
            return RotationResult(
                new_value=json.dumps(updated, ensure_ascii=False),
                reason="traework_refresh",
            )
        return None

    def checkin(self, ctx: AccountContext, creds: Credentials) -> CheckinResult:
        access_token = self._access_tokens.get(ctx.account.account_key)
        if not access_token:
            raise RefreshRequired("TraeWork 缺少 accessToken，需要刷新")

        headers = checkin_headers(access_token, creds.data)
        try:
            status_response = ctx.http.request(
                "POST",
                UG_HOST + STATUS_PATH,
                headers=headers,
                json_body={"req_source": 1},
            )
        except Exception as exc:  # noqa: BLE001
            raise ApiError(f"TraeWork 状态查询失败: {exc}") from exc
        status_payload = as_dict(response_json(status_response))
        data = as_dict(status_payload.get("data") or status_payload)
        code = status_payload.get("code")
        if code not in (0, "0", None):
            raise ApiError(
                f"TraeWork 状态查询异常 code={code} "
                f"message={str(status_payload.get('message') or '')[:120]}"
            )

        prior_current = first_number(data.get("total_credits"), data.get("credits"))
        checked = data.get("checked_in") is True

        if checked:
            points = normalize_points(
                gained=None,
                current=prior_current,
                unit="credits",
                explicit_source="api_unavailable",
                message="签到响应未返回本次积分",
            )
            return CheckinResult(status="already_checked", message="今日已签到", points=points)

        try:
            claim_response = ctx.http.request(
                "POST",
                UG_HOST + CLAIM_PATH,
                headers=headers,
                json_body={"req_source": 1},
            )
        except Exception as exc:  # noqa: BLE001
            raise ApiError(f"TraeWork 领取失败: {exc}") from exc
        claim_payload = as_dict(response_json(claim_response))
        claim_data = as_dict(claim_payload.get("data") or claim_payload)
        claim_code = claim_payload.get("code")
        claim_message = str(claim_payload.get("message") or "")
        gained, current_after = extract_credits(claim_data)

        if claim_code in (0, "0", None) and claim_response.status < 400:
            if gained is not None:
                points = normalize_points(
                    gained=gained,
                    current=current_after if current_after is not None else prior_current,
                    unit="credits",
                )
            elif current_after is not None and prior_current is not None:
                points = normalize_points(
                    gained=None,
                    current=current_after,
                    current_before=prior_current,
                    unit="credits",
                )
            else:
                points = normalize_points(
                    gained=None,
                    current=current_after if current_after is not None else prior_current,
                    unit="credits",
                    explicit_source="api_unavailable",
                    message="签到响应未返回本次积分",
                )
            return CheckinResult(status="success", message="签到成功", points=points)

        if "已签到" in claim_message or "already" in claim_message.lower():
            points = normalize_points(
                gained=None,
                current=current_after if current_after is not None else prior_current,
                unit="credits",
                explicit_source="api_unavailable",
                message="签到响应未返回本次积分",
            )
            return CheckinResult(status="already_checked", message="今日已签到", points=points)

        points = normalize_points(
            gained=None,
            current=current_after if current_after is not None else prior_current,
            unit="credits",
            explicit_source="api_unavailable",
            message="签到失败，签到响应未返回本次积分",
        )
        return CheckinResult(
            status="failed",
            message="TraeWork 签到失败: " + (claim_message or f"code={claim_code}"),
            points=points,
            error_type="api_error",
            error_detail=f"code={claim_code} message={claim_message}",
        )

    def fetch_points(self, ctx: AccountContext, creds: Credentials) -> PointsResult:
        return PointsResult(
            gained=None,
            current=None,
            unit=None,
            source="api_unavailable",
            message="TraeWork 积分在签到响应中解析",
        )


class TraeWorkPlatform:
    platform = "traework"
    accounts = (TRAE_SPEC,)

    def account_adapter(self, account_id: str) -> TraeWorkAdapter:
        if account_id != TRAE_ACCOUNT.account_id:
            raise KeyError(f"未知 TraeWork 账户: {account_id}")
        return TraeWorkAdapter(TRAE_ACCOUNT)


def traework_platform() -> TraeWorkPlatform:
    return TraeWorkPlatform()
