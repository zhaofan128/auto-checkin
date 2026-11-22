"""MiniMax Code platform adapter."""

from __future__ import annotations

import json
from typing import Any, Mapping

from src.core.errors import ApiError, RefreshFailed, RefreshRequired
from src.core.models import AccountRef, CheckinResult, PointsResult, RotationResult
from src.core.points import normalize_points
from src.core.secrets import SecretSpec
from src.platforms.base import AccountContext, AccountSpec, Credentials
from src.platforms.util import as_dict, first_number, response_json

API_HOST = "https://agent.minimax.cn"
ACCOUNT_HOST = "https://account.minimax.cn"
CLIENT_ID = "mcode-public"
TZ = "Asia/Shanghai"

MM_SECRET = SecretSpec(
    logical_name="minimax_creds",
    primary="CHECKIN_MINIMAX_CREDS",
    legacy=("MM_CREDS",),
    rolling=True,
)
MM_ACCOUNT = AccountRef(
    platform="minimax",
    platform_name="MiniMax Code",
    account_id="default",
    account_key="minimax:default",
    account_label="minimax",
)
MM_SPEC = AccountSpec(
    platform="minimax",
    platform_name="MiniMax Code",
    account_id="default",
    account_key="minimax:default",
    secret_specs=(MM_SECRET,),
    rolling=True,
    schedule_profiles=frozenset({"morning", "midmorning", "afternoon", "manual"}),
    enabled_flag="MM_ENABLED",
    account_label="minimax",
)


class MiniMaxAdapter:
    def __init__(self, account: AccountRef = MM_ACCOUNT) -> None:
        self.account = account
        self._access_tokens: dict[str, str] = {}

    def resolve_credentials(self, ctx: AccountContext) -> Credentials:
        secret = ctx.secrets.require(MM_SECRET)
        try:
            data = json.loads(secret.value)
        except json.JSONDecodeError as exc:
            raise ApiError("MM_CREDS 不是合法 JSON") from exc
        if not isinstance(data, dict):
            raise ApiError("MM_CREDS 不是 JSON 对象")
        token = str(data.get("access_token") or "")
        if token and not self._access_tokens.get(ctx.account.account_key):
            self._access_tokens[ctx.account.account_key] = token
        return Credentials(raw=secret.value, source_key=secret.source_key, data=data)

    def refresh(self, ctx: AccountContext, creds: Credentials) -> RotationResult | None:
        if self._access_tokens.get(ctx.account.account_key):
            # Existing code refreshes only when the access token is rejected.
            return None
        refresh_token = str(creds.data.get("refresh_token") or "")
        if not refresh_token:
            raise RefreshFailed("MiniMax 缺少 refresh_token，需要重新授权")
        status, payload = self._call(
            ctx,
            "POST",
            ACCOUNT_HOST + "/oauth2/token",
            body={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": CLIENT_ID,
            },
        )
        data = as_dict(payload)
        token = str(data.get("access_token") or "")
        if status != 200 or not token:
            raise RefreshFailed(f"MiniMax 续期失败: HTTP {status}")
        self._access_tokens[ctx.account.account_key] = token
        updated = {
            "access_token": token,
            "refresh_token": str(data.get("refresh_token") or refresh_token),
            "expires_at": data.get("expires_at") or data.get("expires_in"),
            "token_type": "bearer",
        }
        return RotationResult(new_value=json.dumps(updated, ensure_ascii=False), reason="minimax_refresh")

    def checkin(self, ctx: AccountContext, creds: Credentials) -> CheckinResult:
        token = self._access_tokens.get(ctx.account.account_key)
        if not token:
            raise RefreshRequired("MiniMax 缺少 accessToken，需要刷新")
        status, payload = self._call(
            ctx,
            "GET",
            API_HOST + "/minimax-cloud/api/v1/signin/status?timezone_id=" + TZ,
            token=token,
        )
        if status == 401:
            self._access_tokens.pop(ctx.account.account_key, None)
            raise RefreshRequired("MiniMax accessToken 已失效，需要刷新")
        if status != 200 or not isinstance(payload, dict):
            raise ApiError(f"MiniMax 状态查询失败: HTTP {status}")

        data = as_dict(payload.get("data"))
        days = data.get("days") or []
        today = next((item for item in days if isinstance(item, dict) and item.get("is_today")), {})
        current = self._current_points(data, payload)
        today_points = first_number(today.get("points"))
        today_status = today.get("status")

        if today_status == 3:
            points = normalize_points(
                gained=None,
                current=current,
                unit="points",
                explicit_source="api_unavailable",
                message=(
                    "平台未返回总积分"
                    if current is None
                    else "今日已签到，签到响应未返回本次积分"
                ),
            )
            return CheckinResult(status="already_checked", message="今日已签到", points=points)

        if today_status != 2:
            points = normalize_points(
                gained=None,
                current=current,
                unit="points",
                explicit_source="api_unavailable",
                message=(
                    "平台未返回总积分"
                    if current is None
                    else "签到未开放，签到响应未返回本次积分"
                ),
            )
            return CheckinResult(
                status="skipped",
                message="MiniMax 签到未开放",
                points=points,
                skipped_reason="not_open",
            )

        claim_status, claim_payload = self._call(
            ctx,
            "POST",
            API_HOST + "/minimax-cloud/api/v1/signin/claim?timezone_id=" + TZ,
            token=token,
            body={},
        )
        claim_data = as_dict(as_dict(claim_payload).get("data"))
        claim_result = claim_data.get("claim_result")
        if claim_status != 200:
            raise ApiError(f"MiniMax 领取失败: HTTP {claim_status}")
        current = self._current_points(claim_data, claim_payload) or current

        if claim_result == 1 and today_points is not None:
            if current is not None:
                points = normalize_points(gained=today_points, current=current, unit="points")
            else:
                points = normalize_points(
                    gained=today_points,
                    current=None,
                    unit="points",
                    explicit_source="api_unavailable",
                    message="平台未返回总积分",
                )
            return CheckinResult(status="success", message="签到成功", points=points)

        if claim_result == 2:
            points = normalize_points(
                gained=None,
                current=current,
                unit="points",
                explicit_source="api_unavailable",
                message=(
                    "平台未返回总积分"
                    if current is None
                    else "今日已签到，签到响应未返回本次积分"
                ),
            )
            return CheckinResult(status="already_checked", message="今日已签到", points=points)

        points = normalize_points(
            gained=None,
            current=current,
            unit="points",
            explicit_source="api_unavailable",
            message=(
                "平台未返回总积分"
                if current is None
                else "领取结果未知，签到响应未返回本次积分"
            ),
        )
        return CheckinResult(status="unknown", message="MiniMax 领取结果未知", points=points)

    def fetch_points(self, ctx: AccountContext, creds: Credentials) -> PointsResult:
        return PointsResult(None, None, None, "api_unavailable", "MiniMax 积分在签到响应中解析")

    def _current_points(self, *containers: Mapping[str, Any]) -> int | float | None:
        for container in containers:
            data = as_dict(container.get("data") or container) if isinstance(container, Mapping) else {}
            value = first_number(
                data.get("total_credits"),
                data.get("credits"),
                data.get("total_points"),
                data.get("balance"),
            )
            if value is not None:
                return value
        return None

    def _call(
        self,
        ctx: AccountContext,
        method: str,
        url: str,
        *,
        token: str | None = None,
        body: Any = None,
    ) -> tuple[int, Any]:
        headers = {"Accept": "application/json", "User-Agent": "MiniMaxCheckin/2.0"}
        if token:
            headers["Authorization"] = "Bearer " + token
        try:
            response = ctx.http.request(method, url, headers=headers, json_body=body)
        except Exception as exc:  # noqa: BLE001
            raise ApiError(f"MiniMax 请求失败: {exc}") from exc
        return response.status, response_json(response)


class MiniMaxPlatform:
    platform = "minimax"
    accounts = (MM_SPEC,)

    def account_adapter(self, account_id: str) -> MiniMaxAdapter:
        if account_id != MM_ACCOUNT.account_id:
            raise KeyError(f"未知 MiniMax 账户: {account_id}")
        return MiniMaxAdapter(MM_ACCOUNT)


def minimax_platform() -> MiniMaxPlatform:
    return MiniMaxPlatform()
