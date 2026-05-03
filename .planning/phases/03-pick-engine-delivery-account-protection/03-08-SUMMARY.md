---
phase: 03-pick-engine-delivery-account-protection
plan: 8
status: complete
completed: 2026-05-03
duration: ~15min (executed by orchestrator)
tasks_total: 2
tasks_done: 2
commits: 1
requirements_addressed:
  - PICK-05
---

# Plan 03-08 Summary — PipelineOrchestrator Phase 3 integration

## What was built

Wired `PickEngine` + `_reconcile_results` + Pitfall 6 auto-recover into the existing `PipelineOrchestrator`.

- **Constructor extended** — accepts optional `pick_engine`, `pick_repo`, `telegram_bot`, `api_football_client` (defaults None for Phase 1+2 backcompat).
- **`_run_pipeline`** — calls `pick_engine.evaluate(prediction, opening_odds)` at `t_minus_2h` + `t_minus_30m`. **D-01 dup-alert guard (Blocker #1)** at `t_minus_30m`: queries `pick_repo.get_pending_for_fixture` and SKIPS evaluate when a `(fixture_id, market='1X2')` pick is already `PickStatus.pending`. Emits `t30_skipped_pending_already` log with `t2h_pick_id`.
- **`_reconcile_results`** — D-16 settlement at kickoff+150min:
  - All 16 API-Football status codes handled (Risk 9):
    - SETTLED: FT/AET/AWD/WO → won/lost from regulation+ET goals
    - PEN: 1X2 → push (Betano standard — penalty winner irrelevant for 1X2)
    - VOID: PST/CANC/ABD → `update_status_by_fixture(fixture_id, "void")`
    - IN_PLAY/NOT_STARTED: 1H/HT/2H/ET/BT/P/SUSP/INT/TBD/NS → reschedule +30min
    - Q3 RESOLVED: max 4 retries → log `reconcile_abandoned` ERROR, leave pending
    - Unknown codes → log ERROR, leave pending (Risk 9 no silent failure)
  - `misfire_grace_time=600` (Pitfall 7)
  - Skips non-1X2 markets (D-02 Phase 3 boundary)
- **`_register_fixture_jobs`** — added 4th DateTrigger at `kickoff+150min` for reconcile.
- **`_auto_recover`** extended — Pitfall 6 mitigation: `query_pending_sends` (max_age_minutes=30) + re-queue immediate `DateTrigger(now)` via `_send_recovered_pick`, skipping picks whose `send_pick_*` job already exists.
- **`_send_recovered_pick`** — recovery dispatch helper: rebuilds Pick from DB row, renders via `render_pick`, sends via `telegram_bot.send_html`.

## Tests

30 new GREEN total + 219 pre-existing = **249 / 0 fail / 12 skipped**:
- 14 reconcile tests (all 16 status codes covered via parametrize, 4 settlement, 1 reschedule, 1 max-retries, 1 abandoned, 3 unknown/awarded, 1 register)
- 7 orchestrator tests (4 auto-recover, 3 D-01 dup-alert guard)
- All pre-existing tests/test_scheduler.py + tests/picks/ + tests/claude/ + tests/telegram/ etc. unchanged

## Commits

- `12ba939`: feat(03-08): orchestrator integration + reconcile + auto-recover (PICK-05)

## Deviations

**One:** Plan-spec used `caplog` for asserting structlog ERROR events. structlog writes to stdout (not the standard logging module that caplog captures), so tests assert via `capsys` instead. Same invariant — the event is emitted — verified at the correct boundary.

## Phase 3 Gate

This plan completes Phase 3 implementation. All 12 plans done:
- 03-00 through 03-11 → all SUMMARY.md present
- Total tests: 249 GREEN, 12 skipped (legacy stubs in tests/test_engine.py from Wave 0 that are now superseded but kept for archeology)
