# Phase 2: ML Core — Football - Context

**Gathered:** 2026-04-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Build a calibrated XGBoost + CatBoost + LightGBM ensemble that produces `ProbabilityMap` outputs for football matches across 5 European leagues. Validated by walk-forward backtesting using opening odds with 1-2% slippage. Model versioning and shadow mode infrastructure ship in this phase. Pick engine, Telegram delivery, and Claude validation are Phase 3.

</domain>

<decisions>
## Implementation Decisions

### D-01: Historical Training Data Acquisition
- **D-01**: Full API-Football bulk pull across 5 leagues × 3 seasons using the existing `ApiFootballClient` from Phase 1.
  - One-off script at `scripts/seed_historical.py` — outside the main package, never invoked by the scheduler.
  - Fetches fixtures, results, stats, confirmed lineups, corners history, and H2H for each fixture ID.
  - Rate-limited to respect Pro plan (300 req/min); expect ~20-30 min wall time for the full seed.
  - Writes to Hive-partitioned Parquet store (sport/league/season/matchday) — same format as live ingestion.
  - After initial seed, the live pipeline (Phase 1) accumulates new fixtures going forward.

### D-02: Feature Set — Full Tier
- **D-02**: Full feature set (~40-60 features across all groups):
  - Rolling form: goals scored/conceded, wins/draws/losses over last 3/5/10 games, home/away split
  - ELO ratings: dynamic team strength updated after each match (needs ~1-season bootstrap before first valid fold)
  - H2H history: head-to-head results, goals, last meeting recency
  - Rest days and season progress: days since last game, matchday number, season stage
  - Odds signals: bookmaker implied probability, sharp/soft disagreement, line movement (opening vs current)
  - Dixon-Coles attack/defense ratings via `penaltyblog` compound Poisson — requires per-fold fitting
  - Pressing/tactical features: shots, possession zones, set pieces, corner frequency
  - Motivation context: top-4 race, relegation battle, European spots, dead-rubber classification
- **D-02 constraint**: Include a SHAP or LightGBM feature-importance selection pass after first training run to identify and prune features that don't generalize — 40-60 features on 5,700 rows has measurable overfitting risk with gradient boosting.

### D-03: Ensemble Architecture — LogisticRegression Stacking (ML-01 as-spec'd)
- **D-03a**: XGBoost + CatBoost + LightGBM as base models; LogisticRegression as meta-learner stacking (per ML-01).
- **D-03b**: **CRITICAL — temporal integrity**: OOF predictions for the meta-learner MUST be generated within each walk-forward fold's training window. Generating OOF once over the full dataset and reusing it across folds leaks future fixtures and invalidates all backtest CLV numbers. This is a non-negotiable implementation constraint.
  - Correct flow per fold: train base models on fold's train window → generate OOF via k-fold CV within that window → train meta-learner on OOF predictions → evaluate on fold's test window
- **D-03c**: Calibration (Platt or isotonic per ML-03) is applied to the meta-learner's output probability, not to individual base models.
- **D-03d**: Stacking and weighting are per-league — each league trains its own ensemble independently.

### D-04: Calibration Granularity
- **D-04**: Calibrate per-league per ML-03 thresholds (`calibrate_by_league()`). Not per-league×market in Phase 2. If a market (e.g., btts) has fewer samples than the threshold, fall back to the coarser calibration method for that market.

### D-05: Model Promotion — CLI Command
- **D-05**: Ship a CLI command in Phase 2 for manual model promotion:
  - `python -m bip.train promote --league EPL --version v2`
  - Developer reviews walk-forward CLV in `metadata.json` before running the command.
  - Command updates a model registry (a JSON file at `models/football/registry.json`) marking which version is `production` vs `shadow` per league.
  - Phase 3 (Telegram alerts) reads from the registry to load the active production model.
  - Phase 4 (Production Orchestration) can wrap this CLI in an automated comparison hook later.
- **D-05 constraint**: No auto-promotion in Phase 2. Human review before every model swap — a bad promotion is a direct financial loss.

### Claude's Discretion
- Exact Polars feature engineering pipeline structure within `sports/football/features.py` (which transforms happen in which order, parallelization across leagues).
- Exact hyperparameter grids for XGBoost, CatBoost, LightGBM (use established defaults from football-predictor reference, tune only if walk-forward CLV is below baseline).
- Whether ELO bootstrap and Dixon-Coles fitting are precomputed once over the full historical corpus or re-fitted per fold (precomputed for speed is acceptable if temporal scoping is enforced at the fold boundary).
- Exact format of the `metadata.json` schema fields beyond what ML-04 specifies (training date, feature set hash, calibration method, backtest CLV).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` §ML-01 through ML-05 — Full ML requirements (ensemble spec, walk-forward with opening odds + slippage, calibration thresholds, model versioning, shadow mode)
- `.planning/REQUIREMENTS.md` §DATA-01 through DATA-05 — Feature engineering and Parquet store requirements (Phase 1, already built — context for integration)

### Phase 1 Decisions (locked contracts)
- `.planning/phases/01-foundation-data-pipeline-clv/01-CONTEXT.md` — `ProbabilityMap` format (D-02b/c), `FeatureMatrix` Pydantic model, `SportPlugin.predict()` signature, model storage path (`models/{sport}/{league}/{version}/`)

### Tech Stack Constraints
- `CLAUDE.md` §Technology Stack — Version matrix: XGBoost 3.x, CatBoost 1.2.x, LightGBM 4.x, scikit-learn 1.8 (note: `CalibratedClassifierCV(cv="prefit")` removed — use `IsotonicRegression` directly), penaltyblog 1.9.0 for Dixon-Coles

### Reference Code (read, do not copy blindly)
- `/Users/kevin_beltran/ProyectosPersonales/Sports_Betting/Football_analysis/src/football_betting/` — existing league YAML configs, Pydantic models, repository pattern; feature pipeline at `parquet_store.py`
- `/Users/kevin_beltran/ProyectosPersonales/Apuestas/jeke-xg-model-basic/src/calibration/isotonic.py` — isotonic calibration reference (~45 lines, complete implementation)
- `/Users/kevin_beltran/ProyectosPersonales/Apuestas/jeke-xg-model-basic/src/inference/ensemble.py` — simplex weight fitting reference (useful as fallback if stacking proves unstable)
- `/Users/kevin_beltran/ProyectosPersonales/Apuestas/football-predictor/src/data/feature_pipeline.py` — ~150 documented features across 9 groups; feature group definitions to port to Phase 2
- `/Users/kevin_beltran/ProyectosPersonales/Apuestas/football-predictor/backtest.py` — walk-forward backtest skeleton (TimeSeriesSplit, market configs, EV/Kelly/CLV metrics)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/bip/sports/football/client.py` (Phase 1): `ApiFootballClient` — already handles fixtures, stats, lineups, corners, H2H with tenacity retry; seed script can reuse directly.
- `src/bip/core/storage/parquet_store.py` (Phase 1): Hive-partitioned Parquet write/read — feature engineering pipeline writes directly into this store; training pipeline reads from it.
- `src/bip/sports/football/features.py` (Phase 1): `FeatureEngineer` skeleton — currently 2 features (stats_available, lineups_confirmed); Phase 2 expands to full feature set.
- `src/bip/core/storage/repositories.py` (Phase 1): `PredictionRepository` with `is_shadow` column support — shadow predictions write via this repo.

### Established Patterns
- `pydantic-settings` + `.env` for all config (extend `Settings` with `MODEL_DIR`, feature flags)
- `to_supabase_dict()` on all storage models (standardized serialization to `predictions` table)
- `AsyncIOScheduler` in `core/scheduler.py` — Phase 2 training pipeline is offline (not async), but CLI commands run outside the scheduler loop
- `FeatureMatrix(fixture_id, sport, league, computed_at, features: dict[str, float])` — what feature engineering produces; what the training pipeline consumes

### Integration Points
- `SportPlugin.predict(feature_matrix: FeatureMatrix) -> ProbabilityMap`: Phase 2 implements `FootballPlugin.predict()` backed by the trained ensemble; Phase 3 (pick engine) calls this method
- `PredictionRepository.save(prediction, is_shadow=True)`: shadow mode predictions write here; Phase 3 reads `is_shadow=False` rows for pick filtering
- `models/football/{league}/{version}/metadata.json` + `models/football/registry.json` (new): model versioning and promotion state; Phase 3 reads registry to load production model

</code_context>

<specifics>
## Specific Ideas

- The seed script (`scripts/seed_historical.py`) should checkpoint its progress (e.g., write completed fixture IDs to a local JSON) so it can resume if interrupted mid-run — 5,700+ API calls over 20-30 min has transient failure risk.
- ELO bootstrap: fit over all 3 seasons of historical data before the first walk-forward fold opens — ELO is a stateful running rating that needs a warm-up window to be meaningful; do not reset it per fold.
- Dixon-Coles fitting (penaltyblog): can be pre-fitted once over the full historical corpus for feature extraction, with the walk-forward boundary enforced at the feature level (only use results available before the fold's prediction date). Re-fitting per fold is more correct but significantly slower; pre-fitting with temporal scoping is the pragmatic default.
- `metadata.json` feature set hash: use a deterministic hash of the feature column names list (sorted) — allows detecting when a model was trained with a different feature set without comparing full metadata.

</specifics>

<deferred>
## Deferred Ideas

- Dixon-Coles per-fold re-fitting: More correct than pre-fitting, but significantly slower. Evaluate in Phase 2 iteration pass once baseline is validated.
- Optuna-optimized ensemble weights: Nice-to-have refinement if stacking proves unstable on small folds. The simplex reference from jeke-xg-model-basic is a ready fallback.
- Per-league × per-market calibration: ML-03 specifies per-league only; per-market granularity adds value for btts/corners markets but defers to Phase 6 (timed corners) when those markets are built.
- Auto-comparison promotion script: Phase 4 can wrap the Phase 2 CLI command with automated CLV threshold comparison. Not Phase 2 scope.

</deferred>

---

*Phase: 02-ml-core-football*
*Context gathered: 2026-04-22*
