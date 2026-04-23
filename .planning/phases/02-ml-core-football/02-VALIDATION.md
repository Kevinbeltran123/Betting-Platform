---
phase: 2
slug: ml-core-football
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-22
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 + pytest-asyncio 1.3.0 (Phase 1 already configured) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (existing; add `markers = ["slow"]`) |
| **Quick run command** | `uv run pytest tests/ -x -q -m "not slow"` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~20s (fast unit tests) / ~2 min (full suite) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q -m "not slow"`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green AND manual E2E smoke test (`uv run python -m bip.train fit --league premier_league --version test`) produces a `metadata.json` with all required fields
- **Max feedback latency:** 20 seconds (fast lane)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-??-01 | seed | 1 | D-01 | — | N/A | unit | `uv run pytest tests/test_seed_checkpoint.py -x` | ❌ Wave 0 | ⬜ pending |
| 02-??-02 | features | 1 | DATA-02/D-02 | — | No future match in rolling form | unit | `uv run pytest tests/test_features_rolling.py::test_no_future_match_leakage -x` | ❌ Wave 0 | ⬜ pending |
| 02-??-03 | features | 1 | D-02 | — | ELO snapshot before computed_at | unit | `uv run pytest tests/test_features_elo.py::test_elo_temporal_snapshot -x` | ❌ Wave 0 | ⬜ pending |
| 02-??-04 | features | 1 | D-02 | — | H2H uses only past meetings | unit | `uv run pytest tests/test_features_h2h.py::test_h2h_temporal -x` | ❌ Wave 0 | ⬜ pending |
| 02-??-05 | features | 1 | D-02 | — | Motivation context uses pre-kickoff table state | unit | `uv run pytest tests/test_features_motivation.py::test_motivation_temporal -x` | ❌ Wave 0 | ⬜ pending |
| 02-??-06 | walkforward | 2 | ML-02 | — | All train dates strictly < test dates per fold | unit | `uv run pytest tests/test_walkforward.py::test_no_future_dates_in_train -x` | ❌ Wave 0 | ⬜ pending |
| 02-??-07 | walkforward | 2 | ML-02 | — | Walk-forward CLV uses opening odds + slippage | unit | `uv run pytest tests/test_backtest_clv.py::test_uses_opening_odds_not_closing -x` | ❌ Wave 0 | ⬜ pending |
| 02-??-08 | stacking | 2 | ML-01/D-03b | — | Inner OOF predictions use only fold train window | unit | `uv run pytest tests/test_stacking_oof.py::test_oof_temporal_scope -x` | ❌ Wave 0 | ⬜ pending |
| 02-??-09 | stacking | 2 | ML-01 | — | Ensemble forward pass produces proper probability vector (sums to 1) | unit | `uv run pytest tests/test_stacking_oof.py::test_ensemble_forward_pass -x` | ❌ Wave 0 | ⬜ pending |
| 02-??-10 | calibration | 2 | ML-03 | — | Platt for <300, Isotonic for >500, Platt for 300-500 | unit | `uv run pytest tests/test_calibration.py::test_method_selection -x` | ❌ Wave 0 | ⬜ pending |
| 02-??-11 | calibration | 2 | ML-03 | T-skl-01 | FrozenEstimator used (cv='prefit' removed) | static | `uv run pytest tests/test_calibration.py::test_uses_frozen_estimator -x` | ❌ Wave 0 | ⬜ pending |
| 02-??-12 | calibration | 2 | ML-03 | — | Calibration improves logloss on synthetic skewed probs | unit | `uv run pytest tests/test_calibration.py::test_calibration_improves_logloss -x` | ❌ Wave 0 | ⬜ pending |
| 02-??-13 | registry | 3 | ML-04 | T-reg-01 | ModelMetadata Pydantic schema validates | unit | `uv run pytest tests/test_registry.py::test_metadata_schema -x` | ❌ Wave 0 | ⬜ pending |
| 02-??-14 | registry | 3 | ML-04 | — | Feature set hash is deterministic | unit | `uv run pytest tests/test_registry.py::test_feature_set_hash -x` | ❌ Wave 0 | ⬜ pending |
| 02-??-15 | registry | 3 | ML-04 | T-reg-01 | ModelRegistry.promote() updates registry.json atomically | unit | `uv run pytest tests/test_registry.py::test_promote_atomic -x` | ❌ Wave 0 | ⬜ pending |
| 02-??-16 | loader | 3 | ML-04 | T-art-01 | Model save/load round-trip (identical predictions) | integration | `uv run pytest tests/test_model_loader.py::test_save_load_roundtrip -x` | ❌ Wave 0 | ⬜ pending |
| 02-??-17 | shadow | 3 | ML-05 | — | PredictionRepository.insert(is_shadow=True) writes correct flag | unit (mocked) | `uv run pytest tests/test_repositories.py::test_insert_shadow_prediction -x` | ❌ Wave 0 | ⬜ pending |
| 02-??-18 | predict | 3 | ML-01/ML-05 | — | FootballPlugin.predict() returns calibrated ProbabilityMap with model_version | integration | `uv run pytest tests/test_plugin_predict.py -x` | ❌ Wave 0 | ⬜ pending |
| 02-??-19 | predict | 3 | ML-05 | — | FootballPlugin.predict() dispatches to prod+shadow when registry has both | integration | `uv run pytest tests/test_plugin_predict.py::test_shadow_and_production_paths -x` | ❌ Wave 0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_features_rolling.py` — rolling form point-in-time leakage
- [ ] `tests/test_features_elo.py` — ELO snapshot correctness
- [ ] `tests/test_features_h2h.py` — H2H temporal correctness
- [ ] `tests/test_features_motivation.py` — motivation context temporal correctness
- [ ] `tests/test_walkforward.py` — walk-forward temporal integrity
- [ ] `tests/test_stacking_oof.py` — nested OOF no-leakage + forward pass
- [ ] `tests/test_calibration.py` — ML-03 selection rules, FrozenEstimator usage
- [ ] `tests/test_backtest_clv.py` — opening-odds + slippage math
- [ ] `tests/test_registry.py` — registry JSON CRUD + metadata schema
- [ ] `tests/test_model_loader.py` — model round-trip + feature-hash check
- [ ] `tests/test_plugin_predict.py` — FootballPlugin.predict() E2E + shadow path
- [ ] `tests/test_seed_checkpoint.py` — seed script checkpoint resume
- [ ] `tests/test_repositories.py` extension — is_shadow insert
- [ ] `tests/conftest.py` extension — synthetic training fixtures (small ~50-row dataset with known properties for calibration / backtest tests)
- [ ] Framework config: add `markers = ["slow: mark test as slow (skipped in CI fast-lane)"]` to `[tool.pytest.ini_options]` in `pyproject.toml`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Migration 003 applies to live Supabase (is_shadow column added) | ML-05 | Requires live DB connection | Run `supabase db push`; verify `is_shadow` column on `predictions` via `\d predictions` |
| Historical seed completes across all 5 leagues | D-01 | ~20-30 min wall time; not suitable as unit test | Run `uv run python scripts/seed_historical.py`; verify ~5,700 rows in Parquet |
| Full walk-forward run produces sensible CLV | ML-02 | End-to-end smoke test with real data | Run `uv run python -m bip.train fit --league premier_league`; inspect `metadata.json` `walk_forward_mean_clv_pct` — small positive expected; double-digit is suspicious |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s (fast lane)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
