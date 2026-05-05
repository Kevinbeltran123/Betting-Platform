---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: phase_4_complete_pending_staging
stopped_at: Phase 4 plans 04-00 through 04-08 all complete; staging smoke test (4-07-03) pending operator
last_updated: "2026-05-04T22:00:00.000Z"
last_activity: 2026-05-04 -- Phase 4 execution complete (9/9 plans, 350 tests passing)
progress:
  total_phases: 8
  completed_phases: 5
  total_plans: 57
  completed_plans: 48
  percent: 84
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-22)

**Core value:** Find and deliver bets with genuine statistical edge (CLV > +3% against Pinnacle closing lines) -- if there's no edge, send nothing.
**Current focus:** Phase 4 — production-orchestration (COMPLETE pending staging smoke test)

## Current Position

Phase: 4 (production-orchestration) — COMPLETE pending staging smoke test
Plan: 9 of 9 (all SUMMARY.md files written)
Next: Operator runs `deploy/SMOKE_TEST.md` on Hetzner VPS, then `/gsd-verify-work 4` (or proceed directly to Phase 5 if staging is queued for later)
Status: Phase 4 ready for operator staging exercise
Last activity: 2026-05-04 -- 19 commits across 9 plans; 350 tests passing, 0 skipped, 0 regressions; migration 005 live in Supabase

Progress: [██████████] 100%

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

- Phase 3 closeout (2026-05-03) — quick task series 260503-iql/j74/jkf/k8k closed audit gaps from .planning/AUDIT-GAPS.md before first real pick. Decisions:
  - **Wiring strategy: Strategy 2** — orchestrator constructs full `Prediction` Pydantic before invoking engine; `plugin.predict()` stays returning pure `ProbabilityMap`. Reasons: cleaner separation; Prediction is canonical persistence model; engine signature explicit.
  - **CLV vig removal**: proportional vig removal applied via `bip.clv.odds_math.remove_vig` (Pitfall 7). `ClvRecord.pinnacle_closing_odds` keeps RAW odd (audit trail); `clv_percentage` uses fair odds (success metric). No schema migration.
  - **Per-market thresholds**: `PickEngine.__init__` takes required `league_registry`; lookup `LeagueConfig.model_params.edge_threshold_{normalized_market}` per pick. `EDGE_THRESHOLD_PCT` in `bip.train.backtest` is now backtest-default only.
  - **Closing-line snapshot timing**: moved from `kickoff+105m` (post-match) to `kickoff-1min` (true closing line per Pitfall 7). Result-reconciliation job remains at +105m — different concern.
  - **Event mapping**: added `OddsApiClient.find_event_by_fixture(sport_key, home_team, away_team, kickoff_utc)` using `/v4/sports/{sport_key}/events`. `LeagueConfig.api_mappings.odds_api_sport_key` provides the per-league mapping (no hardcoding required).
  - **Test integrity**: spec-based mocks enforced for `SportPlugin` and `PickRepository`; `tests/test_plugin_contract.py` validates ABC has all 6 abstract methods including `get_opening_odds`.
  - **Out of scope** (Phase 4+): CLV-03 alerting wire (rolling avg function exists, scheduler job missing), CLV-04 daily aggregator, `_reconcile_clv` real implementation, production setup wiring (`__main__.py` instantiation of ClvRecorder/OddsApiClient).
  - **Production caller of PickEngine** does NOT yet exist — only tests instantiate it. Production wiring is a Phase 4 deployment concern.
  - **Empirical PL smoke train** (~1,520 API credits) remains user-deferred — converts ML-02/ML-03 from `structural PASS` to `empirical PASS`.

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
| 260503-jkf | Orchestrator/Plugin/Engine wiring (Strategy 2) | 2026-05-03 | e68df0e | [260503-jkf-orchestrator-plugin-engine-wiring-predic](./quick/260503-jkf-orchestrator-plugin-engine-wiring-predic/) |
| 260503-k8k | Wire ClvRecorder + OddsApiClient en orchestrator (kickoff-1m + find_event_by_fixture) | 2026-05-03 | cc0db4d | [260503-k8k-wire-clvrecorder-oddsapiclient-en-orches](./quick/260503-k8k-wire-clvrecorder-oddsapiclient-en-orches/) |
| 260503-oml | MarketKey enum + migrate callers (G-MAINT-05) | 2026-05-03 | fc0ced1 | [260503-oml-marketkey-enum-migrar-callers-g-maint-05](./quick/260503-oml-marketkey-enum-migrar-callers-g-maint-05/) |
| 260503-q43 | Move bip/scheduler to bip/core/scheduler (G-CODE-04/10) | 2026-05-03 | 2e192d8 | [260503-q43-mover-bip-scheduler-a-bip-core-scheduler](./quick/260503-q43-mover-bip-scheduler-a-bip-core-scheduler/) |
| 260503-txj | Reconcile knobs configurable via Settings (G-MAINT-10) | 2026-05-03 | 6cc30ca | [260503-txj-reschedule-cadence-max-retries-a-setting](./quick/260503-txj-reschedule-cadence-max-retries-a-setting/) |

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: --stopped-at
Stopped at: Phase 4 context gathered
Resume file: --resume-file

**Planned Phase:** 04 (production-orchestration) — 9 plans — 2026-05-04T04:45:40.113Z
