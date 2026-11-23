# Secret compatibility

## Read order

1. New unified alias, if present and non-empty.
2. Legacy key.
3. If neither exists, the account is `skipped` with `secret_missing` and message
   `Secret 缺失，未真实探测：...`.

Existing legacy keys are never deleted or renamed.

## Rolling credentials

| Account | New alias | Legacy | Write-back |
|---|---|---|---|
| WorkBuddy | `CHECKIN_WORKBUDDY_RT` | `WB_RT` | Always write legacy; mirror new if it exists |
| TraeWork CN | `CHECKIN_TRAEWORK_CREDS` | `TRAE_CREDS` | Always write legacy; mirror new if it exists |
| Qoder CN | `CHECKIN_QODER_CN_TOKEN` | `QODER_CN_TOKEN` | Always write legacy; mirror new if it exists |
| MiniMax | `CHECKIN_MINIMAX_CREDS` | `MM_CREDS` | Always write legacy; mirror new if it exists |
| LobsterAI | `CHECKIN_LOBSTER_CREDS` | `LOBSTER_CREDS` | Always write legacy; mirror new if it exists |

Qoder Global is a static token: no refresh, no write-back.

## Static tokens

| Account | New alias | Legacy |
|---|---|---|
| KK | `CHECKIN_KK_TOKEN` | `KK_TOKEN` |
| SeekAI | `CHECKIN_SEEKAI_TOKEN` | `SEEKAI_TOKEN` |
| BENST | `CHECKIN_BENST_TOKEN` | `BENST_TOKEN` |

## Password sites

Global default:

```text
CHECKIN_USERNAME
CHECKIN_PASSWORD
```

Per-site override (optional):

```text
CHECKIN_USERNAME_DGB / CHECKIN_PASSWORD_DGB
CHECKIN_USERNAME_AIAIAI / CHECKIN_PASSWORD_AIAIAI
CHECKIN_USERNAME_HELPCODER / CHECKIN_PASSWORD_HELPCODER
CHECKIN_USERNAME_KEMENG / CHECKIN_PASSWORD_KEMENG
```

Resolution: per-site override first, then global default. If neither exists,
the site is `skipped` with `secret_missing`.

SeekAI and BENST are token-only and never fall back to username/password.
SeekAI's account is created through GitHub registration; check-in still uses
`SEEKAI_TOKEN` and still requires `SEEKAI_TURNSTILE_TOKEN` on an unchecked day.
The current real code path has no SeekAI refresh endpoint, so `SEEKAI_TOKEN` is
a static access token and must be updated manually when invalid.

`KK_TOKEN` is a long-lived access token, but it does not replace
`KK_TURNSTILE_TOKEN`; an unchecked KK run still needs the Turnstile token.

## Manual copy list for the host repo

Only these keys need to be copied from `kk-auto-checkin` to the host repo:

```text
KK_TOKEN
CHECKIN_USERNAME
CHECKIN_PASSWORD
SEEKAI_TOKEN
BENST_TOKEN
```

Optional per-site overrides:

```text
CHECKIN_USERNAME_DGB / CHECKIN_PASSWORD_DGB
CHECKIN_USERNAME_AIAIAI / CHECKIN_PASSWORD_AIAIAI
CHECKIN_USERNAME_HELPCODER / CHECKIN_PASSWORD_HELPCODER
CHECKIN_USERNAME_KEMENG / CHECKIN_PASSWORD_KEMENG
```

`GH_PAT` already exists in the host repo and is required for rolling write-back.

Optional emergency Turnstile overrides:

```text
KK_TURNSTILE_TOKEN
SEEKAI_TURNSTILE_TOKEN
```

These are not required by default. KK and SeekAI now use the Playwright browser
fallback; the manual tokens are only one-run overrides when the browser fallback
fails.

SeekAI's token login still requires a valid `SEEKAI_TOKEN`. The host token was
updated and verified with the browser fallback. It is a static access token and
must be updated manually if it becomes invalid. SeekAI is not treated as a
normal New-API password site.

Optional per-site overrides for the four password sites are listed above. They
are not required when the global `CHECKIN_USERNAME` / `CHECKIN_PASSWORD` works.

## Write-back safety

- Values are passed to `gh secret set` on stdin, never argv.
- No secret value is written to logs, state, docs or error details.
- If `GH_PAT` cannot write Secrets, rolling accounts are `skipped` with
  `skipped_reason="secret_writeback_unavailable"` before refreshing.
- If a refresh succeeds but write-back fails, the account is `failed` with
  `secret_writeback_failed`, not silently treated as skipped.
- A rotated value is written to the legacy key first so old code can read it
  after rollback.
