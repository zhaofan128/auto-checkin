"""Qoder CN / Global platform adapter.

One module, two isolated account targets. CN and Global have separate secrets,
state files, locks and log platform values.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from src.core.errors import ApiError, RefreshFailed, RefreshRequired
from src.core.models import AccountRef, CheckinResult, PointsResult, RotationResult
from src.core.points import normalize_points
from src.core.secrets import SecretSpec
from src.platforms.base import AccountContext, AccountSpec, Credentials
from src.platforms.util import as_dict, first_number, response_json

UA = "Qoder/claim"
CAMPAIGNS_PATH = "/sash/api/v1/me/campaigns"
USAGE_PATH = "/sash/api/v2/me/usage"
DEVICE_REFRESH_PATH = "/api/v1/deviceToken/refresh"
JOB_REFRESH_PATH = "/api/v1/jobToken/refresh"
JOB_EXCHANGE_PATH = "/api/v1/jobToken/exchange"

CN_SECRET = SecretSpec(
    logical_name="qoder_cn_token",
    primary="CHECKIN_QODER_CN_TOKEN",
    legacy=("QODER_CN_TOKEN",),
    rolling=True,
)
GLOBAL_SECRET = SecretSpec(
    logical_name="qoder_global_token",
    primary="CHECKIN_QODER_GLOBAL_TOKEN",
    legacy=("QODER_GLOBAL_TOKEN",),
    rolling=False,
)

CN_ACCOUNT = AccountRef(
    platform="qoder_cn",
    platform_name="Qoder CN",
    account_id="cn",
    account_key="qoder:cn",
    account_label="qoder-cn",
)
GLOBAL_ACCOUNT = AccountRef(
    platform="qoder_global",
    platform_name="Qoder Global",
    account_id="global",
    account_key="qoder:global",
    account_label="qoder-global",
)

CN_SPEC = AccountSpec(
    platform="qoder_cn",
    platform_name="Qoder CN",
    account_id="cn",
    account_key="qoder:cn",
    secret_specs=(CN_SECRET,),
    rolling=True,
    schedule_profiles=frozenset({"qoder", "morning", "midmorning", "afternoon", "manual"}),
    enabled_flag="QODER_ENABLED",
    account_label="qoder-cn",
)
GLOBAL_SPEC = AccountSpec(
    platform="qoder_global",
    platform_name="Qoder Global",
    account_id="global",
    account_key="qoder:global",
    secret_specs=(GLOBAL_SECRET,),
    rolling=False,
    schedule_profiles=frozenset({"qoder", "morning", "midmorning", "afternoon", "manual"}),
    account_label="qoder-global",
)


@dataclass(frozen=True)
class QoderAccountConfig:
    account: AccountRef
    base_url: str
    secret: SecretSpec
    rolling: bool


QODER_CONFIGS = {
    "cn": QoderAccountConfig(CN_ACCOUNT, "https://openapi.qoder.com.cn", CN_SECRET, True),
    "global": QoderAccountConfig(GLOBAL_ACCOUNT, "https://openapi.qoder.sh", GLOBAL_SECRET, False),
}


def _job_token(payload: Mapping[str, Any]) -> str:
    return str(
        payload.get("token")
        or payload.get("access_token")
        or payload.get("device_token")
        or ""
    ).strip()


class QoderAdapter:
    def __init__(self, config: QoderAccountConfig) -> None:
        self.config = config
        self.account = config.account
        self._job_tokens: dict[str, str] = {}
        self._device_tokens: dict[str, str] = {}

    def resolve_credentials(self, ctx: AccountContext) -> Credentials:
        secret = ctx.secrets.require(self.config.secret)
        if secret.value.startswith("dt-"):
            self._device_tokens[ctx.account.account_key] = secret.value
        elif secret.value.startswith("{"):
            try:
                data = json.loads(secret.value)
            except ValueError:
                data = {}
            device_token = str(data.get("device_token") or data.get("deviceToken") or "").strip()
            if device_token:
                self._device_tokens[ctx.account.account_key] = device_token
        return Credentials(raw=secret.value, source_key=secret.source_key)

    def refresh(self, ctx: AccountContext, creds: Credentials) -> RotationResult | None:
        if not self.config.rolling:
            return None
        self.bind_http(ctx)
        if self.config.account.account_id == "cn":
            device_token, device_credential, device_error = self._refresh_device_token(creds.raw)
            if device_token:
                self._device_tokens[ctx.account.account_key] = device_token
                if device_credential:
                    return RotationResult(new_value=device_credential, reason="qoder_device_refresh")
            if device_error:
                # A credential with only a job refresh token is still valid.
                pass
        token, new_credential, error = self._resolve_job_token(creds.raw)
        if error:
            raise RefreshFailed("Qoder 刷新失败: " + error)
        if token:
            self._job_tokens[ctx.account.account_key] = token
        if new_credential:
            return RotationResult(new_value=new_credential, reason="qoder_refresh")
        return None

    def checkin(self, ctx: AccountContext, creds: Credentials) -> CheckinResult:
        self.bind_http(ctx)
        token = self._device_tokens.get(ctx.account.account_key) or self._job_tokens.get(
            ctx.account.account_key
        )
        if not token:
            if self.config.rolling:
                raise RefreshRequired("Qoder 缺少可用 token，需要刷新")
            token, _, error = self._resolve_job_token(creds.raw)
            if error or not token:
                raise ApiError("Qoder 静态令牌不可用: " + (error or "empty"))
            self._job_tokens[ctx.account.account_key] = token

        status, payload = self._call(
            "GET",
            self.config.base_url + CAMPAIGNS_PATH,
            token=token,
        )
        if status != 200 or not isinstance(payload, dict):
            raise ApiError(f"Qoder 活动查询失败: HTTP {status} {str(payload)[:160]}")

        campaigns = payload.get("campaigns") or []
        benefits = [
            item for item in campaigns
            if isinstance(item, dict) and item.get("actionType") == "CLAIM_BENEFIT"
        ]
        current, current_note = self._current_points(token)
        if not benefits:
            actions = sorted(
                {
                    str(item.get("actionType") or "")
                    for item in campaigns
                    if isinstance(item, dict)
                }
            )
            statuses = sorted(
                {
                    str(item.get("claimStatus") or "")
                    for item in campaigns
                    if isinstance(item, dict)
                }
            )
            kind = self._token_kind(creds.raw)
            shape = ""
            if campaigns and isinstance(campaigns[0], dict):
                first = campaigns[0]
                benefit = as_dict(first.get("benefit"))
                shape = (
                    f"; keys={sorted(first.keys())}; "
                    f"campaign_key={str(first.get('campaignKey') or '')[:80]}; "
                    f"placements={str(first.get('placements') or '')[:80]}; "
                    f"benefit_keys={sorted(benefit.keys())}; "
                    f"amount={first_number(benefit.get('amount'), first.get('amount'))}"
                )
            diagnostic = (
                f"无签到活动; campaigns={len(campaigns)}; "
                f"actions={actions}; statuses={statuses}; token={kind}; "
                f"machine={self._machine_present()}; usage={current_note or 'ok'}{shape}"
            )
            points = normalize_points(
                gained=None,
                current=current,
                unit="credits",
                explicit_source="api_unavailable",
                message=diagnostic,
            )
            return CheckinResult(
                status="skipped",
                message=diagnostic,
                points=points,
                skipped_reason="no_activity",
            )

        campaign = benefits[0]
        claimable = campaign.get("claimStatus") == "CLAIMABLE"
        gained = None
        claim_status = "already"
        claim_message = ""
        if claimable:
            claim_status_code, claim_payload = self._call(
                "POST",
                self.config.base_url + f"/sash/api/v1/me/campaigns/{campaign.get('campaignId')}/claim",
                token=token,
                body={},
            )
            claim_data = as_dict(claim_payload)
            gained = self._extract_gained(claim_data)
            if claim_status_code == 200:
                claim_status = "claimed"
            else:
                claim_status = "failed"
                claim_message = str(claim_data.get("message") or claim_data.get("msg") or "")[:160]

        if claim_status == "failed":
            points = normalize_points(
                gained=None,
                current=current,
                unit="credits",
                explicit_source="api_unavailable",
                message=claim_message or "Qoder 领取失败",
            )
            return CheckinResult(
                status="failed",
                message="Qoder 签到失败: " + (claim_message or "claim failed"),
                points=points,
                error_type="api_error",
                error_detail=claim_message,
            )

        if gained is not None and current is not None:
            points = normalize_points(gained=gained, current=current, unit="credits")
        elif gained is not None:
            points = normalize_points(
                gained=gained,
                current=None,
                unit="credits",
                explicit_source="api_unavailable",
                message=current_note or "当前积分接口不可用",
            )
        else:
            points = normalize_points(
                gained=None,
                current=current,
                unit="credits",
                explicit_source="api_unavailable",
                message=(
                    "今日已签到，签到活动未返回本次 gained"
                    if claim_status == "already"
                    else "签到活动未返回本次 gained"
                ),
            )

        return CheckinResult(
            status="already_checked" if claim_status == "already" else "success",
            message="今日已签到" if claim_status == "already" else "签到成功",
            points=points,
        )

    def fetch_points(self, ctx: AccountContext, creds: Credentials) -> PointsResult:
        self.bind_http(ctx)
        token = self._device_tokens.get(ctx.account.account_key) or self._job_tokens.get(
            ctx.account.account_key
        )
        if not token:
            return PointsResult(None, None, None, "api_unavailable", "Qoder 尚未获取 token")
        current, note = self._current_points(token)
        if current is None:
            return PointsResult(None, None, "credits", "api_unavailable", note or "usage 接口不可用")
        return PointsResult(None, current, "credits", "api_field", None)

    def _refresh_device_token(
        self, raw: str
    ) -> tuple[str | None, str | None, str | None]:
        value = (raw or "").strip()
        if value.startswith("dt-"):
            return value, None, None
        refresh = value
        pat = ""
        if value.startswith("{"):
            try:
                data = json.loads(value)
            except ValueError:
                return None, None, "Qoder 凭据 JSON 解析失败"
            refresh = str(data.get("refresh_token") or data.get("refreshToken") or "").strip()
            pat = str(data.get("pat") or data.get("personal_token") or "").strip()
        if not refresh:
            return None, None, "未提供 device refresh_token"
        status, payload = self._call(
            "POST",
            self.config.base_url + DEVICE_REFRESH_PATH,
            body={"refresh_token": refresh},
        )
        body = as_dict(payload)
        token = _job_token(body) if status == 200 else ""
        if not token:
            return None, None, f"deviceToken/refresh 失败 HTTP {status}"
        new_refresh = str(body.get("refresh_token") or body.get("refreshToken") or refresh)
        credential = {"refresh_token": new_refresh}
        if pat:
            credential["pat"] = pat
        return token, json.dumps(credential, ensure_ascii=False), None

    def _resolve_job_token(self, raw: str) -> tuple[str | None, str | None, str | None]:
        value = (raw or "").strip()
        refresh = ""
        pat = ""
        if value.startswith("{"):
            try:
                data = json.loads(value)
            except ValueError:
                return None, None, "Qoder 凭据 JSON 解析失败"
            refresh = str(data.get("refresh_token") or "").strip()
            pat = str(data.get("pat") or data.get("personal_token") or "").strip()
        elif value.startswith("pt-"):
            pat = value
        elif value.startswith("dt-"):
            return value, None, None
        else:
            refresh = value

        errors: list[str] = []
        if refresh:
            status, payload = self._call(
                "POST",
                self.config.base_url + JOB_REFRESH_PATH,
                body={"refresh_token": refresh},
            )
            token = _job_token(as_dict(payload)) if status == 200 else ""
            if token:
                credential = {"refresh_token": str(as_dict(payload).get("refresh_token") or refresh)}
                if pat:
                    credential["pat"] = pat
                return token, json.dumps(credential, ensure_ascii=False), None
            errors.append(f"刷新令牌失败 HTTP {status}")

        if pat:
            status, payload = self._call(
                "POST",
                self.config.base_url + JOB_EXCHANGE_PATH,
                body={"personal_token": pat},
            )
            token = _job_token(as_dict(payload)) if status == 200 else ""
            if token:
                credential = {"refresh_token": str(as_dict(payload).get("refresh_token") or ""), "pat": pat}
                return token, json.dumps(credential, ensure_ascii=False), None
            errors.append(f"个人令牌换取失败 HTTP {status}")

        return None, None, "；".join(errors) or "未提供有效凭据"

    def _current_points(self, token: str) -> tuple[int | float | None, str | None]:
        status, payload = self._call(
            "GET",
            self.config.base_url + USAGE_PATH,
            token=token,
        )
        if status != 200 or not isinstance(payload, dict):
            return None, f"Qoder usage 接口不可用 (HTTP {status})"
        usage = as_dict(payload.get("qoderUsage") or payload.get("qoder_usage"))
        if usage:
            pools = (
                as_dict(usage.get("userQuota") or usage.get("user_quota")),
                as_dict(usage.get("addOnQuota") or usage.get("add_on_quota")),
                as_dict(
                    usage.get("orgResourcePackage")
                    or usage.get("org_resource_package")
                ),
            )
            total_remaining = 0.0
            found = False
            for pool in pools:
                remaining = first_number(pool.get("remaining"), pool.get("remaining_quota"))
                if remaining is None:
                    cap = first_number(pool.get("total"), pool.get("cap"))
                    used = first_number(pool.get("used"))
                    if cap is not None and used is not None:
                        remaining = cap - used
                if remaining is not None:
                    total_remaining += remaining
                    found = True
            if found:
                return total_remaining, None
        data = as_dict(payload.get("data") or payload)
        current = first_number(
            data.get("total_credits"),
            data.get("totalCredits"),
            data.get("credits"),
            data.get("balance"),
        )
        if current is None:
            return None, "Qoder usage v2 未返回 quota remaining"
        return current, None

    @staticmethod
    def _token_kind(raw: str) -> str:
        value = (raw or "").strip()
        if value.startswith("{"):
            try:
                data = json.loads(value)
            except ValueError:
                return "json:invalid"
            return "json:" + ",".join(sorted(data.keys()))
        for prefix in ("dt-", "pt-", "jt-", "eyJ"):
            if value.startswith(prefix):
                return prefix
        return "opaque"

    def _machine_headers(self) -> dict[str, str]:
        prefix = "QODER_CN" if self.config.account.account_id == "cn" else "QODER_GLOBAL"
        token = (
            self.ctx_env.get(prefix + "_MACHINE_TOKEN")
            or self.ctx_env.get("QODER_MACHINE_TOKEN")
            or ""
        ).strip()
        type_ = (
            self.ctx_env.get(prefix + "_MACHINE_TYPE")
            or self.ctx_env.get("QODER_MACHINE_TYPE")
            or ""
        ).strip()
        headers: dict[str, str] = {}
        if token:
            headers["Cosy-MachineToken"] = token
        if type_:
            headers["Cosy-MachineType"] = type_
        return headers

    def _machine_present(self) -> str:
        headers = self._machine_headers()
        return "yes" if "Cosy-MachineToken" in headers and "Cosy-MachineType" in headers else "no"

    @staticmethod
    def _extract_gained(payload: Mapping[str, Any]) -> int | float | None:
        data = as_dict(payload.get("data") or payload)
        for container in (data, payload):
            value = first_number(
                container.get("gained"),
                container.get("credits"),
                container.get("reward_credits"),
                container.get("benefit_credits"),
                container.get("amount"),
            )
            if value is not None:
                return value
        return None

    def _call(
        self,
        method: str,
        url: str,
        *,
        token: str | None = None,
        body: Any = None,
    ) -> tuple[int, Any]:
        headers: dict[str, str] = {
            "Cosy-ClientType": "10",
            "User-Agent": UA,
            "Accept": "application/json",
            **self._machine_headers(),
        }
        if token:
            headers["Authorization"] = "Bearer " + token
        try:
            response = self.ctx_http.request(  # type: ignore[attr-defined]
                method,
                url,
                headers=headers,
                json_body=body,
            )
        except AttributeError:
            raise ApiError("Qoder 适配器未绑定 HTTP 客户端")
        except Exception as exc:  # noqa: BLE001
            raise ApiError(f"Qoder 请求失败: {exc}") from exc
        return response.status, response_json(response)

    def bind_http(self, ctx: AccountContext) -> None:
        self.ctx_http = ctx.http
        self.ctx_env = dict(ctx.secrets.env)


class QoderPlatform:
    platform = "qoder"
    accounts = (CN_SPEC, GLOBAL_SPEC)

    def account_adapter(self, account_id: str) -> QoderAdapter:
        config = QODER_CONFIGS.get(account_id)
        if config is None:
            raise KeyError(f"未知 Qoder 账户: {account_id}")
        adapter = QoderAdapter(config)
        adapter._account_id = account_id  # type: ignore[attr-defined]
        return adapter


def qoder_platform() -> QoderPlatform:
    return QoderPlatform()
