# Phase 2: ML Core — Football - Research

**Researched:** 2026-04-22
**Domain:** Gradient-boosting ensemble (XGBoost / CatBoost / LightGBM) + stacking meta-learner, walk-forward temporal CV with opening-odds CLV backtest, Polars feature engineering, sklearn 1.8 calibration, penaltyblog 1.9 Dixon-Coles + ELO, filesystem model registry, shadow-mode predictions.
**Confidence:** HIGH (stack, APIs, calibration) · MEDIUM (hyperparameter defaults, fold-count heuristics)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01: Historical training data acquisition — Full API-Football bulk pull**
- One-off script at `scripts/seed_historical.py`; never invoked by scheduler.
- 5 leagues × 3 seasons via existing `ApiFootballClient` (Phase 1).
- Fetches fixtures, results, statistics, confirmed lineups, corners history, H2H.
- Rate-limited to Pro plan (300 req/min); ~20-30 min wall time expected.
- Writes to Hive Parquet (`sport/league/season/matchday`) — same format as live ingestion.
- Must checkpoint progress so it resumes after transient failure.

**D-02: Feature set — Full tier (~40–60 features)**
- Rolling form (goals scored/conceded, W/D/L over last 3/5/10, home/away split).
- ELO ratings (dynamic, ~1-season bootstrap required).
- H2H history (results, goals, last-meeting recency).
- Rest days, matchday, season stage.
- Odds signals (implied probability, sharp/soft disagreement, line movement opening→current).
- Dixon-Coles attack/defense ratings via penaltyblog.
- Pressing/tactical (shots, possession zones, set pieces, corner frequency).
- Motivation context (top-4, relegation, European spots, dead-rubber).
- **Constraint**: SHAP / LightGBM feature-importance pass MUST run after first training run — 40–60 features on ~5,700 rows has real overfitting risk.

**D-03: Ensemble architecture — LogisticRegression stacking (ML-01)**
- Base models: XGBoost 3.2 + CatBoost 1.2.10 + LightGBM 4.6.
- Meta-learner: sklearn LogisticRegression.
- **CRITICAL: Temporal integrity** — OOF predictions for the meta-learner MUST be generated within each walk-forward fold's training window. Generating OOF once over the full dataset and reusing it across folds leaks future fixtures. Non-negotiable.
- Calibration applies to meta-learner output only, never to individual base models.
- Per-league training (each league has its own ensemble).

**D-04: Calibration granularity — per-league only**
- `calibrate_by_league()` (not per-league×market in Phase 2).
- Per-league-per-market deferred to Phase 6 (corners / timed markets).
- Markets with fewer samples than the threshold fall back to the coarser method (Platt).

**D-05: Model promotion — CLI command with manual review**
- `python -m bip.train promote --league premier_league --version v2`.
- Developer reviews walk-forward CLV in `metadata.json` before running the command.
- Updates `models/football/registry.json` marking `production` vs `shadow` per league.
- Phase 3 (Telegram alerts) reads the registry to load the active production model.
- **No auto-promotion in Phase 2.**

### Claude's Discretion
- Polars feature engineering pipeline structure within `sports/football/features.py`.
- Hyperparameter grids for XGBoost / CatBoost / LightGBM (defaults acceptable unless baseline CLV is below threshold).
- Whether ELO / Dixon-Coles are pre-computed once or re-fitted per fold (pre-compute with temporal scoping is the acceptable default).
- Exact `metadata.json` field layout beyond the ML-04 minimum.

### Deferred Ideas (OUT OF SCOPE)
- Dixon-Coles per-fold re-fitting (Phase 2 iteration pass if needed).
- Optuna-optimized ensemble weights (fallback if stacking is unstable).
- Per-league × per-market calibration (Phase 6).
- Auto-promotion script (Phase 4 wraps the Phase 2 CLI).
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **ML-01** | XGBoost 3.x + CatBoost 1.2 + LightGBM 4.x ensemble with LogisticRegression meta-learner; outputs `ProbabilityMap` conforming to `SportPlugin` interface | Stacking pattern documented with sklearn `StackingClassifier` + `TimeSeriesSplit` cv; base-model APIs verified in Context7 for all three libraries; `ProbabilityMap` contract already enforced in `src/bip/sports/__init__.py` |
| **ML-02** | Walk-forward backtest uses opening odds (not closing) + 1–2% slippage from day 1 | `TimeSeriesSplit` + per-fold expanding-window pattern documented; slippage formula `odds * (1 - slippage_pct)` on bet-side; CLV computed vs Pinnacle closing from Phase 1 `clv_records` |
| **ML-03** | Platt for <300 validation samples, isotonic for >500, `calibrate_by_league()` | `CalibratedClassifierCV` + `FrozenEstimator` pattern (sklearn 1.8 replaces `cv='prefit'`); thresholds `<300` and `>500` codified; 300–500 sample bucket gap documented with fallback rule |
| **ML-04** | Filesystem versioning `models/{sport}/{league}/{version}/metadata.json` (training date, feature set, calibration method, backtest CLV); promote if walk-forward CLV > current production | Filesystem registry pattern documented (MLflow-inspired, lightweight JSON); feature-set hash via `hashlib.sha256(sorted(feature_names))` |
| **ML-05** | Shadow mode — new model logs to Supabase `predictions` with `is_shadow=true` without affecting production prediction path | **GAP identified**: `is_shadow` column does not yet exist in migration 002; must ship migration 003 in Phase 2. `Prediction` Pydantic model also missing `is_shadow` field. Action required before shadow mode works. |
</phase_requirements>

---

## Project Constraints (from CLAUDE.md)

Binding directives the planner MUST honor (extracted from `CLAUDE.md`):

| Directive | Impact on Phase 2 |
|-----------|-------------------|
| Python 3.12 + uv | Training scripts target 3.12; no 3.13+ to avoid CatBoost wheel gaps |
| XGBoost **3.2.0**, CatBoost **1.2.10**, LightGBM **4.6.0** | Pinned versions for ensemble; `DeviceQuantileDMatrix` removed in 3.0 (CPU-only unaffected) |
| scikit-learn **1.8.0** | `CalibratedClassifierCV(cv='prefit')` REMOVED — use `FrozenEstimator` wrapper + `cv=None`, or `IsotonicRegression` directly |
| penaltyblog **1.9.0** | `DixonColesGoalModel` + `Elo` are in-library; do NOT hand-roll either |
| Polars **1.40.x** for feature engineering | No pandas in the training pipeline; CatBoost 1.2.10 accepts Polars natively, XGBoost 3.2 accepts Polars DataFrame and LazyFrame, LightGBM 4.6 has Polars input support with minor caveats |
| No GPU; CPU only | Gradient-boosting on CPU must stay < 60s per model per league to meet the "5 leagues in reasonable wall time" bar |
| No pandas | Polars for all feature work; convert to numpy at the ML boundary if needed |
| APScheduler 3.11.x | Training pipeline is **offline/CLI-driven**, not scheduled in Phase 2 |
| `ruff` + `pytest` + `pytest-asyncio` + `mypy` | All new code passes lint/type checks |
| No Co-Authored-By in commits | Git policy |
| GSD workflow enforcement | All edits must flow through GSD commands |

---

## Summary

Phase 2 turns the Phase-1 scaffold (2-feature stub, stub `predict()` returning flat 1/3-1/3-1/3) into a production-calibrated 3-model gradient-boosting ensemble across 5 leagues, with honest walk-forward backtesting and a filesystem model registry. The workload splits cleanly into five logical modules:

1. **Historical data seed** — one-off script using the Phase-1 `ApiFootballClient`, rate-limited, checkpoint-resumable. Uses `ApiFootballClient` and `ParquetStore` verbatim; adds only the seed orchestration + checkpoint file.
2. **Feature engineering expansion** — extend the existing `FeatureEngineer._extract_features()` from 2 features to the full ~40-60 feature set, all in Polars, all point-in-time correct (`computed_at` ≤ `kickoff_utc`). ELO and Dixon-Coles ratings come from penaltyblog directly (not hand-rolled).
3. **Training pipeline** — `bip.train.pipeline` module that reads Parquet, runs walk-forward with nested OOF for the meta-learner, produces per-league ensembles, saves to `models/football/{league}/{version}/`.
4. **Calibration + backtest** — sklearn 1.8 calibration via `FrozenEstimator` + `CalibratedClassifierCV`; walk-forward CLV computed using **opening odds with 1–2% slippage** (not closing).
5. **Model registry + CLI + shadow plumbing** — `registry.json` with production/shadow per league, Typer-based `bip.train` CLI with `fit`, `backtest`, `promote` subcommands, and the `is_shadow` column migration + `Prediction` model extension so shadow rows have somewhere to land.

**Three pitfalls dominate the risk surface**:

- **Temporal leakage in stacking**: the default `StackingClassifier(cv=5)` uses stratified KFold, which violates time-order. The pipeline MUST pass `cv=TimeSeriesSplit(...)` explicitly. Failure to do this invalidates every CLV number the backtest produces.
- **`cv='prefit'` is gone**: any reference implementation from 2023–2024 you look at will use `CalibratedClassifierCV(cv='prefit')`. In sklearn 1.8 that raises. Replacement is `CalibratedClassifierCV(estimator=FrozenEstimator(fitted_model), cv=None)`.
- **`is_shadow` column does not exist yet**: the Phase-1 migration (002) did not add it; `Prediction` Pydantic model has no `is_shadow` field; `PredictionRepository.insert()` has no `is_shadow` flag. Phase 2 must ship migration 003 **before** the ensemble pipeline can write shadow predictions.

**Primary recommendation:**
Build in the order `migration-003 → feature-engineer expansion → historical seed → train pipeline → backtest → calibration → model registry + CLI → shadow-mode plumbing → FootballPlugin.predict() wiring`. penaltyblog 1.9 provides Dixon-Coles + ELO + BTTS + totals + Asian handicap probability grids out-of-the-box — use it as a feature provider and as a probability sanity check, never hand-roll any of those.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Historical data ingest (one-off seed) | Script layer (`scripts/`) | Infrastructure client (`ApiFootballClient`) | Not part of runtime pipeline; calls Phase-1 client and writes to Phase-1 Parquet store |
| Feature engineering (rolling form, ELO, DC, H2H, odds, motivation) | Sport-specific (`sports/football/features.py`) | Library (penaltyblog, Polars) | Feature code is football-specific; library call-outs for ELO + Dixon-Coles |
| ELO + Dixon-Coles rating fit | Library (penaltyblog) | Sport-specific orchestration | Do NOT hand-roll — penaltyblog provides both with Cython optimization |
| Base model training (XGB/CB/LGB) | Training pipeline (`bip/train/`) | — | Offline; CLI-invoked; not in core/ |
| Walk-forward CV orchestration | Training pipeline | sklearn (`TimeSeriesSplit`) | Temporal-correct fold iteration is training-pipeline responsibility |
| Meta-learner (LogReg) + OOF generation | Training pipeline (`bip/train/stacking.py`) | sklearn (`StackingClassifier` with custom cv) | Stacking is training-only; meta-learner is sport-agnostic in principle but configured per-league |
| Calibration (Platt / Isotonic) | Training pipeline (`bip/train/calibration.py`) | sklearn 1.8 (`FrozenEstimator`, `CalibratedClassifierCV`) | Post-training artifact; re-applied per-league; never applied to base models |
| Backtest (walk-forward CLV with opening odds + slippage) | Training pipeline (`bip/train/backtest.py`) | Supabase `clv_records` / opening-odds Parquet | Reads historical odds; computes CLV; writes report to `backtest/reports/` |
| Model artifact storage | `models/football/{league}/{version}/` filesystem | — | Simple filesystem layout; no MLflow |
| Model registry (production vs shadow per league) | `models/football/registry.json` | — | JSON sidecar; CLI-updated; read by `FootballPlugin.predict()` |
| CLI entry point (`fit`, `backtest`, `promote`) | `bip/train/__main__.py` (Typer) | — | Offline; runs outside scheduler |
| Shadow-mode prediction write | `core/storage/repositories.py` (`PredictionRepository.insert(is_shadow=True)`) | `predictions` table (needs migration 003) | Shadow is a column flag on existing table; no separate shadow_predictions table |
| Runtime prediction path | `sports/football/plugin.py` `predict()` | Training pipeline (loads saved model) | Phase 2 replaces stub with `ModelLoader(registry).load(league).predict_proba(features)` |

---

## Standard Stack

### Core (already installed — verified in pyproject.toml)

| Library | Version | Purpose | Source |
|---------|---------|---------|--------|
| pydantic | 2.13.3 | Data models (`ProbabilityMap`, `FeatureMatrix`, model metadata) | `[VERIFIED: pyproject.toml]` |
| pydantic-settings | 2.14.0 | Config loading from `.env` + env vars | `[VERIFIED: pyproject.toml]` |
| supabase | 2.28.3 | Shadow prediction writes via `PredictionRepository` | `[VERIFIED: pyproject.toml]` |
| httpx | 0.28.1 | (Re-used from Phase 1) async API-Football client for seed | `[VERIFIED: pyproject.toml]` |
| tenacity | 9.1.4 | Retry on API calls during seed | `[VERIFIED: pyproject.toml]` |
| polars | 1.40.1 | Feature engineering + Parquet I/O | `[VERIFIED: pyproject.toml]` |
| pyarrow | 24.0.0 | Polars' Parquet backend | `[VERIFIED: pyproject.toml]` |
| structlog | 25.5.0 | Structured logs for train pipeline | `[VERIFIED: pyproject.toml]` |

### Supporting (new — to add to pyproject.toml in Phase 2)

| Library | Version | Purpose | Source / Why |
|---------|---------|---------|--------------|
| xgboost | 3.2.0 | Gradient boosting (base model #1) | `[VERIFIED: PyPI 2026-02-10]` · Python >=3.10, CPU wheel on macOS arm64 available |
| catboost | 1.2.10 | Gradient boosting (categorical-aware base model #2) | `[VERIFIED: PyPI 2026-02-18]` · Native Polars input (1.2.10 release note) |
| lightgbm | 4.6.0 | Gradient boosting (fast base model #3) | `[VERIFIED: PyPI 2025-02-15]` · Polars input supported (with a `feature_names_in_` caveat in some versions — fall back to numpy at call site if it bites) |
| scikit-learn | 1.8.0 | StackingClassifier, TimeSeriesSplit, FrozenEstimator, CalibratedClassifierCV, IsotonicRegression, LogisticRegression | `[VERIFIED: PyPI 2025-12-10]` · `FrozenEstimator` replaces `cv='prefit'` |
| penaltyblog | 1.9.0 | DixonColesGoalModel (Cython), Elo, dixon_coles_weights, FootballProbabilityGrid | `[VERIFIED: PyPI 2026-02-28 / Context7 /martineastwood/penaltyblog]` |
| scipy | ≥1.15 | Pulled in transitively by penaltyblog + sklearn | `[CITED: CLAUDE.md]` |
| numpy | ≥2.2 | Required by all ML libs | `[CITED: CLAUDE.md]` |
| typer | 0.24.2 | CLI entry point (`bip.train` subcommands) | `[VERIFIED: PyPI 2026-04-22]` · Better UX than `argparse`; installs `click` transitively |
| joblib | 1.4.x | Serialize trained sklearn ensemble + calibrator to disk | `[ASSUMED: standard sklearn persistence tool]` — verify wheel at install time. Note: joblib uses the standard Python serialization protocol, so only load artifacts produced by this same pipeline (see Security Domain below). |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| LogisticRegression stacking | Simplex-weighted average | Simpler, no OOF required, harder to beat in small-sample regimes — **user explicitly chose stacking (D-03)**, fallback available if stacking is unstable |
| `StackingClassifier` with TimeSeriesSplit cv | Hand-rolled OOF loop | Hand-rolled gives explicit control over which fold's training data computes which OOF row; recommended if `StackingClassifier` cv behavior with custom `TimeSeriesSplit` is unclear in sklearn 1.8. **Recommendation**: hand-roll the OOF loop for absolute clarity on temporal integrity (D-03b is non-negotiable) |
| Typer CLI | `argparse` stdlib | argparse is fine and has zero dependencies; Typer is nicer UX. Either works. |
| joblib for model persistence | ONNX export + runtime | ONNX is the safer long-term choice (no code-execution surface) but adds conversion complexity; joblib keeps the loop tight in Phase 2 with a constrained load path (only load from project-owned `models/` dir) |
| penaltyblog Dixon-Coles | Custom scipy.optimize implementation | penaltyblog is Cython-optimized and battle-tested; rolling your own is 5-10x slower and error-prone (gradient computation especially) |

**Installation (delta over Phase 1):**
```bash
uv add xgboost==3.2.0 catboost==1.2.10 lightgbm==4.6.0 scikit-learn==1.8.0 penaltyblog==1.9.0 typer==0.24.2 joblib
```

**Version verification performed:**
```bash
# Actual command run during research (2026-04-22):
for pkg in xgboost catboost lightgbm scikit-learn penaltyblog typer; do
  # fetched via https://pypi.org/pypi/{pkg}/json
done
```
Result: all versions match CLAUDE.md spec (XGBoost 3.2.0 · 2026-02-10, CatBoost 1.2.10 · 2026-02-18, LightGBM 4.6.0 · 2025-02-15, scikit-learn 1.8.0 · 2025-12-10, penaltyblog 1.9.0 · 2026-02-28).

---

## Architecture Patterns

### System Architecture Diagram

```
                ┌────────────────────────────────────────────────────┐
                │  scripts/seed_historical.py   (one-off, not scheduled)
                │                                                    │
                │     ApiFootballClient  →  checkpoint.json          │
                │            │                                       │
                │            ▼                                       │
                │     ParquetStore.write_features() (Hive-partitioned)
                └────────────────────────────────────────────────────┘
                                      │
                                      ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │   Hive Parquet — sport=football/league=X/season=Y/matchday=Z/   │
   │   (fixtures, stats, lineups, corners, H2H, odds snapshots)       │
   └──────────────────────────────────────────────────────────────────┘
                                      │
                      ┌───────────────┴──────────────────┐
                      ▼                                   ▼
   ┌────────────────────────────────────┐   ┌────────────────────────┐
   │  FeatureEngineer (features.py)     │   │  OpeningOddsCache      │
   │   - rolling form (Polars)           │   │  (Parquet — t=opening) │
   │   - ELO (penaltyblog.ratings.Elo)   │   └────────────────────────┘
   │   - Dixon-Coles (penaltyblog)       │                 │
   │   - H2H aggregates                  │                 │
   │   - rest days, motivation           │                 │
   │   - odds signals                    │                 │
   │                                     │                 │
   │   Output: FeatureMatrix             │                 │
   │   (computed_at ≤ kickoff_utc)       │                 │
   └────────────────────────────────────┘                 │
                      │                                     │
                      ▼                                     │
   ┌────────────────────────────────────┐                  │
   │  bip.train.pipeline.TrainingPipeline│                  │
   │                                     │                  │
   │  for each league:                   │                  │
   │    TimeSeriesSplit(n_splits=5)      │                  │
   │    for each fold:                   │                  │
   │      ┌───────────────────────────┐  │                  │
   │      │ Inner OOF loop (in-fold)  │  │                  │
   │      │  fit base_models on train │  │                  │
   │      │  → OOF preds via k-fold   │  │                  │
   │      │    TimeSeriesSplit WITHIN │  │                  │
   │      │    the fold's train set   │  │                  │
   │      │  → train LogReg on OOF    │  │                  │
   │      └───────────────────────────┘  │                  │
   │      Evaluate on fold's test set    │                  │
   │      → store fold predictions       │                  │
   │                                     │                  │
   │    After all folds:                 │                  │
   │      Calibrate (Platt / Isotonic)   │                  │
   │      Compute walk-forward CLV ──────┼──────────────────┘
   │      Save to models/football/{X}/   │
   │      Write metadata.json            │
   └─────────────────────────────────────┘
                      │
                      ▼
   ┌────────────────────────────────────┐
   │  bip.train CLI (Typer)              │
   │    fit --league X                   │
   │    backtest --league X              │
   │    promote --league X --version vN ─┼──► updates registry.json
   └─────────────────────────────────────┘
                      │
                      ▼
   ┌────────────────────────────────────┐        ┌───────────────────────┐
   │  models/football/registry.json      │◄───────┤ FootballPlugin.predict()
   │  { "premier_league": {              │        │                        │
   │     "production": "v3",             │        │  loads registry        │
   │     "shadow": "v4" } }              │        │  runs BOTH prod+shadow │
   │                                     │        │  writes prediction     │
   │  models/football/                   │        │  prod → is_shadow=False│
   │    premier_league/                  │        │  shadow → is_shadow=True│
   │      v3/{model.joblib, metadata.json}└───────►                        │
   │      v4/{model.joblib, metadata.json}│        │                        │
   └────────────────────────────────────┘        └───────────────────────┘
                                                              │
                                                              ▼
                                                 ┌──────────────────────────┐
                                                 │  Supabase predictions    │
                                                 │  (needs migration 003:   │
                                                 │   ADD COLUMN is_shadow)  │
                                                 └──────────────────────────┘
```

### Recommended Project Structure

```
src/bip/
├── core/                              # (unchanged from Phase 1)
├── clv/                               # (unchanged from Phase 1)
├── scheduler/                         # (unchanged from Phase 1)
├── sports/
│   ├── __init__.py                   # (SportPlugin ABC — unchanged)
│   └── football/
│       ├── plugin.py                  # replaces predict() stub
│       ├── features.py                # EXPANDED from 2 features to ~40-60
│       ├── client.py                  # (unchanged)
│       ├── model_loader.py            # NEW: reads registry.json, loads ensemble
│       └── config/                    # (unchanged)
└── train/                             # NEW package — training pipeline
    ├── __init__.py
    ├── __main__.py                    # Typer CLI entry point
    ├── pipeline.py                    # TrainingPipeline orchestrator
    ├── base_models.py                 # factory for XGB/CB/LGB with default params
    ├── stacking.py                    # nested OOF stacking (NOT sklearn default)
    ├── calibration.py                 # Platt / Isotonic selector per ML-03
    ├── walkforward.py                 # TimeSeriesSplit + fold iteration
    ├── backtest.py                    # CLV with opening odds + 1-2% slippage
    ├── registry.py                    # read/write models/football/registry.json
    └── metadata.py                    # metadata.json schema (Pydantic)

scripts/
└── seed_historical.py                 # NEW: one-off historical pull
    # checkpoint file: data/seed_checkpoint.json

models/                                # NEW root-level directory
└── football/
    ├── registry.json
    ├── premier_league/
    │   ├── v1/
    │   │   ├── ensemble.joblib
    │   │   ├── calibrator.joblib
    │   │   └── metadata.json
    │   └── v2/…
    └── …(4 more leagues)

supabase/migrations/
└── 20260501000000_add_is_shadow_column.sql    # NEW: migration 003

tests/
├── test_features_rolling.py           # NEW
├── test_features_elo.py               # NEW
├── test_features_h2h.py               # NEW
├── test_features_motivation.py        # NEW
├── test_walkforward.py                # NEW — temporal integrity check
├── test_stacking_oof.py               # NEW — verify no leakage
├── test_calibration.py                # NEW — Platt vs Isotonic selection
├── test_backtest_clv.py               # NEW — opening odds + slippage
├── test_registry.py                   # NEW
├── test_model_loader.py               # NEW
└── test_plugin_predict.py             # NEW — FootballPlugin.predict() E2E
```

### Pattern 1: Nested walk-forward with in-fold OOF (D-03b, non-negotiable)

**What:** Outer `TimeSeriesSplit` iterates over time; inside each fold we run an inner `TimeSeriesSplit` on the training window to generate OOF predictions for the meta-learner. No global OOF reuse.

**Why hand-rolled, not `StackingClassifier`:** sklearn's `StackingClassifier` accepts a `cv=` argument that could in theory be set to a `TimeSeriesSplit`, but its semantics around how the base models are re-fit on the full training window after OOF generation are not what we want for a walk-forward backtest — you also have to refit at every outer fold. Hand-rolling makes the temporal ordering explicit and auditable.

**Example:**
```python
# Source: hand-rolled pattern, based on sklearn.model_selection.TimeSeriesSplit docs
# [CITED: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html]
from sklearn.model_selection import TimeSeriesSplit
from sklearn.linear_model import LogisticRegression
from xgboost import XGBClassifier
from catboost import CatBoostClassifier
from lightgbm import LGBMClassifier
import numpy as np

def walk_forward_stacked_fit(X, y, dates, n_outer=5, n_inner=5):
    """
    X: feature matrix ordered by date ASC.
    y: labels ordered by date ASC.
    dates: ordered dates (for sanity-check assertions).
    Returns: list of (fold_idx, test_indices, test_predictions, calibrated_predictions).
    """
    outer = TimeSeriesSplit(n_splits=n_outer)
    fold_results = []
    for fold_idx, (train_idx, test_idx) in enumerate(outer.split(X)):
        X_tr, y_tr = X[train_idx], y[train_idx]
        X_te, y_te = X[test_idx], y[test_idx]

        # Sanity: every training date must be strictly < every test date
        assert dates[train_idx].max() < dates[test_idx].min(), \
            f"Fold {fold_idx} temporal leakage detected"

        # Inner OOF on train window only (D-03b)
        inner = TimeSeriesSplit(n_splits=n_inner)
        oof = np.zeros((len(train_idx), len(CLASSES)))  # one column per class
        for inner_train, inner_val in inner.split(X_tr):
            base = [
                XGBClassifier(**XGB_PARAMS).fit(X_tr[inner_train], y_tr[inner_train]),
                CatBoostClassifier(**CB_PARAMS, verbose=0).fit(X_tr[inner_train], y_tr[inner_train]),
                LGBMClassifier(**LGBM_PARAMS, verbose=-1).fit(X_tr[inner_train], y_tr[inner_train]),
            ]
            probs = [m.predict_proba(X_tr[inner_val]) for m in base]
            # average class-wise probs across base models → meta features
            oof[inner_val] = np.mean(probs, axis=0)

        # Train meta-learner on OOF
        meta = LogisticRegression(max_iter=2000).fit(oof, y_tr[:len(oof)])
        # Retrain base models on FULL train window
        final_base = [
            XGBClassifier(**XGB_PARAMS).fit(X_tr, y_tr),
            CatBoostClassifier(**CB_PARAMS, verbose=0).fit(X_tr, y_tr),
            LGBMClassifier(**LGBM_PARAMS, verbose=-1).fit(X_tr, y_tr),
        ]
        # Predict on test fold
        test_probs = np.mean(
            [m.predict_proba(X_te) for m in final_base], axis=0
        )
        test_preds = meta.predict_proba(test_probs)
        fold_results.append((fold_idx, test_idx, test_preds))
    return fold_results
```

**When to use:** Every walk-forward backtest in this phase. The sanity-check assertion is mandatory — it's the single best insurance policy against temporal leakage.

### Pattern 2: Calibration in sklearn 1.8 (no `cv='prefit'`)

**What:** sklearn 1.8 removed `CalibratedClassifierCV(cv='prefit')`. Replacement is wrapping the fitted estimator in `FrozenEstimator` and passing `cv=None`.

**Example:**
```python
# Source: [CITED: https://scikit-learn.org/stable/modules/calibration.html]
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator

# Assume `stacked_ensemble` is a fitted estimator (wrapper that runs base+meta and returns probas)

def calibrate(ensemble, X_cal, y_cal, n_cal_samples):
    """ML-03 thresholds."""
    if n_cal_samples < 300:
        method = 'sigmoid'     # Platt
    elif n_cal_samples > 500:
        method = 'isotonic'
    else:
        # 300–500: fall back to Platt (coarser method is safer for intermediate sample sizes)
        method = 'sigmoid'
    calibrated = CalibratedClassifierCV(
        estimator=FrozenEstimator(ensemble),
        method=method,
        cv=None,  # does not re-fit; uses the frozen estimator as-is
    )
    calibrated.fit(X_cal, y_cal)
    return calibrated
```

**Alternative minimal pattern (bypasses sklearn wrapper entirely):**
```python
# Source: [CITED: https://scikit-learn.org/stable/modules/generated/sklearn.isotonic.IsotonicRegression.html]
from sklearn.isotonic import IsotonicRegression

# For single-class (binary) markets like BTTS
probs_train = ensemble.predict_proba(X_cal)[:, 1]
iso = IsotonicRegression(out_of_bounds='clip').fit(probs_train, y_cal)
calibrated_probs = iso.predict(probs_test)
```
This direct pattern is cleaner for per-outcome (per 1X2 class) calibration but requires one `IsotonicRegression` per class.

### Pattern 3: Opening odds + slippage CLV (ML-02)

**What:** The walk-forward backtest must use **opening odds** as the "stake price" and deduct 1–2% slippage, not closing odds. Retrofitting closing-odds CLV later invalidates early results (project decision).

**Example:**
```python
# Slippage application
SLIPPAGE_PCT = 0.015  # 1.5% mid-range of 1-2% spec

def apply_slippage(opening_odds: float) -> float:
    """Bet-taker always loses 1.5% of odds edge to market movement / line taken."""
    return opening_odds * (1 - SLIPPAGE_PCT)

def compute_clv(staked_odds: float, pinnacle_closing: float) -> float:
    """CLV % vs Pinnacle closing (ML-02 / CLV-02)."""
    return (staked_odds / pinnacle_closing - 1) * 100.0
```

CLV calculation uses **simulated stake odds** (opening × (1 − slippage)) and **actual Pinnacle closing** pulled from `clv_records` for that fixture+market. If CLV closing not yet recorded for a historical fixture, the fold excludes that row from CLV summary (fold size shrinks) but still includes it in accuracy/logloss. Document the `null_clv_rows` count in `metadata.json`.

### Pattern 4: ELO rating bootstrapping across seasons

**What:** ELO is stateful. Fit over all 3 seasons of historical data in chronological order before the first walk-forward fold opens. Do NOT reset per fold.

**Example:**
```python
# Source: [CITED: Context7 /martineastwood/penaltyblog — ratings.elo]
from penaltyblog.ratings import Elo
import polars as pl

def bootstrap_elo(historical_matches: pl.DataFrame) -> Elo:
    """
    historical_matches: sorted ASC by kickoff_utc;
    columns: home_team, away_team, home_goals, away_goals, kickoff_utc
    """
    elo = Elo(k=20.0, home_field_advantage=100.0)
    # result encoding: 0=home win, 1=draw, 2=away win (penaltyblog spec)
    for row in historical_matches.iter_rows(named=True):
        if row['home_goals'] > row['away_goals']:
            r = 0
        elif row['home_goals'] == row['away_goals']:
            r = 1
        else:
            r = 2
        elo.update_ratings(row['home_team'], row['away_team'], r)
    return elo
```

**Critical:** When computing features for fixture X at `computed_at=T`, use `elo.get_team_rating(team)` after updating with all matches finishing before T. A feature-time snapshot of the ELO state per fixture avoids re-running the bootstrap for every fixture (O(n) instead of O(n²)).

### Pattern 5: Dixon-Coles per-fold scoping via temporal feature cutoff

**What:** Fit `DixonColesGoalModel` once over the full historical corpus. At feature-extraction time, only use the Dixon-Coles rating as it stood at the fixture's `computed_at` cutoff. The pragmatic shortcut: pre-compute a per-matchday Dixon-Coles rating snapshot.

**Example:**
```python
# Source: [CITED: Context7 /martineastwood/penaltyblog]
import penaltyblog as pb

# Fit once (Cython-optimized)
dc_weights = pb.models.dixon_coles_weights(df['date'], xi=0.001)
dc_model = pb.models.DixonColesGoalModel(
    df['home_goals'], df['away_goals'], df['home_team'], df['away_team'],
    weights=dc_weights,
)
dc_model.fit(use_gradient=True, minimizer_options={"maxiter": 3000})

# Extract per-team attack/defense from fitted params
attack_ratings = {k: v for k, v in dc_model.params.items() if k.startswith('attack_')}
defence_ratings = {k: v for k, v in dc_model.params.items() if k.startswith('defence_')}
# Use these as features.
# For backtest: refit the DC model using ONLY matches before fold boundary when exact
# temporal correctness matters (deferred per CONTEXT.md Deferred Ideas).
```

Pre-fitting with temporal scoping is the documented pragmatic default. Per-fold refit is deferred.

### Anti-Patterns to Avoid

- **Global OOF reuse across walk-forward folds:** Generating OOF predictions once over the entire dataset and reusing them across all folds is temporal leakage. Every fold's meta-learner must train only on OOF data whose ground truth predates the fold's test set. (D-03b enforces this.)
- **`CalibratedClassifierCV(cv='prefit')`:** Removed in sklearn 1.8. Code that imports or uses this pattern will raise; replace with `FrozenEstimator` wrapper.
- **Using `StackingClassifier` default `cv=5`:** Default is stratified KFold — temporally unsafe. If you do use `StackingClassifier`, pass `cv=TimeSeriesSplit(n_splits=5)` explicitly.
- **Calibrating base models individually:** Calibration happens on the meta-learner output only (D-03c). Calibrating base models first breaks the probability composition — meta-learner expects raw base probs as features.
- **Closing-odds CLV in the backtest:** Closing odds are the reference benchmark; staked-odds CLV must use opening odds minus slippage (ML-02). Retrofitting later invalidates all earlier numbers.
- **Hand-rolled Dixon-Coles:** penaltyblog 1.9 has a Cython-optimized implementation with analytical Jacobian gradients (5-10x faster than naive scipy). Use it.
- **Hand-rolled ELO:** penaltyblog 1.9 ships `Elo` with home-field advantage. Use it.
- **Writing `is_shadow=True` before migration 003 exists:** Will raise a Postgres column-not-found error. Sequence the migration first.
- **Putting `scripts/seed_historical.py` inside `src/bip/`:** D-01 mandates `scripts/` (outside the package) precisely because it should not be importable by the scheduler.
- **Pandas anywhere in the training pipeline:** CLAUDE.md forbids it. Polars end-to-end. If a library forces numpy, convert at the call site, not upstream.
- **Auto-promotion of any kind in Phase 2:** D-05 explicitly prohibits this. A bad promotion is a direct financial loss.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Dixon-Coles model | Custom scipy.optimize with log-likelihood | `penaltyblog.models.DixonColesGoalModel` | Cython + analytical gradients = 5-10× faster; correct correlation parameter for low-score draws |
| ELO rating | Custom dict + update_rating() method | `penaltyblog.ratings.Elo` | Handles home-field advantage, match probability conversion, draw-base/width adjustments |
| Walk-forward fold splitter | Hand-rolled index loop | `sklearn.model_selection.TimeSeriesSplit` | Battle-tested; handles `gap`, `test_size`, `max_train_size`; integrates with sklearn |
| Platt scaling | Custom logistic regression on probs | `CalibratedClassifierCV(method='sigmoid')` | Well-tested; handles multi-class via OvR automatically |
| Isotonic calibration | Custom piecewise-constant interpolator | `sklearn.isotonic.IsotonicRegression` or `CalibratedClassifierCV(method='isotonic')` | O(n log n) fit; handles out-of-bounds via `'clip'` |
| Stratified time-aware CV | Hand-rolled fold generator | `TimeSeriesSplit` (or a thin wrapper for the OOF loop) | Has `gap` parameter for look-ahead bias |
| BTTS / Over-Under / Asian Handicap probabilities | Poisson integration from scratch | `FootballProbabilityGrid.btts_yes`, `.totals(line)`, `.asian_handicap_probs()` returned by `DixonColesGoalModel.predict()` | Penaltyblog grid already supports every Phase-1 market; use as a sanity-check baseline and as a feature |
| Feature set hash | Custom comparison logic | `hashlib.sha256(json.dumps(sorted(feature_names)).encode()).hexdigest()[:16]` | Detects model-vs-feature-set mismatches deterministically |
| CLI argument parsing | `argparse` with manual subcommands | `typer.Typer()` + `@app.command()` | Auto-help, type coercion, Rich output; already familiar in FastAPI-ish ecosystems |
| Model persistence | Stdlib serialization | `joblib.dump()` with a constrained load path | Faster for numpy-heavy artifacts; handles mmap for large arrays. **Security note**: only load artifacts produced by this same pipeline (see Security Domain) |

**Key insight:** Every "core ML operation" in this phase has a battle-tested library solution. The only code Phase 2 should actually write from scratch is: (a) the orchestration (walk-forward loop, per-league training driver), (b) the feature functions that combine raw API data into features, (c) the registry JSON manipulation, (d) the backtest CLV accounting. Everything else is a library call.

---

## Runtime State Inventory

Phase 2 is primarily greenfield ML code — **no** renames, refactors, or string replacements. One category applies:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | **`is_shadow` column missing from `predictions` table** (migration 002 did not add it despite ML-05 requiring it) | Ship migration 003 in Phase 2 Wave 0 before any shadow-prediction write |
| Stored data | No historical training data exists yet in Parquet (Phase 1 only writes live ingestion) | `scripts/seed_historical.py` creates it (D-01); not a migration, a data build |
| Live service config | None — no external services configured in Phase 2 beyond those already in Phase 1 | None |
| OS-registered state | None — no systemd/launchd/Task Scheduler registrations | None (Phase 4 scope) |
| Secrets / env vars | `API_FOOTBALL_KEY`, `SUPABASE_URL`, `SUPABASE_KEY` already in `.env`; new env var `MODEL_DIR` (default `models/`) in `core/settings.py` | Update `Settings` class to add `model_dir` field |
| Build artifacts | `pyproject.toml` dependencies need expansion (xgboost, catboost, lightgbm, sklearn, penaltyblog, typer, joblib) | `uv add` the new deps before any import in Phase 2 code |

**Nothing found for OS-registered state / secrets** — verified by grep across codebase and manual inspection of `core/settings.py`.

---

## Common Pitfalls

### Pitfall 1: Temporal leakage via global OOF reuse

**What goes wrong:** A tempting optimization — run k-fold OOF once over the full dataset, store the OOF matrix, and reuse it across walk-forward folds to save compute.

**Why it happens:** k-fold OOF allows one k-fold's validation rows to be "predicted" by base models that saw fixtures occurring *after* that validation fixture. When you then train a meta-learner using those OOF predictions and evaluate it on walk-forward fold F (say, December 2025), the meta-learner's training data included OOF predictions generated using training data from *after* December 2025. The CLV numbers look great; they're fantasy.

**How to avoid:** Generate OOF predictions inside each walk-forward fold, using only that fold's train window, with an inner `TimeSeriesSplit`. Include an assertion that every training date is strictly less than every test date at every outer fold boundary.

**Warning signs:** OOS logloss on fold N suspiciously close to IS logloss; CLV numbers that are 2-3x higher than any comparable literature benchmark; model retains edge even on most recent season (unlikely in reality — sharps close in quickly).

### Pitfall 2: Using `cv='prefit'` from old reference code

**What goes wrong:** AttributeError / deprecation error when `CalibratedClassifierCV(cv='prefit')` is imported under sklearn 1.8.

**Why it happens:** Every pre-2025 example online uses this pattern. sklearn 1.8 (Dec 2025) removed it. The reference code linked in CONTEXT.md (jeke-xg-model-basic/src/calibration/isotonic.py) likely predates 1.8.

**How to avoid:** Use `CalibratedClassifierCV(estimator=FrozenEstimator(fitted), cv=None)` or directly fit `IsotonicRegression` / `LogisticRegression` on the probability outputs. Add the migration note to any calibration code comment so future maintainers don't regress.

**Warning signs:** Any PR that imports `from sklearn.calibration import CalibratedClassifierCV` and does not also import `from sklearn.frozen import FrozenEstimator`.

### Pitfall 3: Polars→numpy coercion differences between XGBoost / CatBoost / LightGBM

**What goes wrong:** Silent feature-order mismatch. CatBoost 1.2.10 accepts Polars natively; XGBoost 3.2 accepts Polars DataFrame/LazyFrame; LightGBM 4.6 has documented issues with `feature_names_in_` on Polars inputs.

**Why it happens:** Each library has its own Polars compatibility story. Mixed usage (one model gets Polars, another gets numpy) can silently reorder columns.

**How to avoid:** Standardize on ONE ingress format to all three base models. Recommendation: convert Polars → numpy (`df.to_numpy()`) at the training driver boundary, keeping the feature-name list as a separate artifact. This gives one source of truth for column order.

**Warning signs:** Different base model predictions disagree wildly (one is near-uniform, others are confident); feature-importance orderings don't make sense.

### Pitfall 4: Dixon-Coles team-name mismatch

**What goes wrong:** DixonColesGoalModel fit on historical data that uses "Tottenham Hotspur" crashes at prediction time when the fixture API returns "Tottenham".

**Why it happens:** API-Football and Betano/Odds API use different team-name canonicalizations. Phase 1 YAML config has `team_name_mappings` that normalize API-Football → Betano names.

**How to avoid:** Apply the Phase-1 `team_name_mappings` normalization at feature-extraction time, BEFORE fitting the Dixon-Coles model. Verify in a unit test that all team names in the DC model's `params` dict match the canonical names used at prediction time.

**Warning signs:** `KeyError` in `dc_model.predict(home, away)`; attack_/defence_ keys that look like duplicates with different spellings.

### Pitfall 5: ELO rating drift across fold boundaries

**What goes wrong:** ELO ratings computed once over the full corpus include updates from fixtures in the test fold, so features for test fold N reflect ELO state that used information from the test fold itself.

**Why it happens:** Naive `bootstrap_elo()` over the full corpus = temporal leakage.

**How to avoid:** At feature-extraction time for fixture F (computed_at=T), snapshot the ELO state as of T (i.e., only include matches finishing before T in the ELO update sequence). Pre-compute per-matchday ELO snapshots to avoid O(n²) runtime.

**Warning signs:** Same-day re-run of features for a fixture that already played produces different ELO numbers than the original pre-match feature extraction.

### Pitfall 6: Opening-odds Parquet coverage gaps

**What goes wrong:** ML-02 walk-forward CLV requires opening odds for every historical fixture. Phase 1 only fetched *closing* odds (via The Odds API) and only for fixtures that occurred after Phase 1 went live. Historical opening odds may not be in Parquet.

**Why it happens:** The Odds API Rookie tier has no retroactive history endpoint. Historical opening odds likely need to come from another source or the seed script.

**How to avoid:** Phase 2 seed script must fetch historical opening odds too, or the backtest must document that early folds have no CLV and the test set only starts at the first fold where odds coverage exists. **This is a potential blocker** — must verify during seed-script planning.

**Warning signs:** `opening_odds = NULL` for the majority of fold rows; CLV computation skips too many rows to be statistically meaningful.

### Pitfall 7: Calibration sample-size boundary (300–500 gap)

**What goes wrong:** ML-03 specifies `<300 → Platt` and `>500 → isotonic` but leaves the 300–500 range ambiguous.

**Why it happens:** Specification gap. The reference implementation linked in CONTEXT.md has hardcoded thresholds but no documented 300-500 handling.

**How to avoid:** Codified decision in this phase: 300–500 falls back to Platt (safer on intermediate sample sizes; isotonic can overfit below ~500 samples because its non-parametric nature chases noise). Log the chosen method in `metadata.json` per league per fold.

**Warning signs:** Logloss improvement from calibration is negative (calibration made it worse) — suggests overfitting and the fallback should be more conservative.

### Pitfall 8: Feature hash mismatch silently loads wrong model

**What goes wrong:** `FootballPlugin.predict()` loads a saved model trained on feature set v1 but runtime feature engineering has added a feature (v2). Model silently predicts on wrong feature dimensions.

**Why it happens:** Feature engineering drift during active development; no hash check at load time.

**How to avoid:** `metadata.json` stores `feature_set_hash` computed as `sha256(sorted(feature_names))[:16]`. `ModelLoader.load()` recomputes the hash from current `FeatureEngineer` output and raises if mismatch. This also catches accidental feature re-ordering.

**Warning signs:** Prediction shape mismatch error at runtime; silently different probabilities than backtest recorded.

---

## Code Examples

Verified patterns from official sources:

### Dixon-Coles fit + predict (penaltyblog 1.9)
```python
# Source: [VERIFIED: Context7 /martineastwood/penaltyblog]
import penaltyblog as pb

weights = pb.models.dixon_coles_weights(df['date'], xi=0.001)
model = pb.models.DixonColesGoalModel(
    df['goals_home'], df['goals_away'],
    df['team_home'], df['team_away'],
    weights=weights,
)
model.fit(use_gradient=True, minimizer_options={"maxiter": 3000})

pred = model.predict("Arsenal", "Manchester City")
p_home, p_draw, p_away = pred.home_draw_away     # 1X2
p_btts_yes = pred.btts_yes                        # BTTS
p_under, p_push, p_over = pred.totals(2.5)        # Totals
ah = pred.asian_handicap_probs("home", -0.25)    # {win, push, lose}
```

### ELO rating system (penaltyblog 1.9)
```python
# Source: [VERIFIED: Context7 /martineastwood/penaltyblog]
from penaltyblog.ratings import Elo

elo = Elo(k=20.0, home_field_advantage=100.0)
# result: 0=home win, 1=draw, 2=away win
elo.update_ratings("Arsenal", "Chelsea", 0)
rating = elo.get_team_rating("Arsenal")
probs = elo.calculate_match_probabilities("Arsenal", "Liverpool")
# → {'home_win': 0.51, 'draw': 0.21, 'away_win': 0.28}
```

### TimeSeriesSplit walk-forward
```python
# Source: [CITED: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html]
from sklearn.model_selection import TimeSeriesSplit

tscv = TimeSeriesSplit(n_splits=5, test_size=None, gap=0)
# Default test_size = n_samples // (n_splits + 1)
# Use gap=N if you want to exclude the final N samples of the train window
for fold_idx, (train_idx, test_idx) in enumerate(tscv.split(X)):
    # train_idx grows fold by fold (expanding window)
    # test_idx is a disjoint, contiguous, later-in-time slice
    pass
```

### Calibration (sklearn 1.8)
```python
# Source: [CITED: sklearn.org/stable/modules/calibration.html and sklearn.frozen.FrozenEstimator]
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator

# `stacked` is a fitted custom ensemble exposing predict_proba
calibrator = CalibratedClassifierCV(
    estimator=FrozenEstimator(stacked),
    method='isotonic',  # or 'sigmoid' for Platt, 'temperature' for multi-class temp scaling
    cv=None,
)
calibrator.fit(X_cal, y_cal)
calibrated_probs = calibrator.predict_proba(X_test)
```

### Typer CLI scaffold for `python -m bip.train ...`
```python
# Source: [CITED: https://typer.tiangolo.com/tutorial/subcommands/]
# src/bip/train/__main__.py
import typer
from bip.train.pipeline import TrainingPipeline
from bip.train.registry import ModelRegistry

app = typer.Typer()

@app.command()
def fit(league: str, version: str = typer.Option("auto")):
    """Train ensemble for a league and save artifacts under models/football/{league}/{version}/."""
    pipeline = TrainingPipeline()
    pipeline.run(league=league, version=version)

@app.command()
def backtest(league: str, version: str):
    """Re-run walk-forward backtest on an existing version and update metadata.json."""
    pipeline = TrainingPipeline()
    pipeline.backtest(league=league, version=version)

@app.command()
def promote(league: str, version: str):
    """Mark version as production for this league in registry.json (manual CLI — D-05)."""
    registry = ModelRegistry.load()
    registry.promote(league=league, version=version)
    registry.save()
    typer.echo(f"Promoted {league}/{version} to production")

if __name__ == "__main__":
    app()
```

### Feature set hash (for `metadata.json`)
```python
# Source: [VERIFIED: hashlib stdlib docs]
import hashlib, json

def feature_set_hash(feature_names: list[str]) -> str:
    canonical = json.dumps(sorted(feature_names)).encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()[:16]
```

### `metadata.json` schema (Pydantic — Claude's discretion over ML-04 minimum)
```python
# Proposed schema — beyond ML-04 minimum (training_date, feature_set, calibration_method, backtest_CLV)
from datetime import datetime
from pydantic import BaseModel, Field

class ModelMetadata(BaseModel):
    sport: str = "football"
    league: str                          # e.g., "premier_league"
    version: str                         # e.g., "v3" — monotonically increasing
    training_date: datetime
    training_data_seasons: list[str]     # e.g., ["2023-2024", "2024-2025", "2025-2026"]
    training_rows: int
    feature_names: list[str]             # canonical order
    feature_set_hash: str                # sha256[:16] of sorted feature_names
    calibration_method: str              # "sigmoid" | "isotonic" | "temperature"
    calibration_samples: int
    walk_forward_folds: int
    walk_forward_mean_clv_pct: float     # average CLV% across folds (the promotion criterion)
    walk_forward_fold_details: list[dict]  # per-fold logloss, CLV, n_test
    base_model_params: dict              # hyperparameters for XGB/CB/LGB
    base_model_packages: dict            # {"xgboost": "3.2.0", "catboost": "1.2.10", ...}
    sklearn_version: str
    null_clv_rows: int                   # fixtures with missing Pinnacle closing
    slippage_pct: float                  # 0.015
    git_commit: str | None = None        # optional git SHA at training time
```

### Model registry JSON (proposed schema)
```json
{
  "schema_version": 1,
  "updated_at": "2026-04-30T12:00:00Z",
  "leagues": {
    "premier_league": {
      "production": "v3",
      "shadow": "v4",
      "history": ["v1", "v2", "v3"]
    },
    "la_liga": {
      "production": "v2",
      "shadow": null,
      "history": ["v1", "v2"]
    }
  }
}
```

### Migration 003 SQL (required for ML-05 shadow mode)
```sql
-- supabase/migrations/20260501000000_add_is_shadow_column.sql
-- Migration 003: Add is_shadow for ML-05 shadow-mode prediction logging

ALTER TABLE predictions
    ADD COLUMN IF NOT EXISTS is_shadow BOOLEAN NOT NULL DEFAULT false;

-- Index for production-only reads (Phase 3 pick engine reads is_shadow=false)
CREATE INDEX IF NOT EXISTS idx_predictions_is_shadow ON predictions (is_shadow);
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `CalibratedClassifierCV(cv='prefit')` | `CalibratedClassifierCV(estimator=FrozenEstimator(fitted), cv=None)` | sklearn 1.6 (FrozenEstimator introduced), 1.8 (cv='prefit' removed) | Any reference code pre-2025 needs this rewrite |
| pandas for feature engineering | Polars with lazy evaluation | 2024-2025 (CLAUDE.md mandates Polars) | 10-50× speedup on rolling/group operations |
| Hand-rolled Dixon-Coles (scipy.optimize) | `penaltyblog.models.DixonColesGoalModel` | penaltyblog 1.5 (Cython + analytical gradients) → 1.9 current | 5-10× faster fit; less fragile |
| `np.random.seed` globally | `numpy.random.default_rng(seed)` generators per model | numpy 1.17+, universal in 2026 | Reproducibility without global state |
| Stdlib serialization for models | joblib with compression | Ongoing standard since sklearn 1.0 | Better numpy array handling |
| `StackingClassifier(cv=5)` stratified KFold | `StackingClassifier(cv=TimeSeriesSplit(5))` for time-series data | Always correct pattern; frequently missed | Prevents silent temporal leakage |
| XGBoost `DeviceQuantileDMatrix` | Removed in XGBoost 3.0 | XGBoost 3.0 (2025) | Not used in CPU workflows — no impact |
| XGBoost `get_params` returned internal defaults | XGBoost 3.x `get_params` returns only user-set | XGBoost 3.x | Affects model serialization round-trips — test metadata round-trip |

**Deprecated / outdated:**
- Any `CalibratedClassifierCV(..., cv='prefit')` usage — raises in 1.8.
- Custom Dixon-Coles `scipy.optimize.minimize(..., method='Nelder-Mead')` — 10× slower than penaltyblog's Cython + analytical Jacobian.
- APScheduler 4.x — alpha; CLAUDE.md locks to 3.11.x (not Phase 2 concern; the training pipeline is offline anyway).

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Historical opening odds are obtainable from API-Football or the seed script (not just The Odds API closing snapshots) | Pitfall 6, Backtest architecture | HIGH — ML-02 requires opening odds for CLV backtest. If no historical opening odds exist, backtest CLV cannot be computed for early folds; must be descoped or the Phase-1 data source extended. **Recommend verifying with user before planning seed-script tasks.** |
| A2 | 300–500 sample gap in ML-03 falls back to Platt | Pattern 2 / Pitfall 7 | LOW — user can override in the discuss phase; documented decision with fallback reasoning |
| A3 | LightGBM 4.6 Polars input works for our feature set (despite the `feature_names_in_` issue reported in GitHub #6849) | Standard Stack / Pitfall 3 | LOW — fallback is `df.to_numpy()` conversion at call site, no blocker |
| A4 | joblib serialization of the nested ensemble (base models + meta + calibrator) round-trips correctly across XGBoost 3.2, CatBoost 1.2.10, LightGBM 4.6, sklearn 1.8 | Model persistence | MEDIUM — joblib has historically been stable but cross-library serialization protocol changes can bite; **smoke-test round-trip in Wave 0 test `test_model_loader.py`** |
| A5 | Typer 0.24.2 is a suitable CLI framework choice (no strong ecosystem lock-in to argparse from other parts of codebase) | Standard Stack | LOW — if user prefers stdlib, swap to argparse with zero architectural change |
| A6 | `ModelMetadata` schema as designed includes all fields Phase 3 (pick engine) will need (no missing required fields) | Code Examples | MEDIUM — Phase 3 planner should verify; current fields cover promotion criterion and prediction path |
| A7 | 3 seasons × 5 leagues = ~5,700 fixtures is "enough" for per-league training (~1,140 per league minus test folds) | Backtest architecture | MEDIUM — 5 outer folds × ~200 test rows = per-fold logloss is noisy. If results are too volatile, may need to combine leagues or reduce folds. Validation plan includes logloss variance per fold. |
| A8 | Reference code paths in CONTEXT.md (`/Apuestas/jeke-xg-model-basic/`, `/Apuestas/football-predictor/`) exist on dev machine | Canonical refs | **CONFIRMED WRONG** — these paths do NOT exist at `/Users/kevin_beltran/ProyectosPersonales/Apuestas/`. Planner should not cite them as canonical — this research doc replaces them as the calibration/backtest pattern authority. |
| A9 | Phase 1 `FeatureMatrix.features: dict[str, float]` holds the final feature dict; the training pipeline can accept this and stack into a Polars DataFrame for batch training | Architecture | LOW — verified in `src/bip/sports/__init__.py`; simple dict-to-dataframe |
| A10 | The `xi` time-decay factor for `dixon_coles_weights` should be ~0.001 (very slow decay, emphasizes recency mildly) for football | Pattern 5 | LOW — penaltyblog docs suggest 0.001 as the common default; tuneable as part of feature importance pass (D-02 constraint) |

**A1 and A8 are actionable:** A1 needs user verification before the seed script is planned in detail. A8 means the planner cannot rely on those external reference code paths; this research doc is the authoritative pattern source.

---

## Open Questions

1. **Historical opening odds source — unknown**
   - What we know: The Odds API Rookie tier records closing odds (CLV snapshots); Phase 1's `OddsApiClient` only records closing. API-Football does not appear to offer historical opening odds as a standard endpoint.
   - What's unclear: Where do historical opening odds come from for the backtest? Possible paths: (a) API-Football `/odds/history` if available on Pro, (b) scrape an archive, (c) descope opening-odds CLV for early seasons and start backtest from a date where Phase-1 has been recording.
   - Recommendation: **Raise this in the planner's first wave** as a blocker-class question. If no good source exists, convert ML-02 to "closing-odds CLV for historical test-set + opening-odds CLV going forward" and document the gap. Do not invent numbers.

2. **Hyperparameter grids for XGBoost / CatBoost / LightGBM**
   - What we know: CONTEXT.md defers to "football-predictor defaults" but that reference code path does not exist locally.
   - What's unclear: What hyperparameters produce sane baseline performance on ~1,100 rows per league?
   - Recommendation: Use library defaults + mild regularization (e.g., `max_depth=4`, `n_estimators=500`, `learning_rate=0.05`, early_stopping on validation fold). Document in `metadata.json.base_model_params`. Tune only if walk-forward CLV underperforms a simple odds-implied baseline.

3. **How is `matchday` determined at feature-extraction time?**
   - What we know: `FeatureEngineer.to_parquet_row()` currently uses `matchday=1` as a placeholder (`src/bip/sports/football/features.py` line 134).
   - What's unclear: API-Football returns `round` in fixture metadata (e.g., "Regular Season - 12") — Phase 1 plan left this as a Phase 2 concern.
   - Recommendation: Parse `round` from API-Football response in `_parse_fixture()` or store as a separate field; use for partition. Small work item but needs explicit handling.

4. **Test isolation for training pipeline**
   - What we know: Full walk-forward with 3 base models × 5 inner folds × 5 outer folds × 5 leagues = 375 model fits. Even at 10s each that's 63 minutes.
   - What's unclear: Do we gate CI on this? Per-task test execution needs < 30s per validation spec.
   - Recommendation: Split tests into (a) fast unit tests with synthetic data (<1s each), (b) integration tests that run a mini-pipeline on 50 synthetic rows (<10s), (c) `@pytest.mark.slow` end-to-end test skipped in fast CI runs.

5. **Which concrete market(s) does each `ProbabilityMap.probabilities` dict serve?**
   - What we know: Markets configured in Phase 1 are `onextwo`, `btts`, `ou`, `ah`, `corners`. 1X2 has 3 outcomes; BTTS has 2; OU has 2 per line; AH has 2 per line; corners tbd (Phase 6).
   - What's unclear: Do we train ONE ensemble predicting a multi-class 1X2 distribution and derive the other markets via penaltyblog's Dixon-Coles grid, OR do we train separate ensembles per market?
   - Recommendation: Phase 2 trains ONE ensemble per league predicting the **1X2 outcome** (the richest supervised signal). Derive BTTS / OU / AH probabilities from the Dixon-Coles grid using the goal-expectation features. This matches penaltyblog's `FootballProbabilityGrid` output shape and halves the model count. `FootballPlugin.predict(market)` dispatches on market. Corners deferred to Phase 6.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | All code | ✓ | verified via pyproject `requires-python = ">=3.12"` | — |
| uv | Package install | ✓ (per Phase 1 plan completion) | 0.11.x | `pip` if uv unavailable |
| Supabase instance | Shadow-mode writes | ✓ (Phase 1 applied migration 002) | — | Cannot be faked; needed for ML-05 |
| API-Football Pro plan key | Historical seed (D-01) | ✓ (`API_FOOTBALL_KEY` in `.env`) | Pro tier | None — hard dependency |
| The Odds API Rookie key | Closing-odds CLV lookups (already in Phase 1) | ✓ (`ODDS_API_KEY` in `.env`) | Rookie | None — hard dependency |
| `xgboost==3.2.0` wheel | Base model #1 | **UNVERIFIED on target arch** | 3.2.0 | Dependency install step (Wave 0) — macOS arm64 has CPU wheel per PyPI; Linux x86_64 is fine |
| `catboost==1.2.10` wheel | Base model #2 + Polars input | **UNVERIFIED on target arch** | 1.2.10 | CatBoost has been slower to ship macOS arm64 wheels historically — verify at install |
| `lightgbm==4.6.0` wheel | Base model #3 | Likely available (pure-ish) | 4.6.0 | — |
| `penaltyblog==1.9.0` wheel | DC + ELO | Cython build required — may not have universal wheel | 1.9.0 | Build from source if wheel missing (requires C compiler; macOS has one via Xcode) |
| `scikit-learn==1.8.0` | Calibration, stacking, CV | Standard wheel | 1.8.0 | — |
| Disk space for historical Parquet | D-01 seed | — | ~100-500 MB estimated | — |
| Disk space for saved models | Model artifacts | — | ~5 MB per league per version; ~50 MB total over 5 versions | — |

**Missing dependencies with no fallback:** None catastrophic — all libraries have PyPI wheels or can build from source.

**Missing dependencies with fallback:** Libraries listed `UNVERIFIED on target arch` — must run `uv add` in Wave 0 to confirm installation succeeds before planning downstream tasks.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest 9.0.3` + `pytest-asyncio 1.3.0` (Phase 1 already configured) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (existing; add `markers = ["slow"]`) |
| Quick run command | `uv run pytest tests/ -x -q -m "not slow"` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ML-01 | `FootballPlugin.predict()` returns calibrated `ProbabilityMap` with `model_version` sourced from registry | integration | `uv run pytest tests/test_plugin_predict.py -x` | ❌ Wave 0 |
| ML-01 | Ensemble forward pass: XGB + CB + LGB probs → LogReg meta → calibrator produces proper probability vector (sums to 1) | unit | `uv run pytest tests/test_stacking_oof.py::test_ensemble_forward_pass -x` | ❌ Wave 0 |
| ML-02 | Walk-forward CLV uses opening odds × (1 − slippage), NOT closing | unit | `uv run pytest tests/test_backtest_clv.py::test_uses_opening_odds_not_closing -x` | ❌ Wave 0 |
| ML-02 | Temporal integrity: all training dates strictly < test dates per fold | unit | `uv run pytest tests/test_walkforward.py::test_no_future_dates_in_train -x` | ❌ Wave 0 |
| ML-02 | Inner OOF loop generates predictions using only fold's train window | unit | `uv run pytest tests/test_stacking_oof.py::test_oof_temporal_scope -x` | ❌ Wave 0 |
| ML-03 | Calibration selects Platt for <300, Isotonic for >500, Platt for 300-500 | unit | `uv run pytest tests/test_calibration.py::test_method_selection -x` | ❌ Wave 0 |
| ML-03 | `FrozenEstimator` usage — code does NOT import `cv='prefit'` | static/lint | `uv run pytest tests/test_calibration.py::test_uses_frozen_estimator -x` | ❌ Wave 0 |
| ML-03 | Calibration improves logloss (or noop) — regression test on synthetic skewed probs | unit | `uv run pytest tests/test_calibration.py::test_calibration_improves_logloss -x` | ❌ Wave 0 |
| ML-04 | `metadata.json` schema validates via `ModelMetadata` Pydantic model | unit | `uv run pytest tests/test_registry.py::test_metadata_schema -x` | ❌ Wave 0 |
| ML-04 | `feature_set_hash` is deterministic and sensitive to column additions | unit | `uv run pytest tests/test_registry.py::test_feature_set_hash -x` | ❌ Wave 0 |
| ML-04 | Model artifact saves and loads round-trip (predictions identical pre/post joblib dump) | integration | `uv run pytest tests/test_model_loader.py::test_save_load_roundtrip -x` | ❌ Wave 0 |
| ML-04 | `ModelRegistry.promote()` updates `registry.json` atomically | unit | `uv run pytest tests/test_registry.py::test_promote_atomic -x` | ❌ Wave 0 |
| ML-05 | `is_shadow` column exists on `predictions` table (post-migration-003) | manual / integration | Apply migration 003; verify column via `supabase db diff` or direct query | N/A (manual) |
| ML-05 | `PredictionRepository.insert(prediction, is_shadow=True)` writes correct flag | unit (mocked) | `uv run pytest tests/test_repositories.py::test_insert_shadow_prediction -x` | ❌ Wave 0 |
| ML-05 | `FootballPlugin.predict()` dispatches to prod+shadow when registry has both | integration | `uv run pytest tests/test_plugin_predict.py::test_shadow_and_production_paths -x` | ❌ Wave 0 |
| — (architectural) | Features point-in-time correct: rolling form for fixture F uses only matches before F.kickoff_utc | unit | `uv run pytest tests/test_features_rolling.py::test_no_future_match_leakage -x` | ❌ Wave 0 |
| — (architectural) | ELO snapshot for fixture F uses only matches ending before F.computed_at | unit | `uv run pytest tests/test_features_elo.py::test_elo_temporal_snapshot -x` | ❌ Wave 0 |
| — (architectural) | H2H aggregation uses only meetings before F.kickoff_utc | unit | `uv run pytest tests/test_features_h2h.py::test_h2h_temporal -x` | ❌ Wave 0 |
| — (architectural) | Motivation context (top-4, relegation) uses only league-table state before F.kickoff_utc | unit | `uv run pytest tests/test_features_motivation.py::test_motivation_temporal -x` | ❌ Wave 0 |
| — (data) | Seed script checkpoint resumes from interrupted state | unit | `uv run pytest tests/test_seed_checkpoint.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q -m "not slow"` (fast unit tests only, target < 20s)
- **Per wave merge:** `uv run pytest tests/ -v` (includes integration tests, target < 2 min)
- **Phase gate (before `/gsd-verify-work`):** Full suite green AND a manual end-to-end `uv run python -m bip.train fit --league premier_league --version test` produces a `metadata.json` with all required fields

### Wave 0 Gaps
- [ ] `tests/test_features_rolling.py` — rolling form point-in-time
- [ ] `tests/test_features_elo.py` — ELO snapshot correctness
- [ ] `tests/test_features_h2h.py` — H2H temporal correctness
- [ ] `tests/test_features_motivation.py` — motivation context temporal correctness
- [ ] `tests/test_walkforward.py` — walk-forward temporal integrity
- [ ] `tests/test_stacking_oof.py` — nested OOF no-leakage
- [ ] `tests/test_calibration.py` — ML-03 selection rules, FrozenEstimator usage
- [ ] `tests/test_backtest_clv.py` — opening-odds + slippage math
- [ ] `tests/test_registry.py` — registry JSON CRUD + metadata schema
- [ ] `tests/test_model_loader.py` — model round-trip + feature-hash check
- [ ] `tests/test_plugin_predict.py` — `FootballPlugin.predict()` E2E
- [ ] `tests/test_seed_checkpoint.py` — seed-script resume
- [ ] `tests/test_repositories.py` extension — `is_shadow` insert
- [ ] `tests/conftest.py` extension — synthetic training fixtures (small ~50-row dataset with known properties for calibration / backtest tests)
- [ ] Framework config: add `markers = ["slow: mark test as slow (skipped in CI fast-lane)"]` to `[tool.pytest.ini_options]`

### Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Migration 003 applies to live Supabase | ML-05 | Requires live DB connection | Run `supabase db push`; verify `is_shadow` column on `predictions` via `\d predictions` |
| Historical seed completes successfully across all 5 leagues | D-01 | ~20-30 min wall time; not a unit test | Run `uv run python scripts/seed_historical.py`; verify ~5,700 rows in Parquet |
| Full walk-forward run produces sensible CLV (not negative, not too good to be true) | ML-02 | End-to-end smoke test | Run `uv run python -m bip.train fit --league premier_league`; inspect `metadata.json` `walk_forward_mean_clv_pct` — expect small positive, double-digit is suspicious |

---

## Security Domain

> Applicable per the `security_enforcement` default (enabled). This phase is primarily offline training — attack surface is narrow but not zero.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no — no user auth in Phase 2; API keys only | n/a |
| V3 Session Management | no | n/a |
| V4 Access Control | yes — `models/` directory must not be writable by untrusted processes | Restrict `models/` to the user account running training |
| V5 Input Validation | yes — `registry.json` and `metadata.json` loaded from disk must be validated by Pydantic models before use | `ModelMetadata` + `RegistryFile` Pydantic models reject malformed JSON |
| V6 Cryptography | no — no PII, no encryption requirements beyond transport to Supabase (handled by supabase-py over HTTPS) | n/a |

### Known Threat Patterns for ML training pipelines

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Untrusted-artifact deserialization (loading a model artifact from an external source can execute arbitrary code) | Tampering + Elevation of Privilege | **Only load artifacts produced by this same pipeline.** `ModelLoader` accepts only absolute paths under `settings.model_dir` (rooted at project `models/`); never from user-supplied paths, downloads, or tarballs. Recommend ONNX export as a future hardening step. |
| Registry JSON tampering (someone modifies `registry.json` to point production at a broken model) | Tampering | Validate with Pydantic on load; optional checksum of model artifact vs `metadata.json` at load time |
| Secret leakage in `metadata.json` (API keys accidentally serialized) | Information Disclosure | `ModelMetadata` schema has no secret fields; review before save; git hook can scan staged metadata files for patterns like `api_key`, `secret`, `token` |
| Unbounded disk growth (model directory accumulates versions) | Denial of Service | `registry.history` list can inform pruning — Phase 4 scope; document max version retention policy |
| API-Football key in log output during seed run | Information Disclosure | Phase 1 already enforces "never log API key" (T-05-04); maintain in Phase 2 seed script |
| SQL injection via league/version strings | Tampering | All DB writes via `PredictionRepository` which uses supabase-py parameterized queries; do not interpolate league/version directly into SQL |

---

## Sources

### Primary (HIGH confidence)
- **Context7 `/martineastwood/penaltyblog`** — DixonColesGoalModel API, Elo API, FootballProbabilityGrid methods, time-weighted decay (`dixon_coles_weights`), BayesianGoalModel API (not used Phase 2 but referenced).
- **scikit-learn docs** — https://scikit-learn.org/stable/modules/calibration.html (FrozenEstimator replacement for cv='prefit'), https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html (walk-forward CV), https://scikit-learn.org/stable/modules/generated/sklearn.frozen.FrozenEstimator.html, https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.StackingClassifier.html, https://scikit-learn.org/stable/modules/generated/sklearn.isotonic.IsotonicRegression.html.
- **PyPI version verification** (2026-04-22 query): xgboost 3.2.0, catboost 1.2.10, lightgbm 4.6.0, scikit-learn 1.8.0, penaltyblog 1.9.0, typer 0.24.2 — all matched CLAUDE.md pinned versions.
- **Local code read** — `src/bip/sports/football/features.py`, `plugin.py`, `client.py`; `src/bip/core/storage/models.py`, `repositories.py`, `parquet_store.py`; `src/bip/sports/__init__.py`; `src/bip/core/types.py`; `supabase/migrations/20260422000000_add_sport_column.sql`; `pyproject.toml`; `markets.yaml`; `premier_league.yaml`.
- **Phase 1 artifacts** — `01-CONTEXT.md`, `01-RESEARCH.md`, `01-PATTERNS.md`, `01-VALIDATION.md`.

### Secondary (MEDIUM confidence)
- **XGBoost release notes** https://xgboost.readthedocs.io/en/stable/changes/ — 3.0 breaking changes (DeviceQuantileDMatrix removed, `get_params` behavior change). Web search verified against this.
- **CatBoost Polars support** — https://github.com/catboost/catboost/discussions/2699 + v1.2.10 release notes.
- **LightGBM Polars input** — GitHub issues #6204 / #6849 (minor caveats around `feature_names_in_`).
- **Typer subcommand docs** — https://typer.tiangolo.com/tutorial/subcommands/.

### Tertiary (LOW confidence / needs validation)
- Hyperparameter defaults from "football-predictor" — the repo path in CONTEXT.md does NOT exist locally. Claims citing those defaults are downgraded; defaults in this doc are library vendor defaults plus mild regularization.
- General walk-forward fold-count heuristics — "5 outer × 5 inner" is a common pattern but not specifically validated against this dataset size.

---

## Metadata

**Confidence breakdown:**
- Standard stack (versions, APIs): HIGH — all versions verified against PyPI 2026-04-22; Context7 confirmed penaltyblog API.
- Architecture (pipeline structure, file layout): HIGH — derived from Phase 1 conventions + ML-01 through ML-05 requirement wording.
- Pitfalls: HIGH — temporal leakage and cv='prefit' removal are well-documented ecosystem changes; pitfalls 3 (Polars variance) and 6 (opening-odds availability) carry moderate residual uncertainty.
- Hyperparameter defaults: LOW — reference codebase doesn't exist locally; recommended approach is library defaults + feature-importance pass after first training run.
- Opening-odds data source availability: LOW — **needs user verification before seed script is planned in detail (A1)**.

**Research date:** 2026-04-22
**Valid until:** ~2026-05-22 (30 days — stable ML library ecosystem; sklearn 1.9 may ship with further calibration API changes)
