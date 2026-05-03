# Requirements — betting-intelligence-platform

## v1 Requirements

### CORE — Plugin Architecture

- [x] **CORE-01**: `SportPlugin` ABC defined in `sports/__init__.py` with all required methods: `get_fixtures()`, `build_features()`, `predict()`, `build_claude_context()`, `get_available_markets()`, `get_opening_odds()` (G-CODE-01 closed in quick-260503-jkf)
- [ ] **CORE-02**: `core/` layer contains zero sport-specific code — EV engine, Claude layer, Telegram bot, CLV tracker, pick engine, scheduler, Supabase client all sport-agnostic *(scheduler lives at `bip/scheduler/` not `bip/core/`; ev_engine + kelly folded into `core/picks/`. Layout drift documented in AUDIT-GAPS.md G-CODE-04..06; no SCALE-01 violation today since only football exists)*
- [x] **CORE-03**: Supabase migration 002 adds `sport VARCHAR(20) NOT NULL DEFAULT 'football'` to all 6 existing tables (predictions, picks, odds_snapshots, results, clv_records, performance_metrics)
- [x] **CORE-04**: Football plugin (`sports/football/`) implements full `SportPlugin` interface and passes interface contract tests
- [x] **CORE-05**: Markets defined as runtime YAML config (name, display, edge_threshold, kelly_max) — no hardcoded market enum in core (per-market threshold lookup wired in quick-260503-j74)

### DATA — Data Pipeline

- [x] **DATA-01**: Async API-Football v3 client with tenacity retry/backoff for fixtures, stats, confirmed lineups, corners history, injuries, H2H — rate-limited to avoid Pro plan exhaustion
- [x] **DATA-02**: Feature engineering pipeline (Polars) with Parquet cache Hive-partitioned by `sport/league/season/matchday`; `computed_at` timestamps on all rows to enforce point-in-time correctness
- [x] **DATA-03**: League config YAML loader extended from existing Football_analysis configs — 5 leagues (PL, La Liga, Bundesliga, Serie A, Ligue 1) with API-Football IDs, edge thresholds per market
- [x] **DATA-04**: APScheduler 3.11.x `AsyncIOScheduler` pipeline runs at T-2h (data refresh + prediction) and T-30min (lineup-adjusted re-prediction) before each fixture kickoff
- [x] **DATA-05**: Integration test validates no future data leaks across the feature pipeline (all features computable from data available at prediction time)

### ML — Machine Learning Core

- [x] **ML-01**: XGBoost 3.x + CatBoost 1.2 + LightGBM 4.x ensemble training pipeline with meta-learner (LogisticRegression stacking), outputs `ProbabilityMap` conforming to `SportPlugin` interface
- [x] **ML-02**: Walk-forward backtesting uses opening odds (not closing) + 1-2% slippage assumption from day 1 — retrofitting this later invalidates all earlier results *(structural PASS; empirical PL smoke train deferred per Phase 02.1 user-accepted risk)*
- [x] **ML-03**: Calibration strategy: Platt scaling for leagues with <300 validation samples, isotonic regression for >500 samples; `calibrate_by_league()` (not walk-forward variant — documented overfitting failure) *(structural PASS; empirical per-league logloss numbers pending smoke train)*
- [x] **ML-04**: Model versioning on filesystem (`models/{sport}/{league}/{version}/`) with `metadata.json` (training date, feature set, calibration method, backtest CLV); new model promoted only if walk-forward CLV > current production model *(promotion criterion is manual D-05 decision)*
- [x] **ML-05**: Shadow mode for model A/B testing — new model logs predictions without acting on them; shadow predictions stored in Supabase `predictions` table with `is_shadow=true`

### CLV — Closing Line Value (Phase 1, non-deferrable)

- [x] **CLV-01**: The Odds API v4 client fetches Pinnacle closing odds at kickoff-1min for all markets bet; closing-line snapshot timing corrected per Pitfall 7 in quick-260503-k8k
- [x] **CLV-02**: CLV recorded in `clv_records` table (existing schema): `pick_id`, `odds_at_pick`, `pinnacle_closing_odds`, `clv_percentage` = vig-removed math via `remove_vig` (Pitfall 7 mitigation in quick-260503-iql); raw closing odd preserved in `pinnacle_closing_odds` for audit
- [ ] **CLV-03**: CLV trend alert: if rolling 50-pick average CLV drops below +1%, Telegram sends warning to pause betting and audit *(function exists; scheduler job wiring deferred to Phase 4)*
- [ ] **CLV-04**: Performance metrics aggregated in `performance_metrics` table by sport, league, market, period: ROI, yield, avg CLV, win/loss/void counts *(table + repository exist; aggregator job deferred to Phase 4)*

### PICK — Pick Engine + Delivery

- [x] **PICK-01**: EV filter: per-market edge threshold from `markets.yaml` / `LeagueConfig.model_params.edge_threshold_*` (1X2=0.08, BTTS/OU=0.05, AH=0.06, corners=0.07); picks below threshold are logged with status `filtered`. Per-market lookup wired in quick-260503-j74 (was hardcoded 5%, violated CORE-05).
- [x] **PICK-02**: Quarter-Kelly sizing: `kelly_fraction = (edge / (odds - 1)) × 0.25`; stake rounded to nearest 0.5 unit; ±10% deterministic md5-based jitter to avoid fingerprinting
- [x] **PICK-03**: Account longevity protections: 60% market rotation cap, deterministic send-time variance (D-11), quarter-Kelly clamping. Note: structurally dormant in 1X2-only Phase 3 — needs second market for rotation to bite
- [x] **PICK-04**: Telegram alert format (HTML mode per D-12): fixture, market, selection, model probability, bookmaker odds, edge%, recommended stake, Claude validation status, key reasoning (≤3 bullet points capped per D-15)
- [x] **PICK-05**: All picks (sent and filtered) logged to `picks` table with extended status enum (`pending|won|lost|void|push|filtered|rejected`); reconciliation updates won/lost/void/push post-match via results pipeline

### CLAUDE — AI Integration

- [x] **CLAUDE-01**: Role C (validator) reads pick and learnings.md red flags; outputs `CONFIRM / FLAG (reason) / REJECT` via `tool_use` strict mode (cache_control ephemeral); `REJECT` blocks alert, `FLAG` sends with warning tag, API failure → `filtered/claude_api_unavailable` (D-07 conservative)
- [ ] **CLAUDE-02**: Role B (confidence modifier) runs pre-prediction, reads fixture context from API-Football (injuries, motivation, news), outputs `confidence_modifier` float (-0.15 to +0.15) and structured reasoning; **shipped in shadow mode first** — logged but not applied to model until walk-forward CLV improvement is confirmed
- [ ] **CLAUDE-03**: All Claude interactions logged to Supabase `predictions` table (`claude_context`, `claude_modifier`, `claude_validation`, `claude_reasoning`) for audit and backtesting analysis

### CORNERS — Timed Corners Module (Conditional on Gate)

- [ ] **CORNERS-01**: Go/no-go gate executed before Phase 3 engineering: (a) manually verify exact Betano corner time-window markets available, (b) verify API-Football corner timing data exists for all 5 leagues across >=3 seasons — if either fails, Phase 3 is descoped or redesigned
- [ ] **CORNERS-02**: Historical corner timing data ingested from API-Football and stored in Parquet by time window (0-15, 15-30, 30-45, 45-60, 60-75, 75-90 min) for each fixture and league
- [ ] **CORNERS-03**: Corner time-window distribution model per fixture using penaltyblog compound Poisson + custom features: team pressing intensity, match motivation level, H2H corner timing history, weather
- [ ] **CORNERS-04**: Per-team corner timing profile: quantifies pressing style (high/medium/low) from API-Football stats (ball possession zone, shots from set pieces, corner frequency per 15min window)
- [ ] **CORNERS-05**: EV check for corner window picks runs same pipeline as core markets — probability per window vs Betano implied probability -> edge -> Kelly stake -> Claude validation -> Telegram alert

### SCALE — Scalability Validation

- [ ] **SCALE-01**: Tennis `SportPlugin` scaffold (`sports/tennis/`) implements `SportPlugin` ABC without any changes to `core/` — validates plugin architecture is genuinely sport-agnostic
- [ ] **SCALE-02**: Integration test confirms Supabase schema, Telegram delivery, EV engine, Claude layer, and CLV tracker all work with `sport="tennis"` without code modification

---

## v2 Requirements (deferred)

- Full tennis plugin implementation (tournament data, surface features, serve/return model)
- NBA plugin port from existing nba-wl-predictor (reference `/Apuestas/nba-wl-predictor/`)
- In-play / live betting pipeline (real-time odds polling, live feature updates)
- Web dashboard for performance monitoring (v1 is Telegram-only)
- Multi-bookmaker support (Betfair Exchange for account longevity hedge)
- Steam move detection (sharp line movement alerts for odds API)
- Player prop markets (goalscorer, cards, assists)
- Automated model retraining trigger (vs manual retraining)

---

## Out of Scope (v1)

- **Auto-placing bets** -- Legal risk + Betano ToS violation; human places all bets
- **GPU training** -- Not needed; gradient boosting on CPU < 60s per model
- **Web UI / dashboard** -- Telegram-only delivery; dashboard is v2
- **Real-time in-play pipeline** -- Pre-kickoff only (T-2h, T-30min); in-play is v2
- **Multiple bookmaker integrations** -- Betano only; Pinnacle used read-only for CLV reference
- **Martingale / progressive staking on corners** -- Replaced by EV-based flat Kelly staking per window
- **Exact-score or first-goalscorer markets** -- Insufficient sample size for calibrated edge detection

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CORE-01 | Phase 1 | Complete |
| CORE-02 | Phase 1 | Partial (layout drift — see G-CODE-04..06) |
| CORE-03 | Phase 1 | Complete |
| CORE-04 | Phase 1 | Complete |
| CORE-05 | Phase 1 | Complete (per-market wiring closed in 260503-j74) |
| DATA-01 | Phase 1 | Complete |
| DATA-02 | Phase 1 | Complete |
| DATA-03 | Phase 1 | Complete |
| DATA-04 | Phase 1 | Complete |
| DATA-05 | Phase 1 | Complete |
| CLV-01 | Phase 1 | Complete (kickoff-1m timing fixed in 260503-k8k) |
| CLV-02 | Phase 1 | Complete (vig-removed math via 260503-iql) |
| CLV-03 | Phase 1 | Pending (function exists; scheduler job → Phase 4) |
| CLV-04 | Phase 1 | Pending (table + repo exist; aggregator job → Phase 4) |
| ML-01 | Phase 2 | Complete |
| ML-02 | Phase 2 | Complete (structural; empirical PL smoke train deferred) |
| ML-03 | Phase 2 | Complete (structural; empirical per-league logloss deferred) |
| ML-04 | Phase 2 | Complete |
| ML-05 | Phase 2 | Complete |
| PICK-01 | Phase 3 | Complete |
| PICK-02 | Phase 3 | Complete |
| PICK-03 | Phase 3 | Complete (1X2-only — rotation dormant until 2nd market) |
| PICK-04 | Phase 3 | Complete |
| PICK-05 | Phase 3 | Complete |
| CLAUDE-01 | Phase 3 | Complete |
| CORNERS-01 | Phase 3 | Pending (manual probe templates exist; user fills in) |
| CLAUDE-02 | Phase 5 | Pending |
| CLAUDE-03 | Phase 5 | Pending |
| CORNERS-02 | Phase 6 | Pending |
| CORNERS-03 | Phase 6 | Pending |
| CORNERS-04 | Phase 6 | Pending |
| CORNERS-05 | Phase 6 | Pending |
| SCALE-01 | Phase 7 | Pending |
| SCALE-02 | Phase 7 | Pending |
