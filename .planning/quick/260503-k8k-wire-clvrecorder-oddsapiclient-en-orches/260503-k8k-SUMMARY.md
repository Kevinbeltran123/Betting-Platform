---
plan_id: 260503-k8k
title: Wire ClvRecorder + OddsApiClient into orchestrator (real CLV snapshot)
type: tdd
status: complete
completed: 2026-05-03
duration_min: ~25
tasks_completed: 2
files_created: 1
files_modified: 4
tests_added: 9
tests_total_after: 282
---

# Quick Task 260503-k8k -- Summary

**One-liner:** PipelineOrchestrator._record_clv now resolves the Pinnacle event,
fetches closing odds, projects outcomes into {1,X,2}, and persists one ClvRecord
per pending 1X2 pick at kickoff - 1 minute (replacing the old logging-only stub
and the +105m placeholder trigger).

## Tasks

| Task | Type | Description | Commit(s) |
|------|------|-------------|-----------|
| 1 | TDD | OddsApiClient.find_event_by_fixture (sport_key + team-name + ±2h commence_time match → event_id, retry-decorated) | 8b2c0cd (RED), 58289a7 (GREEN) |
| 2 | TDD | Wire ClvRecorder + OddsApiClient + LeagueRegistry into PipelineOrchestrator; rewrite _record_clv with real snapshot logic; defer _reconcile_clv to Phase 4; move snapshot trigger from kickoff +105m to kickoff -1m | f09f7a7 (RED), 25a15f1 (GREEN) |

## Files

### Modified

- `src/bip/clv/client.py` -- added `find_event_by_fixture` method (calls
  `/v4/sports/{sport_key}/events`, case-insensitive home/away contains-match,
  ±2h commence_time tolerance, same retry decorator as
  `fetch_pinnacle_closing_odds`).
- `src/bip/scheduler/orchestrator.py` -- added 3 optional constructor kwargs
  (`odds_api_client`, `clv_recorder`, `league_registry`); rewrote `_record_clv`
  body (~110 lines of real wiring logic with structured early-return logs);
  replaced `_reconcile_clv` body with a `clv_reconciliation_deferred` warning;
  changed snapshot trigger from `kickoff + timedelta(minutes=105)` to
  `kickoff - timedelta(minutes=1)`; removed obsolete `clv_snapshot_triggered`
  log line.
- `tests/test_clv_client.py` -- added `TestFindEventByFixture` class (5 tests):
  team-and-time match, no-team-match, time-window-miss, case-insensitive
  matching, apiKey query param presence on /events call.
- `tests/scheduler/test_orchestrator.py` -- added `TestRecordClv` class
  (4 tests): happy path (pending pick + matched event + Pinnacle quote →
  ClvRecorder.record), skip-no-pending, skip-no-pinnacle-event, skip-unwired.
- `tests/test_scheduler.py` -- updated the structural CLV trigger test to
  assert `t_minus_1m` and `kickoff - timedelta(minutes=1)` against the
  rewritten `_register_fixture_jobs` source (was: literal "105" in
  `_daily_orchestrator`).

### Created

- `.planning/quick/260503-k8k-wire-clvrecorder-oddsapiclient-en-orches/260503-k8k-PLAN.md`

## Verification

| Check | Result |
|-------|--------|
| `uv run pytest tests/test_clv_client.py -v` | 9 passed (4 existing + 5 new) |
| `uv run pytest tests/scheduler/ -v` | 37 passed (33 existing + 4 new) |
| `uv run pytest -q` | 282 passed, 0 failed (was 273 baseline) |
| `grep -n "clv_snapshot_triggered" src/bip/scheduler/orchestrator.py` | empty (removed) |
| `grep -n "clv_recorder" src/bip/scheduler/orchestrator.py` | 6 hits (constructor kwarg, attr, log keys, gating, .record() call) |
| `_record_clv` body length | ~110 lines of real logic |
| `_reconcile_clv` body | `logger.warning("clv_reconciliation_deferred", note="Phase 4 ...")` |
| Snapshot trigger | `t_minus_1m = kickoff - timedelta(minutes=1)` (id `clv_{fixture_id}_t_minus_1m`) |

## Key Decisions

- **Snapshot trigger moved from kickoff + 105m to kickoff - 1m.** The +105m
  trigger was a placeholder while the recorder was unwired -- semantically
  wrong because Pinnacle h2h freezes at kickoff. Capturing 1 minute prior is
  the actual closing line we benchmark CLV against.
- **One ClvRecord per pending 1X2 pick on the fixture.** Multiple pending picks
  on the same 1X2 market are rare but possible (e.g., T-2h pick stayed pending
  through T-30m re-evaluation); each gets its own snapshot row so the audit
  trail joins cleanly to picks via pick_id.
- **`_reconcile_clv` kept callable but deferred.** The nightly cron entry stays
  (ops can confirm it fires); the body is a single warning until Phase 4 lands
  rolling-50 trend alerting + back-fill for fixtures that missed the T-1m
  snapshot. Signature unchanged so the existing `start()` registration still
  works.
- **`league_registry` is optional** (falls back to `"soccer_epl"`). The
  registry has a flat `slug → LeagueConfig.api_mappings.odds_api_sport_key`
  shape; keeping it optional preserves the existing `PipelineOrchestrator(plugin=plugin)`
  call sites (the existing 273 tests construct orchestrators in many shapes).
- **Outcome projection is name-based, case-insensitive contains.** Pinnacle
  returns outcomes as `{name: <team or "Draw">, price: <decimal>}`; we map
  `"Draw"` → `"X"`, fixture.home_team → `"1"`, fixture.away_team → `"2"`. If
  the projected dict is incomplete (missing any of `1/X/2`) we log
  `clv_skip_incomplete_market` and skip recording rather than persisting a
  partial market.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated stale `test_scheduler.py` structural test**

- **Found during:** verification after Task 2 GREEN
- **Issue:** `tests/test_scheduler.py::test_clv_snapshot_job_registered_at_kickoff_plus_105min`
  asserted that the literal `"105"` appears in `_daily_orchestrator`'s source.
  After moving the snapshot trigger to kickoff - 1m (intentional spec change
  per the plan), the literal no longer exists. The test was a stale
  placeholder from the unwired era.
- **Fix:** Renamed to `test_clv_snapshot_job_registered_at_kickoff_minus_1min`,
  updated docstring, asserted `"t_minus_1m"` and
  `"kickoff - timedelta(minutes=1)"` against `_register_fixture_jobs` source
  (the actual location of the trigger).
- **Files modified:** `tests/test_scheduler.py`
- **Commit:** included in `25a15f1` (Task 2 GREEN)

**2. [Rule 3 - Blocking] Installed missing `pytest_httpx` dependency**

- **Found during:** baseline `uv run pytest --collect-only` (before Task 1 RED)
- **Issue:** `tests/test_clv_client.py` already imported `from pytest_httpx
  import HTTPXMock`, but `pytest-httpx` was declared in `pyproject.toml` dev
  extras and not installed in the worktree's `.venv`. Three test files were
  failing collection.
- **Fix:** `uv sync --extra dev` -- installed `pytest_httpx-0.36.2` (declared
  spec: `>=0.35.0`).
- **Files modified:** none (`uv.lock` was already correct)
- **Commit:** none (environment fix only)

## Auth Gates

None.

## Threat Flags

None. The new code path is internal (orchestrator -> existing OddsApiClient ->
existing ClvRecorder); no new network endpoint, no new auth surface, no new
trust boundary.

## Known Stubs

`_reconcile_clv` is now an explicit Phase-4 deferral (`clv_reconciliation_deferred`
warning + comment). The cron entry is intentional (ops visibility while the
deliverable is pending); this is not an accidental UI/data stub -- it is a
documented placeholder for Phase 4 work.

## Self-Check: PASSED

- FOUND: `src/bip/clv/client.py` (modified, has `find_event_by_fixture`)
- FOUND: `src/bip/scheduler/orchestrator.py` (modified, has new kwargs +
  rewritten `_record_clv`)
- FOUND: `tests/test_clv_client.py` (modified, has `TestFindEventByFixture`)
- FOUND: `tests/scheduler/test_orchestrator.py` (modified, has `TestRecordClv`)
- FOUND: `tests/test_scheduler.py` (modified, structural check updated)
- FOUND commit: `8b2c0cd` (Task 1 RED)
- FOUND commit: `58289a7` (Task 1 GREEN)
- FOUND commit: `f09f7a7` (Task 2 RED)
- FOUND commit: `25a15f1` (Task 2 GREEN)
- FOUND: 282 tests pass (was 273 baseline; +9 new = 5 client + 4 orchestrator)

## TDD Gate Compliance

Both tasks executed full RED → GREEN cycle:

- Task 1: `test(quick-260503-k8k): RED tests for OddsApiClient.find_event_by_fixture`
  → `feat(quick-260503-k8k): OddsApiClient.find_event_by_fixture`
- Task 2: `test(quick-260503-k8k): RED tests for orchestrator _record_clv wiring`
  → `feat(quick-260503-k8k): wire ClvRecorder + OddsApiClient into orchestrator`

REFACTOR phase: not needed -- both implementations were minimal-by-design.
