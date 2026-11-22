"""WorkBuddy platform adapter."""

from __future__ import annotations

import random
from typing import Any, Mapping

from src.core.errors import ApiError, RefreshFailed, RefreshRequired
from src.core.models import AccountRef, CheckinResult, PointsResult, RotationResult
from src.core.points import normalize_points
from src.core.secrets import SecretSpec
from src.platforms.base import AccountContext, AccountSpec, Credentials, PlatformAdapter

PLUGIN = "https://copilot.tencent.com"
REFRESH = "/v2/plugin/auth/token/refresh"
BILLING = "https://www.codebuddy.cn/v2"
STATUS = "/billing/meter/checkin-activity-status"
CHECKIN = "/billing/meter/daily-checkin"
TRAVEL = "https://www.workbuddy.cn"
T_STATUS = "/activity/growth/buddy/travel/status"
T_CONFIG = "/activity/growth/buddy/travel/config"
T_CLAIM = "/activity/growth/buddy/travel/claim"
T_DEPART = "/activity/growth/buddy/travel/depart"
UA = "WorkBuddy-Checkin-Script/2.0"

WB_SECRET = SecretSpec(
    logical_name="workbuddy_rt",
    primary="CHECKIN_WORKBUDDY_RT",
    legacy=("WB_RT",),
    rolling=True,
)

WORKBUDDY_ACCOUNT = AccountRef(
    platform="workbuddy",
    platform_name="WorkBuddy",
    account_id="default",
    account_key="workbuddy:default",
    account_label="workbuddy",
)

WORKBUDDY_SPEC = AccountSpec(
    platform="workbuddy",
    platform_name="WorkBuddy",
    account_id="default",
    account_key="workbuddy:default",
    secret_specs=(WB_SECRET,),
    rolling=True,
    schedule_profiles=frozenset({"morning", "midmorning", "afternoon", "manual"}),
    enabled_flag="WB_ENABLED",
    account_label="workbuddy",
)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_number(*values: Any) -> int | float | None:
    for value in values:
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return value
    return None


class WorkBuddyAdapter:
    def __init__(self, account: AccountRef = WORKBUDDY_ACCOUNT) -> None:
        self.account = account
        self._access_tokens: dict[str, str] = {}

    def resolve_credentials(self, ctx: AccountContext) -> Credentials:
        secret = ctx.secrets.require(WB_SECRET)
        return Credentials(raw=secret.value, source_key=secret.source_key)

    def refresh(self, ctx: AccountContext, creds: Credentials) -> RotationResult | None:
        status_code, body = self._request(
            ctx,
            "POST",
            PLUGIN + REFRESH,
            headers={
                "Content-Type": "application/json",
                "X-Refresh-Token": creds.raw,
                "X-Auth-Refresh-Source": "plugin",
                "X-Domain": "copilot.tencent.com",
            },
            json_body={},
        )
        payload = _as_dict(body)
        data = _as_dict(payload.get("data"))
        code = payload.get("code")
        access_token = str(data.get("accessToken") or "")
        if status_code < 200 or status_code >= 300 or code not in (0, "0", None) or not access_token:
            message = payload.get("msg") or payload.get("message") or "refresh failed"
            raise RefreshFailed(f"WorkBuddy 刷新失败: HTTP {status_code} code={code} msg={message}")
        self._access_tokens[ctx.account.account_key] = access_token
        new_refresh = str(data.get("refreshToken") or "")
        if new_refresh and new_refresh != creds.raw:
            return RotationResult(new_value=new_refresh, reason="workbuddy_refresh")
        return None

    def checkin(self, ctx: AccountContext, creds: Credentials) -> CheckinResult:
        access_token = self._access_tokens.get(ctx.account.account_key)
        if not access_token:
            raise RefreshRequired("WorkBuddy 缺少 accessToken，需要刷新")

        status_code, status_body = self._request(
            ctx,
            "POST",
            BILLING + STATUS,
            headers=self._auth(access_token),
            json_body={},
        )
        status_payload = _as_dict(status_body)
        status_data = _as_dict(status_payload.get("data"))
        status_code_value = status_payload.get("code")
        if status_code != 200 or status_code_value not in (0, "0", None):
            raise ApiError(
                f"WorkBuddy 状态查询失败: HTTP {status_code} "
                f"code={status_code_value} msg={status_payload.get('msg') or ''}"
            )

        checked = status_data.get("today_checked_in") is True
        prior_current = _first_number(status_data.get("total_credits"), status_data.get("balance"))
        unit = "credits" if prior_current is not None else None

        if ctx.dry_run:
            points = normalize_points(
                gained=None,
                current=prior_current,
                unit=unit,
                explicit_source="api_unavailable",
                message="dry-run：未执行签到，签到响应未返回本次积分",
            )
            if checked:
                return CheckinResult(
                    status="already_checked",
                    message="dry-run：今日已签到，未执行签到",
                    points=points,
                )
            return CheckinResult(
                status="skipped",
                message="dry-run：未执行签到",
                points=points,
                skipped_reason="dry_run",
            )

        if checked:
            travel = self._travel_suffix(ctx, access_token)
            points = normalize_points(
                gained=None,
                current=prior_current,
                unit=unit,
                explicit_source="api_unavailable",
                message="今日已签到，签到响应未返回本次积分",
            )
            return CheckinResult(
                status="already_checked",
                message="今日已签到" + travel,
                points=points,
            )

        claim_code, claim_body = self._request(
            ctx,
            "POST",
            BILLING + CHECKIN,
            headers=self._auth(access_token),
            json_body={},
        )
        claim_payload = _as_dict(claim_body)
        claim_data = _as_dict(claim_payload.get("data"))
        code = str(claim_payload.get("code", ""))
        message = str(claim_payload.get("msg") or claim_payload.get("message") or "")
        success_flag = claim_payload.get("success")
        current_after = _first_number(
            claim_data.get("total_credits"),
            claim_data.get("balance"),
        )
        unit = "credits" if (current_after is not None or prior_current is not None) else None

        if code == "10001" or "已签到" in message or "今天已签到" in message:
            travel = self._travel_suffix(ctx, access_token)
            current = current_after if current_after is not None else prior_current
            points = normalize_points(
                gained=None,
                current=current,
                unit=unit,
                explicit_source="api_unavailable",
                message="今日已签到，签到响应未返回本次积分",
            )
            return CheckinResult(
                status="already_checked",
                message="今日已签到" + travel,
                points=points,
            )

        if 200 <= claim_code < 300 and success_flag is not False and code in ("", "0", "200"):
            gained = _first_number(claim_data.get("credit"), claim_payload.get("credit"))
            if gained is not None:
                current = current_after if current_after is not None else prior_current
                points = normalize_points(
                    gained=gained,
                    current=current,
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
                    current=prior_current,
                    unit=unit,
                    explicit_source="api_unavailable",
                    message="签到响应未返回本次积分",
                )
            travel = self._travel_suffix(ctx, access_token)
            return CheckinResult(
                status="success",
                message="签到成功" + travel,
                points=points,
            )

        current = current_after if current_after is not None else prior_current
        points = normalize_points(
            gained=None,
            current=current,
            unit=unit,
            explicit_source="api_unavailable",
            message="签到失败，签到响应未返回本次积分" if current is not None else "签到失败且无法获取当前积分",
        )
        return CheckinResult(
            status="failed",
            message="WorkBuddy 签到失败: " + (message or f"HTTP {claim_code} code={code}"),
            points=points,
            error_type="api_error",
            error_detail=f"HTTP {claim_code} code={code} msg={message}",
        )

    def fetch_points(self, ctx: AccountContext, creds: Credentials) -> PointsResult:
        # WorkBuddy points are already captured during checkin/status.
        return PointsResult(
            gained=None,
            current=None,
            unit=None,
            source="api_unavailable",
            message="WorkBuddy 积分在签到响应中解析",
        )

    def _travel_suffix(self, ctx: AccountContext, access_token: str) -> str:
        try:
            result = self._travel(ctx, access_token)
            return f"; travel={result}" if result else ""
        except Exception as exc:  # noqa: BLE001 - travel must never fail check-in
            return f"; travel_error={type(exc).__name__}"

    def _travel(self, ctx: AccountContext, access_token: str) -> str:
        status_code, body = self._request(
            ctx,
            "GET",
            TRAVEL + T_STATUS,
            headers=self._auth(access_token),
        )
        payload = _as_dict(body)
        if status_code != 200 or payload.get("code") != 0:
            return "unavailable"
        state = _as_dict(payload.get("data"))

        if state.get("state") == "arrived":
            self._request(
                ctx,
                "POST",
                TRAVEL + T_CLAIM,
                headers=self._auth(access_token),
                json_body={},
            )
            status_code, body = self._request(
                ctx,
                "GET",
                TRAVEL + T_STATUS,
                headers=self._auth(access_token),
            )
            state = _as_dict(_as_dict(body).get("data")) if status_code == 200 else state

        if state.get("daily_limit_reached"):
            return "daily_limit_reached"
        if state.get("state") in (None, "", "idle"):
            config_code, config_body = self._request(
                ctx,
                "GET",
                TRAVEL + T_CONFIG,
                headers=self._auth(access_token),
            )
            locations = _as_dict(_as_dict(config_body).get("data")).get("locations") or []
            ids = [
                item.get("id")
                for item in locations
                if isinstance(item, dict) and item.get("id") is not None
            ]
            if config_code != 200 or not ids:
                return "no_location"
            location_id = random.choice(ids)
            depart_code, depart_body = self._request(
                ctx,
                "POST",
                TRAVEL + T_DEPART,
                headers=self._auth(access_token),
                json_body={"location_id": location_id},
            )
            if depart_code == 200 and _as_dict(depart_body).get("code") == 0:
                location = _as_dict(_as_dict(_as_dict(depart_body).get("data")).get("location"))
                return "departed:" + str(location.get("name") or location_id)
            return "depart_failed"
        return str(state.get("state") or "traveling")

    def _request(
        self,
        ctx: AccountContext,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        json_body: Any = None,
    ) -> tuple[int, Any]:
        try:
            response = ctx.http.request(method, url, headers=headers, json_body=json_body)
        except Exception as exc:  # noqa: BLE001 - network errors become typed API errors
            raise ApiError(f"WorkBuddy 请求失败: {exc}") from exc
        try:
            return response.status, response.json()
        except Exception:
            return response.status, {"raw": response.text[:300]}

    @staticmethod
    def _auth(access_token: str) -> dict[str, str]:
        return {
            "Authorization": "Bearer " + access_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": UA,
        }


class WorkBuddyPlatform:
    platform = "workbuddy"
    accounts = (WORKBUDDY_SPEC,)

    def account_adapter(self, account_id: str) -> WorkBuddyAdapter:
        if account_id != WORKBUDDY_ACCOUNT.account_id:
            raise KeyError(f"未知 WorkBuddy 账户: {account_id}")
        return WorkBuddyAdapter(WORKBUDDY_ACCOUNT)


def workbuddy_platform() -> WorkBuddyPlatform:
    return WorkBuddyPlatform()
