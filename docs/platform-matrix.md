# Platform matrix (final Step 4 status)

Summary:

- `verified`: 1（WorkBuddy）
- `blocked_no_secret`: 12
- `code_only`: 0

WorkBuddy was verified through the host repo Actions workflow
`probe-platform` on 2026-11-23. The other rows have not produced a real
check-in response yet; their point values remain `null`.

| # | platform | account | points_gained | points_current | points_source | verification_status | points_gained_semantics | points_current_semantics | 备注 |
|---:|---|---|---|---|---|---|---|---|---|
| 1 | workbuddy | workbuddy:default | 100 | 3500 | api_field | verified | explicit `credit`/`data.credit` → `api_field`; else before/after diff → `diff_before_after`; status-only → null + `api_unavailable`; never `today_credit` | status `total_credits`/`balance` | real probe 2026-11-23: success, travel=departed:古镇客栈; tokens not logged |
| 2 | traework | traework:cn | null | null | api_unavailable | blocked_no_secret | claim `credits_earned_today`/`grant_credits`/`credits`; else before/after diff | claim/status `total_credits` or `credits` | no `TRAE_CREDS`; P-256 device proof ported |
| 3 | qoder_cn | qoder:cn | null | null | api_unavailable | blocked_no_secret | campaign claim `gained`/`credits`/`reward_credits`; else null | usage `total_credits` (candidate `/sash/api/v1/me/usage`) | independent state/lock/log; no `QODER_CN_TOKEN` |
| 4 | qoder_global | qoder:global | null | null | api_unavailable | blocked_no_secret | campaign claim fields; static token | usage/account interface | independent state/lock/log; no `QODER_GLOBAL_TOKEN` |
| 5 | minimax | minimax:default | null | null | api_unavailable | blocked_no_secret | today `days[].points` when `claim_result=1` | no total field found in code; null + `api_unavailable` | no `MM_CREDS` |
| 6 | lobsterai | lobsterai:default | null | null | api_unavailable | blocked_no_secret | explicit `creditsGranted`/`rewardCredits`/`credits`; `alreadyProcessed`/`claimedToday` → null + `idempotent_reset` | `total_credits`/`credits`/`balance`; else null | first-login is a reset, not gained; no `LOBSTER_CREDS` |
| 7 | dgb | dgb:default | null | null | api_unavailable | blocked_no_secret | `quota_awarded` | `/api/user/self` → `/api/data/self` → `/api/usage/token/`; parse `quota`/`total_available`; `total_quota` forbidden | password site; no `CHECKIN_USERNAME`/`PASSWORD` |
| 8 | aiaiai | aiaiai:default | null | null | api_unavailable | blocked_no_secret | `quota_awarded` | same as DGB | password site |
| 9 | helpcoder | helpcoder:default | null | null | api_unavailable | blocked_no_secret | `quota_awarded` | same as DGB | password site |
| 10 | kemeng | kemeng:default | null | null | api_unavailable | blocked_no_secret | `quota_awarded` | same as DGB | password site |
| 11 | seekai | seekai:default | null | null | api_unavailable | blocked_no_secret | New-API `quota_awarded` | `/api/user/self` → `/api/data/self` → `/api/usage/token/`; no password fallback | token-only; no `SEEKAI_TOKEN` |
| 12 | benst | benst:default | null | null | api_unavailable | blocked_no_secret | New-API `quota_awarded` | `/api/user/self` → `/api/data/self` → `/api/usage/token/` | token-only; 02:00/02:10 window; synced origin/main `ebfd8b7` |
| 13 | kk | kk:default | null | null | api_unavailable | blocked_no_secret | `quota_awarded` | `/api/user/self`; not check-in count | if `KK_TOKEN` exists but `KK_TURNSTILE_TOKEN` missing → `turnstile_unavailable`; no `KK_TOKEN` → `secret_missing` |

## Verified probe sample: WorkBuddy (2026-11-23)

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

This confirms WorkBuddy's explicit `credit` path and status `total_credits`
path. No token or cookie is present in the event.

## Evidence for degraded runs

`tests/test_all_platforms_degraded.py` runs all 13 account targets with empty
Secrets and asserts for each:

- `checkin_status="skipped"`
- `points_gained=null`
- `points_current=null`
- `points_source="api_unavailable"`
- message starts with `Secret 缺失，未真实探测`
- no HTTP call is required to fabricate a result

## Real probe rule

A real probe must run in the host repo Actions or a local machine with Secrets:

```bash
python tools/probe_platform.py --platform workbuddy
python tools/probe_platform.py --platform workbuddy --apply
```

Every real probe must record the actual response fields and update the row to
`verified` or `null_reason`. Never substitute `0` or a guessed value.

## KK fallback caveat

KK's main path is `manual_token` (`KK_TURNSTILE_TOKEN`). If it is absent, the
adapter skips with `turnstile_unavailable`; browser fallback is not the default
CI path. Keeping the old kk repository is only a temporary fallback if that
repository can actually pass Turnstile; after the new host validates all 13
targets, stop the old schedule and archive it. No long-term dual run.

See [kk-turnstile.md](kk-turnstile.md), [turnstile-fallback.md](turnstile-fallback.md),
[secret-compatibility.md](secret-compatibility.md) and
[refresh-locking.md](refresh-locking.md).
