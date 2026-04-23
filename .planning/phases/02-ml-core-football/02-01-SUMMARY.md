---
phase: 02-ml-core-football
plan: 1
subsystem: testing
tags: [pytest, tdd, xgboost, catboost, lightgbm, scikit-learn, penaltyblog, typer]

requires: []
provides:
  - "13 RED-state test stub files covering ML-01 through ML-05"
  - "synthetic_training_data + tmp_model_dir fixtures in tests/conftest.py"
  - "ML dependency declarations in pyproject.toml (pinned versions)"
  - "pytest slow marker configuration"
affects:
  - 02-03-features
  - 02-04-training
  - 02-05-calibration
  - 02-06-pipeline
  - 02-07-predict

tech-stack:
  added:
    - xgboost==3.2.0
    - catboost==1.2.10
    - lightgbm==4.6.0
    - scikit-learn==1.8.0
    - penaltyblog==1.9.0
    - typer==0.24.2
    - joblib>=1.4.0
    - numpy>=2.2,<3
    - scipy>=1.15,<2
  patterns:
    - "TDD RED state: assert False stubs with in-function imports to allow collection before source exists"
    - "Synthetic fixture pattern: seeded numpy rng for deterministic temporal training data"

key-files:
  created:
    - tests/test_walkforward.py
    - tests/test_stacking_oof.py
    - tests/test_calibration.py
    - tests/test_backtest_clv.py
    - tests/test_registry.py
    - tests/test_model_loader.py
    - tests/test_plugin_predict.py
    - tests/test_seed_checkpoint.py
    - tests/test_features_rolling.py
    - tests/test_features_elo.py
    - tests/test_features_h2h.py
    - tests/test_features_motivation.py
  modified:
    - pyproject.toml
    - tests/conftest.py
    - tests/test_repositories.py

key-decisions:
  - "Imports placed inside function bodies — pytest collection passes even when source modules don't exist yet"
  - "All ML libraries pinned to exact versions matching RESEARCH.md to prevent drift"
  - "asyncio_mode = auto means no @pytest.mark.asyncio needed on async test methods"

patterns-established:
  - "RED stub pattern: module docstring cites requirement IDs; assert False with explanatory message"
  - "Temporal correctness contract: every feature/splitter test names the point-in-time invariant explicitly"

requirements-completed:
  - ML-01
  - ML-02
  - ML-03
  - ML-04
  - ML-05

duration: 15min
completed: 2026-04-23
---

# Plan 02-01: Test Infrastructure Summary

**13 TDD test stub files (RED state) + ML dependency declarations — full Nyquist coverage for ML-01 through ML-05 before any implementation**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-04-23
- **Completed:** 2026-04-23
- **Tasks:** 3
- **Files modified:** 15

## Accomplishments
- Added 9 ML libraries (pinned) to pyproject.toml; uv sync installs clean
- Extended conftest.py with `synthetic_training_data` (50-row seeded dataset) and `tmp_model_dir` fixtures
- Created 12 new test stub files + extended test_repositories.py — every ML-01..ML-05 requirement has at least one named test function

## Task Commits

1. **Task 1: ML deps + synthetic fixtures** — `255ce47` (chore)
2. **Task 2: Feature/seed/shadow-repo stubs** — `d7b9f9e` (test)
3. **Task 3: ML pipeline stubs (walkforward, stacking, calibration, backtest, registry, loader, predict)** — `bf4696e` (test)

## Files Created/Modified
- `pyproject.toml` — ML dependencies (xgboost, catboost, lightgbm, sklearn, penaltyblog, typer, joblib, numpy, scipy) + pytest slow marker
- `tests/conftest.py` — `synthetic_training_data` + `tmp_model_dir` fixtures appended
- `tests/test_repositories.py` — `TestPredictionRepositoryShadow` class appended (ML-05)
- `tests/test_walkforward.py` — 3 stubs: temporal integrity invariants (ML-02)
- `tests/test_stacking_oof.py` — 4 stubs: OOF scope, forward pass, base models, meta-learner (ML-01, D-03b)
- `tests/test_calibration.py` — 3 stubs: method selection, FrozenEstimator check, logloss improvement (ML-03)
- `tests/test_backtest_clv.py` — 3 stubs: opening odds, default slippage, null CLV exclusion (ML-02)
- `tests/test_registry.py` — 6 stubs: metadata schema, hash determinism, atomic promote, history (ML-04)
- `tests/test_model_loader.py` — 3 stubs: round-trip, hash gate, path traversal guard (ML-04)
- `tests/test_plugin_predict.py` — 3 async stubs: predict return, model version, shadow path (ML-01, ML-05)
- `tests/test_seed_checkpoint.py` — 2 stubs: resume + atomic write (D-01)
- `tests/test_features_rolling.py` — 3 stubs: no future leakage, windows, home/away split (D-02)
- `tests/test_features_elo.py` — 3 stubs: temporal snapshot, penaltyblog usage, home advantage (D-02)
- `tests/test_features_h2h.py` — 2 stubs: temporal correctness, recency (D-02)
- `tests/test_features_motivation.py` — 2 stubs: table-state temporal, dead rubber flag (D-02)

## Decisions Made
- In-function imports used throughout (not module-level) so `pytest --collect-only` succeeds before source modules exist
- numpy >=2.2,<3 and scipy >=1.15,<2 added as range pins (not exact) — ML libs manage exact versions internally

## Deviations from Plan
One operational deviation: the git sandbox rejected `git add`/`git commit` calls during Task 3 execution (permission model inconsistency in the worktree agent). The 7 Task 3 files were created on disk but not committed by the agent. The orchestrator detected the uncommitted files and committed them directly (`bf4696e`) before worktree merge.

**Impact on plan:** No functional impact — all 13 stubs exist and are committed. All acceptance criteria met.

## Issues Encountered
- Agent git permission issue during Task 3 (sandbox restriction on write commands mid-session). Resolved by orchestrator rescue commit before worktree teardown.

## Next Phase Readiness
- Wave 2 (02-03): `test_features_rolling.py`, `test_features_elo.py`, `test_features_h2h.py`, `test_features_motivation.py` define the GREEN targets for feature engineering
- Wave 3 (02-04): `test_walkforward.py`, `test_stacking_oof.py`, `test_backtest_clv.py` define targets for training pipeline
- Wave 4 (02-05): `test_calibration.py` defines the FrozenEstimator + method selection targets
- Waves 5-6 (02-06, 02-07): `test_registry.py`, `test_model_loader.py`, `test_plugin_predict.py` define end-to-end targets

---
*Phase: 02-ml-core-football*
*Completed: 2026-04-23*
