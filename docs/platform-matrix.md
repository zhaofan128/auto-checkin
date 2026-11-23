# Platform matrix (latest verified probe status)

Summary:

- `verified`: 11
- `blocked_no_secret`: 2（Qoder CN：账号 `personal_standard` 不满足 Pro/付费资格；Qoder Global：缺桌面设备身份/资格确认）
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
| 3 | qoder_cn | qoder:cn | null | 1433 | api_field | blocked_no_secret | campaign `CLAIM_BENEFIT` claim fields; absent here | usage v2 `qoderUsage.userQuota.remaining` | PAT exchange 200; `userType=personal_standard`; event requires Pro trial/paid; campaigns=1 `VIEW_DETAILS` |
| 4 | qoder_global | qoder:global | null | 771 | api_field | blocked_no_secret | campaign `CLAIM_BENEFIT` claim fields; absent here | usage v2 `qoderUsage` | campaigns=1 `VIEW_DETAILS`; machine=no; need desktop identity and eligibility confirmation |
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

- Qoder CN PAT exchange succeeds (`HTTP 200`), but the account usage reports
  `userType=personal_standard`. The official daily 100 Credits event is open to
  Pro trial and individual paid subscribers; `personal_standard` is not
  eligible. The only campaign is the unrelated `VIEW_DETAILS` popup
  `act-20261020-008`; there is no `CLAIM_BENEFIT`.
- Qoder Global usage works (771), but campaigns still only return `VIEW_DETAILS`
  and `machine=no`. It needs the desktop device identity and eligibility check.
- These are account/device-eligibility blockers, not token expiry and not
  "already checked". Claiming the `VIEW_DETAILS` popup returns 200 but does not
  change the credit balance.
- A Pro trial or paid Qoder account, plus the desktop `runtime-info` identity
  where required, is needed before the daily campaign can be claimed.

KK and SeekAI are verified and no longer blocked.
