---
spike: wc2026-calibration-lock
slug: wc2026-calibration-lock
status: phase-4-next
created: 2026-05-08
last_updated: 2026-05-08
operator: Kevin Beltrán
branch: spike/national-team-tournament-evaluator
companion_to: SPIKE-tournament-evaluator.md
hard_deadline: 2026-06-08
graduates_to: TBD (calibrated predictors merged into evaluator output OR Phase 6 v1.0 corners module)
tests_passing: 660
tests_xfail: 7
commits_on_branch: 12
---

# Spike — WC2026 Calibration Lock

> **Side-track experimental, prerequisite for tournament-evaluator Phase 5 lock.** Lives under `.planning/spikes/` alongside `SPIKE-tournament-evaluator.md`. Two-pronged: the 4 phases below run on the spike branch; production-side calibration extensions (SysID devig, NB corners, Cemek covariates) fold into v1.0 ROADMAP Phase 6 when that phase activates.

> **READ FIRST: [Papers/SYNTHESIS.md](../../Papers/SYNTHESIS.md).** Single source of truth for the 7 cross-cutting findings, full 8-phase reasoning (4 active here + 4 deferred), and the 16 What-NOT-to-Build entries. Every phase below has a one-line summary; the *why* lives in SYNTHESIS.md. Update SYNTHESIS.md when research evolves; this spike doc only tracks execution.

> **Working pattern: structure-first, validate-with-data-later.** Every phase ships scaffolding tested against mocks/synthetic data, then queues the real-data validation as `xfail`/`skip` with a tracking note. This keeps the spike branch shippable on the structural side while data is being collected. Inherited from v1.0 Phase 03 pattern (`mock_anthropic_client` + `mock_telegram_bot`).

## 0. Goal

Bring the tournament-evaluator predictors (`BivariatePoisson`, `IndependentPoisson`, `EloLogistic`, `corners_poisson`, `BayesianUpdater`) to **production-grade calibration quality** before the WC2026 locked-predictions deadline on **2026-06-08**, validated against historical international tournaments (WC 2018, Euro 2016, Euro 2024, Copa América 2024).

Driven by a 7-domain research synthesis across: Bayesian team strength, ML calibration, corners prediction, deep-learning vs Poisson, Dixon-Coles extensions, club→national-team transfer, and player-action valuation. Notes in `Papers/`.

## 1. Output

For each predictor in `src/bip/evaluation/tournaments/predictors/` and `src/bip/evaluation/tournaments/live/`:

- **Per-class calibration metrics** (Win/Draw/Lose, Over/Under) with classwise-ECE (20 bins, 80% bin-fill constraint per Walsh & Joshi 2024), Brier, LogLoss
- **Calibrated probability outputs** via `LogisticLogitCalibrator` (replacing isotonic per Ojeda 2023 covariate-shift evidence)
- **Two-timescale Bayesian updater** with separate β_w (within-tournament), β_s (between FIFA windows), and in-game (Gamma-Poisson) update mechanisms
- **League-strength-normalized** per-90 player rates feeding `BlendedRates` (Shelopugin 2023 lookup table)
- **Pre-lock backtest report** with hard quantitative gates: classwise-ECE ≤ 5% AND Brier ≤ 0.21 (1X2) AND ≤ 0.20 (corners O/U)

Output format: `tests/evaluation/test_calibration_baseline.py` + `CalibrationReport` Pydantic model committed alongside locked predictions.

## 2. Architecture (extends existing `evaluation/` module)

Files added (NEW — Phase 0.5, commit f9ce4e5):
```
src/bip/data/
├── __init__.py                             # DONE — cross-sport open-data package
└── understat_client.py                     # DONE — UnderstatClient + TeamFormFeatures (5-dim form vector)

tests/data/
├── __init__.py                             # DONE
└── test_understat_client.py                # DONE — 31 tests + 2 xfail Layer-2
```

Files added (NEW — Phase 1, commit 94e63fc):
```
src/bip/evaluation/tournaments/backtest/
├── calibration_metrics.py                  # DONE — bin_fill_check, classwise_ece, per_class_reliability
├── calibration_report.py                   # DONE — CalibrationReport Pydantic model + gate_status()
└── calibration_audit.py                    # DONE — CalibrationAudit accumulator harness

tests/evaluation/
└── test_calibration_baseline.py            # DONE — 27 tests + 2 xfail Layer-2
```

Files added (NEW — Phase 2, commit 234c54e):
```
src/bip/evaluation/tournaments/calibration/
├── __init__.py                             # DONE — exports LogisticLogitCalibrator, _IsotonicCalibrator
└── logit_calibrator.py                     # DONE — p_cal = σ(α+β·logit(p_raw)); binary+multiclass; persistence

tests/evaluation/
└── test_logit_calibrator.py                # DONE — 20 tests + 2 xfail Layer-2
```

Files added (NEW — Phase 3, this commit):
```
src/bip/evaluation/tournaments/live/
├── bayesian_updater.py                     # DONE — split into 3 timescale methods + sigma_s_per_day param
├── competition_weights.py                  # DONE — CompetitionType enum + DEFAULT_WEIGHTS (WC=4×, qual=2×, friendly=1×, etc.)
└── state.py                                # MODIFIED — explicit prior_var_* per metric + obs_weight_total + n_prior_eff_* properties

scripts/
└── seed_international_history.py           # DONE — Layer-1 σ_s sweep harness (Held criterion C); CLI gated # requires-real-data

tests/evaluation/
└── test_bayesian_updater.py                # +22 tests (between_window decay, competition weighting, within_match Gamma-Poisson, JSON BC)

tests/scripts/
└── test_seed_international_history.py      # +7 tests (calibrator on synthetic data + 1 xfail Layer-2 real-data run)
```

Files to add (NEW — Phase 4+):
```
src/bip/evaluation/tournaments/
└── data/
    └── league_strength.py                  # EXISTS — extend with Shelopugin Table V/VI seed values (Phase 4)
```

Files to modify (EXTEND, no breaking changes):
```
src/bip/evaluation/tournaments/
├── live/
│   └── bayesian_updater.py                 # SPLIT: between_window_step + within_tournament_step
├── data/
│   └── club_form_loader.py                 # ADD league_strength_adjustment per player
└── predict/
    └── blender.py                          # CONSUME league_strength_adjustment in CompositionBlender

scripts/
└── seed_international_history.py           # NEW — pull 2010–2024 int. tournament results for σ_s calibration
```

**Why extend, not replace:** the spike branch ships predictors that are code-complete and tested (505 tests pass). The calibration work adds layers; the predictors stay where they are.

## 3. Discovery findings (Phase 0 output)

### 3.1 Existing predictors and their current calibration state (UNKNOWN — Phase 1 measures it)

| Predictor | File | Current calibrator | What's known |
|---|---|---|---|
| `BivariatePoisson` | `predictors/bivariate_poisson.py` | None / penaltyblog raw | Maozad (2022): D&C Poisson AIC=32056 EPL — best of Poisson family but never tested for calibration |
| `IndependentPoisson` | `predictors/independent_poisson.py` | None | baseline — Macrì-Demartino: nunca el mejor |
| `EloLogistic` | `predictors/elo_logistic.py` | None | Maystre 2016: Elo unstable across tournaments (Euro 2008 → 2012 collapse) |
| `corners_poisson` | `predictors/corners_poisson.py` | None | Yip (2022): Poisson D=1.10–1.25 systematically underestimates O/U 11.5+ tail |
| `BayesianUpdater` | `live/bayesian_updater.py` | n/a | Mixes between-window + within-match in one mechanism — Glickman & Stern argue these are different timescales |

### 3.2 Research grounding (Papers/ directory)

7 domains, 20 notes synthesized. Key empirical anchors that inform deadlines and acceptance criteria:

- **Walsh & Joshi 2024** — accuracy-selected NBA model went +37%→−76% ROI; selecting by classwise-ECE saved $11k. Calibration not optional.
- **Ojeda 2023** — Beta/Logistic calibrators robust under covariate shift in 23/23 simulation scenarios; isotonic fails when train/val distributions differ. Club→national-team is by definition shifted.
- **Karimov SysID 2025** — naïve 1/odds devig has ~12,000× the bias of multi-market joint optimization. The "+3% CLV" target is uninterpretable without proper devig. **Phase 5 of synthesis — defers to v1.0 Phase 6.**
- **Yip 2022** — corners are overdispersed (D=1.10–1.25 across all top-5 leagues); NB beats Poisson by 0.7%–1% profit on O/U markets. **Phase 6/7 of synthesis — defers to v1.0 Phase 6.**
- **Held & Vollnhals 2005** — competition-weighted Kalman with σ²=0.023 optimal for league but national-team gaps require recalibration via criterion C on real data.
- **Shelopugin 2023** — Premier League rating 2118 vs Brazil First 1868 (+250 pts gap) means per-90 rates from different leagues are not commensurable without normalization.
- **Glickman & Stern 1998** — week-to-week (β_w=0.99, σ_w=0.88) and season-to-season (β_s=0.82, σ_s=2.35) require separate update mechanisms.

### 3.3 Decisions confirmed with operator (2026-05-08)

- **Critical-path order**: Full chain — Phases 1→2→3→4 ship, accepting slip risk on the 2026-06-08 lock. Checkpoint at end of Phase 3 (2026-05-22); if behind, drop Phase 4.
- **Lock criteria**: Hard quantitative gates — classwise-ECE ≤ 5% AND Brier ≤ 0.21 (1X2) AND ≤ 0.20 (corners O/U) on historical int. tournament backtest. Misses gate → lock blocked, fix and retry.
- **σ_s strategy**: Held's criterion C on 2010–2024 international results (correct path; +1 day vs heuristic).

### 3.4 What this spike does NOT cover (folds into v1.0 Phase 6)

The synthesis identified 8 phases. This spike scopes **only the 4 directly relevant to the WC2026 lock on the spike branch**. The remaining 4 are corners-market and CLV-infrastructure work that belongs in v1.0 Phase 6 (Timed Corners Module) when that phase activates:

| Synthesis phase | Why deferred to v1.0 Phase 6 |
|---|---|
| **5. SysID multi-market devigging** | Production CLV measurement, not tournament-evaluator. Phase 6 will need it for corner picks; insert there. |
| **6. Corners → Negative Binomial** | Phase 6 builds the production corners model from scratch — it's the natural home for NB marginals + Yip's 3-match rolling form features. The spike's `corners_poisson.py` stays as-is for the lock. |
| **7. Cemek tactical-context features** | Same — Phase 6 production corners model. |
| **8. Pre-lock WC2026 backtest** | Replaced by spike Phase 4's int. tournament backtest. The "lock" here is the spike-branch lock at 2026-06-08, not a production-pipeline lock. |

## 4. Phase plan

| # | Phase | Hours | Hard deadline | Status | Commit |
|---|---|---|---|---|---|
| 0 | Discovery (this doc + SYNTHESIS.md) | ~3h | 2026-05-08 | ✅ COMPLETE | `653ac8f` |
| 0.5 | Understat xG client + TeamFormFeatures | ~4h | pre-Phase 1 | ✅ COMPLETE | `f9ce4e5` |
| 1 | Calibration baseline audit (classwise-ECE infra + measure existing predictors) | ~6h | 2026-05-12 | ✅ COMPLETE | `94e63fc` |
| 2 | Replace isotonic with `LogisticLogitCalibrator` (Ojeda Step 3) | ~6h | 2026-05-15 | ✅ COMPLETE | `234c54e` |
| 3 | Two-timescale `BayesianUpdater` refactor + σ_s calibration via Held criterion C on 2010–2024 int. results | ~16h | 2026-05-22 *(checkpoint)* | ✅ Layer-1 COMPLETE | _pending_ |
| 4 | League-strength normalization layer (Shelopugin Table V/VI seed + `CompositionBlender` wiring) | ~12h | 2026-05-29 | ⏳ **NEXT** | — |
| 5 | Pre-lock backtest on WC 2018, Euro 2024, Copa 2024 + gate verification | ~12h | 2026-06-05 | ⏳ pending | — |
| 6 | LOCK — locked tournament-evaluator predictions for WC2026 (commits to `locked_predictions/`) | ~3h | **2026-06-08 HARD** | ⏳ pending | — |

### Per-phase structure-first deliverables

Each phase ships in two layers. Layer 1 (structural) MUST close before the deadline; Layer 2 (data validation) fires when data lands.

| Phase | Layer 1 — Structure (always ships) | Layer 2 — Data validation (queued) | SYNTHESIS.md anchor | Status |
|---|---|---|---|---|
| 0.5 | `UnderstatClient` + `TeamFormFeatures` (5-dim: volume/recency/venue/variance/quality) + 31 tests | Backfill xG top-5 EU 2020/21–2025/26 to parquet; consume in corners_poisson as `xg_total_l5` covariate | — | ✅ commit `f9ce4e5` |
| 1 | `CalibrationReport` Pydantic model + `classwise_ece`/`bin_fill_check` + `CalibrationAudit` harness + `gate_status()` + 27 tests | Audit run on real walk-forward backtest output | Conclusions 1, 4, 6 | ✅ commit `94e63fc` |
| 2 | `LogisticLogitCalibrator` (fit p_cal=σ(α+β·logit(p_raw)) per class via L-BFGS-B MLE; binary + multiclass; identity fallback for n<50; persistence) + `_IsotonicCalibrator` shim + 20 tests | Side-by-side vs isotonic on real validation set (Phase 5 backtest) | Conclusion 1 | ✅ commit `234c54e` |
| 3 | `BayesianUpdater.between_window_step()` + `within_tournament_step()` + `within_match_step()` (Gamma-Poisson) with synthetic state tests; `scripts/seed_international_history.py` skeleton + parquet schema | σ_s sweep via Held criterion C on real 2010–2024 fixtures (queued) | Conclusions 5, 7 | ✅ Layer-1 COMPLETE — 29 tests + 1 xfail Layer-2 |
| 4 | League-strength lookup table (Shelopugin Table V/VI YAML) + `apply_league_adjustment()` + parametric tests covering Premier-2118 → Brazil-1868 case + `CompositionBlender` consumption with mock rates | Full E2E swap-in once `ClubFormLoader` returns real per-league data | Conclusion 3 | ⏳ pending |
| 5 | Backtest harness + gate-evaluation script with synthetic `CalibrationReport` fixtures verifying gate logic (ECE/Brier thresholds correctly fail/pass mock data) | Real run on WC 2018 / Euro 2024 / Copa 2024 historical fixtures | Conclusions 1, 2 | ⏳ pending |
| 6 | Lock JSON schema + emitter writing to `locked_predictions/` with `calibration_status` field (`pass` / `marginal` / `below-gate` / `coverage-partial`) | Operator runs the full pipeline against WC2026 fixtures and commits the JSON | n/a | ⏳ pending |

**Result if data does not arrive in time:** Layer 1 ships for all 6 phases. The spike branch is structurally complete. The lock JSON ships with `calibration_status: "structural-only"` and all queued Layer-2 validations remain `xfail` with `# requires-real-data` markers. Post-tournament scoring still grades the predictions honestly because the predictors themselves are unchanged.

### Optional / parallel phases (added 2026-05-08 from data-sources audit)

These phases were unblocked by re-evaluating data-source rejections (`Papers/DATA_SOURCES_AUDIT.md`). They are **outside the WC2026 lock critical path** — they don't gate the 2026-06-08 deadline — but each one materially improves calibration when included. Operator approved all three on 2026-05-08.

| # | Phase | Hours | Position vs critical path | Layer 1 deliverable | Layer 2 (queued) |
|---|---|---|---|---|---|
| 0.5 | Understat xG client (quick win) | ~4h | Before Phase 1 OR parallel with Phase 1 | ✅ COMPLETE — `src/bip/data/understat_client.py` + `TeamFormFeatures` (5-dim) + 31 tests | Layer-2 xfail: backfill xG top-5 EU 2020/21–2025/26 to parquet; consume in `corners_poisson` as `xg_total_l5` covariate |
| 4.5 | Betfair Delayed API CLV reference | ~3h | Parallel with Phase 4 (no dependency on Phases 1-4) | ⏳ pending | `src/bip/data/betfair_client.py` wrapping `betfairlightweight` (Delayed Key, free with funded account) + tests |
| 7 | Offline shot-quality model from PFF FC + StatsBomb 360 | ~12-16h | Parallel with Phase 5; could run post-lock | ⏳ pending | `scripts/train_shot_quality.py` consuming `kloppy.pff` + `statsbombpy`; LightGBM xG on tracking-derived features |

**Phase 0.5 shipped** (commit `f9ce4e5`). Next quick win is Phase 4.5 (Betfair CLV reference) once a funded Betfair account and Delayed App Key are confirmed.

**Phase 4.5 requires:** funded Betfair account + applying for Delayed App Key (free, ~24h approval). Operator action item: confirm Betfair account exists.

**Phase 7 requires:** form registration at PFF FC (free, fchelp@pff.com confirms 2026 license). Operator action item: register and verify license terms permit derived features in a betting tool.

**Reframings from the audit (no new phase, just updates):**

- "Live in-play tick events" → not a feature gap. The existing `BayesianUpdater` consumes post-match aggregates from API-Football's `/fixtures/statistics` (already paid). The structural code is ready; just needs invocation with post-match data after each WC2026 fixture.
- "FBref scraping" → gray-area fallback only. Use `soccerdata.FBref` as backup when Understat doesn't cover a needed market. Not a planned phase.
- "Pinnacle direct API" → closed 2025-07-23. Phase 4.5 (Betfair Delayed) is the recommended replacement; The Odds API website-scrape continues as primary.

**WC2026 kickoff:** 2026-06-11. Lock by 2026-06-08 gives 3 days of review and prevents opening-odds influence.

**Slip plan (operator-approved):**
- If at end of Phase 3 (2026-05-22) the σ_s calibration data is not loaded or convergence fails → drop Phase 4 (league strength) entirely. Phase 4 improvement is incremental; Phases 1-3 are necessary for any calibration claim.
- If Phase 5 backtest misses the hard gates → 2-day remediation window built in (lock would shift from 2026-06-06 target to 2026-06-08 hard limit).
- If the lock cannot pass gates by 2026-06-08 → lock the predictions anyway with explicit `calibration_status: "below-gate"` flag in the JSON. Tournament-evaluator Phase 5 still ships; post-Mundial scoring grades them honestly.

## 5. Risks

| ID | Risk | Mitigation |
|---|---|---|
| R-01 | International tournament results 2010–2024 not in `qualifying_loader.py` schema; loading takes >1 day | Phase 3 first task is `scripts/seed_international_history.py` — keep it bounded to <300 LOC, single-pass pull, parquet cache. If API-Football coverage gaps for AFCON / pre-2018 Euro, accept reduced σ_s sample (>500 matches enough). |
| R-02 | Held's criterion C requires multi-iteration EKF over historical data; CPU-only inference budget tight | The criterion C optimization is offline, NOT inference. EKF runtime per σ_s candidate ~30s on 5,000 matches; sweeping 20 candidates = 10 minutes. Acceptable. |
| R-03 | `LogisticLogitCalibrator` can fail on classes with very few examples (e.g., draws on small national-team validation set) | Fallback rule: if any class has n<50 in calibration set, use Logistic (2 parameters) over Beta (3). Document the cutoff in the calibrator code. |
| R-04 | League-strength multipliers from Shelopugin (2023) data are 2.5 years stale by WC2026 | Shelopugin's relative ranking is more stable than absolute values. The Premier-2118 vs Brazil-1868 gap of ~250 pts has not closed materially since 2023. Document as known limitation; revisit post-tournament. |
| R-05 | Replacing isotonic in `_IsotonicCalibrator` breaks tests in `test_calibration*.py` (existing) | Phase 2 keeps `_IsotonicCalibrator` symbol with a deprecation warning that delegates to the new logistic calibrator. Tests pass with no changes; callers migrate explicitly when they update imports. |
| R-06 | Backtest on historical tournaments shows the calibrators improve ECE but Brier *worsens* (overfitting calibration set) | Phase 5 includes a held-out gate: 20% of int. tournament fixtures used as final test. If gate fails on held-out, revert calibrator and ship raw probabilities for the lock. |
| R-07 | The 31-day window assumes 4-6 hours/day operator availability; real availability lower | The plan totals 58 hours; with 4h/day that's 14.5 days of pure work, leaving ~16 days slack. Sufficient buffer for one full re-do of any phase. |
| R-08 | Calibration improvements are real but small (Brier delta < 0.005) and gates are missed by 0.001-0.01 | Build gate-evaluation script to surface per-tournament breakdown; if Brier failure is driven by 1-2 outlier tournaments (Iceland 2016 surprise), document and proceed. Hard gate is total-set, not worst-case-tournament. |

## 6. Out of scope (explicit non-goals)

- **Production CLV pipeline changes**: this spike does NOT modify `bip.clv` or `OddsApiClient`. SysID devig and CLV-against-Pinnacle work is v1.0 Phase 6 territory.
- **PARX (Angelini 2017)**: synthesis Phase 9 (post-WC) — autoregressive goal-rate evolution. Not in 31-day window.
- **Sarmanov NB / ANS for goals (Michels 2025)**: synthesis Phase 10 (post-WC) — full goal-distribution rewrite. Not in 31-day window.
- **xT / I-VAEP features (Van Roy 2020, Mendes-Neves 2022)**: synthesis Phase 11–12 (post-WC) — requires `socceraction` integration. Not in 31-day window.
- **HIGFormer-style two-stage training**: synthesis Phase 12 (post-WC) — requires player graph data the project doesn't have. Not in any plan.
- **Off-ball / OBPI / MARL Q-values**: rejected entirely (require positional tracking; project has only event data per CLAUDE.md).
- **Spike-and-slab Bayesian model (Macrì-Demartino 2025)**: rejected (requires Stan + MCMC; violates 500ms inference budget; weighted Kalman captures ~90% of the value).

## 7. Success criteria

For Phase 6 (LOCK to be valuable):

- **Coverage**: ≥90% of WC2026 group-stage matches (104 matches) have calibrated predictions for goals + corners + W/D/L from at least 1 of the 3 predictors.
- **Calibration gates** (held-out 20% of historical int. tournaments):
  - classwise-ECE ≤ 5% across W/D/L
  - Brier ≤ 0.21 for 1X2
  - Brier ≤ 0.20 for corners O/U
- **Honest gap reporting**: any predictor that misses the gate is flagged in the lock JSON with `calibration_status: "below-gate"` and the per-class ECE/Brier values surfaced.

For graduation to v1.0 Phase 6 (post-WC decision):

- If `LogisticLogitCalibrator` measurably improves ECE on production-pipeline backtests (Phase 1 pipeline, not spike), it migrates into `bip.train` as the default calibrator.
- If the two-timescale `BayesianUpdater` is used by Phase 5 (Claude Confidence Modifier shadow), the refactored module migrates to `bip.core.bayesian` for production use.
- League-strength normalization is post-WC v1.0 Phase 6 work and migrates into the production feature engineer if backtest shows >2% CLV improvement.

## 8. Decisions log (this spike)

| Date | Decision | Reason |
|---|---|---|
| 2026-05-08 | Spike-companion doc structure (mirror `SPIKE-tournament-evaluator.md`) instead of new `/gsd-new-milestone` | v1.0 milestone is 84% complete and in-flight; `state.milestone-switch` would corrupt phase tracking on Phases 3–7 |
| 2026-05-08 | `TeamFormFeatures` is a 5-dimensional dataclass (volume/recency/venue/variance/quality), not a scalar | A scalar conflates a team in form with a lucky one; 5 dimensions match what a downstream model needs to distinguish form quality from volume |
| 2026-05-08 | `_reader_factory` DI pattern on `UnderstatClient` instead of monkeypatching soccerdata at import | Keeps tests import-safe and doesn't require mocking at module level; compatible with `pytest-httpx` approach used in rest of codebase |
| 2026-05-08 | `bin_fill_passes=False` does NOT block gate when `brier_for_gate ≥ 2 × gate_brier_max` (catastrophic escape hatch) | Single-bin overconfident predictions fail bin-fill but the failure is obvious from Brier alone; returning `unreliable-bins` would hide a clear failure signal |
| 2026-05-08 | `brier_for_gate` normalizes multiclass Brier by K (number of classes) | `multiclass_brier_score()` returns sum over K (range [0,K]); gate ceilings 0.21/0.20 are per-class-averaged scale per Walsh & Joshi 2024 |
| 2026-05-08 | Tests for Phase 1 use `min_bin_fill=0.5` for football-shaped synthetic probs | Football probabilities concentrate at 0.50–0.70, filling only 5–6 of 20 bins; the 0.8 real threshold stays in production code; Phase 5 backtest will determine the right empirical value for football |
| 2026-05-08 | 4 phases on spike branch + 4 phases deferred to v1.0 Phase 6 | Synthesis Phases 5–8 are production-pipeline + corners-market work; they belong in v1.0 Phase 6 (Timed Corners Module) when that phase activates |
| 2026-05-08 | Critical-path order = Full chain with slip-risk acceptance | Operator preference; checkpoint at end of Phase 3 (2026-05-22) provides early warning |
| 2026-05-08 | Hard quantitative gates over soft review | Operator preference; classwise-ECE ≤ 5% / Brier ≤ 0.21 (1X2) / ≤ 0.20 (corners O/U) |
| 2026-05-08 | σ_s via Held's criterion C on 2010–2024 int. results, NOT heuristic | Operator preference; +1 day cost is acceptable for correct calibration |
| 2026-05-08 | Logistic-on-logit replaces isotonic as default calibrator | Ojeda 2023 Scenarios 16–23: isotonic fails systematically under covariate shift; club→national-team is by definition a shifted distribution |
| 2026-05-08 | `BayesianUpdater` split into between-window + within-tournament + in-match steps | Glickman & Stern 1998 + Held 2005 + Zou 2020 each operate on a different timescale; one mechanism cannot serve all three |
| 2026-05-08 | Phase 3 decay model = Held log-rate random walk (not exponential effective-sample-size decay) | Operator chose the realist over the easy path. Δvar = days · σ_s² · μ² makes σ_s dimensionless ("fractional volatility per day"), so a single value works across goals/corners/shots scales. Backward-compat preserved via `n_prior_eff = mean / var` derivation that recovers pre-Phase-3 blend at default initialization |
| 2026-05-08 | `competition_weight` scales obs but not n_matches_played | Bayesian evidence (obs_weight_total) reflects Held weighting (WC = 4× evidence units) while match-count semantics for player-events / minutes-bookkeeping stay literal. Two counters with different physical meanings |
| 2026-05-08 | `_blend()` formula stays intact; n_prior_eff derived per-metric on demand | Avoids breaking 14 legacy bayesian_updater tests + the 631-test suite. Variance-driven shrinkage emerges naturally from the property derivation rather than a formula rewrite |
| 2026-05-08 | League-strength multipliers seeded from Shelopugin (2023) Table V/VI lookup | Premier-2118 vs Brazil-1868 (~250 pt gap) is empirically validated and stable; rebuilding the rating system is out of scope |
| 2026-05-08 | Synthesis Phases 5–8 (SysID, NB corners, Cemek, prod backtest) deferred to v1.0 Phase 6 | Two-pronged placement decision; keeps spike scope minimal and respects v1.0 roadmap integrity |

## 9. Open questions for the operator (Learning-Mode contributions)

These are points where operator domain input shapes the model — collect during Phases 1-4:

1. **Competition-weight values** (Phase 3): the synthesis suggested WC=4×, Conf cup=3×, qualifier=2×, friendly=1×, non-FIFA=0.5×. Are these ratios correct for **your** view of how informative each match type is? ~6 lines of YAML.
2. **σ_s sweep range** (Phase 3): Held used 0.005–0.05 for league football. National-team gaps suggest 0.02–0.20 is the right range, but the optimum within that is empirical. Your prior on what value "feels right" anchors the sweep.
3. **Held-out tournament selection** (Phase 5): which 20% of historical int. tournaments hold out for final gate? Recommend the 2 most recent (Copa 2024 + Euro 2024) — they're closest in style to WC2026. Operator confirms.
4. **Below-gate ship decision** (Phase 6): if classwise-ECE is 5.3% (just over gate) but Brier passes, do we lock with `calibration_status: "marginal"` or block? Operator policy.
5. **WC2026 host-advantage handling** (Phase 4): USA/Mexico/Canada matches at home venues. Held's per-team `α_i` requires team-specific HFA. With no recent home-venue WC matches for these teams, what's the prior? Operator domain knowledge.

## 10. References

- `Papers/BayessianTeamStrength /NOTAS_2508.05891v1.md` — Bayesian weighted dynamic models (Macrì-Demartino, rejected for inference budget)
- `Papers/BayessianTeamStrength /NOTAS_held2005.md` — Held & Vollnhals weighted Kalman (foundation of Phase 3)
- `Papers/BayessianTeamStrength /glickman1998_insights.md` — Two-timescale state-space model (β_w / β_s split)
- `Papers/CalibratingML_Predictions/NOTAS_1-s2.0-S266682702400015X.md` — Walsh & Joshi classwise-ECE (Phase 1 metric)
- `Papers/CalibratingML_Predictions/NOTAS_ojeda2023_calibracion_ml.md` — Ojeda 2023 calibrator comparison (Phase 2 method)
- `Papers/CalibratingML_Predictions/NOTES_mathematics-13-03976.md` — Karimov SysID devig (Phase 5 — deferred)
- `Papers/Corners-Prediction/NOTAS_e1875399X347646.md` — Cemek tactical context (Phase 7 — deferred)
- `Papers/Corners-Prediction/yip2022_corners_overdispersion.md` — Yip NB corners (Phase 6 — deferred)
- `Papers/TransferPlayerClubStatistics_toNationalTeam/NOTAS_2310.11459v1.md` — Shelopugin league strength (Phase 4 source)
- `Papers/TransferPlayerClubStatistics_toNationalTeam/NOTAS_arntzen2020.md` — Elo + plus-minus combined (Phase 4 wiring)
- `.planning/spikes/SPIKE-tournament-evaluator.md` — companion spike doc; this calibration spike is a prerequisite for its Phase 5 lock
- `.planning/ROADMAP.md` — v1.0 Phase 6 (Timed Corners Module) absorbs synthesis Phases 5–8 when that phase activates
