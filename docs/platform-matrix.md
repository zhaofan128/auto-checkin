# Platform matrix (latest verified probe status)

Summary:

- `verified`: 11（WorkBuddy、TraeWork CN、Qoder CN、Qoder Global、MiniMax、LobsterAI、DGB、AIAIAI、帮帮程序员、可萌、BENST）
- `blocked_no_secret`: 2（SeekAI、KK；均缺 Turnstile 人工 token）
- `code_only`: 0

Real redacted events are in [verified-probes.md](verified-probes.md).
SeekAI and KK returned real `already_checked` balances, but their next unchecked
run requires `SEEKAI_TURNSTILE_TOKEN` / `KK_TURNSTILE_TOKEN`; they are therefore
still blocked, not marked fully verified.

| # | platform | account | points_gained | points_current | points_source | verification_status | points_gained_semantics | points_current_semantics | 备注 |
|---:|---|---|---|---|---|---|---|---|---|
| 1 | workbuddy | workbuddy:default | 100 | 3500 | api_field | verified | explicit `credit`/`data.credit` → `api_field`; else before/after diff → `diff_before_after`; status-only → null + `api_unavailable`; never `today_credit` | status `total_credits`/`balance` | real success 2026-11-23; travel=departed:古镇客栈 |
| 2 | traework | traework:cn | null | 100 | api_unavailable | verified | claim `credits_earned_today`/`grant_credits`/`credits`; else before/after diff | claim/status `total_credits` or `credits` | real success; claim returned no gained, current from status |
| 3 | qoder_cn | qoder:cn | null | null | api_unavailable | verified | campaign claim fields; else null | usage `total_credits` (candidate `/sash/api/v1/me/usage`) | real skipped/no_activity; usage no total |
| 4 | qoder_global | qoder:global | null | null | api_unavailable | verified | static token; campaign claim fields | usage/account interface | real skipped/no_activity; separate state/lock/log |
| 5 | minimax | minimax:default | 400 | null | api_unavailable | verified | today `days[].points` when `claim_result=1` | no total field in actual response; null + `api_unavailable` | real success gained 400; already message includes “平台未返回总积分” |
| 6 | lobsterai | lobsterai:default | 100 | null | api_unavailable | verified | explicit `creditsGranted`/`rewardCredits`/`credits`; `alreadyProcessed`/`claimedToday` → null + `idempotent_reset` | `total_credits`/`credits`/`balance`; else null | real success gained 100; current interface unavailable |
| 7 | dgb | dgb:default | null | 112238913 | api_unavailable | verified | `quota_awarded` | `/api/user/self` → `/api/data/self` → `/api/usage/token/`; parse `quota`/`total_available`; `total_quota` forbidden | real already_checked; current balance from API |
| 8 | aiaiai | aiaiai:default | null | 38636 | api_unavailable | verified | `quota_awarded` | same as DGB | real already_checked |
| 9 | helpcoder | helpcoder:default | null | 160000000 | api_unavailable | verified | `quota_awarded` | same as DGB | real already_checked |
| 10 | kemeng | kemeng:default | null | 1008044 | api_unavailable | verified | `quota_awarded` | same as DGB | real already_checked |
| 11 | seekai | seekai:default | null | 18999999 | api_unavailable | blocked_no_secret | New-API `quota_awarded` after Turnstile | `/api/user/self` → `/api/data/self` → `/api/usage/token/` | real already_checked; `SEEKAI_TURNSTILE_TOKEN` missing; next unchecked run skips |
| 12 | benst | benst:default | null | 773199 | api_unavailable | verified | New-API `quota_awarded` | `/api/user/self` → `/api/data/self` → `/api/usage/token/` | real already_checked; 02:00/02:10 window |
| 13 | kk | kk:default | null | 997759 | api_unavailable | blocked_no_secret | `quota_awarded` after Turnstile | `/api/user/self`; not check-in count | real already_checked; `KK_TOKEN` copied; `KK_TURNSTILE_TOKEN` missing |

## Remaining blocked targets

Only two:

- SeekAI: `SEEKAI_TOKEN` exists; `SEEKAI_TURNSTILE_TOKEN` missing.
- KK: `KK_TOKEN` exists; `KK_TURNSTILE_TOKEN` missing.

Both returned real `already_checked` balances today. The next unchecked run will
skip with `turnstile_unavailable` until the manual token is supplied. No 0 or
guessed value is used.
