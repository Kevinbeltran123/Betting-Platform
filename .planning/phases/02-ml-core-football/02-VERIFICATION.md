---
phase: 02-ml-core-football
verified: 2026-04-23T00:00:00Z
status: gaps_found
score: 2/4 success criteria fully verified (plus 2 PARTIAL)
overrides_applied: 0
gaps:
  - truth: "Walk-forward backtest over 5 leagues produces per-fold CLV estimates using opening odds with 1-2% slippage applied"
    status: partial
    reason: "backtest.py ships correct opening-odds + slippage math (apply_slippage, compute_clv, SLIPPAGE_PCT=0.015) with passing unit tests, and StackedEnsemble + WalkForwardSplitter produce per-fold predictions. But TrainingPipeline.run() never invokes apply_slippage/compute_clv -- pipeline.py:99-104 hardcodes clv_pct=None per fold and pipeline.py:149 defaults walk_forward_mean_clv_pct=0.0. No fold has ever produced a real CLV number because (a) scripts/seed_historical.py does not fetch opening odds from The Odds API historical endpoint, (b) the Parquet feature schema has no opening_home/draw/away columns, and (c) the pipeline has no join step from feature rows to opening-odds rows. Additionally, the seed script does not fetch match results (home_goals/away_goals) which pipeline.py:60-64 REQUIRES to derive labels -- so TrainingPipeline.run() cannot even be invoked end-to-end today without manual Parquet augmentation. Criterion 1 says per-fold CLV estimates are produced -- they are not."
    artifacts:
      - path: "src/bip/train/pipeline.py"
        issue: "Line 99: fold CLV is a 'placeholder -- requires opening odds joined into df'; apply_slippage/compute_clv imports are absent; mean_clv falls back to 0.0"
      - path: "scripts/seed_historical.py"
        issue: "Does not fetch opening odds from The Odds API /historical endpoint; does not fetch match results (home_goals/away_goals) needed for labels"
      - path: "src/bip/sports/football/features.py"
        issue: "to_parquet_row does not emit opening_home/draw/away columns"
    missing:
      - "Historical opening-odds ingestion into Parquet (join from The Odds API /historical into feature rows by fixture_id + market)"
      - "Historical match-result ingestion into Parquet (home_goals, away_goals columns required by pipeline.py line 60-64)"
      - "TrainingPipeline.run() must call apply_slippage(opening_odds) + compute_clv(staked, pinnacle_closing) per test-set row and aggregate into fold_details[...]['clv_pct']"
      - "End-to-end smoke test that trains one league on synthetic or real data and asserts a non-null per-fold CLV lands in metadata.json"

  - truth: "Calibration logloss improvement is documented per league"
    status: partial
    reason: "select_calibrator implements the <300 Platt / >500 Isotonic rule correctly (with 300-500 fallback to Platt per RESEARCH Pitfall 7), and calibration.calibrate() uses the sklearn 1.8 FrozenEstimator pattern. A unit test (test_calibration_improves_logloss) verifies logloss does not regress on synthetic data. But NOTHING in the production pipeline records per-league logloss_before/logloss_after in metadata.json. ModelMetadata has no logloss_uncalibrated / logloss_calibrated / logloss_improvement fields. TrainingPipeline.run() fits a calibrator on the last test fold and writes it, but never computes uncalibrated-vs-calibrated logloss and never persists the delta. Criterion 2's wording 'documented logloss improvement per league' is unmet at the artifact level."
    artifacts:
      - path: "src/bip/train/metadata.py"
        issue: "ModelMetadata Pydantic schema has no logloss_uncalibrated / logloss_calibrated / logloss_improvement fields"
      - path: "src/bip/train/pipeline.py"
        issue: "Lines 110-142 fit a calibrator but never compute log_loss(y_val, raw_probs) vs log_loss(y_val, cal_probs); no delta written to metadata"
    missing:
      - "ModelMetadata fields: logloss_uncalibrated: float, logloss_calibrated: float, logloss_improvement_pct: float"
      - "TrainingPipeline step after calibration: compute log_loss on a held-out slice before and after calibration, persist both to metadata.json"
      - "Per-league comparison output (logs or CLI table) showing which leagues benefited from which calibration method"

deferred: []

human_verification:
  - test: "Run migration 003 (20260423000000_add_is_shadow.sql) against the live Supabase project and verify the is_shadow column + idx_predictions_is_shadow index exist on the predictions table"
    expected: "SQL query `SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns WHERE table_name='predictions' AND column_name='is_shadow'` returns one row: is_shadow | boolean | NO | false. `SELECT indexname FROM pg_indexes WHERE tablename='predictions' AND indexname='idx_predictions_is_shadow'` returns one row."
    why_human: "Supabase live DB credentials are not available to the verifier. Plan 02-06 explicitly flagged this as a BLOCKING checkpoint. Until the migration is applied, any real shadow-write path will fail with a Postgres 'column does not exist' error at runtime -- local tests pass because they mock the client."
  - test: "Train one league end-to-end (after seed + backfill of home_goals/away_goals + opening odds) and inspect the resulting metadata.json"
    expected: "models/football/{league}/v1/metadata.json exists with training_date (ISO), training_rows >0, feature_set_hash (16-char hex), calibration_method in {platt, isotonic}, walk_forward_mean_clv_pct a real number (NOT 0.0), and walk_forward_fold_details with per-fold clv_pct floats"
    why_human: "Requires live API-Football Pro + The Odds API keys and hours of data ingestion; cannot be run inside the verifier session. The artifact-producing path is wired, but has never been exercised end-to-end."
---

# Phase 2: ML Core -- Football Verification Report

**Phase Goal:** A calibrated ensemble model produces probability maps for football matches, validated by walk-forward backtesting with opening odds and slippage, with model versioning and shadow mode infrastructure.

**Verified:** 2026-04-23
**Status:** gaps_found
**Re-verification:** No -- initial verification

**Test run:** `uv run pytest tests/` -> 95 passed, 0 failed, 12 warnings, 20.47s.

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Walk-forward backtest over 5 leagues produces per-fold CLV estimates using opening odds with 1-2% slippage -- not closing odds | PARTIAL | Math primitives correct and unit-tested (SLIPPAGE_PCT=0.015; apply_slippage(2.0)=1.97; compute_clv(2.10, 2.00)=+5.0%). WalkForwardSplitter + StackedEnsemble produce per-fold probabilities. But TrainingPipeline.run() does NOT invoke the CLV math -- pipeline.py:99 is explicitly a "placeholder" and fold_details[].clv_pct = None always. The 5-league coverage is a matter of configuration (5 league YAMLs exist) and is never exercised because no training run has happened. |
| 2 | Platt for <300, Isotonic for >500, documented logloss improvement per league | PARTIAL | select_calibrator thresholds correct (tests enumerate 250/299/300/400/500/501/1000). FrozenEstimator pattern correctly used (sklearn 1.8 compliant). test_calibration_improves_logloss passes on synthetic data. GAP: no per-league logloss delta is computed in TrainingPipeline.run() or persisted in ModelMetadata -- "documented logloss improvement per league" has no artifact backing it. |
| 3 | Model version saved to models/football/{league}/{version}/ with metadata.json containing training_date, feature_set_hash, calibration_method, backtest CLV | PASS | ModelMetadata Pydantic schema includes training_date, training_data_seasons, training_rows, feature_names, feature_set_hash (sha256(sorted_names)[:16]), calibration_method, calibration_samples, walk_forward_folds, walk_forward_mean_clv_pct, walk_forward_fold_details, base_model_params, base_model_packages, sklearn_version, null_clv_rows, slippage_pct, git_commit. TrainingPipeline.run() (pipeline.py:151-184) writes ensemble.joblib, calibrator.joblib, and metadata.json to `{model_dir}/football/{league}/{version}/`. ModelRegistry (registry.json schema_version=1) tracks production/shadow/history per league with atomic .tmp + replace writes. ModelLoader enforces path-traversal guard (loader.py:43-49) and feature-hash gate. Caveat: backtest CLV in the saved metadata.json will be 0.0 until Gap 1 is closed -- the FIELD is present, but its VALUE is degenerate in the current wiring. |
| 4 | Shadow mode logs new model predictions to Supabase with is_shadow=true without affecting production | PASS | Prediction.is_shadow: bool = False field present (models.py:27). Migration 003 (20260423000000_add_is_shadow.sql) adds column + idx_predictions_is_shadow index. PredictionRepository.get_production() filters .eq("is_shadow", False) (repositories.py:77-92). FootballPlugin.predict() resolves prod_version then shadow_version independently, calls _predict_one twice, wraps shadow path in try/except (plugin.py:215-234) -- shadow failure logs `shadow_predict_failed` and never raises. _write_prediction_rows (plugin.py:287-345) inserts a production row (is_shadow=False) and conditionally a shadow row (is_shadow=True), each in its own try/except. test_shadow_and_production_paths asserts 2 repo.insert calls with sorted is_shadow flags [False, True]. Caveat: Supabase migration 003 has not been APPLIED to the live DB (Plan 02-06 flagged this as blocking-human-action); code is correct but the runtime insert will fail until the column exists. Code-level verification: PASS; operational verification: human checkpoint required. |

**Score:** 2/4 fully verified; 2/4 partial (both have working primitives but missing end-to-end data plumbing/metadata persistence).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/bip/train/walkforward.py` | WalkForwardSplitter with temporal leakage assertion | VERIFIED | 47 lines. `dates[train].max() < dates[test].min()` asserted per fold; AssertionError message contains "temporal leakage". Tests: test_walkforward.py (3 passing). |
| `src/bip/train/backtest.py` | SLIPPAGE_PCT + apply_slippage + compute_clv | VERIFIED (exists, correct, unused by pipeline) | 24 lines. SLIPPAGE_PCT=0.015. apply_slippage = opening * (1 - 0.015). compute_clv = (staked/closing - 1) * 100. Unit tests pass. WIRING GAP: neither function is imported or invoked anywhere outside tests + bip.train.__init__.py re-exports. |
| `src/bip/train/calibration.py` | select_calibrator + calibrate with FrozenEstimator | VERIFIED | 94 lines. select_calibrator(n<=500) -> platt, n>500 -> isotonic (tests enumerate boundary cases). FrozenEstimator imported + used; no legacy cv sentinel strings anywhere. |
| `src/bip/train/stacking.py` | StackedEnsemble with nested OOF (D-03b) | VERIFIED | 139 lines. XGB+CB+LGB base models, LogReg meta-learner. Inner TimeSeriesSplit inside each fold's train window; inner assert `dates_tr[inner_train].max() < dates_tr[inner_val].min()`. _align_proba pads missing classes for tiny folds. Tests pass (12 warnings re LGBM feature-name mismatch on synthetic data -- acceptable noise). |
| `src/bip/train/metadata.py` | ModelMetadata + feature_set_hash | VERIFIED | 50 lines. Pydantic model with all required fields. feature_set_hash = sha256(json.dumps(sorted(names)))[:16]; order-invariant; addition-sensitive. Missing logloss_* fields (see Gap 2). |
| `src/bip/train/registry.py` | ModelRegistry with promote/set_shadow + atomic writes | VERIFIED | 95 lines. Dataclass with load/promote/set_shadow/save. Atomic write via .tmp + Path.replace. Schema v1. History list appended on promote; no pruning. |
| `src/bip/train/loader.py` | ModelLoader with path-traversal guard + feature-hash gate | VERIFIED | 79 lines. artifact_dir.resolve().relative_to(model_dir.resolve()) guard. Missing metadata.json or ensemble.joblib -> StorageError. check_feature_hash raises on mismatch. Tests assert path traversal rejected and hash mismatch raises. |
| `src/bip/train/pipeline.py` | TrainingPipeline orchestrator | PARTIAL | 190 lines. Wires read_features -> label derivation -> temporal sort -> WalkForwardSplitter -> per-fold fit_fold -> calibrate last fold -> save joblib + metadata. MISSING: apply_slippage/compute_clv invocation (line 99 is "placeholder"); logloss_before/after computation; opening-odds Parquet column reading; results Parquet column reading. RuntimeError if home_goals/away_goals columns missing (line 60-64). |
| `src/bip/sports/football/plugin.py` | predict() wired to registry + shadow path | VERIFIED | 354 lines. FootballPlugin.__init__ loads ModelRegistry + ModelLoader. predict() does cold-start (stub-v0) -> registry.get_production -> _predict_one -> optional shadow via registry.get_shadow -> _write_prediction_rows. Shadow errors logged-and-swallowed. 4 async tests pass. |
| `src/bip/core/storage/models.py` | Prediction.is_shadow field | VERIFIED | Line 27: `is_shadow: bool = False`. to_supabase_dict serializes via model_dump. |
| `src/bip/core/storage/repositories.py` | PredictionRepository.get_production | VERIFIED | Lines 77-92. `.eq("is_shadow", False)` enforced; market filter optional. Test test_get_production_filters_is_shadow_false passes. |
| `supabase/migrations/20260423000000_add_is_shadow.sql` | is_shadow column + index | VERIFIED (not yet applied) | 9 lines. ADD COLUMN IF NOT EXISTS is_shadow BOOLEAN NOT NULL DEFAULT false. CREATE INDEX IF NOT EXISTS idx_predictions_is_shadow. Idempotent. Apply-to-live-DB step is a human checkpoint. |
| `src/bip/train/cli.py` | python -m bip.train fit\|backtest\|promote | VERIFIED | Typer app; fit supports --version auto (v{len(history)+1}); backtest re-runs pipeline; promote calls registry.promote + save. |
| `tests/` | 95 tests passing | VERIFIED | `uv run pytest tests/ -q` -> 95 passed in 20.47s. Only warnings are 12 sklearn "LGBMClassifier feature names" on synthetic test data. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| FootballPlugin.predict | ModelLoader.load | self._loader.load(league, version) | WIRED | plugin.py:251 |
| FootballPlugin.predict | ModelRegistry.get_production_version | self._model_registry.get_production_version | WIRED | plugin.py:191 |
| FootballPlugin.predict | ModelRegistry.get_shadow_version | self._model_registry.get_shadow_version | WIRED | plugin.py:216 |
| FootballPlugin.predict | PredictionRepository.insert | self._prediction_repo.insert (prod + shadow) | WIRED | plugin.py:316, 339 |
| TrainingPipeline.run | WalkForwardSplitter.split | splitter.split(X, dates) | WIRED | pipeline.py:91 |
| TrainingPipeline.run | StackedEnsemble.fit_fold | ens.fit_fold(...) | WIRED | pipeline.py:93 |
| TrainingPipeline.run | calibrate | calibrate(wrapper, X_cal, y_cal) | WIRED | pipeline.py:142 |
| TrainingPipeline.run | apply_slippage / compute_clv | (none) | NOT_WIRED | backtest.py functions are imported in __init__ but NEVER called from pipeline.py. This is the core gap for criterion 1. |
| TrainingPipeline.run | log_loss (before/after calibration) | (none) | NOT_WIRED | No logloss computation in pipeline; no log_loss field in ModelMetadata. Gap for criterion 2. |
| ModelMetadata.to_dict | metadata.json on disk | artifact_dir / "metadata.json".write_text | WIRED | pipeline.py:182 |
| ModelRegistry.save | registry.json on disk | tmp.replace(self.registry_path) | WIRED | registry.py:79-84 |
| PredictionRepository.get_production | Supabase is_shadow column | .eq("is_shadow", False) | WIRED (code); NOT-YET-APPLIED (DB) | repositories.py:86; migration 003 not yet pushed to live |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| TrainingPipeline.run (metadata.walk_forward_mean_clv_pct) | mean_clv | list comp over fold_details[*].clv_pct (all None) | NO (degrades to 0.0 fallback) | DISCONNECTED from opening-odds source |
| TrainingPipeline.run (labels y) | home_goals / away_goals columns | ParquetStore.read_features -> requires results join | NO (seed script does not write goals; RuntimeError raised) | DISCONNECTED from results source |
| FootballPlugin.predict -> ProbabilityMap | prod_probs | ModelLoader.load(production_version).predict_proba(X) | YES (once a model is trained and promoted) | FLOWING (given a trained model; no model trained yet) |
| FootballPlugin.predict -> shadow Prediction row | shadow_probs | ModelLoader.load(shadow_version).predict_proba(X) | YES (once a shadow model is trained and set) | FLOWING (same caveat) |
| FootballPlugin.predict -> repo.insert | Prediction rows | prod_map + optional shadow_map | YES (given a trained model) | FLOWING (runtime-dependent on migration 003 applied) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `python -m bip.train --help` prints fit/backtest/promote | `uv run python -m bip.train --help` (not actually run; only Typer structure inspected) | Typer app 3 commands registered | SKIP (requires shell; Typer code confirmed present) |
| `uv run pytest tests/` all pass | `uv run pytest tests/ -q` | 95 passed in 20.47s | PASS |
| Module imports cleanly (no circulars) | Test suite imports every key module at collection time | All tests collected, no import errors | PASS |
| 5-league YAML configs exist | `ls src/bip/sports/football/config/leagues/` | 5 files: bundesliga, la_liga, ligue_1, premier_league, serie_a | PASS |
| TrainingPipeline end-to-end smoke | (not runnable) | `models/` directory does not exist; no seeded Parquet; no trained model on disk | SKIP -> human-verify |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| ML-01 | 02-04, 02-06, 02-07 | XGB + CB + LGB ensemble with LogReg meta-learner outputs ProbabilityMap | SATISFIED | StackedEnsemble (stacking.py) + FootballPlugin.predict (plugin.py) return ProbabilityMap conformant to SportPlugin ABC. |
| ML-02 | 02-04, 02-06 | Walk-forward uses opening odds + 1-2% slippage | BLOCKED | Math primitives present and unit-tested (SLIPPAGE_PCT=0.015, apply_slippage, compute_clv) but never invoked by TrainingPipeline. Net effect: no walk-forward backtest has ever produced a real CLV number. |
| ML-03 | 02-05 | Platt <300 / Isotonic >500; calibrate_by_league; documented logloss improvement | PARTIAL | select_calibrator threshold rule correct; FrozenEstimator used; synthetic-data logloss improvement test passes. Missing: per-league logloss_before/after in metadata.json. |
| ML-04 | 02-06 | Filesystem versioning + metadata.json + promotion only if walk-forward CLV > production | SATISFIED (artifact layer) / BLOCKED (promotion criterion) | Filesystem layout implemented; metadata.json Pydantic schema complete; ModelRegistry.promote is a manual CLI (D-05 decision -- no auto-promotion). The "only if CLV > production" check is D-05 manual human action -- no code gate. Acceptable per explicit decision. |
| ML-05 | 02-06, 02-07 | Shadow mode -- is_shadow=true in Supabase; shadow does not affect production | SATISFIED | Prediction.is_shadow field, migration 003, PredictionRepository.get_production filter, FootballPlugin shadow path, 4 async tests. Operational caveat: migration 003 not yet applied to live Supabase (human checkpoint). |

All 5 Phase 2 requirements have implementation evidence. ML-02 is BLOCKED by missing end-to-end wiring (primitives OK; pipeline does not invoke them). ML-03 is PARTIAL at the documentation level (selection rule works; logloss delta not persisted).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| src/bip/train/pipeline.py | 99 | `# Per-fold CLV (placeholder -- requires opening odds joined into df)` | Blocker for criterion 1 | Pipeline's fold_details[].clv_pct is always None; walk_forward_mean_clv_pct always defaults 0.0. Roadmap success criterion 1 cannot be demonstrated until this placeholder is replaced. |
| src/bip/train/pipeline.py | 113-141 | `_EnsembleProbaWrapper` re-fits the last fold's base models on a tiny slice (max(idx[0], 1) rows) purely to satisfy FrozenEstimator's API contract | Warning | Noted in 02-06-SUMMARY as a known ergonomic wart. Calibration math is correct but wasteful. Does not invalidate the calibration outcome -- the wrapper ends up wrapping a correctly-fit ensemble. |
| src/bip/train/pipeline.py | 60-64 | Raises `RuntimeError` when home_goals/away_goals columns missing | Info | Honest failure; but seed_historical.py does not write those columns, so the pipeline is non-executable today even on ingested data. Coupled with Gap 1. |
| scripts/seed_historical.py | all | No results ingestion (home_goals/away_goals); no opening-odds ingestion | Blocker for criterion 1 | Prerequisite data for backtest CLV simply does not exist in the Parquet store; 02-06-SUMMARY explicitly defers this. |

### Human Verification Required

See frontmatter. Two items:

1. **Apply migration 003 to live Supabase** and verify `is_shadow` column + index exist. Until this runs, any real shadow-write (Phase 3+) will fail at runtime with a Postgres "column does not exist" error -- local tests pass because they mock the client. This was flagged as a blocking human checkpoint by Plan 02-06.

2. **End-to-end pipeline smoke** -- once opening-odds + results ingestion lands, train one league and inspect `models/football/{league}/v1/metadata.json` to confirm walk_forward_mean_clv_pct is a real number (not 0.0) and walk_forward_fold_details carries per-fold clv_pct floats. Until then, the full criterion-1 success path is unexercised.

### Gaps Summary (Narrative)

**Phase 2 ships a high-quality artifact layer** -- the plugin-architecture abstractions, walk-forward splitter, nested OOF stacker, calibration selector with sklearn 1.8 FrozenEstimator compliance, model metadata schema, registry with atomic writes, loader with path-traversal + feature-hash guards, CLI, and migration SQL -- all with solid unit-test coverage (95/95 passing). The plugin's predict() path is correctly wired for both production and shadow. ML-01, ML-04, and ML-05 are implementation-complete.

**Two specific gaps block criterion 1 and partially block criterion 2:**

1. **Criterion 1 (walk-forward CLV over 5 leagues):** The math primitives (SLIPPAGE_PCT, apply_slippage, compute_clv) are correct, imported, and unit-tested -- but `TrainingPipeline.run()` never invokes them. `pipeline.py:99` is explicitly labelled "placeholder" and fold CLV is hardcoded to `None`; `walk_forward_mean_clv_pct` defaults to `0.0`. Additionally, `scripts/seed_historical.py` does not ingest opening odds (The Odds API /historical) or match results (home_goals/away_goals) -- the Parquet feature store has no columns to compute CLV against even if the pipeline were wired up, and the pipeline raises `RuntimeError` on the missing goals columns before it ever reaches the CLV step. Plan 02-06 explicitly calls this out as deferred, but the deferral is NOT documented in ROADMAP Phase 3's goal or success criteria -- it is effectively un-homed work.

2. **Criterion 2 (documented logloss improvement per league):** `select_calibrator` correctly implements the <300 Platt / >500 Isotonic rule (tests enumerate the boundaries), and `calibrate()` uses the sklearn 1.8 `FrozenEstimator` pattern. A unit test (`test_calibration_improves_logloss`) verifies on synthetic data that calibrated logloss does not regress. But there is no mechanism to compute or persist the calibrated-vs-uncalibrated logloss delta per league: `ModelMetadata` has no logloss fields; `TrainingPipeline.run()` never calls `sklearn.metrics.log_loss` on the held-out slice. "Documented" has no artifact backing.

**Risks for Phase 3 (Pick Engine + Delivery + Account Protection):**

- Phase 3's EV filter (`model_probability × odds - 1 >= 0.05`) depends on calibrated probabilities. The calibration code itself is correct; risk is moderate because synthetic tests show it does not regress -- but with no per-league logloss evidence, there is no empirical guarantee the calibration is improving the numbers the EV filter consumes.
- Phase 3's Kelly sizing depends on edge; if the walk-forward CLV backtest is never run and logged, there is no historical CLV trendline to compare against the CLV-03 "pause if rolling 50-pick CLV < +1%" alert threshold. Phase 3 can ship mechanically but cannot validate its thresholds pre-flight.
- Phase 3's shadow-write path will fail at runtime until migration 003 is applied to the live Supabase project -- a human checkpoint, not a code gap.

**Recommendation:** Before starting Phase 3, close Gap 1 (opening-odds + results ingestion + TrainingPipeline CLV wire-up) and Gap 2 (logloss delta persistence) in a focused plan (suggested name: "Phase 2.1: CLV backtest end-to-end + logloss documentation"). Also apply migration 003 to live Supabase. Phase 3 can then start with honest walk-forward CLV numbers per league and verified shadow infrastructure.

---

_Verified: 2026-04-23_
_Verifier: Claude (gsd-verifier)_
_Test run: `uv run pytest tests/` -> 95 passed, 0 failed, 20.47s_
_Git HEAD: 437b1c8_
