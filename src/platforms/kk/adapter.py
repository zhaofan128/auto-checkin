"""KK platform adapter.

Production path is manual_token. Browser evaluation is intentionally not
invoked by default because GitHub Actions data-center IPs are high-risk for
Cloudflare Turnstile.
"""

from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import quote

from src.browser.turnstile import manual_token_from_env
from src.core.errors import ApiError
from src.core.models import AccountRef, CheckinResult, PointsResult
from src.core.points import normalize_points
from src.core.secrets import SecretSpec
from src.platforms.base import AccountContext, AccountSpec, Credentials
from src.platforms.util import as_dict, first_number, response_json

KK_SECRET = SecretSpec(
    logical_name="kk_token",
    primary="CHECKIN_KK_TOKEN",
    legacy=("KK_TOKEN",),
    rolling=False,
)
KK_ACCOUNT = AccountRef(
    platform="kk",
    platform_name="KK",
    account_id="default",
    account_key="kk:default",
    account_label="kk",
)
KK_SPEC = AccountSpec(
    platform="kk",
    platform_name="KK",
    account_id="default",
    account_key="kk:default",
    secret_specs=(KK_SECRET,),
    rolling=False,
    schedule_profiles=frozenset({"morning", "midmorning", "afternoon", "manual"}),
    account_label="kk",
)


class KKAdapter:
    def __init__(self, account: AccountRef = KK_ACCOUNT) -> None:
        self.account = account

    def resolve_credentials(self, ctx: AccountContext) -> Credentials:
        secret = ctx.secrets.require(KK_SECRET)
        return Credentials(raw=secret.value, source_key=secret.source_key)

    def refresh(self, ctx: AccountContext, creds: Credentials):
        return None

    def checkin(self, ctx: AccountContext, creds: Credentials) -> CheckinResult:
        base = (ctx.secrets.env.get("KK_BASE_URL") or "https://kk.xjidjjdj.xyz").rstrip("/")
        status_code, status_payload = self._call(
            ctx,
            "GET",
            base + "/api/user/checkin",
            token=creds.raw,
        )
        status_data = as_dict(status_payload.get("data"))
        stats = as_dict(status_data.get("stats"))
        current, current_note = self._current_points(ctx, base, creds.raw)
        if status_code != 200 or status_payload.get("success") is not True:
            points = normalize_points(
                gained=None,
                current=current,
                unit="quota",
                explicit_source="api_unavailable",
                message="签到状态查询失败" + (f"；{current_note}" if current_note else ""),
            )
            return CheckinResult(
                status="failed",
                message=f"KK 签到状态查询失败: HTTP {status_code}",
                points=points,
                error_type="api_error",
            )

        if stats.get("checked_in_today"):
            points = normalize_points(
                gained=None,
                current=current,
                unit="quota",
                explicit_source="api_unavailable",
                message="今日已签到，签到响应未返回本次积分",
            )
            return CheckinResult(status="already_checked", message="今日已签到", points=points)

        manual_token = manual_token_from_env(ctx.secrets.env)
        if not manual_token:
            points = normalize_points(
                gained=None,
                current=current,
                unit="quota",
                explicit_source="turnstile_unavailable",
                message=(
                    "KK_TURNSTILE_TOKEN 未配置，浏览器 fallback 在 GitHub Actions "
                    "环境通过率极低"
                ),
            )
            return CheckinResult(
                status="skipped",
                message="KK_TURNSTILE_TOKEN 未配置，浏览器 fallback 在 GitHub Actions 环境通过率极低",
                points=points,
                skipped_reason="turnstile_unavailable",
                manual_required=True,
                turnstile={
                    "mode": "browser_fallback",
                    "result": "skipped",
                    "manual_required": True,
                    "token_present": False,
                },
            )

        claim_code, claim_payload = self._call(
            ctx,
            "POST",
            base + "/api/user/checkin?turnstile=" + quote(manual_token, safe=""),
            token=creds.raw,
            body={},
        )
        claim_data = as_dict(claim_payload.get("data"))
        claim_message = str(claim_payload.get("message") or claim_payload.get("message_key") or "")
        if claim_payload.get("success") is True:
            gained = first_number(claim_data.get("quota_awarded"), claim_payload.get("quota_awarded"))
            fresh_current, fresh_note = self._current_points(ctx, base, creds.raw)
            if fresh_current is not None:
                current = fresh_current
            if fresh_note:
                current_note = fresh_note
            if gained is not None and current is not None:
                points = normalize_points(gained=gained, current=current, unit="quota")
            elif gained is not None:
                points = normalize_points(
                    gained=gained,
                    current=None,
                    unit="quota",
                    explicit_source="api_unavailable",
                    message="当前余额接口不可用" + (f"；{current_note}" if current_note else ""),
                )
            else:
                points = normalize_points(
                    gained=None,
                    current=current,
                    unit="quota",
                    explicit_source="api_unavailable",
                    message="签到响应未返回 quota_awarded",
                )
            return CheckinResult(
                status="success",
                message="签到成功",
                points=points,
                turnstile={
                    "mode": "manual_token",
                    "result": "manual_token",
                    "manual_required": False,
                    "token_present": True,
                },
            )

        if "已签到" in claim_message or "already" in claim_message.lower():
            points = normalize_points(
                gained=None,
                current=current,
                unit="quota",
                explicit_source="api_unavailable",
                message="今日已签到，签到响应未返回本次积分",
            )
            return CheckinResult(status="already_checked", message="今日已签到", points=points)

        points = normalize_points(
            gained=None,
            current=current,
            unit="quota",
            explicit_source="api_unavailable",
            message="签到失败，签到响应未返回本次积分",
        )
        return CheckinResult(
            status="failed",
            message="KK 签到失败: " + (claim_message or f"HTTP {claim_code}"),
            points=points,
            error_type="api_error",
            error_detail=claim_message[:200],
        )

    def fetch_points(self, ctx: AccountContext, creds: Credentials) -> PointsResult:
        base = (ctx.secrets.env.get("KK_BASE_URL") or "https://kk.xjidjjdj.xyz").rstrip("/")
        current, note = self._current_points(ctx, base, creds.raw)
        if current is None:
            return PointsResult(None, None, "quota", "api_unavailable", note or "当前余额接口不可用")
        return PointsResult(None, current, "quota", "api_field", None)

    def _current_points(
        self,
        ctx: AccountContext,
        base: str,
        token: str,
    ) -> tuple[int | float | None, str | None]:
        for path in ("/api/user/self", "/api/data/self"):
            status, payload = self._call(ctx, "GET", base + path, token=token)
            if status != 200 or payload.get("success") is False:
                continue
            data = as_dict(payload.get("data") or payload)
            value = first_number(
                data.get("quota"),
                data.get("total_available"),
                data.get("balance"),
                data.get("remaining_quota"),
            )
            if value is not None:
                return value, None
        return None, "当前余额接口不可用"

    def _call(
        self,
        ctx: AccountContext,
        method: str,
        url: str,
        *,
        token: str,
        body: Any = None,
    ) -> tuple[int, Mapping[str, Any]]:
        headers = {
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AutoCheckin/2.0",
        }
        try:
            response = ctx.http.request(method, url, headers=headers, json_body=body)
        except Exception as exc:  # noqa: BLE001
            raise ApiError(f"KK 请求失败: {exc}") from exc
        return response.status, as_dict(response_json(response))


class KKPlatform:
    platform = "kk"
    accounts = (KK_SPEC,)

    def account_adapter(self, account_id: str) -> KKAdapter:
        if account_id != KK_ACCOUNT.account_id:
            raise KeyError(f"未知 KK 账户: {account_id}")
        return KKAdapter(KK_ACCOUNT)


def kk_platform() -> KKPlatform:
    return KKPlatform()
