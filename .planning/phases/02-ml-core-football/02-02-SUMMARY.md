---
phase: 02-ml-core-football
plan: 2
subsystem: data-pipeline
tags: [api-football, seed, polars, parquet, checkpoint, rate-limit, historical-data]

# Dependency graph
requires:
  - phase: 01-foundation-data-pipeline-clv
    provides: ApiFootballClient, FeatureEngineer, ParquetStore, LeagueRegistry, FixtureData
provides:
  - One-off historical data seed script covering 5 leagues x 3 seasons (~5,700 fixtures)
  - Checkpoint-resumable seed runs (atomic write + replace)
  - Rate-limited (300 req/min) bulk historical backfill via Pro-plan client
  - Reusable season_date_range helper and matchday parser
affects:
  - 02-03 feature-expansion (Dixon-Coles ratings)
  - 02-04 per-league ensemble training
  - 02-05 walk-forward backtesting
  - 02-06 calibration per-league
  - 02-07 model registry

# Tech tracking
tech-stack:
  added:
    - structlog (already in Phase 1 stack; first use in scripts/)
  patterns:
    - D-01 enforcement: one-off scripts live at scripts/ OUTSIDE src/bip/ so the scheduler cannot import them
    - Atomic-write pattern for checkpoint files (.tmp + Path.replace) — reusable for any durable single-file state
    - Checkpoint-resume loop pattern for long-running API backfills (skip completed IDs, persist every N items)
    - Script-as-module test loading via importlib.util (tests can exercise scripts/ without modifying sys.path)

key-files:
  created:
    - scripts/seed_historical.py
    - tests/test_seed_checkpoint.py
    - data/.gitkeep
  modified: []

key-decisions:
  - "Use fixture.kickoff_utc as computed_at for historical rows — live pipeline uses now(UTC); both satisfy DATA-05 point-in-time correctness because pre-kickoff is the authoritative boundary"
  - "Persist checkpoint every 25 fixtures plus once per (league, season) — trades durability vs I/O; 25 is a safe batch for ~0.2s per request"
  - "Per-day GET /fixtures query over Aug 1 → May 31 season window — mirrors live pipeline granularity; 304 days * 5 leagues * 3 seasons = ~4,560 fixture-list requests, well under Pro plan quotas"
  - "Tests load scripts/seed_historical.py via importlib.util.spec_from_file_location — scripts/ is intentionally not on sys.path so D-01 is preserved"

patterns-established:
  - "D-01 boundary pattern: scheduler-excluded code lives under scripts/ not src/bip/; tests reach it via importlib"
  - "Atomic-write pattern: temp file with .tmp suffix → write → Path.replace() onto target for durable single-file state"
  - "Checkpoint-resume pattern: load set of completed IDs → skip inside loop → persist every N items + at batch boundaries"
  - "API key hygiene: never pass secrets into logger.info/warning/error calls — Phase 1 T-05-04 enforced via ApiFootballClient construction-time header, seed script reuses"

requirements-completed:
  - ML-01
  - ML-02

# Metrics
duration: 3min
completed: 2026-04-23
---

# Phase 02 Plan 02: Historical Data Seed Summary

**Checkpoint-resumable, rate-limited seed script pulling ~5,700 fixtures across 5 leagues x 3 seasons via the Phase 1 ApiFootballClient into the shared Hive-partitioned Parquet store, with GREEN tests covering checkpoint round-trip, atomic write, and empty-file handling.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-23T18:49:25Z
- **Completed:** 2026-04-23T18:52:06Z
- **Tasks:** 2
- **Files created:** 3
- **Files modified:** 0

## Accomplishments

- `scripts/seed_historical.py` — async seed covering 5 leagues x 3 seasons with Pro-plan (300 req/min) rate limit, structured logging, and `--seasons` CLI subset flag
- Checkpoint file at `data/seed_checkpoint.json` — atomic `.tmp` + `Path.replace()` write pattern; reruns skip already-completed fixture IDs
- D-01 enforcement: seed script lives OUTSIDE `src/bip/` so the scheduler cannot import it; tests reach it via `importlib.util.spec_from_file_location`
- 3 GREEN tests in `tests/test_seed_checkpoint.py` (resume round-trip, atomic write, empty-file default) — full suite 56/56 passing, no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Create scripts/seed_historical.py with checkpoint + rate-limited bulk pull** — `071ea4a` (feat)
2. **Task 2: Implement seed checkpoint tests in tests/test_seed_checkpoint.py (GREEN)** — `9e1e1b3` (test)

_Note: The TDD gate order is inverted vs canonical RED-then-GREEN because Task 1 shipped the functions the tests exercise (the plan explicitly sequenced it this way — Task 2's `<behavior>` describes tests against already-implemented helpers). See TDD Gate Compliance section below._

## Files Created/Modified

- `scripts/seed_historical.py` — Async seed loop: iterates leagues × seasons × day-by-day fixture queries; per-fixture pulls stats + lineups; writes features to `ParquetStore`; checkpoints every 25 fixtures and at each (league, season) boundary; lives outside `src/bip/` per D-01
- `tests/test_seed_checkpoint.py` — Three `TestSeedCheckpoint` methods verifying save/load round-trip, no-`.tmp`-leaks, and empty-set when checkpoint file is missing; uses `monkeypatch.setattr(seed, "CHECKPOINT_PATH", ...)` + `tmp_path` so no real `data/` state is touched
- `data/.gitkeep` — Empty marker ensuring `data/` directory exists and is git-tracked ahead of first seed run

## Decisions Made

- **`computed_at = fixture.kickoff_utc` for historical rows:** Live pipeline uses `datetime.now(UTC)`. For historical seed rows, using kickoff is correct under DATA-05 because pre-kickoff data is the authoritative point-in-time boundary; the live pipeline ultimately crosses the same boundary. This keeps the feature matrix semantically consistent across historical and live rows.
- **25-fixture checkpoint interval:** Balances durability (lose ≤25 fixtures on interrupt) vs I/O (one JSON write per ~5s of API calls at 0.2s/request). Also saved at each (league, season) boundary so resumes are clean.
- **Per-day `GET /fixtures` over Aug 1 → May 31 season window:** 304 days/season x 5 leagues x 3 seasons = ~4,560 fixture-list requests. Matches live pipeline granularity (per-day queries). Well within Pro plan daily quotas.
- **Tests load the script via `importlib.util.spec_from_file_location`:** `scripts/` is deliberately off `sys.path` (D-01). Tests reach the module by absolute path so D-01 is preserved — production code literally cannot `from scripts... import ...`.
- **Rate limit constant computed from RPM, not hardcoded:** `INTER_REQUEST_DELAY_S = 60.0 / RATE_LIMIT_RPM` (= 0.2s). If the API-Football plan tier changes, one constant updates.

## Deviations from Plan

None - plan executed exactly as written.

All acceptance criteria met on first attempt. No auto-fixes required. No architectural decisions deferred. Plan text mapped 1:1 to code.

## Issues Encountered

None. All verification steps passed on first run:
- Module imports cleanly; constants expose expected values (`CHECKPOINT_PATH=data/seed_checkpoint.json`, `SEASONS=['2023-2024', '2024-2025', '2025-2026']`, `INTER_REQUEST_DELAY_S=0.2`)
- `uv run python scripts/seed_historical.py --help` prints usage with `--seasons` flag
- `uv run ruff check` passes on both files
- `uv run pytest tests/test_seed_checkpoint.py -x -q` → 3 passed in 0.20s
- Full suite: 56/56 passing, no regressions

## TDD Gate Compliance

Plan-level `type: execute` (not `type: tdd`), but Task 2 has `tdd="true"`. Commit order:
- `9e1e1b3` test(02-02): tests for checkpoint helpers
- `071ea4a` feat(02-02): seed script with helpers

This is GREEN-first (feat before test) rather than canonical RED-then-GREEN, because the plan explicitly sequenced Task 1 to ship the helpers and Task 2 to verify them. Tests were GREEN on first run — no RED assertion recorded. This matches the plan's explicit intent ("Test 1 (test_checkpoint_resume): save_checkpoint({101, 102, 103}), then load_checkpoint() returns {101, 102, 103}" is a post-hoc verification spec, not a driving test). For future TDD-mode plans on new functionality, prefer RED → GREEN ordering.

## User Setup Required

None - no external service configuration required for this plan.

Manual run (deferred to phase gate): when the developer chooses to populate the Parquet store, they will invoke `uv run python scripts/seed_historical.py --seasons 2025-2026` with `API_FOOTBALL_KEY` set in `.env`. No new secrets, no new dashboards, no new quotas.

## Next Phase Readiness

- **Plan 02-03 (feature expansion):** ParquetStore now has a documented path for bulk historical backfill; feature engineer can expand `_extract_features` in confidence that the upstream seed path exists
- **Plan 02-04 (ensemble training):** Training pipeline will read from the same `data/cache/features/sport=football/league=*/season=*/matchday=*/*.parquet` partition layout this seed writes to — zero schema drift between seed and live paths
- **Plan 02-05 (walk-forward backtesting):** Historical partitions enable walk-forward splits; the `season` partition column is the natural split key
- **No blockers** for the remaining Phase 2 plans. Seed is ready to run whenever the developer decides to populate Parquet (expected before Plan 02-04)

## Self-Check: PASSED

Verified:
- `scripts/seed_historical.py` exists (FOUND)
- `data/.gitkeep` exists (FOUND)
- `tests/test_seed_checkpoint.py` exists (FOUND)
- Commit `071ea4a` present in git log (FOUND)
- Commit `9e1e1b3` present in git log (FOUND)
- `uv run pytest tests/test_seed_checkpoint.py -x -q` → 3 passed
- `uv run ruff check scripts/seed_historical.py tests/test_seed_checkpoint.py` → All checks passed
- `uv run python scripts/seed_historical.py --help` → usage printed
- Full regression sweep: 56/56 pytest passing

---
*Phase: 02-ml-core-football*
*Completed: 2026-04-23*
