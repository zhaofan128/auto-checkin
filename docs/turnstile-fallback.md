# Turnstile fallback evaluation

## Current production path

KK's production path is `KK_TURNSTILE_TOKEN` (manual token). If it is absent,
the adapter returns:

- `checkin_status="skipped"`
- `points_source="turnstile_unavailable"`
- `message` explains that the manual token is missing and CI browser fallback is
  unreliable.

The browser evaluator remains in `src/browser/turnstile.py` for local evaluation
and future work, but it is not the default CI path.

## cloudflare-solver / cf_clearance

A `cf_clearance` cookie obtained by cloudflare-solver is bound to the exit IP
and User-Agent used when it was issued. Replaying it from a different IP or UA
fails. GitHub Actions runners use shared data-center egress IPs, so:

- the issuing IP often differs from the replay IP;
- the IP reputation is already elevated-risk;
- a clearance minted on one runner may be useless on the next run;
- storing the cookie creates a new sensitive credential that must be rotated.

**Conclusion:** `cf_clearance` is not a production default. `KK_TURNSTILE_TOKEN`
is the supported path. cloudflare-solver remains a future, opt-in evaluation
only, subject to compliance, account-risk and security review. Clearance
cookies must never be logged or committed.
