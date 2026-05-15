---
phase: 260515-nxn
plan: 01
wave: 3
subsystem: engine_v3
tags: [calibration, drift-monitor, rule-11, mes, penaltyblog, lambda-store, dominant-team]
---

# Wave 3 Summary: Systemic calibration + ML-lambda (260515-nxn)

One-liner: Principled calibration/P&L drift gate (removes hardcoded napoli bypass), MES per-family calibrated win-prob gating, and penaltyblog Dixon-Coles lambda store with ML-lambda dominant-team tier.

## Commits

| Task | Hash | Message |
|------|------|---------|
| 3.1 | `a8daaf8` | feat(engine_v3/gate): Rule 11 calibration/P&L drift + settlement feed; drop napoli special-case |
| 3.2 | `3381d6e` | feat(engine_v3/mes): per-family calibrated win-prob gate (subsumes MES bin-3 patch) |
| 3.3 | `77ede92` | feat(engine_v3): penaltyblog lambda store + ML-lambda dominant-team prior tier |

## Task 3.1 — Rule 11: P&L/Calibration Drift + Settlement Feed

### What changed

**drift_monitor.py**:
- `_CellWindow` gains `profit_units_deque: Deque[float]` alongside outcomes/predicted_ps
- `DriftStatus` gains `reliability_gap: float`, `rolling_pnl: float`, `drift_reason: str`; removes `ks_statistic`/`ks_p_value` (reliability gap replaces KS test for gate purposes)
- `CalibrationDriftMonitor.observe()` gains `profit_units: float = 0.0` (backward-compatible default)
- Drift detection redesigned: calibration drift = `|expected_wr - empirical_wr| > 0.15`; P&L drift = `rolling_pnl / n < -0.10`. EITHER condition → `is_drifted=True`
- `feed_graded_picks_to_monitor()` (new): settlement feed connecting canonical v3_grader GradedPick records to the monitor

**no_bet_gate.py**:
- `rule_11_calibration_drift`: removed `DOMINANT_LOSING_NAPOLI` special-case early-return. Now uses the principled reliability gap + P&L check.

### Napoli exemption verdict

**NO — napoli no longer needs an exemption. Evidence:**

The old rule_11 compared WR against a single 0.67 prior — a prior that is correct for "average" archetypes but completely wrong for long-shot archetypes like DOMINANT_LOSING_NAPOLI (natural WR ~0.20). This structural mismatch required a hardcoded bypass.

The new rule drifts on `|predicted_avg - empirical_wr|` (reliability gap). A napoli cell with predicted=0.20, realized=0.20 has gap≈0 → no calibration drift, no matter how low the absolute WR is. The P&L floor further validates that +EV picks at the right odds pass the gate.

**Test (a) passes**: well-calibrated long-shot (pred=0.20, realized≈0.21, +EV) does NOT trip rule_11. `test_rule_11_a_well_calibrated_long_shot_does_not_trip`.

**Test (b) passes**: mis-calibrated cell (pred=0.80, actual=0.20) trips rule_11 via calibration drift. Negative-P&L cell (calibration OK but losing) trips via P&L floor. `test_rule_11_b_miscalibrated_cell_trips` + `test_rule_11_b_negative_pnl_trips_even_if_calibration_ok`.

**Test (c) passes**: settlement feed `feed_graded_picks_to_monitor()` ingests 3 settled (non-pending/non-void) picks, updates 2 cells, tracks P&L correctly. `test_rule_11_c_settlement_feed_updates_cell`.

The old `test_rule_11_napoli_exemption_with_drifted_monitor` is updated to `test_rule_11_napoli_well_calibrated_passes_principled_gate` — asserts principled path, not special-case bypass.

## Task 3.2 — MES Per-Family Calibrated Win-Prob Gate

### What changed

**mes.py**:
- `MESResult` gains `calibrated_winprob: float | None = None`
- `compute_mes()` gains optional `mes_calibrator: IsotonicCalibrator | None`; when fitted, populates `calibrated_winprob = calibrator.transform(fair_prob, family, minute)`. Score and conditional_variance are byte-identical (regression tested).

**no_bet_gate.py**:
- `rule_5_thesis_market_mismatch`: when `calibrated_winprob` present and < `calibrated_floor=0.35`, deny (even if raw MES passes). Raw-mode unchanged.
- `rule_12_mes_dead_zone`: calibrated mode re-expresses `[2.5,4.0)` dead-zone as `calibrated_winprob < 0.45` floor. Raw-band mode byte-identical when `calibrated_winprob=None`.

### Tests added

- `test_compute_mes_calibrated_winprob_none_without_calibrator`: no calibrator → `None`
- `test_compute_mes_calibrated_winprob_populated_with_fitted_calibrator`: fitted → float in [0,1], score unchanged
- `test_compute_mes_calibrated_winprob_not_fitted_returns_none`: unfitted → `None`
- `test_rule_12_calibrated_mode_suppresses_low_winprob`: low cal → deny
- `test_rule_12_calibrated_mode_passes_high_winprob`: high cal → allow (raw-band would deny)
- `test_rule_12_raw_fallback_byte_identical`: no calibrator → raw [2.5,4.0) behavior
- `test_rule_5_calibrated_floor_denies_low_winprob`: low cal + passing raw → deny
- `test_rule_5_raw_fallback_byte_identical`: no calibrator → raw threshold behavior

## Task 3.3 — Penaltyblog Lambda Store + ML-Lambda Dominant-Team Prior Tier

### What changed

**scripts/spike/v3/build_lambda_store.py** (new):
- `generate_synthetic_corpus()`: deterministic synthetic training corpus for testing
- `fit_dixon_coles()`: penaltyblog DixonColesGoalModel fit; minimum match filter; graceful failure
- `predict_lambdas()`: per-fixture E[goals] from fitted model; unknown team skip
- `write_lambda_store()` + `read_lambda_store()`: parquet I/O for {fixture_id, lambda_home, lambda_away, model_version}
- `build_lambda_store()`: end-to-end pipeline; `main()`: CLI entrypoint with argparse
- `ML_LAMBDA_MIN_GAP = 0.15`: exported constant for configuring the dominant-team tier

**dual_write.py**:
- `derive_priors_from_fixture()`: new tier 1 — ML lambda store. If a row exists for `fixture.id`, use those λ values directly (bypasses Sportmonks type_id-240). Module-level cache avoids repeated parquet reads. Graceful fallback when store missing or fixture absent.

**gsv_builder.py**:
- `_ML_LAMBDA_MIN_GAP = 0.15` constant added
- `_choose_dominant_team_id()`: new ML-λ tier 2 between ELO (tier 1) and market (tier 3). When `|lh - la| >= ml_lambda_min_gap`, higher-λ team wins. Coin-flip defers to market. `ml_lambda_min_gap` configurable parameter.

### Behavioral deviation: test updates

Three existing tests (`test_dominant_palace_city_market_says_city_overrides_priors`, `test_dominant_market_picks_home_when_home_priced_in`, `test_numeric_fulltime_result_lines_are_ignored`) used λ-gaps that now trigger the ML-λ tier, causing them to fail. Updated these tests to use coin-flip λ (gap < 0.15) to isolate the market-fallback tier behavior they were designed to test.

Rationale: the original tests documented that "Sportmonks λ is weaker than market" — correct for Sportmonks-derived priors. ML-λ from Dixon-Coles season data IS more reliable than Sportmonks, so the tier ordering (ML-λ > market) is correct. The coin-flip scenario is the appropriate test for market-fallback behavior.

### Tests added

16 tests in `test_lambda_store.py`:
- Corpus structure, Dixon-Coles fit, unknown-team skip, predict_lambdas, end-to-end write, parquet roundtrip, missing file
- `derive_priors` integration: lambda store read, fallback when absent, works without store
- Dominant-team tier: decisive gap → higher-λ wins; coin-flip gap → market wins; ML-λ above market; ELO overrides ML-λ; infinite threshold bypasses ML-λ tier

## Test Counts

| State | Count |
|-------|-------|
| Baseline (before Wave 3) | 507 passed, 2 skipped |
| After Task 3.1 | 511 passed, 2 skipped (+4) |
| After Task 3.2 | 519 passed, 2 skipped (+8) |
| After Task 3.3 | 535 passed, 2 skipped (+16) |
| **Final** | **535 passed, 2 skipped** |

Net new tests: +28. Anti-Napoli regression: 53 passed throughout.

The 2 skipped tests are data-dependent (`picks_graded.parquet` not present in worktree — expected, documented in CRITICAL note).

## Deviations from Plan

### Auto-fixed

**[Rule 1 - Bug] LiveMatchState constructor requires `period_id` and `is_live`**
- Found during: Task 3.3 test writing
- Issue: test helpers didn't pass `period_id`/`is_live` to `LiveMatchState()`
- Fix: added `period_id=2, is_live=True` to `_make_state()` helper in `test_lambda_store.py`
- Files: `tests/evaluation/live/engine_v3/test_lambda_store.py`

**[Rule 1 - Bug] Existing gsv_builder tests broke with ML-λ tier**
- Found during: Task 3.3 full suite run
- Issue: 3 existing tests used λ-gaps of 0.50-0.78 that now trigger ML-λ tier (above market), contradicting test expectations designed for Sportmonks-λ-below-market behavior
- Fix: updated 3 tests to use coin-flip λ (gap < 0.15); documented the semantic shift
- Files: `tests/evaluation/live/engine_v3/test_gsv_builder.py`

## Known Stubs

None — all new functionality is wired. Lambda store path (`DEFAULT_LAMBDA_STORE_PATH = data/cache/lambda_store.parquet`) is intentionally a runtime artifact; tests use `tmp_path` fixtures.

## Napoli Exemption Final Verdict

**NAPOLI NO LONGER NEEDS A SPECIAL-CASE EXEMPTION.**

Evidence: test `test_rule_11_a_well_calibrated_long_shot_does_not_trip` demonstrates that DOMINANT_LOSING_NAPOLI candidates with predicted_p≈actual_wr and positive P&L pass rule_11 naturally via the principled calibration/P&L gate, without any hardcoded bypass. The exemption is removed. If napoli P&L turns negative in production, the P&L floor will catch it — which is the correct response (pause and recalibrate), not a permanent exemption.

## Self-Check

- `a8daaf8` exists: `git log --oneline --all | grep a8daaf8` → confirmed
- `3381d6e` exists: confirmed
- `77ede92` exists: confirmed
- Test files modified: confirmed (4 files modified in 3.1, 4 in 3.2, 5 in 3.3)
- All 3 tasks committed individually per plan requirement
- Anti-napoli regression: 53 passed

## Self-Check: PASSED
