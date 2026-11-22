# Platform matrix (latest verified probe status)

Summary:

- `verified`: 6（WorkBuddy、TraeWork CN、Qoder CN、Qoder Global、MiniMax、LobsterAI）
- `blocked_no_secret`: 7（DGB、AIAIAI、帮帮程序员、可萌、SeekAI、BENST、KK）
- `code_only`: 0

Real redacted events are in [verified-probes.md](verified-probes.md).
The seven blocked targets have no corresponding Secrets in the host repo yet;
their measured points remain `null` and no 0/guess is used.

| # | platform | account | points_gained | points_current | points_source | verification_status | points_gained_semantics | points_current_semantics | 备注 |
|---:|---|---|---|---|---|---|---|---|---|
| 1 | workbuddy | workbuddy:default | 100 | 3500 | api_field | verified | explicit `credit`/`data.credit` → `api_field`; else before/after diff → `diff_before_after`; status-only → null + `api_unavailable`; never `today_credit` | status `total_credits`/`balance` | real probe 2026-11-23: success, travel=departed:古镇客栈 |
| 2 | traework | traework:cn | null | 100 | api_unavailable | verified | claim `credits_earned_today`/`grant_credits`/`credits`; else before/after diff | claim/status `total_credits` or `credits` | real probe: success; claim returned no gained, current from status |
| 3 | qoder_cn | qoder:cn | null | null | api_unavailable | verified | campaign claim fields; else null | usage `total_credits` (candidate `/sash/api/v1/me/usage`) | real probe: skipped/no_activity; usage no total |
| 4 | qoder_global | qoder:global | null | null | api_unavailable | verified | static token; campaign claim fields | usage/account interface | real probe: skipped/no_activity; separate state/lock/log |
| 5 | minimax | minimax:default | 400 | null | api_unavailable | verified | today `days[].points` when `claim_result=1` | no total field in actual response; null + `api_unavailable` | real success gained 400; later already_checked message includes “平台未返回总积分” |
| 6 | lobsterai | lobsterai:default | 100 | null | api_unavailable | verified | explicit `creditsGranted`/`rewardCredits`/`credits`; `alreadyProcessed`/`claimedToday` → null + `idempotent_reset` | `total_credits`/`credits`/`balance`; else null | real success gained 100; current interface unavailable |
| 7 | dgb | dgb:default | null | null | api_unavailable | blocked_no_secret | `quota_awarded` | `/api/user/self` → `/api/data/self` → `/api/usage/token/`; parse `quota`/`total_available`; `total_quota` forbidden | no `CHECKIN_USERNAME`/`PASSWORD` |
| 8 | aiaiai | aiaiai:default | null | null | api_unavailable | blocked_no_secret | `quota_awarded` | same as DGB | no `CHECKIN_USERNAME`/`PASSWORD` |
| 9 | helpcoder | helpcoder:default | null | null | api_unavailable | blocked_no_secret | `quota_awarded` | same as DGB | no `CHECKIN_USERNAME`/`PASSWORD` |
| 10 | kemeng | kemeng:default | null | null | api_unavailable | blocked_no_secret | `quota_awarded` | same as DGB | no `CHECKIN_USERNAME`/`PASSWORD` |
| 11 | seekai | seekai:default | null | null | api_unavailable | blocked_no_secret | New-API `quota_awarded` | `/api/user/self` → `/api/data/self` → `/api/usage/token/`; no password fallback | no `SEEKAI_TOKEN` |
| 12 | benst | benst:default | null | null | api_unavailable | blocked_no_secret | New-API `quota_awarded` | `/api/user/self` → `/api/data/self` → `/api/usage/token/` | no `BENST_TOKEN`; 02:00/02:10 window; synced origin/main `ebfd8b7` |
| 13 | kk | kk:default | null | null | api_unavailable | blocked_no_secret | `quota_awarded` | `/api/user/self`; not check-in count | no `KK_TOKEN`; if token exists but `KK_TURNSTILE_TOKEN` missing → `turnstile_unavailable` |

## Degraded evidence

`tests/test_all_platforms_degraded.py` runs all 13 targets with empty Secrets
and asserts `skipped`, null points, `points_source="api_unavailable"`, and a
message starting with `Secret 缺失，未真实探测`.

## Remaining verification

The seven blocked targets need the missing Secret keys before a real probe:
`CHECKIN_USERNAME`/`CHECKIN_PASSWORD`, `SEEKAI_TOKEN`, `BENST_TOKEN`,
`KK_TOKEN`, and (for KK) `KK_TURNSTILE_TOKEN`. Never substitute 0 or a guessed
value.
