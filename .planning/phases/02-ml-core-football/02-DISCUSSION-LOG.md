# Phase 2: ML Core — Football - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-22
**Phase:** 02-ml-core-football
**Areas discussed:** Historical data source, Feature set scope, Ensemble architecture, Model promotion workflow

---

## Historical Data Source

| Option | Description | Selected |
|--------|-------------|----------|
| Hybrid: Supabase → API gap-fill | Migrate Football_analysis Supabase first, then targeted API-Football pull for missing lineups/corners. <1,000 API calls for gap-fill. First training run in ~1 day. | |
| Full API-Football bulk pull | Fetch everything fresh from API-Football across 5 leagues × 3 seasons. ~5,700+ calls, ~20-30 min one-off run. | ✓ |
| Supabase only (no gap-fill) | Use Football_analysis data as-is. Fast but lineups/corners sparse until live ingestion accumulates. | |

**User's choice:** Full API-Football bulk pull
**Notes:** Complete fidelity from day 1; single source of truth for all features including lineups, corners, H2H. Research recommended hybrid as the faster path, but user preferred data completeness.

---

## Feature Set Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal: rolling form + rest + odds | ~6-8 features. Fastest iteration. Proven baseline from prior work. | |
| Medium: form + ELO + H2H + rest + odds | ~15-25 features. All data from Phase 1 API client. Validated signal set. | |
| Full: medium + Dixon-Coles + tactical + motivation | ~40-60 features. Includes penaltyblog Poisson, pressing stats, motivation context. Closest to sharp betting models. | ✓ |

**User's choice:** Full feature set
**Notes:** Research recommended Medium as lower overfitting risk for 5,700 rows, but user wants the full feature set. SHAP/LightGBM feature selection pass included to manage overfitting risk.

---

## Ensemble Architecture

| Option | Description | Selected |
|--------|-------------|----------|
| Weighted average — simplex | Grid-search optimal weights via logloss minimization. No nested CV. Proven in reference code. | |
| LogisticRegression stacking (ML-01 as-spec'd) | Train meta-learner on out-of-fold predictions. Requires nested OOF inside walk-forward. Temporal leakage risk if not implemented precisely. | ✓ |
| Weighted average — Optuna continuous | Same as simplex but Optuna TPE sampler. Marginal improvement, adds Optuna dependency. | |

**User's choice:** LogisticRegression stacking as spec'd in ML-01
**Notes:** Research flagged temporal leakage risk at this dataset size. User confirmed stacking per ML-01 spec. Critical constraint logged: OOF generation must be scoped to each fold's training window — no full-dataset shortcut.

---

## Model Promotion Workflow

| Option | Description | Selected |
|--------|-------------|----------|
| CLI command in Phase 2 | `python -m bip.train promote --league EPL --version v2`. Human reviews CLV before running. Promotion path ready before Phase 3 alerts. | ✓ |
| Defer to Phase 4 | Phase 2 just logs shadow predictions. Promotion logic ships with Production Orchestration. Phase 3 needs ad-hoc file swaps. | |
| Auto-comparison script | Weekly script auto-promotes if CLV threshold met. No human review checkpoint. | |

**User's choice:** CLI command in Phase 2
**Notes:** Account safety priority — human review before every model swap. Gives Phase 3 a clean promotion path before live alerts start.

---

## Claude's Discretion

- Feature engineering pipeline structure within `features.py`
- Hyperparameter grids for base models (use football-predictor defaults)
- Whether ELO/Dixon-Coles are precomputed or per-fold re-fitted (precomputed is acceptable default)
- Exact `metadata.json` schema fields beyond ML-04 minimum

## Deferred Ideas

- Dixon-Coles per-fold re-fitting (more correct, significantly slower — evaluate in iteration pass)
- Optuna-optimized weights (fallback if stacking proves unstable)
- Per-league × per-market calibration (Phase 6 / corners module)
- Auto-promotion script (Phase 4 wraps the CLI command)
