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

## New-API sites and KK (2026-11-23, already checked)

```jsonl
{"schema_version":1,"timestamp":"2026-11-23T12:27:21+08:00","run_id":"20261123T122718-776391","platform":"dgb","platform_name":"DGB 公益站","account":"d***b","account_key":"dgb:default","checkin_status":"already_checked","points_gained":null,"points_current":112238913,"points_unit":"quota","points_source":"api_unavailable","message":"今日已签到；今日已签到，签到响应未返回 quota_awarded","duration_ms":3232}
{"schema_version":1,"timestamp":"2026-11-23T12:27:37+08:00","run_id":"20261123T122736-339e73","platform":"aiaiai","platform_name":"AIAIAI 工具箱","account":"ai***ai","account_key":"aiaiai:default","checkin_status":"already_checked","points_gained":null,"points_current":38636,"points_unit":"quota","points_source":"api_unavailable","message":"今日已签到；今日已签到，签到响应未返回 quota_awarded","duration_ms":1086}
{"schema_version":1,"timestamp":"2026-11-23T12:27:55+08:00","run_id":"20261123T122754-5173b4","platform":"helpcoder","platform_name":"帮帮程序员","account":"he***er","account_key":"helpcoder:default","checkin_status":"already_checked","points_gained":null,"points_current":160000000,"points_unit":"quota","points_source":"api_unavailable","message":"今日已签到；今日已签到，签到响应未返回 quota_awarded","duration_ms":1013}
{"schema_version":1,"timestamp":"2026-11-23T12:28:19+08:00","run_id":"20261123T122819-b39078","platform":"kemeng","platform_name":"可萌中转站","account":"ke***ng","account_key":"kemeng:default","checkin_status":"already_checked","points_gained":null,"points_current":1008044,"points_unit":"quota","points_source":"api_unavailable","message":"今日已签到；今日已签到，签到响应未返回 quota_awarded","duration_ms":367}
{"schema_version":1,"timestamp":"2026-11-23T12:28:37+08:00","run_id":"20261123T122836-5a9e47","platform":"benst","platform_name":"神秘小站 BENST","account":"be***st","account_key":"benst:default","checkin_status":"already_checked","points_gained":null,"points_current":773199,"points_unit":"quota","points_source":"api_unavailable","message":"今日已签到；今日已签到，签到响应未返回 quota_awarded","duration_ms":1521}
{"schema_version":1,"timestamp":"2026-11-23T12:28:55+08:00","run_id":"20261123T122855-870113","platform":"seekai","platform_name":"SeekAI","account":"se***ai","account_key":"seekai:default","checkin_status":"already_checked","points_gained":null,"points_current":18999999,"points_unit":"quota","points_source":"api_unavailable","message":"今日已签到；今日已签到，签到响应未返回 quota_awarded","duration_ms":486}
{"schema_version":1,"timestamp":"2026-11-23T12:29:46+08:00","run_id":"20261123T122945-3951f9","platform":"kk","platform_name":"KK","account":"***","account_key":"kk:default","checkin_status":"already_checked","points_gained":null,"points_current":997759,"points_unit":"quota","points_source":"api_unavailable","message":"今日已签到；今日已签到，签到响应未返回本次积分","duration_ms":880}
```

These events were produced before the duplicate-reason cleanup. Future logs read
`今日已签到；签到响应未返回 ...`. No token/cookie is present.

SeekAI and KK are already checked today, so the Turnstile paths were not
exercised. They still need `SEEKAI_TURNSTILE_TOKEN` / `KK_TURNSTILE_TOKEN`
before the next unchecked run.
