# Platform matrix (latest verified probe status)

Summary:

- `verified`: 11
- `blocked_no_secret`: 2（Qoder CN、Qoder Global：缺桌面设备身份）
- `code_only`: 0

Real redacted events are in [verified-probes.md](verified-probes.md).
KK and SeekAI both solved Turnstile with the Playwright browser fallback in
GitHub Actions, without a manual Turnstile token.

Qoder usage is fixed (`/sash/api/v2/me/usage`), but campaigns only return the
`VIEW_DETAILS` campaign `act-20261020-008`; no `CLAIM_BENEFIT` is offered
without Qoder desktop `Cosy-MachineToken` / `Cosy-MachineType`.

| # | platform | account | points_gained | points_current | points_source | verification_status | points_gained_semantics | points_current_semantics | 备注 |
|---:|---|---|---|---|---|---|---|---|---|
| 1 | workbuddy | workbuddy:default | 100 | 3500 | api_field | verified | explicit `credit`/`data.credit` → `api_field`; else before/after diff → `diff_before_after`; status-only → null + `api_unavailable`; never `today_credit` | status `total_credits`/`balance` | real success 2026-11-23; travel=departed:古镇客栈 |
| 2 | traework | traework:cn | null | 100 | api_unavailable | verified | claim `credits_earned_today`/`grant_credits`/`credits`; else before/after diff | claim/status `total_credits` or `credits` | real success; claim returned no gained, current from status |
| 3 | qoder_cn | qoder:cn | null | 1433 | api_field | blocked_no_secret | campaign `CLAIM_BENEFIT` claim fields; absent here | usage v2 `qoderUsage.userQuota.remaining` | campaigns=1 `VIEW_DETAILS` act-20261020-008; machine=no; need `Cosy-MachineToken/Type` |
| 4 | qoder_global | qoder:global | null | 771 | api_field | blocked_no_secret | campaign `CLAIM_BENEFIT` claim fields; absent here | usage v2 `qoderUsage` | campaigns=1 `VIEW_DETAILS` act-20261020-008; machine=no; need `Cosy-MachineToken/Type` |
| 5 | minimax | minimax:default | 400 | null | api_unavailable | verified | today `days[].points` when `claim_result=1` | no total field in actual response; null + `api_unavailable` | real success gained 400; already message includes “平台未返回总积分” |
| 6 | lobsterai | lobsterai:default | 100 | null | api_unavailable | verified | explicit `creditsGranted`/`rewardCredits`/`credits`; `alreadyProcessed`/`claimedToday` → null + `idempotent_reset` | `total_credits`/`credits`/`balance`; else null | real success gained 100; current interface unavailable |
| 7 | dgb | dgb:default | null | 112238913 | api_unavailable | verified | `quota_awarded` | `/api/user/self` → `/api/data/self` → `/api/usage/token/`; parse `quota`/`total_available`; `total_quota` forbidden | real already_checked; current balance from API |
| 8 | aiaiai | aiaiai:default | null | 38636 | api_unavailable | verified | `quota_awarded` | same as DGB | real already_checked |
| 9 | helpcoder | helpcoder:default | null | 160000000 | api_unavailable | verified | `quota_awarded` | same as DGB | real already_checked |
| 10 | kemeng | kemeng:default | null | 1008044 | api_unavailable | verified | `quota_awarded` | same as DGB | real already_checked |
| 11 | seekai | seekai:default | null | 18999999 | api_unavailable | verified | New-API `quota_awarded` after Turnstile | `/api/user/self` → `/api/data/self` → `/api/usage/token/` | real already_checked; browser_fallback solved, 2 clicks, no manual token |
| 12 | benst | benst:default | null | 773199 | api_unavailable | verified | New-API `quota_awarded` | `/api/user/self` → `/api/data/self` → `/api/usage/token/` | real already_checked; 02:00/02:10 window |
| 13 | kk | kk:default | null | 997759 | api_unavailable | verified | `quota_awarded` after Turnstile | `/api/user/self`; not check-in count | browser_fallback solved, 2 clicks, no manual token |

## Remaining blocked targets

Only Qoder CN and Qoder Global:

- Their bearer tokens authenticate usage (CN 1433 / Global 771), but the daily
  credit campaign is only listed with Qoder's desktop device identity.
- Current campaigns response: one `VIEW_DETAILS` campaign
  (`act-20261020-008`), no `CLAIM_BENEFIT`, `machine=no`.
- Add `QODER_CN_MACHINE_TOKEN` / `QODER_CN_MACHINE_TYPE` and
  `QODER_GLOBAL_MACHINE_TOKEN` / `QODER_GLOBAL_MACHINE_TYPE` from the official
  Qoder desktop `runtime-info` helper, then rerun the probe.
- Without that identity, the API will keep returning no claimable daily
  campaign; this is not a token-expiry or "already checked" state.

KK and SeekAI are verified and no longer blocked.
