# Refreshing and cross-process locking

## Scope

The core serializes refresh per account with:

- `state/.locks/<account_key>.lock` via `fcntl.flock` on POSIX and `msvcrt.locking` on Windows.
- state generation + secret `updated_at` CAS in `core/state.py` and `core/refresh.py`.

This protects **two processes on the same runner/host**. It does not coordinate
separate GitHub Actions jobs, runners or local machines.

A `flock` lock belongs to an open file descriptor inside one process. It cannot
be passed between GitHub Actions steps or jobs, and it does not survive a step
boundary. Cross-step/cross-job serialization can only be provided by
`concurrency.group` plus a single job; `flock` is only a within-runner guard.

## GitHub Actions requirements

1. Run all accounts in **one job**, not a matrix of rolling-token accounts.
2. Set a repository-wide concurrency group:

```yaml
concurrency:
  group: daily-checkin
  cancel-in-progress: false
```

3. Do not run the old workflow, the new workflow, or the local desktop helper
   at the same time for rolling accounts (`WorkBuddy`, `TraeWork CN`,
   `Qoder CN`, `MiniMax`, `LobsterAI`).
4. If a future change splits rolling accounts into multiple jobs, add a remote
   lock or disable rolling refresh for those accounts.

## POSIX lock reliability

`fcntl.flock` on GitHub-hosted `ubuntu-latest` local disks is expected to work.
Self-hosted runners on NFS/network filesystems may not provide reliable advisory
locks. Validate with:

```bash
python3 -m pytest tests/test_refresh_cross_process.py -q
```

If the lock is unreliable:

- Keep a single workflow job and `concurrency.group` as the primary protection.
- Do not parallelize rolling accounts.
- If serialization still cannot be guaranteed, fail the account with
  `lock_timeout` (or a documented `lock_unavailable` wrapper) and require manual
  action; do not silently continue.
- Keep the old repository/schedule running as the fallback.

## What the cross-process test proves

`tests/test_refresh_cross_process.py` starts two OS processes that:

1. Read the same refresh token.
2. Race to refresh the same account.
3. Use the real file lock, state generation and CAS.

Only one process refreshes and writes `generation=1`; the other observes the
new generation and does not overwrite the new credential with a stale value.

## Secrets

Lock files contain no secret values. Secret values are never written to
`state/`, `history/`, logs or error messages.
