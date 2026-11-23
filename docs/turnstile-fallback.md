# Turnstile fallback evaluation

## Current production path

KK and SeekAI now use the Playwright browser fallback by default:

- headful Chromium under `xvfb-run`
- wait for `cf-turnstile-response`
- click challenge if needed (max 3)
- perform the check-in fetch inside the browser context
- log only mode/result/attempts/clicks/duration/token_present

KK was verified in GitHub Actions on 2026-11-23: `solved`, 2 clicks, 1 attempt.
Manual `KK_TURNSTILE_TOKEN` / `SEEKAI_TURNSTILE_TOKEN` remain optional overrides,
not requirements.

## cloudflare-solver / cf_clearance

A `cf_clearance` cookie obtained by cloudflare-solver is bound to the exit IP
and User-Agent used when it was issued. Replaying it from a different IP or UA
fails. GitHub Actions runners use shared data-center egress IPs, so:

- the issuing IP often differs from the replay IP;
- the IP reputation is already elevated-risk;
- a clearance minted on one runner may be useless on the next run;
- storing the cookie creates a new sensitive credential that must be rotated.

**Conclusion:** `cf_clearance` is not a production default. Browser fallback is
the default; manual Turnstile tokens are optional emergency overrides.
cloudflare-solver remains a future, opt-in evaluation only, subject to
compliance, account-risk and security review. Clearance cookies must never be
logged or committed.
