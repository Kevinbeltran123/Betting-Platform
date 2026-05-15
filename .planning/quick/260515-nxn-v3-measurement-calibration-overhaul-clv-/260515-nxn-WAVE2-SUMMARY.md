---
phase: 260515-nxn
plan: 01
wave: 2
subsystem: engine_v3/clv
tags: [clv, shadow-promotion, parquet-sink, measurement]
completed_date: 2026-05-15
---

# Phase 260515-nxn Wave 2: CLV Sink + Shadow-Promotion Harness Summary

**One-liner:** Vig-removed CLV parquet sink for delivered v3 picks (goals/btts/1X2 scope) + per-rule shadow-promotion report grading via canonical v3_grader.

## Commits

| Task | Subject | Commit | Files | Tests Added |
|------|---------|--------|-------|-------------|
| 2.1 | `feat(clv): v3 live CLV parquet sink (goals/btts/totals; corners unsupported)` | `ec68070` | `src/bip/clv/v3_clv_sink.py` (new), `tests/evaluation/live/engine_v3/test_v3_clv_sink.py` (new) | 24 |
| 2.2 | `feat(scripts/v3): shadow-promotion report (per-rule promote/keep/revert deltas)` | `02587c3` | `scripts/spike/v3/shadow_promotion_report.py` (new), `tests/evaluation/live/engine_v3/test_shadow_promotion_report.py` (new) | 26 |

**Pre-wave merge commit:** `bec55a3` — merged Wave 1 (ecdd707) into worktree branch before starting (worktree was behind main by 2 commits).

## What Changed

### Task 2.1 — v3 CLV parquet sink (`src/bip/clv/v3_clv_sink.py`)

New module providing a callable `run_clv_sink_for_delivered_picks` that:

- Reads `deliveries.parquet` from Wave 1 filtered to `send_result="sent"` — CLV measured only on SENT picks
- For supported families (goals, btts, totals, result_1x2): calls `OddsApiClient.find_event_by_fixture` + `fetch_pinnacle_closing_odds`, then computes vig-removed CLV via `calculate_clv_percentage` from `bip.clv.recorder` (untouched)
- For unsupported families (corners, cards, next_goal): writes row with `clv_percentage=None` + `reason="clv_unsupported_family"` — OddsApiClient has no Betfair/corners support per plan scope constraints
- Persists to `data/cache/v3_shadow/dt=*/clv.parquet` using same `diagonal_relaxed` append as `shadow_logger`
- Provides `rolling_clv_from_parquet()` for trend monitoring (wraps `compute_rolling_clv_average`)
- `ClvRecorder`/Supabase NOT touched
- Scheduler wiring deferred (noted in commit body): wire as DateTrigger at kickoff+5min in `watch.py` flush site

### Task 2.2 — Shadow-promotion report (`scripts/spike/v3/shadow_promotion_report.py`)

New script + `build_promotion_report` callable that:

- Reads `gate_denials.parquet` filtered to `is_shadow=True` (rule_8, rule_9 shadow denials)
- Reads `gsv_log.parquet` and extracts frames where `shadow_dominant_team_id != dominant_team_id` (the 0.025 vs 0.04 gap divergence)
- Grades shadow-denied theses via canonical `v3_grader.grade_picks_for_date` — NOT GSV reconstruction
- Per rule computes: `n`, `effective_N` (unique fixtures — prevents one blowout dominating), `delta_pl`, `delta_precision`, `delta_volume`, `clv_delta` (where clv.parquet has coverage)
- Recommendation logic: `PROMOTE` (effective_N ≥ 5 AND delta_pl > 0 AND delta_precision ≥ 0), `REVERT` (effective_N ≥ 5 AND delta_pl < -2.0), `KEEP-SHADOW` otherwise
- Three tracked rules: `rule_8`, `rule_9`, `dom_gap_0.025vs0.04`
- Emits markdown table + detailed notes, or JSON (`--format json`)
- CLI: `uv run python -m scripts.spike.v3.shadow_promotion_report --start YYYY-MM-DD --end YYYY-MM-DD`

## Tests Added

### Task 2.1: 24 tests in `tests/evaluation/live/engine_v3/test_v3_clv_sink.py`
- `TestExtractClosingOddsDict` (4) — h2h/totals outcome extraction, missing market, single outcome
- `TestResolveSelectionKey` (4) — direct match, substring, direction-map, no match
- `TestComputeClvForRow` (6) — goals picks with CLV, corners unsupported family, no event match, no pinnacle data, no bookmaker odd, btts picks
- `TestRunClvSinkForDeliveredPicks` (4) — goals→clv.parquet, corners→unsupported row, skipped/failed excluded, no deliveries=empty
- `TestWriteClvRecords` (3) — single partition, append, null CLV row
- `TestRollingClvFromParquet` (3) — no data→None, average from parquet, null rows excluded

### Task 2.2: 26 tests in `tests/evaluation/live/engine_v3/test_shadow_promotion_report.py`
- `TestReadShadowDenials` (5) — is_shadow filter, no shadow rows, date range, no parquets, missing column
- `TestRecommend` (4) — insufficient data, revert, promote, mixed signals
- `TestComputeRuleResult` (9) — effective_N present, deduplication, delta_pl, delta_volume, CLV delta, no coverage, keep-shadow, promote, revert
- `TestBuildPromotionReport` (4) — all rules present, effective_N always present, deterministic deltas, no data
- `TestFormatting` (4) — markdown rules, JSON validity, effective_N in JSON, markdown table header

## Final Test Counts (Honest)

| Checkpoint | Count |
|-----------|-------|
| Baseline (Wave 1 merged, venv synced) | 513 passed, 2 skipped |
| After task 2.1 commit | 537 passed, 2 skipped |
| After task 2.2 commit | 563 passed, 2 skipped |

**Verified cause of 2 skipped:** Pre-existing skips (OOD/calibrator-dependent tests that skip when pkl files absent in worktree). Identical skip behavior on base commit ecdd707.

**Anti-Napoli regression:** 53/53 passed after both commits.

## Deviations from Plan

### Pre-wave: Worktree behind main

Wave 1 (ecdd707) had been merged to main but the worktree was still at commit 5886142 (Wave 0). Merged main into the worktree branch (`bec55a3`) before starting Wave 2. This is expected workflow in the sequential-wave pattern — no code deviation.

### Auto-fix (Rule 2): Module-level import for patchable grader

Task 2.2 initially imported `grade_picks_for_date` inside `build_promotion_report` (local import). This prevented `patch.object` from targeting it in tests (AttributeError on module attribute). Fixed by hoisting the import to module level so the symbol is patchable — standard Python testability pattern, no behavioral change.

### Auto-fix (Rule 2): Structlog vs stdlib logger kwargs

Initial draft used `log = logging.getLogger()` but passed structlog-style `key=value` kwargs to `log.warning()`. Fixed by switching to `structlog.get_logger()` (consistent with the rest of the codebase). No behavioral change to production logging.

## Known Stubs

None that block the plan's goal. The one intentional stub:

- `run_clv_sink_for_delivered_picks` is NOT wired to the live scheduler. Documented in commit body: wire as `DateTrigger` at kickoff+5min in `watch.py`. This is the defined follow-up per the plan spec ("just the sink + a tested function; wiring is a follow-up note in the commit body").

## Threat Flags

None — no new network endpoints, auth paths, or trust boundaries introduced. The CLV sink reads local parquet files and calls existing OddsApiClient (already in scope). The promotion report is a read-only offline analysis tool.
