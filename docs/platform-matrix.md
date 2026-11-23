# Platform matrix (latest verified probe status)

Summary:

- `verified`: 12（WorkBuddy、TraeWork CN、Qoder CN、Qoder Global、MiniMax、LobsterAI、DGB、AIAIAI、帮帮程序员、可萌、BENST、KK）
- `blocked_no_secret`: 1（SeekAI：`SEEKAI_TOKEN` 返回 401 invalid access token）
- `code_only`: 0

Real redacted events are in [verified-probes.md](verified-probes.md).
KK's browser fallback solved Turnstile in GitHub Actions without a manual token.
SeekAI's browser fallback is implemented, but the current host `SEEKAI_TOKEN`
is invalid, so the request never reached the Turnstile step.

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
| 11 | seekai | seekai:default | null | 18999999 | api_unavailable | blocked_no_secret | New-API `quota_awarded` after Turnstile | `/api/user/self` → `/api/data/self` → `/api/usage/token/` | last real already_checked before expiry; later 401 `invalid access token`; update `SEEKAI_TOKEN` |
| 12 | benst | benst:default | null | 773199 | api_unavailable | verified | New-API `quota_awarded` | `/api/user/self` → `/api/data/self` → `/api/usage/token/` | real already_checked; 02:00/02:10 window |
| 13 | kk | kk:default | null | 997759 | api_unavailable | verified | `quota_awarded` after Turnstile | `/api/user/self`; not check-in count | browser_fallback solved, 2 clicks, no manual token |

## Remaining blocked target

Only SeekAI:

- `SEEKAI_TOKEN` in the host repo is old/invalid; the latest probe returned
  `401 Unauthorized, invalid access token`.
- The browser fallback is implemented, but it cannot start because status
  authentication fails first.
- Update `SEEKAI_TOKEN` in the host repo; then rerun the probe. No 0 or guessed
  value is used.

KK is no longer blocked: its browser fallback solved Turnstile with 2 clicks
and returned real `already_checked` data.
