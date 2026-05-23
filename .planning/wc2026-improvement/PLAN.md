# WC2026 Improvement — Implementation Plan

**Status:** in_progress
**Started:** 2026-05-23
**Deadline:** 2026-06-11 (kickoff) — 18 days remaining
**Lock baseline:** commit 8c0ce19 (`lock.json`, predictor `bayesian_bivariate_xg_blended`,
ρ=0.0, α=0.20, calibration_status='below-gate')
**Strategy:** shadow lock_v2 (no overwrite); 4-tournament hold-out (AFCON 2023 + Copa 2024
+ Euro 2024 + WC 2022); 60/40 calibration vs new-signals split

## Operator decisions (Turn 1, confirmed)
- **Lock strategy:** shadow paralelo — `lock_v2.json` coexists; MundialModelV2 emits with
  `status='shadow'`; post-WC comparison.
- **Hold-out set:** triple actual (AFCON 2023 + Copa 2024 + Euro 2024) + WC 2022.
- **Improvement axis:** mix calibrado (60% calibration/ensemble, 40% new signals with
  local data).

## Reference docs
- Research: [WC2026_IMPROVEMENT_RESEARCH.md](../../Papers/WC2026_IMPROVEMENT_RESEARCH.md)
- Synthesis: [SYNTHESIS.md](../../Papers/SYNTHESIS.md)
- Prior spike: [SPIKE-wc2026-calibration-lock.md](../spikes/SPIKE-wc2026-calibration-lock.md)
- V4 wave plan: `/Users/kevin_beltran/.claude/plans/revisa-la-planeaci-n-que-linear-wave.md`

## Data inventory (local, ready to use)
- `data/cache/statsbomb/match_outcomes.parquet` — 314 matches across 6 tournaments
  (WC2018:64, WC2022:64, Euro2020:51, Euro2024:51, Copa2024:32, AFCON2023:52). Has
  goals + corners + xG per match.
- `data/cache/martj42_international_results.csv` — 49k international matches 1872–2026.
  Goals only; no xG. Match-importance via competition column.
- `data/cache/international_history.parquet` — pre-processed history (existing artifact).

## Data split (immovable)
- **Training corpus (strength prior fit):** martj42 49k matches with match-importance
  weighting + time decay. **Excludes** the 4 hold-out tournaments completely.
- **Validation corpus (calibration fit):** StatsBomb WC2018 + Euro2020 = 115 matches
  (these have xG; suitable for DIBP π_diag and beta calibrator fit).
- **Held-out test:** AFCON 2023 + Copa 2024 + Euro 2024 + WC 2022 = 199 matches.
  Rolling-origin CV; no signal from these touches any fit parameter.

## Frozen / off-limits
- `src/bip/evaluation/live/engine_v3/` — D-09, untouched.
- `src/bip/core/picks/engine.py` — legacy, untouched.
- `src/bip/evaluation/tournaments/locked_predictions/world_cup_2026/lock.json` —
  **do not overwrite**. lock_v2.json is a separate file.

## Quality gate (Tier-2 promotion criteria for lock_v2)
- Brier CI upper bound on 1X2 < 0.21 on held-out test (currently CI: 0.2027–0.2290 → not met)
- ECE < 0.05 on 1X2 held-out (currently 0.1074 → not met)
- Brier improvement of ≥ 0.005 with bootstrap CI not crossing 0 vs baseline
- Pass on ≥ 2 of 4 hold-out tournaments by per-tournament Brier
- No leakage assertion failures in walk-forward harness

If all four → **PASS** (mint lock_v2.json, MundialModelV2 in shadow registered for
ModelRegistry routing during WC2026).
If only Brier improvement criterion met → **SHADOW only** (run, log, post-WC scoring).
If none → **FAIL** (document honestly; old lock ships; signals queued for v3).

---

## Olas (atomic commits, each ends with green tests)

### Ola 0 — Data substrate + EDA invariants (0.5 day)

**Goal:** Confirm martj42 + StatsBomb integrity; build a unified pre-processed table
for the 199-match hold-out + 115-match validation + martj42 49k training.

**Files to create:**
- `scripts/wc2026_v2/load_corpus.py` — loads martj42 CSV + StatsBomb parquet, builds
  3 split parquets to `data/cache/wc2026_v2/{train,validation,heldout}.parquet`
- `tests/wc2026_v2/test_corpus_loader.py` — invariants:
  - Disjoint splits (no match in both train and validation/heldout)
  - Train excludes all 4 hold-out tournaments
  - Match-date ordering preserved (no future-data leak into past)
  - Schema invariants (required columns present)

**Files to modify:** none.

**Commit:** `feat(wc2026-v2): corpus loader + 3-way split + integrity tests`

**Gate:** all integrity tests green; row counts match expected.

---

### Ola 1 — Match-importance weighted strength prior (1 day)

**Goal:** Implement Ley/Van Eetvelde (2019) weighted-MLE attack/defence rates on
martj42 — directly tackles AFCON-vs-Copa regime shift.

**Files to create:**
- `src/bip/evaluation/tournaments/signals/match_importance.py` — FIFA factor table
  (friendly=20, qualifier=40, continental=50, WC=60), time-decay (half-life 36mo)
- `src/bip/evaluation/tournaments/signals/weighted_strength.py` — `WeightedMLEFitter`
  class fitting (μ_attack_i, μ_defence_i, c_home) via weighted Poisson MLE
- `tests/wc2026_v2/test_match_importance.py` — parametrized over boundary cases
  (friendly→friendly, friendly→WC, decay at half-life)
- `tests/wc2026_v2/test_weighted_strength.py` — synthetic Poisson generation + recover

**Files to modify:** none (new modules).

**Commit:** `feat(wc2026-v2): match-importance weighted strength prior (Ley 2019)`

**Gate:** synthetic recovery within 5%; per-tournament Brier on hold-out drops; tests green.

---

### Ola 2 — Beta calibration (replacing logistic-logit) (1 day)

**Goal:** Drop-in replacement for `LogisticLogitCalibrator` — Kull, Filho, Flach (2017),
parametric 3-param beta calibration map. Direct attack on ECE=0.1074.

**Files to create:**
- `src/bip/evaluation/tournaments/calibration/beta_calibrator.py` — `BetaCalibrator`
  fitting (a, b, c) via L-BFGS-B on cross-entropy
- `tests/wc2026_v2/test_beta_calibrator.py` — parametrized boundary cases:
  (a=1,b=1,c=0)→identity; S-shape; inverted-S; degenerate p=0 / p=1; bootstrap
  consistency check.

**Files to modify:** none (new module; existing logistic calibrator stays).

**Commit:** `feat(wc2026-v2): beta calibration (Kull et al. 2017)`

**Gate:** ECE on held-out 1X2 drops below 0.06; tests green.

---

### Ola 3 — Diagonal-inflated Bivariate Poisson (2 days)

**Goal:** DIBP per Karlis & Ntzoufras (2003) — π_diag fit on validation corpus
(WC2018 + Euro2020). Direct attack on draw mass underestimation.

**Files to create:**
- `src/bip/evaluation/tournaments/predictors/diagonal_inflated_bivariate.py` —
  `DiagonalInflatedBivariatePredictor(GoalsModel)` with `(rho, pi_diag)` parameters.
  Score grid = (1-π_diag) · BP(rho) + π_diag · Diag(weights)
- `src/bip/evaluation/tournaments/fit/dibp_fitter.py` — MLE fitter for (ρ, π_diag)
  on validation corpus
- `tests/wc2026_v2/test_dibp.py` — parametrized:
  - π_diag=0 collapses to plain BP (regression vs existing BP)
  - π_diag=1 produces draw-only mass
  - Markets derived from inflated grid sum to 1.0
  - Synthetic recovery of (ρ, π_diag) within tolerance

**Files to modify:** none (new predictor module).

**Commit:** `feat(wc2026-v2): DIBP predictor + MLE fitter (Karlis-Ntzoufras 2003)`

**Gate:** plain-BP behaviour preserved at π_diag=0; held-out draw probability calibration improves.

---

### Ola 4 — Ensemble predictor v2 (1 day)

**Goal:** Compose the v2 predictor: weighted-MLE prior (Ola 1) → DIBP predictor
(Ola 3) → beta calibration (Ola 2). One callable class for downstream use.

**Files to create:**
- `src/bip/evaluation/tournaments/predictors/v2_calibrated_dibp.py` —
  `CalibratedDIBPPredictor` that:
  - Takes per-team weighted-MLE attack/defence rates as input
  - Outputs Bivariate-Poisson grid → DIBP-inflated → beta-calibrated 1X2/BTTS/OU2.5
- `tests/wc2026_v2/test_calibrated_dibp.py` — e2e on small fixture sample.

**Files to modify:** none.

**Commit:** `feat(wc2026-v2): ensemble predictor v2 (weighted-MLE + DIBP + beta)`

**Gate:** e2e fixture produces valid `GoalsDistribution`; markets sum to 1.0.

---

### Ola 5 — Walk-forward backtest + bootstrap CI (1 day)

**Goal:** Rolling-origin CV over 4 hold-outs with bootstrap CI on Brier + ECE.

**Files to create:**
- `scripts/wc2026_v2/run_backtest.py` — runs predictor over hold-out fixtures using
  existing `run_backtest` harness from `tournaments/backtest/walk_forward.py`
- `src/bip/evaluation/tournaments/backtest/bootstrap.py` — bootstrap_brier_ci(
  reports, n_resamples=2000, seed=42) → returns (lower, upper, point)
- `tests/wc2026_v2/test_bootstrap_ci.py` — synthetic check (known distribution)

**Files to modify:** none.

**Commit:** `feat(wc2026-v2): walk-forward backtest harness + bootstrap CI`

**Gate:** harness runs without leakage assertion failure; per-tournament Brier reported
+ overall CI computed.

---

### Ola 6 — Ablation study (1 day)

**Goal:** Quantify marginal contribution of each new signal: full vs full-minus-each.

**Files to create:**
- `scripts/wc2026_v2/run_ablation.py` — drives backtest with each signal toggled off:
  - Toggle 1: weighted-MLE off (revert to plain xG-blend)
  - Toggle 2: DIBP off (π_diag=0)
  - Toggle 3: beta calibration off (revert to logistic-logit)
  - Toggle 4: all 3 off (= baseline)
- `Papers/WC2026_IMPROVEMENT_ABLATION.md` — auto-generated table with bootstrap
  delta-Brier + CI per ablation cell

**Files to modify:** none.

**Commit:** `feat(wc2026-v2): ablation study + per-signal delta-Brier with CI`

**Gate:** each signal evaluated; signals with delta < 0.005 and CI crossing 0 are
flagged for removal in Ola 7.

---

### Ola 7 — Gate verdict + lock_v2 emission (1 day)

**Goal:** Apply quality gate from §"Quality gate" above; if pass: emit lock_v2.json.

**Files to create:**
- `scripts/wc2026_v2/emit_lock_v2.py` — adapts the existing
  `scripts/spike/lock_world_cup_2026_xg.py` for the v2 predictor; writes to
  `src/bip/evaluation/tournaments/locked_predictions/world_cup_2026/lock_v2.json`
  with computed SHA-256 content hash
- `tests/wc2026_v2/test_lock_v2_integrity.py` — invariants:
  - SHA-256 hash matches recomputation
  - Same 135 fixtures as lock_v1
  - calibration_status field present
  - Bootstrap CI metadata recorded

**Files to modify:**
- `src/bip/models/mundial/model.py` — already accepts `lock_path` parameter (verified
  Turn 1). No changes needed if MundialModelV2 just instantiates with different path.
- Optionally: `src/bip/models/mundial/__init__.py` — register `MundialModelV2` class
  that subclasses MundialModel and defaults `lock_path` to v2.

**Commit:** `feat(wc2026-v2): lock_v2 emission + MundialModelV2 shadow registration`

**Gate verdict written to `Papers/WC2026_IMPROVEMENT_RESULTS.md` section "Gate Verdict":**
- PASS → both locks coexist; ModelRegistry routes v2 in shadow; lock_v1 in production.
- SHADOW only → same as PASS but flagged transparency.
- FAIL → lock_v2.json still written for post-mortem but **NOT registered**; verdict
  documented; signals queued for post-WC v3 iteration.

---

### Ola 8 — Documentation + memory updates + final test sweep (0.5 day)

**Files to create:**
- `Papers/WC2026_IMPROVEMENT_RESULTS.md` — methodology, datasets, ablation table,
  calibration plots, gate verdict, lessons learned. Each numeric claim citable.

**Files to modify:**
- `/Users/kevin_beltran/.claude/projects/-Users-kevin-beltran-ProyectosPersonales-Sports-Betting-betting-intelligence-platform/memory/MEMORY.md` —
  add link to a new memory file `project_wc2026_v2_lock_shipped.md` (or
  `project_wc2026_v2_shadow_failed.md` per verdict)

**Final sweep:**
- `uv run pytest tests/wc2026_v2/ -q` — all new tests green
- `uv run pytest tests/ -q` — full suite green (no regressions)
- Anti-Napoli regression suite still green (per memory: it's a CI gate)
- `tests/models/mundial/test_model.py` still green (Sprint 0 wrapper untouched)

**Commit:** `docs(wc2026-v2): results doc + memory update + final tests sweep`

---

## Timeline summary

| Ola | Days | Cumulative | Risk |
|-----|------|------------|------|
| 0 — Data substrate | 0.5 | 0.5 | LOW |
| 1 — Match-importance prior | 1 | 1.5 | LOW |
| 2 — Beta calibration | 1 | 2.5 | LOW |
| 3 — DIBP predictor | 2 | 4.5 | MED (custom MLE) |
| 4 — Ensemble v2 wrapper | 1 | 5.5 | LOW |
| 5 — Backtest + bootstrap | 1 | 6.5 | LOW |
| 6 — Ablation | 1 | 7.5 | LOW |
| 7 — Lock_v2 emission + gate | 1 | 8.5 | LOW (gate may FAIL — that's an honest outcome) |
| 8 — Docs + memory | 0.5 | 9 | LOW |

**Total ETA: ~9 days of focused work** (buffer to 18 = ~9 days).
**Risk pad:** if Ola 3 (DIBP) overruns past 3 days, drop Ola 6 (ablation auto-tables)
and produce ablation manually.

## What we are explicitly NOT doing
- Transfermarkt scraping (Tier 2 #5 in research) — out of scope for 18-day window;
  legal/scraping risk; queue for v3.
- Pinnacle Odds API capture (Tier 1 #4) — orthogonal to the predictor; doesn't change
  lock_v2; can be added as separate Sprint without touching this work.
- 538-style club-form blend (Tier 2 #6) — requires lineup predictions we don't have.
- Sarmanov DC extension (A4) — identifiability risk at n=314.
- Stacking GLM+RF+XGB (A5) — overfit risk at n=135.
- New telegram code paths, new live picks logic — none of this work affects v3 engine
  or DeliveryWorker.

## Cross-cutting reminders (from memory + ops prompt)
- No emojis in any committed Python output or telegram-bound code paths.
- No Co-Authored-By trailers in git commits.
- Parametrize boundary tests (numeric thresholds, line edges).
- Each numeric claim in WC2026_IMPROVEMENT_RESULTS.md must be traceable to executed
  code or a paper citation (no training-data hallucinations).
- Lock_v2.json content_hash verified by recomputation in CI test.
- D-09: do not touch `engine_v3/`, `core/picks/`, or `core/telegram/`.
