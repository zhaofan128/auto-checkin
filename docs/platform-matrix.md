# Platform matrix (latest verified probe status)

Summary:

- `verified`: 13（全部账户目标）
- `blocked_no_secret`: 0
- `code_only`: 0

Real redacted events are in [verified-probes.md](verified-probes.md).
KK and SeekAI both solved Turnstile with the Playwright browser fallback in
GitHub Actions, without a manual Turnstile token.

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
| 11 | seekai | seekai:default | null | 18999999 | api_unavailable | verified | New-API `quota_awarded` after Turnstile | `/api/user/self` → `/api/data/self` → `/api/usage/token/` | real already_checked; browser_fallback solved, 2 clicks, no manual token |
| 12 | benst | benst:default | null | 773199 | api_unavailable | verified | New-API `quota_awarded` | `/api/user/self` → `/api/data/self` → `/api/usage/token/` | real already_checked; 02:00/02:10 window |
| 13 | kk | kk:default | null | 997759 | api_unavailable | verified | `quota_awarded` after Turnstile | `/api/user/self`; not check-in count | browser_fallback solved, 2 clicks, no manual token |

## Verification complete

All 13 account targets now have real probe evidence.

- KK: browser_fallback solved, 2 clicks, no manual token.
- SeekAI: `SEEKAI_TOKEN` updated; browser_fallback solved, 2 clicks, no manual
  Turnstile token.
- No account is blocked by a missing Secret or Turnstile token.

The remaining work is operational cutover: point the main workflow at
`src/main.py`, then stop the old kk schedule after a full cycle.
