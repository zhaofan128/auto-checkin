# KK Turnstile policy

## Default path: browser fallback

KK now uses the Playwright browser fallback by default:

- Open `/login` under `xvfb-run` with headful Chromium.
- Wait for `cf-turnstile-response`, click the challenge if needed.
- Perform the check-in fetch inside the browser context.
- Log `turnstile.mode="browser_fallback"`, `result`, `attempts`, `clicks`,
  `duration_ms`, `token_present`.
- The token value is never logged.

Real CI result on 2026-11-23:

```text
turnstile.mode=browser_fallback
turnstile.result=solved
attempts=1
clicks=2
duration_ms=23571
checkin_status=already_checked
```

## Optional manual token

`KK_TURNSTILE_TOKEN` remains an optional emergency override. It is not required
for normal operation. When present, the adapter uses `mode="manual_token"` and
does not launch the browser.

## Old kk repository fallback

Keeping the old kk repository running is only meaningful if that repository can
actually pass Turnstile. If it also relies on a manual token, keeping it is
**status quo, not restored capability**. The old repository is only a temporary
fallback until the new host validates all 13 account targets; after validation,
stop its schedule and archive it. Do not keep a long-term dual run.

## CI acceptance

- If browser fallback succeeds, continue using it.
- If it times out repeatedly, use `KK_TURNSTILE_TOKEN` as a one-run override or
  keep the old repository as the temporary fallback.
- Do not retry aggressively; repeated attempts lower IP reputation.

See [turnstile-fallback.md](turnstile-fallback.md) for the cf_clearance
evaluation.
