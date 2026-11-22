"""Shared New-API gateway adapter for the six compatible sites."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

from src.core.errors import ApiError, SecretMissing
from src.core.models import AccountRef, CheckinResult, PointsResult
from src.core.points import normalize_points
from src.core.secrets import SecretSpec
from src.platforms.base import AccountContext, AccountSpec, Credentials
from src.platforms.util import as_dict, first_number, response_json

AuthMode = Literal["password", "token"]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"

CURRENT_BALANCE_KEYS = (
    "quota",
    "total_available",
    "balance",
    "remaining_quota",
    "remaining",
)
FORBIDDEN_CURRENT_KEYS = ("total_quota", "used_quota", "total_checkins")


@dataclass(frozen=True)
class NewApiSite:
    site_code: str
    platform_name: str
    base_url: str
    auth_mode: AuthMode
    token_spec: SecretSpec | None = None
    schedule_profiles: frozenset[str] = frozenset({"morning", "midmorning", "afternoon", "manual"})
    quota_window: bool = False

    @property
    def account(self) -> AccountRef:
        return AccountRef(
            platform=self.site_code,
            platform_name=self.platform_name,
            account_id="default",
            account_key=f"{self.site_code}:default",
            account_label=self.site_code,
        )

    @property
    def spec(self) -> AccountSpec:
        secrets = (self.token_spec,) if self.token_spec is not None else ()
        return AccountSpec(
            platform=self.site_code,
            platform_name=self.platform_name,
            account_id="default",
            account_key=f"{self.site_code}:default",
            secret_specs=secrets,
            rolling=False,
            schedule_profiles=self.schedule_profiles,
            account_label=self.site_code,
        )


@dataclass
class _Session:
    token: str = ""
    cookies: str = ""
    user_id: str = ""


class NewApiAdapter:
    def __init__(self, site: NewApiSite) -> None:
        self.site = site
        self.account = site.account

    def resolve_credentials(self, ctx: AccountContext) -> Credentials:
        if self.site.auth_mode == "token":
            if self.site.token_spec is None:
                raise SecretMissing(f"{self.site.site_code} 未配置 token spec")
            secret = ctx.secrets.require(self.site.token_spec)
            return Credentials(raw=secret.value, source_key=secret.source_key, data={"mode": "token"})
        password = ctx.secrets.resolve_password(self.site.site_code.upper())
        if password is None:
            raise SecretMissing(
                f"缺少 {self.site.site_code} 用户名/密码 Secret 键"
            )
        return Credentials(
            raw=password.username,
            source_key=password.source,
            data={"mode": "password"},
        )

    def checkin(self, ctx: AccountContext, creds: Credentials) -> CheckinResult:
        session = self._authenticate(ctx, creds)
        status_code, status_payload = self._call(
            ctx,
            "GET",
            self.site.base_url + "/api/user/checkin",
            session=session,
        )
        status_data = as_dict(status_payload.get("data"))
        if status_code != 200 or status_payload.get("success") is not True or not status_data:
            current, current_note = self._current_points(ctx, session)
            points = normalize_points(
                gained=None,
                current=current,
                unit="quota",
                explicit_source="api_unavailable",
                message="签到状态查询失败" + (f"；{current_note}" if current_note else ""),
            )
            return CheckinResult(
                status="failed",
                message=f"{self.site.platform_name} 签到状态查询失败: HTTP {status_code}",
                points=points,
                error_type="api_error",
                error_detail=str(status_payload.get("message") or "")[:200],
            )

        stats = as_dict(status_data.get("stats"))
        current, current_note = self._current_points(ctx, session)
        if stats.get("checked_in_today"):
            points = normalize_points(
                gained=None,
                current=current,
                unit="quota",
                explicit_source="api_unavailable",
                message="今日已签到，签到响应未返回 quota_awarded"
                + (f"；{current_note}" if current_note else ""),
            )
            return CheckinResult(status="already_checked", message="今日已签到", points=points)

        claim_code, claim_payload = self._call(
            ctx,
            "POST",
            self.site.base_url + "/api/user/checkin",
            session=session,
            body={},
        )
        claim_data = as_dict(claim_payload.get("data"))
        claim_message = str(claim_payload.get("message") or claim_payload.get("message_key") or "")
        if claim_payload.get("success") is True:
            gained = first_number(claim_data.get("quota_awarded"), claim_payload.get("quota_awarded"))
            fresh_current, fresh_note = self._current_points(ctx, session)
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
                    message="签到响应未返回 quota_awarded"
                    + (f"；{current_note}" if current_note else ""),
                )
            return CheckinResult(status="success", message=claim_message or "签到成功", points=points)

        if "已签到" in claim_message or "already" in claim_message.lower():
            points = normalize_points(
                gained=None,
                current=current,
                unit="quota",
                explicit_source="api_unavailable",
                message="今日已签到，签到响应未返回 quota_awarded",
            )
            return CheckinResult(status="already_checked", message="今日已签到", points=points)

        points = normalize_points(
            gained=None,
            current=current,
            unit="quota",
            explicit_source="api_unavailable",
            message="签到失败，签到响应未返回 quota_awarded"
            + (f"；{current_note}" if current_note else ""),
        )
        return CheckinResult(
            status="failed",
            message=f"{self.site.platform_name} 签到失败: " + (claim_message or f"HTTP {claim_code}"),
            points=points,
            error_type="api_error",
            error_detail=claim_message[:200],
        )

    def fetch_points(self, ctx: AccountContext, creds: Credentials) -> PointsResult:
        session = self._authenticate(ctx, creds)
        current, note = self._current_points(ctx, session)
        if current is None:
            return PointsResult(None, None, "quota", "api_unavailable", note or "当前余额接口不可用")
        return PointsResult(None, current, "quota", "api_field", None)

    def _authenticate(self, ctx: AccountContext, creds: Credentials) -> _Session:
        if self.site.auth_mode == "token":
            if not creds.raw:
                raise SecretMissing(f"{self.site.site_code} token 为空")
            return _Session(token=creds.raw)
        password = ctx.secrets.resolve_password(self.site.site_code.upper())
        if password is None:
            raise SecretMissing(f"缺少 {self.site.site_code} 用户名/密码 Secret 键")
        response = ctx.http.request(
            "POST",
            self.site.base_url + "/api/user/login",
            headers={"Content-Type": "application/json", "User-Agent": UA},
            json_body={"username": password.username, "password": password.password},
        )
        payload = response_json(response)
        data = as_dict(payload.get("data"))
        user = as_dict(data.get("user") or data)
        token = str(data.get("access_token") or "")
        cookies = "; ".join(
            cookie.split(";", 1)[0]
            for cookie in response.set_cookies
        )
        user_id = str(user.get("id") or "")
        if response.status != 200 or payload.get("success") is False or (not token and not cookies):
            raise ApiError(f"{self.site.platform_name} 登录失败: HTTP {response.status}")
        return _Session(token=token, cookies=cookies, user_id=user_id)

    def _current_points(
        self,
        ctx: AccountContext,
        session: _Session,
    ) -> tuple[int | float | None, str | None]:
        # /api/user/self may reject a browser-style login with 401. The token
        # usage endpoint is an explicit fallback; both are parsed for quota or
        # total_available, never total_quota/stats.
        for path in ("/api/user/self", "/api/data/self", "/api/usage/token/"):
            status, payload = self._call(
                ctx,
                "GET",
                self.site.base_url + path,
                session=session,
            )
            if status != 200 or payload.get("success") is False:
                continue
            data = as_dict(payload.get("data") or payload)
            value, _key = self._extract_balance(data)
            if value is not None:
                return value, None
        return None, "当前余额接口不可用（含 /api/usage/token/ 备选）"

    @staticmethod
    def _extract_balance(data: Mapping[str, Any]) -> tuple[int | float | None, str | None]:
        for key in CURRENT_BALANCE_KEYS:
            value = data.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                return value, key
        # Nested account blocks are common; never use total_quota/stats.
        for block_key in ("account", "quota", "data"):
            block = data.get(block_key)
            if isinstance(block, dict):
                value, key = NewApiAdapter._extract_balance(block)
                if value is not None:
                    return value, f"{block_key}.{key}"
        return None, None

    def _call(
        self,
        ctx: AccountContext,
        method: str,
        url: str,
        *,
        session: _Session,
        body: Any = None,
    ) -> tuple[int, dict[str, Any]]:
        headers = {
            "User-Agent": UA,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if session.token:
            headers["Authorization"] = "Bearer " + session.token
        if session.cookies:
            headers["Cookie"] = session.cookies
        if session.user_id:
            headers["New-Api-User"] = session.user_id
        try:
            response = ctx.http.request(method, url, headers=headers, json_body=body)
        except Exception as exc:  # noqa: BLE001
            raise ApiError(f"{self.site.platform_name} 请求失败: {exc}") from exc
        return response.status, as_dict(response_json(response))


class NewApiPlatform:
    def __init__(self, site: NewApiSite) -> None:
        self.site = site
        self.platform = site.site_code
        self.accounts = (site.spec,)

    def account_adapter(self, account_id: str) -> NewApiAdapter:
        if account_id != "default":
            raise KeyError(f"未知 {self.site.site_code} 账户: {account_id}")
        return NewApiAdapter(self.site)
