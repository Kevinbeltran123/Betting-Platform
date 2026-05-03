---
phase: 03-pick-engine-delivery-account-protection
plan: 3
status: complete
completed: 2026-05-03
duration: ~5min (rescued from worktree after subagent Bash denial)
tasks_total: 2
tasks_done: 2
commits: 2
requirements_addressed:
  - PICK-02
  - PICK-03
---

# Plan 03-03 Summary — Account-longevity math + PickRepository extensions

## What was built

The deterministic math layer for account-longevity protections (PICK-02 + PICK-03), plus the four PickRepository methods that engine (Wave 4) and orchestrator (Wave 4) will need.

- **`src/bip/core/picks/account_longevity.py`** — 5 pure functions:
  - `kelly_stake_units(...)` — Kelly with 0.5-unit rounding (PICK-02 D-09)
  - `apply_market_cap(...)` — 60% market cap enforcement (PICK-03 D-10)
  - `compute_jitter_seed(...)` — `hashlib.md5` deterministic jitter seed (D-11)
  - `apply_jitter(...)` — ±10% stake jitter (PICK-03)
  - `compute_send_at(...)` — 0-1800s send-time variance (PICK-03 D-11)
- **`src/bip/core/storage/repositories.py`** — 4 new methods on PickRepository:
  - `get_window_picks(window)` — for market-cap calculation
  - `get_pending_for_fixture(fixture_id)` — idempotency check
  - `update_status_by_fixture(...)` — terminal status transitions
  - `query_pending_sends()` — scheduler resume
  - All wrapped with `StorageError` per PATTERNS.md convention

## Tests

13 GREEN (8 account_longevity + 5 PickRepositoryExtensions). Engine tests still skipped (await Wave 4).

## Commits

- `19f4b14`: feat(03-03): account longevity pure-function module (PICK-02 + PICK-03)
- `64198f2`: feat(03-03): PickRepository extensions for engine + orchestrator

## Deviations

**One:** Subagent twice failed to invoke Bash from inside the worktree (despite `bypassPermissions` in `.claude/settings.local.json` of the worktree). Code was correctly written by agent; orchestrator (main thread) salvaged the files, ran tests, and committed atomically per the plan's task structure. No code changes from the agent's intent.

**Implication for remaining waves**: Switch to sequential execution on main (no worktrees) for Waves 3 and 4 to avoid the permission inheritance issue.
