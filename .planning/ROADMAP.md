# Roadmap: betting-intelligence-platform

## Overview

This roadmap delivers a production betting intelligence platform in 7 phases, following a strict dependency chain: foundation and CLV infrastructure first (the primary success metric), then ML models trained against honest backtesting, then pick delivery with account protection from day one. Claude AI roles ship in dependency order (validator before confidence modifier). Timed corners is conditional on a hard go/no-go gate. Tennis scaffold validates the plugin architecture last.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation + Data Pipeline + CLV** - Plugin architecture, async data client, Supabase schema, feature store, and CLV recording infrastructure
- [x] **Phase 2: ML Core -- Football** - Ensemble training pipeline with walk-forward backtesting using opening odds + slippage from day 1
- [ ] **Phase 3: Pick Engine + Delivery + Account Protection** - EV filter, Kelly sizing, Betano account longevity protections, Telegram alerts, and Claude validator (Role C)
- [ ] **Phase 4: Production Orchestration** - APScheduler pipeline, systemd deployment, graceful degradation, health monitoring, and CLV trend alerting
- [ ] **Phase 5: Claude Confidence Modifier (Shadow)** - Role B confidence modifier shipped in shadow mode; promoted only after walk-forward CLV improvement confirmed
- [ ] **Phase 6: Timed Corners Module (Conditional)** - Corner time-window distribution model and EV integration, gated on CORNERS-01 verification
- [ ] **Phase 7: Scalability Validation -- Tennis Scaffold** - Tennis SportPlugin scaffold proving zero core changes required for new sports

## Phase Details

### Phase 1: Foundation + Data Pipeline + CLV
**Goal**: The platform has a working plugin architecture, can ingest football data from API-Football, store features in Parquet, persist to Supabase, and record CLV against Pinnacle closing lines
**Depends on**: Nothing (first phase)
**Requirements**: CORE-01, CORE-02, CORE-03, CORE-04, CORE-05, DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, CLV-01, CLV-02, CLV-03, CLV-04
**Success Criteria** (what must be TRUE):
  1. Running the football plugin fetches today's fixtures, stats, lineups, injuries, and H2H from API-Football and stores them in Hive-partitioned Parquet files with correct `computed_at` timestamps
  2. Supabase migration 002 succeeds and all 6 tables accept rows with `sport='football'` and `sport='tennis'` (schema is sport-agnostic)
  3. The Odds API client fetches Pinnacle closing odds for a completed match and records CLV percentage in the `clv_records` table
  4. An integration test confirms no future data leaks -- every feature is computable from data available at prediction time
  5. APScheduler triggers the data pipeline at T-2h and T-30min before a fixture kickoff on the configured schedule
**Plans**: 7 plans

Plans:
- [x] 01-01-PLAN.md — Project scaffold: pyproject.toml, Python 3.12, directory skeleton, migration 002 SQL
- [x] 01-02-PLAN.md — Wave 0 test stubs: all 11 test files for Nyquist compliance
- [x] 01-03-PLAN.md — Core layer port: types, errors, logging, settings, storage (models/repos/parquet)
- [x] 01-04-PLAN.md — SportPlugin ABC + football config: leagues, markets YAML, FootballPlugin stub
- [x] 01-05-PLAN.md — Football async client + feature engineering: ApiFootballClient, FeatureEngineer, plugin wiring
- [x] 01-06-PLAN.md — CLV infrastructure: OddsApiClient, ClvRecorder, rolling average utility
- [x] 01-07-PLAN.md — APScheduler orchestrator + Supabase migration 002 apply [BLOCKING]

### Phase 2: ML Core -- Football
**Goal**: A calibrated ensemble model produces probability maps for football matches, validated by walk-forward backtesting with opening odds and slippage, with model versioning and shadow mode infrastructure
**Depends on**: Phase 1
**Requirements**: ML-01, ML-02, ML-03, ML-04, ML-05
**Success Criteria** (what must be TRUE):
  1. Walk-forward backtest over 5 leagues produces per-fold CLV estimates using opening odds with 1-2% slippage applied -- not closing odds
  2. Calibration uses Platt scaling for leagues with <300 validation samples and isotonic regression for leagues with >500 samples, with documented logloss improvement per league
  3. A new model version is saved to `models/football/{league}/{version}/` with `metadata.json` containing training date, feature set hash, calibration method, and backtest CLV
  4. Shadow mode logs a new model's predictions to Supabase with `is_shadow=true` without affecting the production prediction pipeline
**Plans**: 7 plans

Plans:
- [x] 02-01-PLAN.md — Wave 0 test stubs (13 new test files) + pyproject.toml ML dependency set + pytest slow marker (2026-04-23)
- [x] 02-02-PLAN.md — Historical data seed script (scripts/seed_historical.py) — checkpointed, rate-limited, Pro-plan aware (D-01) (2026-04-23)
- [x] 02-03-PLAN.md — FeatureEngineer expansion: rolling form, ELO (penaltyblog), H2H, motivation, rest days, odds signals + matchday parsing from API (2026-04-23)
- [x] 02-04-PLAN.md — bip.train package skeleton: WalkForwardSplitter, StackedEnsemble with nested OOF (D-03b), base-model hyperparams, backtest CLV math (2026-04-23)
- [x] 02-05-PLAN.md — Calibration module (Platt/Isotonic selection, sklearn 1.8 FrozenEstimator) (2026-04-23)
- [x] 02-06-PLAN.md — Artifact layer: ModelMetadata, ModelRegistry, ModelLoader, TrainingPipeline, Typer CLI + migration 003 (is_shadow column) [BLOCKING checkpoint]
- [x] 02-07-PLAN.md — FootballPlugin.predict() wiring: registry-driven production + shadow paths, graceful cold-start fallback

### Phase 02.1: Close Phase 2 verification gaps: CLV end-to-end test + logloss improvement documentation (INSERTED)

**Goal:** Wire `apply_slippage` + `compute_clv` into `TrainingPipeline.run()`, extend `seed_historical.py` to fetch historical opening odds (Betano via API-Football) + match results, surface real per-fold CLV numbers in `metadata.json`, and persist calibrated-vs-uncalibrated logloss improvement — closing both PARTIAL gaps from the Phase 2 verification report.
**Requirements**: ML-02, ML-03
**Depends on:** Phase 2
**Plans:** 13 plans

Plans:
- [x] 02.1-00-PLAN.md — Wave 0 stubs: 5 pytest stubs + verify_migration_003.py skeleton (2026-05-02)
- [x] 02.1-01-PLAN.md — Migration 003 verification script (psycopg, information_schema queries, D-15) (2026-05-02)
- [x] 02.1-02-PLAN.md — One-shot probe script for bulk /odds?league&season endpoint (verification deferred per user) (2026-05-01)
- [x] 02.1-03-PLAN.md — backtest.py: EDGE_THRESHOLD_PCT + simulate_pick() (D-09, D-10) (2026-05-02)
- [x] 02.1-04-PLAN.md — ModelMetadata: logloss_uncalibrated / logloss_calibrated / logloss_improvement_pct fields (D-13) (2026-05-02)
- [x] 02.1-05-PLAN.md — ParquetStore: write_results / read_results / write_odds / read_odds with 3-level Hive partitioning (D-04) (2026-05-02)
- [x] 02.1-06-PLAN.md — ApiFootballClient.get_odds() dual-mode dispatch: per-fixture (live) + bulk-per-season (historical) (2026-05-02)
- [x] 02.1-07-PLAN.md — OddsApiClient.fetch_historical_closing() stub (plumbing only, returns None — D-01) (2026-05-02)
- [ ] 02.1-08-PLAN.md — features.py: feature_schema_version=2 + parquet_store.py mixed-version warning (D-08)
- [ ] 02.1-09-PLAN.md — seed_historical.py: results extraction + bulk odds fetch + 3-key checkpoint (D-05, D-06)
- [ ] 02.1-10-PLAN.md — TrainingPipeline.run(): wire CLV + logloss (the core gap-closer) (D-05, D-09, D-13)
- [ ] 02.1-11-PLAN.md — Synthetic E2E integration test: test_training_pipeline_e2e.py (D-17 synthetic gate)
- [ ] 02.1-12-PLAN.md — Premier League smoke train: real end-to-end exit check (D-16 one-shot) [BLOCKING]

### Phase 3: Pick Engine + Delivery + Account Protection
**Goal**: Qualified picks with genuine edge are delivered via Telegram with account longevity protections active from the first alert, and Claude Role C validates every pick against red flags before sending
**Depends on**: Phase 2
**Requirements**: PICK-01, PICK-02, PICK-03, PICK-04, PICK-05, CLAUDE-01, CORNERS-01
**Success Criteria** (what must be TRUE):
  1. A pick with >=5% edge triggers a Telegram alert showing fixture, market, selection, model probability, odds, edge%, stake, Claude validation status, and key reasoning bullets
  2. Quarter-Kelly stake sizing is applied with rounding to nearest 0.5 unit, and no more than 60% of weekly picks come from the same market (account longevity rotation enforced)
  3. Claude Role C reads each pick against `learnings/football-learnings.md` and outputs CONFIRM/FLAG/REJECT -- REJECT blocks the alert, FLAG sends with a warning tag
  4. All picks (sent and filtered) are logged to Supabase `picks` table with status `pending` and updated to `won/lost/void` post-match
  5. CORNERS-01 go/no-go gate is executed: Betano time-window corner markets verified and API-Football corner timing data confirmed for 5 leagues across 3+ seasons -- result documented regardless of outcome
**Plans**: TBD

Plans:
- [ ] 03-01: TBD
- [ ] 03-02: TBD
- [ ] 03-03: TBD

### Phase 4: Production Orchestration
**Goal**: The full pipeline runs autonomously on a VPS with scheduled jobs, graceful degradation when external services fail, health monitoring, and CLV-based performance alerting
**Depends on**: Phase 3
**Requirements**: (no new requirements -- integrates CORE, DATA, CLV, PICK, CLAUDE requirements into production orchestration)
**Success Criteria** (what must be TRUE):
  1. APScheduler runs all jobs on schedule: pre-kickoff (T-2h, T-30min), CLV snapshot (post-match), results collection, daily metrics aggregation, and weekly drift check
  2. When Claude API is unavailable, the pipeline sends picks with `claude_validation='SKIPPED'` instead of failing; when Odds API is unavailable, picks still send but CLV recording is deferred
  3. A systemd service on Hetzner VPS auto-restarts on crash, and a heartbeat file is updated every 5 minutes for external monitoring
  4. Performance metrics (ROI, yield, average CLV, win/loss/void counts) are aggregated in `performance_metrics` table by sport, league, market, and period
  5. If rolling 50-pick average CLV drops below +1%, a Telegram warning is sent recommending to pause betting and audit
**Plans**: TBD

Plans:
- [ ] 04-01: TBD
- [ ] 04-02: TBD
- [ ] 04-03: TBD

### Phase 5: Claude Confidence Modifier (Shadow)
**Goal**: Claude Role B runs pre-prediction in shadow mode, logging confidence modifiers and reasoning without affecting live picks, until walk-forward CLV improvement is confirmed
**Depends on**: Phase 4
**Requirements**: CLAUDE-02, CLAUDE-03
**Success Criteria** (what must be TRUE):
  1. Claude Role B reads fixture context (injuries, motivation, news) and outputs a `confidence_modifier` float (-0.15 to +0.15) with structured reasoning, logged to Supabase `predictions` table alongside the production prediction
  2. Shadow predictions are stored with `is_shadow=true` and do not influence pick engine decisions or Telegram alerts
  3. A walk-forward backtest comparison (ensemble with modifier vs without) can be run, and Role B is promoted to production only if OOS CLV improves
**Plans**: TBD

Plans:
- [ ] 05-01: TBD
- [ ] 05-02: TBD

### Phase 6: Timed Corners Module (Conditional)
**Goal**: Corner time-window predictions produce EV-positive picks integrated into the standard pick engine and Telegram delivery, conditional on CORNERS-01 gate passing in Phase 3
**Depends on**: Phase 3 (CORNERS-01 gate must have passed), Phase 4 (production infrastructure)
**Requirements**: CORNERS-02, CORNERS-03, CORNERS-04, CORNERS-05
**Success Criteria** (what must be TRUE):
  1. Historical corner timing data for all 5 leagues across 3+ seasons is stored in Parquet partitioned by time window (0-15, 15-30, 30-45, 45-60, 60-75, 75-90 min)
  2. A per-fixture corner distribution model (compound Poisson + custom features) outputs probabilities per time window that beat a flat-rate baseline by >5% MAE
  3. Per-team corner timing profiles quantify pressing style from API-Football stats and are used as model features
  4. Corner window picks flow through the same EV filter, Kelly sizing, Claude validation, and Telegram delivery as core market picks
**Plans**: TBD

Plans:
- [ ] 06-01: TBD
- [ ] 06-02: TBD
- [ ] 06-03: TBD

### Phase 7: Scalability Validation -- Tennis Scaffold
**Goal**: A tennis SportPlugin scaffold proves the plugin architecture is genuinely sport-agnostic with zero changes to `core/`
**Depends on**: Phase 4
**Requirements**: SCALE-01, SCALE-02
**Success Criteria** (what must be TRUE):
  1. `sports/tennis/` implements the `SportPlugin` ABC (all required methods stubbed or minimally implemented) without any modifications to `core/` code
  2. An integration test confirms Supabase schema, Telegram delivery, EV engine, Claude layer, and CLV tracker all work with `sport='tennis'` without code changes
**Plans**: TBD

Plans:
- [ ] 07-01: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7
Note: Phase 6 is conditional on CORNERS-01 gate (verified in Phase 3). Phase 7 can run in parallel with Phases 5-6.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation + Data Pipeline + CLV | 7/7 | Complete | 2026-04-22 |
| 2. ML Core -- Football | 7/7 | Complete | 2026-04-23 |
| 02.1. Close Phase 2 Gaps (INSERTED) | 8/13 | In progress | - |
| 3. Pick Engine + Delivery + Account Protection | 0/3 | Not started | - |
| 4. Production Orchestration | 0/3 | Not started | - |
| 5. Claude Confidence Modifier (Shadow) | 0/2 | Not started | - |
| 6. Timed Corners Module (Conditional) | 0/3 | Not started | - |
| 7. Scalability Validation -- Tennis Scaffold | 0/1 | Not started | - |
