---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Phase 3 context gathered
last_updated: "2026-05-03T19:10:00.000Z"
last_activity: 2026-05-03 -- Completed quick task 260503-j74: Per-market edge thresholds desde YAML
progress:
  total_phases: 8
  completed_phases: 3
  total_plans: 39
  completed_plans: 29
  percent: 74
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-22)

**Core value:** Find and deliver bets with genuine statistical edge (CLV > +3% against Pinnacle closing lines) -- if there's no edge, send nothing.
**Current focus:** Phase --phase — 03

## Current Position

Phase: --phase (03) — EXECUTING
Plan: 1 of --name
Next: Execute Phase 2 (7 plans, 6 waves)
Status: Executing Phase --phase
Last activity: 2026-05-03 -- Phase --phase execution started

Progress: [██████████] 96%

## Performance Metrics

**Velocity:**

- Total plans completed: 13
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 02.1 | 13 | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 02.1 P00 | 4min | 1 tasks | 6 files |
| Phase 02.1 P01 | 16min | 2 tasks | 3 files |
| Phase 02.1 P03 | 7min | 1 tasks | 2 files |
| Phase 02.1 P04 | 2min | 1 tasks | 2 files |
| Phase 02.1 P05 | 2 | 1 tasks | 2 files |
| Phase 02.1 P06 | 2min | 1 tasks | 2 files |
| Phase 02.1 P07 | 1min | 1 tasks | 1 files |
| Phase 02.1 P08 | 3min | 2 tasks | 3 files |
| Phase 02.1 P09 | 4min | 2 tasks | 2 files |
| Phase 02.1 P10 | 6min | 2 tasks | 3 files |
| Phase 02.1 P11 | 12min | 1 tasks | 2 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: CLV infrastructure is Phase 1, not deferred -- every downstream decision depends on it
- [Roadmap]: Account longevity protections ship with first Telegram alert (Phase 3), not later
- [Roadmap]: Claude Role C (validator) ships Phase 3; Role B (confidence modifier) ships Phase 5 in shadow mode
- [Roadmap]: CORNERS-01 gate executed in Phase 3; Phase 6 engineering conditional on gate passing
- [Roadmap]: Walk-forward backtesting uses opening odds + slippage from day 1 (non-negotiable, not retrofittable)
- Phase 02.1 Wave 0 stubs use module-level pytest.mark.skip; verify_migration_003.py stub returns exit 1 even when SUPABASE_DB_PASSWORD set so accidental run cannot mark D-15 complete
- Phase 02.1 D-15 (live migration 003) satisfied via Supabase MCP apply_migration; reconstructed migration 001 (base_schema) from Pydantic models because live project was empty (CLAUDE.md schema claim was inherited from upstream)
- Phase 02.1 P03 — EDGE_THRESHOLD_PCT lives in bip.train.backtest (single source) so backtest CLV and Phase 3 pick engine import the same symbol; D-10 single-source-of-truth satisfied
- Phase 02.1 P04 — ModelMetadata.logloss_(uncalibrated|calibrated|improvement_pct) added as float | None = None; nullable defaults preserve Phase 2 backcompat (Pitfall 7); negative improvement_pct allowed (Pitfall 6 — regression signal)
- Phase 02.1 P05 — ParquetStore extended with write/read_results + write/read_odds (3-level Hive: sport/league/season). _write helper refactored to accept partition_cols kwarg; features store unchanged at 4-level. Pitfall 1 + Pitfall 4 regression guards in test suite.
- Phase 02.1 P06 — get_odds dispatch: fixture_id-only for live (Phase 3), league_id+season for historical bulk seeding (research finding 1: /odds?fixture has 7-day lookback). Single method, two modes, ValueError on neither.
- Phase 02.1 P07 — fetch_historical_closing stub returns None + structlog warning (D-01); no @retry on stub (retry stack lands with real implementation post-02.1); Pinnacle /v4/historical implementation deferred until API-Football CLV numbers validate dual-source architecture
- Phase 02.1 P08 — feature_schema_version=2 stamped on every new feature row (D-08); ParquetStore.read_features warns on Phase 1 mixed reads (column absent → implicit v1). Hardcoded literal, not config; warning suppressed on empty DataFrames to prevent test false alarms.
- Phase 02.1 P09 — seed_historical extended with results + bulk odds in single pass; 3-key checkpoint (features/results/odds) with Phase 2 backward-compat; ALLOWED_LEAGUE_SLUGS frozenset enforced before any I/O (T-02.1-04); _parse_odds_entry rejects partial Match Winner markets
- Phase 02.1 P10 — TrainingPipeline.run() now joins features+results+odds on fixture_id and computes per-fold CLV via simulate_pick + per-fold logloss with labels=[0,1,2] (research finding 2 invariant). walk_forward_mean_clv_pct made nullable in ModelMetadata to honor D-11 (None when no fold reaches >=20 picks); CLI format strings updated. Phase 2 home_goals schema guard removed; replaced by zero-rows RuntimeError on the join. Closes Phase 2 verification ML-02 and ML-03 (PARTIAL → PASS pending smoke train numbers from 02.1-12).
- Phase 02.1 P11 — synthetic e2e gate: TrainingPipeline.run() exercised in tmp_path; surfaced 3 Rule 1 bugs in plan 02.1-10 wiring (df_results suffix collision; _EnsembleProbaWrapper non-pickleable nested + missing sklearn 1.8 BaseEstimator + missing predict). All auto-fixed. 120 tests pass.

### Roadmap Evolution

- Phase 2.1 inserted after Phase 2 (2026-04-24): Close Phase 2 verification gaps — CLV end-to-end test + logloss improvement documentation (URGENT). Driver: Phase 2 verification (commit 43b4a7a) reported 2/4 PARTIAL items blocking clean handoff to Phase 3.

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 1]: Pinnacle closing line delay via The Odds API unknown -- must measure empirically; fallback is Betfair Exchange
- [Phase 3]: CORNERS-01 gate outcome unknown -- determines whether Phase 6 proceeds
- [Phase 5]: Claude Role B is a novel ML integration with no established patterns -- needs careful backtesting design

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260503-iql | Vig removal en CLV recorder | 2026-05-03 | 783b05c | [260503-iql-vig-removal-en-clv-recorder](./quick/260503-iql-vig-removal-en-clv-recorder/) |
| 260503-j74 | Per-market edge thresholds desde YAML | 2026-05-03 | db0075d | [260503-j74-per-market-edge-thresholds-desde-yaml](./quick/260503-j74-per-market-edge-thresholds-desde-yaml/) |

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: --stopped-at
Stopped at: Phase 3 context gathered
Resume file: --resume-file

**Planned Phase:** 3 (pick-engine-delivery-account-protection) — 12 plans — 2026-05-02T20:26:30.526Z
