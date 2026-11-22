"""LobsterAI (Youdao) platform adapter."""

from __future__ import annotations

import json
import uuid
from typing import Any, Mapping

from src.core.errors import ApiError, RefreshFailed, RefreshRequired
from src.core.models import AccountRef, CheckinResult, PointsResult, RotationResult
from src.core.points import normalize_points
from src.core.secrets import SecretSpec
from src.platforms.base import AccountContext, AccountSpec, Credentials
from src.platforms.util import as_dict, first_number, response_json

API_BASE = "https://lobsterai-server.youdao.com"
VERSION_API = "https://api-overmind.youdao.com/openapi/get/luna/hardware/lobsterai/prod/update"

LOBSTER_SECRET = SecretSpec(
    logical_name="lobster_creds",
    primary="CHECKIN_LOBSTER_CREDS",
    legacy=("LOBSTER_CREDS",),
    rolling=True,
)
LOBSTER_ACCOUNT = AccountRef(
    platform="lobsterai",
    platform_name="LobsterAI",
    account_id="default",
    account_key="lobsterai:default",
    account_label="lobsterai",
)
LOBSTER_SPEC = AccountSpec(
    platform="lobsterai",
    platform_name="LobsterAI",
    account_id="default",
    account_key="lobsterai:default",
    secret_specs=(LOBSTER_SECRET,),
    rolling=True,
    schedule_profiles=frozenset({"morning", "midmorning", "afternoon", "manual"}),
    enabled_flag="LOBSTER_ENABLED",
    account_label="lobsterai",
)


class LobsterAIAdapter:
    def __init__(self, account: AccountRef = LOBSTER_ACCOUNT) -> None:
        self.account = account
        self._access_tokens: dict[str, str] = {}
        self._versions: dict[str, str] = {}

    def resolve_credentials(self, ctx: AccountContext) -> Credentials:
        secret = ctx.secrets.require(LOBSTER_SECRET)
        try:
            data = json.loads(secret.value)
        except json.JSONDecodeError as exc:
            raise ApiError("LOBSTER_CREDS 不是合法 JSON") from exc
        if not isinstance(data, dict):
            raise ApiError("LOBSTER_CREDS 不是 JSON 对象")
        if data.get("access_token"):
            self._access_tokens[ctx.account.account_key] = str(data["access_token"])
        return Credentials(raw=secret.value, source_key=secret.source_key, data=data)

    def refresh(self, ctx: AccountContext, creds: Credentials) -> RotationResult | None:
        if self._access_tokens.get(ctx.account.account_key):
            return None
        version = self._version(ctx)
        body = {
            "firstKeyfrom": creds.data.get("first_keyfrom", ""),
            "latestKeyfrom": creds.data.get("latest_keyfrom", ""),
            "version": version,
            "refreshToken": creds.data.get("refresh_token", ""),
        }
        if creds.data.get("uuid"):
            body["uuid"] = creds.data["uuid"]
        if creds.data.get("user_id"):
            body["userId"] = creds.data["user_id"]
        status, payload = self._call(
            ctx,
            "POST",
            API_BASE + "/api/auth/refresh",
            body=body,
        )
        data = as_dict(as_dict(payload).get("data") or payload)
        token = str(data.get("accessToken") or "")
        if status != 200 or not token:
            raise RefreshFailed(f"LobsterAI 续期失败: HTTP {status}")
        self._access_tokens[ctx.account.account_key] = token
        updated = dict(creds.data)
        updated["access_token"] = token
        updated["refresh_token"] = str(data.get("refreshToken") or creds.data.get("refresh_token") or "")
        updated["expires_at"] = data.get("expiresAt") or creds.data.get("expires_at")
        return RotationResult(new_value=json.dumps(updated, ensure_ascii=False), reason="lobsterai_refresh")

    def checkin(self, ctx: AccountContext, creds: Credentials) -> CheckinResult:
        token = self._access_tokens.get(ctx.account.account_key)
        if not token:
            raise RefreshRequired("LobsterAI 缺少 accessToken，需要刷新")
        version = self._version(ctx)
        slot_status, slot_payload = self._call(
            ctx,
            "GET",
            API_BASE
            + "/api/client-activities/slot?placement=desktop_sidebar"
            + "&containerApiVersion=2&platform=win32&clientVersion="
            + version,
            token=token,
        )
        if slot_status == 401:
            self._access_tokens.pop(ctx.account.account_key, None)
            raise RefreshRequired("LobsterAI accessToken 已失效，需要刷新")
        if slot_status == 403:
            message = str(as_dict(slot_payload).get("message") or "")[:160]
            return CheckinResult(
                status="failed",
                message="LobsterAI 账号受限: " + (message or "403"),
                error_type="restricted",
                error_detail=message,
            )
        if slot_status != 200 or not isinstance(slot_payload, dict):
            raise ApiError(f"LobsterAI 槽位查询失败: HTTP {slot_status}")

        slot = as_dict(slot_payload.get("data"))
        activity = as_dict(slot.get("activity"))
        code = str(activity.get("activityCode") or slot.get("activityCode") or "")
        revision = activity.get("configRevision")
        if revision is None:
            revision = slot.get("configRevision")
        slot_state = slot.get("slotState") or activity.get("slotState")
        if slot_state != "available" or not code:
            points = normalize_points(
                gained=None,
                current=None,
                unit="credits",
                explicit_source="api_unavailable",
                message="LobsterAI 当前无可用签到活动",
            )
            return CheckinResult(
                status="skipped",
                message="LobsterAI 当前无可用签到活动",
                points=points,
                skipped_reason="inactive",
            )

        context_status, context_payload = self._call(
            ctx,
            "GET",
            API_BASE + f"/api/client-activities/{code}/context?configRevision={revision}",
            token=token,
        )
        if context_status != 200 or not isinstance(context_payload, dict):
            raise ApiError(f"LobsterAI 上下文查询失败: HTTP {context_status}")
        context = as_dict(context_payload.get("data"))
        state = as_dict(context.get("state"))
        actions = context.get("actions") or []
        current = self._current_points(state, context, context_payload)
        claimed = context.get("claimedToday")
        if claimed is None:
            claimed = state.get("claimedToday")
        if claimed or context.get("alreadyProcessed"):
            points = normalize_points(
                gained=None,
                current=current,
                unit="credits",
                explicit_source="idempotent_reset",
                message="平台返回额度重置，非签到获得积分",
            )
            return CheckinResult(status="already_checked", message="LobsterAI 今日已处理", points=points)

        if "check_in" not in actions:
            points = normalize_points(
                gained=None,
                current=current,
                unit="credits",
                explicit_source="api_unavailable",
                message="LobsterAI 当前无 check_in 动作",
            )
            return CheckinResult(
                status="skipped",
                message="LobsterAI 当前无 check_in 动作",
                points=points,
                skipped_reason="inactive",
            )

        claim_status, claim_payload = self._call(
            ctx,
            "POST",
            API_BASE + f"/api/client-activities/{code}/actions/check_in",
            token=token,
            body={
                "configRevision": revision,
                "idempotencyKey": uuid.uuid4().hex,
                "payload": {},
            },
        )
        if claim_status != 200 or not isinstance(claim_payload, dict):
            raise ApiError(f"LobsterAI 签到失败: HTTP {claim_status}")
        result = as_dict(as_dict(claim_payload.get("data")).get("result"))
        if result.get("alreadyProcessed"):
            points = normalize_points(
                gained=None,
                current=current,
                unit="credits",
                explicit_source="idempotent_reset",
                message="平台返回额度重置，非签到获得积分",
            )
            return CheckinResult(status="already_checked", message="LobsterAI 今日已处理", points=points)
        gained = self._extract_gained(result, claim_payload)
        current = self._current_points(result, state, context_payload) or current
        if gained is not None:
            if current is not None:
                points = normalize_points(gained=gained, current=current, unit="credits")
            else:
                points = normalize_points(
                    gained=gained,
                    current=None,
                    unit="credits",
                    explicit_source="api_unavailable",
                    message="当前积分接口不可用",
                )
            return CheckinResult(status="success", message="签到成功", points=points)

        points = normalize_points(
            gained=None,
            current=current,
            unit="credits",
            explicit_source="api_unavailable",
            message="签到响应未返回本次增加额度",
        )
        return CheckinResult(status="success", message="签到成功但未返回本次额度", points=points)

    def fetch_points(self, ctx: AccountContext, creds: Credentials) -> PointsResult:
        return PointsResult(None, None, None, "api_unavailable", "LobsterAI 积分在签到响应中解析")

    @staticmethod
    def _extract_gained(result: Mapping[str, Any], payload: Mapping[str, Any]) -> int | float | None:
        for container in (result, as_dict(payload.get("data")), payload):
            value = first_number(
                container.get("creditsGranted"),
                container.get("rewardCredits"),
                container.get("credits"),
            )
            if value is not None:
                return value
        return None

    @staticmethod
    def _current_points(*containers: Mapping[str, Any]) -> int | float | None:
        for container in containers:
            data = as_dict(container.get("state") or container.get("data") or container)
            value = first_number(
                data.get("total_credits"),
                data.get("credits"),
                data.get("balance"),
            )
            if value is not None:
                return value
        return None

    def _version(self, ctx: AccountContext) -> str:
        cached = self._versions.get(ctx.account.account_key)
        if cached:
            return cached
        status, payload = self._call(ctx, "GET", VERSION_API)
        data = as_dict(payload.get("data") or payload)
        version = str(as_dict(data.get("value") or data).get("version") or "")
        if status != 200 or not version:
            raise ApiError("LobsterAI 版本号获取失败")
        self._versions[ctx.account.account_key] = version
        return version

    def _call(
        self,
        ctx: AccountContext,
        method: str,
        url: str,
        *,
        token: str | None = None,
        body: Any = None,
    ) -> tuple[int, Any]:
        headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}
        if token:
            headers["Authorization"] = "Bearer " + token
        try:
            response = ctx.http.request(method, url, headers=headers, json_body=body)
        except Exception as exc:  # noqa: BLE001
            raise ApiError(f"LobsterAI 请求失败: {exc}") from exc
        return response.status, response_json(response)


class LobsterAIPlatform:
    platform = "lobsterai"
    accounts = (LOBSTER_SPEC,)

    def account_adapter(self, account_id: str) -> LobsterAIAdapter:
        if account_id != LOBSTER_ACCOUNT.account_id:
            raise KeyError(f"未知 LobsterAI 账户: {account_id}")
        return LobsterAIAdapter(LOBSTER_ACCOUNT)


def lobsterai_platform() -> LobsterAIPlatform:
    return LobsterAIPlatform()
