# KK Turnstile policy

## Production path: manual_token

- `KK_TURNSTILE_TOKEN` is read first.
- If present, the adapter calls the check-in API directly with that token.
- Log fields: `turnstile.mode="manual_token"`, `result="manual_token"`,
  `token_present=true`.
- The token value is never logged, stored in state, or included in errors.

## Missing manual token

If `KK_TURNSTILE_TOKEN` is absent, the adapter returns:

- `checkin_status="skipped"`
- `points_source="turnstile_unavailable"`
- `message="KK_TURNSTILE_TOKEN 未配置，浏览器 fallback 在 GitHub Actions 环境通过率极低"`
- `turnstile.mode="browser_fallback"`, `manual_required=true`

The browser evaluator exists in `src/browser/turnstile.py` for local/experimental
use, but it is not invoked by default in CI. This avoids burning IP reputation
on repeated challenges.

## Old kk repository fallback

Keeping the old kk repository running is only meaningful if that repository can
actually pass Turnstile. If it also relies on a manual token, keeping it is
**status quo, not restored capability**. The old repository is only a temporary
fallback until the new host validates all 13 account targets; after validation,
stop its schedule and archive it. Do not keep a long-term dual run.

## CI acceptance metric

Record per attempt:

- `turnstile.mode` (`manual_token` / `browser_fallback`)
- `turnstile.result`
- `manual_required`
- `attempts`, `clicks`, `duration_ms`

If browser fallback succeeds less than 50% over at least 3 attempts, do not keep
retrying; use manual_token only.

See [turnstile-fallback.md](turnstile-fallback.md) for the cf_clearance
evaluation.
