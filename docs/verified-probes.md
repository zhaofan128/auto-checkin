# Verified probe samples (2026-11-23)

All samples are redacted sign-in events produced by the host repo Actions
workflow `probe-platform`. No Token/Cookie is present.

## WorkBuddy

```json
{
  "schema_version": 1,
  "timestamp": "2026-11-23T01:39:42+08:00",
  "run_id": "20261123T013932-be91d9",
  "platform": "workbuddy",
  "platform_name": "WorkBuddy",
  "account": "wo***dy",
  "account_key": "workbuddy:default",
  "checkin_status": "success",
  "points_gained": 100,
  "points_current": 3500,
  "points_unit": "credits",
  "points_source": "api_field",
  "message": "签到成功; travel=departed:古镇客栈",
  "error_type": null,
  "error_detail": null,
  "duration_ms": 9685,
  "run_profile": "manual",
  "attempt": 1,
  "manual_required": false,
  "skipped_reason": null,
  "turnstile": null
}
```

## TraeWork CN

```json
{
  "schema_version": 1,
  "timestamp": "2026-11-23T01:40:36+08:00",
  "run_id": "20261123T014031-408fa5",
  "platform": "traework",
  "platform_name": "TraeWork CN",
  "account": "tr***rk",
  "account_key": "traework:cn",
  "checkin_status": "success",
  "points_gained": null,
  "points_current": 100,
  "points_unit": "credits",
  "points_source": "api_unavailable",
  "message": "签到成功",
  "error_type": null,
  "error_detail": null,
  "duration_ms": 4911,
  "run_profile": "manual",
  "attempt": 1,
  "manual_required": false,
  "skipped_reason": null,
  "turnstile": null
}
```

Claim response did not provide a usable `credits_earned_today` / `grant_credits` /
`credits`; current `100` came from the status interface.

## Qoder CN

```json
{
  "schema_version": 1,
  "timestamp": "2026-11-23T01:41:24+08:00",
  "run_id": "20261123T014119-9e7578",
  "platform": "qoder_cn",
  "platform_name": "Qoder CN",
  "account": "qo***cn",
  "account_key": "qoder:cn",
  "checkin_status": "skipped",
  "points_gained": null,
  "points_current": null,
  "points_unit": "credits",
  "points_source": "api_unavailable",
  "message": "无签到活动",
  "error_type": null,
  "error_detail": null,
  "duration_ms": 4781,
  "run_profile": "manual",
  "attempt": 1,
  "manual_required": false,
  "skipped_reason": "no_activity",
  "turnstile": null
}
```

## Qoder Global

```json
{
  "schema_version": 1,
  "timestamp": "2026-11-23T01:41:59+08:00",
  "run_id": "20261123T014158-c18cab",
  "platform": "qoder_global",
  "platform_name": "Qoder Global",
  "account": "qo***al",
  "account_key": "qoder:global",
  "checkin_status": "skipped",
  "points_gained": null,
  "points_current": null,
  "points_unit": "credits",
  "points_source": "api_unavailable",
  "message": "无签到活动",
  "error_type": null,
  "error_detail": null,
  "duration_ms": 881,
  "run_profile": "manual",
  "attempt": 1,
  "manual_required": false,
  "skipped_reason": "no_activity",
  "turnstile": null
}
```

## MiniMax Code (success run)

```json
{
  "schema_version": 1,
  "timestamp": "2026-11-23T01:43:18+08:00",
  "run_id": "20261123T014315-d55a6b",
  "platform": "minimax",
  "platform_name": "MiniMax Code",
  "account": "mi***ax",
  "account_key": "minimax:default",
  "checkin_status": "success",
  "points_gained": 400,
  "points_current": null,
  "points_unit": "points",
  "points_source": "api_unavailable",
  "message": "签到成功",
  "error_type": null,
  "error_detail": null,
  "duration_ms": 2777,
  "run_profile": "manual",
  "attempt": 1,
  "manual_required": false,
  "skipped_reason": null,
  "turnstile": null
}
```

The platform returned today's `points=400` but no total points. A later run
returned `already_checked` with `message="今日已签到；平台未返回总积分"`.

## LobsterAI

```json
{
  "schema_version": 1,
  "timestamp": "2026-11-23T01:44:59+08:00",
  "run_id": "20261123T014455-6c330b",
  "platform": "lobsterai",
  "platform_name": "LobsterAI",
  "account": "lo***ai",
  "account_key": "lobsterai:default",
  "checkin_status": "success",
  "points_gained": 100,
  "points_current": null,
  "points_unit": "credits",
  "points_source": "api_unavailable",
  "message": "签到成功；当前积分接口不可用",
  "error_type": null,
  "error_detail": null,
  "duration_ms": 3897,
  "run_profile": "manual",
  "attempt": 1,
  "manual_required": false,
  "skipped_reason": null,
  "turnstile": null
}
```
