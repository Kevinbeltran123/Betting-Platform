# WC2026 v3 Sprint — Implementation Plan

**Status:** ready_to_start
**Started:** 2026-05-23
**Deadline:** lock_v3.json emittable by 2026-06-08 — **WC2026 kickoff 2026-06-11**
**Days available:** 16 engineering days (with 3-day buffer to kickoff)
**Lock baseline:** commit 8c0ce19 (`lock.json` v1, `bayesian_bivariate_xg_blended` ρ=0.0 α=0.20).
v2 spike FAILED (commit f500783, `lock_v2.json` archived as audit artifact, NOT registered).
**Strategy:** Shadow `lock_v3.json` — coexists with lock_v1 (production) and lock_v2.json
(audit). MundialModelV3 registered in shadow if v3 passes ≥1 gate; lock_v1 stays in
production routing through tournament. Post-WC scoring decides v4.

## Operator directive (Turn 1, confirmed 2026-05-23)

- **Goal:** "El objetivo es tener un modelo validado antes de que empiece el mundial."
  Validated v3 BEFORE WC start (2026-06-11), NOT post-tournament.
- **Scope cut (confirmed via AskUserQuestion):**
  - IN: A (Transfermarkt squad market value, Peeters 2018) + C (Hierarchical Bayesian
    pooling, Macrì-Demartino 2024, offline-only) + D (Pinnacle CLV via Odds API Rookie,
    parallel infrastructure)
  - OUT: B (538-style 25% club-form anchor — data-blocked, StatsBomb open lacks 2025/26
    coverage AND SPI lost 6.2% ROI vs Pinnacle on 36k matches per transferscience.com)
  - OUT: E (Sarmanov DC family extension — no public impl, AIC-only evidence in source paper)
  - B + E queued as v4 post-WC.
- **Validation rigor:** Same 5 quality gates as v2 spike (see §Quality gate below); no
  relaxation. "Validated" = ran the paired-ΔBrier ablation with bootstrap CI, regardless
  of pass/fail verdict.
- **Engineering days = budget to spend, not conserve.** Per memory `wc2026-goal-most-complete-model`.

## Reference docs

- Eval: [Papers/WC2026_V3_CANDIDATES_EVALUATION.md](../../Papers/WC2026_V3_CANDIDATES_EVALUATION.md)
  — per-candidate verdicts, effect-size ranges, risk registers
- v2 PLAN: [.planning/wc2026-improvement/PLAN.md](../wc2026-improvement/PLAN.md)
  — gates inherited verbatim
- v2 RESULTS: [Papers/WC2026_IMPROVEMENT_RESULTS.md](../../Papers/WC2026_IMPROVEMENT_RESULTS.md)
  — what was already ruled out (DIBP, beta-cal, K-importance)
- Research: [Papers/WC2026_IMPROVEMENT_RESEARCH.md](../../Papers/WC2026_IMPROVEMENT_RESEARCH.md)
- Synthesis: [Papers/SYNTHESIS.md](../../Papers/SYNTHESIS.md)
- v2 module map (reusable base): [src/bip/evaluation/tournaments/wc2026_v2/](../../src/bip/evaluation/tournaments/wc2026_v2/)
- Memory: `project_wc2026_v2_spike_failed`, `project_wc2026_v3_candidates_evaluation`,
  `project_wc2026_goal_most_complete_model`

## Data inventory (local, ready to use)

Inherited from v2 (unchanged):
- `data/cache/statsbomb/match_outcomes.parquet` — 314 matches across 6 tournaments
  (WC2018:64, WC2022:64, Euro2020:51, Euro2024:51, Copa2024:32, AFCON2023:52).
  Goals + corners + xG per match.
- `data/cache/martj42_international_results.csv` — 49k international matches 1872–2026.
  Goals only; no xG. Match-importance via competition column.
- `data/cache/wc2026_v2/{train,validation,heldout}.parquet` — pre-split corpora from
  Ola 0 of v2 spike (reused as-is, no re-split).

New for v3 (Wave 1 acquires):
- `data/cache/transfermarkt/squad_values.parquet` — 128 squads (32 WC2026 + 32 WC2022
  + 24 AFCON2023 + 16 Copa2024 + 24 Euro2024) × log-sum-EUR-value at tournament-start
  date. One-time scrape per Scraperly difficulty 2/5.

New for v3 (Wave 2 captures, ongoing):
- `data/cache/odds_api/pinnacle/{event_id}.json` — Pinnacle closing line snapshots
  per fixture, captured T-5min via Odds API Rookie tier.

## Data split (immovable — inherited from v2)

- **Training corpus (strength prior fit):** martj42 49k matches with match-importance
  weighting + time decay. **Excludes** the 4 hold-out tournaments completely.
- **Validation corpus (calibration fit):** StatsBomb WC2018 + Euro2020 = 115 matches.
  Used for: hierarchical hyperparameter tuning (Wave 2.C), TM offset coefficient fit
  if any (Wave 1.A).
- **Held-out test:** AFCON 2023 + Copa 2024 + Euro 2024 + WC 2022 = 199 matches.
  Rolling-origin CV; no signal from these touches any fit parameter.
- **NOT re-shuffled.** Same split as v2 spike — direct comparability with lock_v1 and
  lock_v2 ablation results.

## Frozen / off-limits

- `src/bip/evaluation/live/engine_v3/` — D-09 production engine, untouched.
- `src/bip/core/picks/engine.py` — legacy, untouched.
- `src/bip/evaluation/tournaments/locked_predictions/world_cup_2026/lock.json` —
  v1 production lock; **do not overwrite**. lock_v3.json is a separate file.
- `src/bip/evaluation/tournaments/locked_predictions/world_cup_2026/lock_v2.json` —
  v2 audit artifact (SHA-256 `0421a5c487ca6d57...`); preserved unchanged for v2 vs v3
  post-tournament forensics.
- `src/bip/evaluation/tournaments/wc2026_v2/` — 11 modules from v2 spike. **Extend
  via toggles, do NOT rewrite.** Existing 159 tests must stay green.
- `tests/wc2026_v2/` — 159 existing tests; v3 adds new tests under `tests/wc2026_v3/`.

## Quality gate (Tier-2 promotion criteria for lock_v3)

Inherited verbatim from v2 PLAN §Quality gate:

1. Brier CI upper bound on 1X2 < 0.21 on held-out test (currently CI: 0.2027–0.2290
   for lock_v1; v2 had 0.2325)
2. ECE < 0.05 on 1X2 held-out (currently 0.1074 for lock_v1; v2 had 0.1145).
   **Known structural ceiling at n<500 per Walsh-Joshi — this gate is the hardest to
   pass and may force SHADOW-only verdict.**
3. Brier improvement of ≥ 0.005 with bootstrap CI not crossing 0 vs lock_v1 baseline
4. Pass on ≥ 2 of 4 hold-out tournaments by per-tournament 1X2 Brier (AFCON 2023 is
   the fold C explicitly targets)
5. No leakage assertion failures in walk-forward harness

**Verdict matrix:**
- All 5 gates → **PASS** (lock_v3.json registered; MundialModelV3 in shadow during WC).
- Gate 3 only (Brier improvement) → **SHADOW-only** (lock_v3 emitted, run + logged,
  post-WC scoring).
- None → **FAIL** (lock_v3.json archived as audit artifact like v2; lock_v1 stays in
  production; document honestly; queue for v4).

## Honest outcome distribution (per eval doc §3.1)

- ~30% Lock_v3 = lock_v1 + A + C, modest improvement (ΔBrier −0.005 to −0.020)
- ~50% Lock_v3 = lock_v1 + A only (C kills on feasibility check)
- ~20% Lock_v1 unchanged (both A and C fail gates; v3 documented as rigorous negative)

In all 3 outcomes, "validated" is true. The deliverable is the bootstrap-CI ablation
evidence + audit-trail lock_v3.json, not necessarily a better predictor.

---

## Olas (atomic commits, each ends with green tests)

### Ola 0 — Sprint setup + spec sync (0.5 day, Day 1 morning)

**Goal:** Confirm v2 module surface is intact; create v3 test directory; write v3-specific
config (gate thresholds, sample sizes); commit baseline lock_v1 numbers as ground-truth
reference.

**Files to create:**
- `tests/wc2026_v3/__init__.py` (empty marker)
- `tests/wc2026_v3/conftest.py` — fixtures for v3 hold-out parquets, baseline lock_v1
  numbers
- `scripts/wc2026_v3/__init__.py` (empty marker)
- `scripts/wc2026_v3/baseline_reference.py` — re-runs lock_v1 backtest, emits canonical
  Brier + ECE + per-tournament numbers to `data/cache/wc2026_v3/baseline_v1.json`
  (committed for diff-traceability)

**Files to modify:** none.

**Commit:** `chore(wc2026-v3): sprint scaffolding + baseline v1 reference numbers`

**Gate:** v2 159 tests still green; baseline_v1.json reproduces Brier 0.2156 ± bootstrap.

---

### Ola 1.A — Transfermarkt squad market value covariate (3 days, Days 1-3)

**Goal:** Add log(squad market value) as a multiplicative rate offset in the Bivariate
Poisson team-strength layer. Plug as `use_market_value=True` toggle in
`pipeline.fit_v2_pipeline` per Stage 1.5 design from eval doc §2.A.

**Files to create:**
- `src/bip/evaluation/tournaments/wc2026_v2/_market_data.py` — loaders + offset
  computer. Functions:
  - `load_transfermarkt_values(csv_path) → dict[team_name, market_value_eur]`
  - `compute_offsets(values_dict, reference_median) → dict[team_name, log_offset]`
- `scripts/wc2026_v3/scrape_transfermarkt.py` — one-time scraping script (rotating
  User-Agent, plain HTTP per Scraperly Apr 2026 difficulty 2/5). Targets 128 squads
  × tournament-start dates. Writes `data/cache/transfermarkt/squad_values.parquet`.
  Idempotent (skips already-scraped squads).
- `tests/wc2026_v3/test_market_data.py` — parametrized:
  - Offset = 0 when team value = median
  - Offset > 0 when team value > median (and < 0 when <)
  - Missing team falls back to median (no NaN propagation)
  - Boundary: zero-value team produces finite log offset (clamped, no -inf)

**Files to modify:**
- `src/bip/evaluation/tournaments/wc2026_v2/weighted_strength.py` — extend
  `WeightedMLEResult.predict_lambdas` to accept optional `market_offsets: dict | None`
  parameter; inject into log-rate computation when present. Mean-zero re-anchoring
  needed if offsets used during MLE fit (Wave 1.A.day-2 design call).
- `src/bip/evaluation/tournaments/wc2026_v2/pipeline.py` — add `use_market_value: bool
  = False` toggle to `fit_v2_pipeline`. When True, loads parquet + injects offsets
  into the `WeightedMLEResult` before predictor instantiation.
- `tests/wc2026_v2/test_weighted_strength.py` — extend existing 11 tests with
  parametrized `[market_offsets=None, market_offsets=zero_dict]` to verify
  backward-compatibility (existing v2 behavior unchanged when toggle is False).

**Files to modify (tests):**
- `tests/wc2026_v2/test_pipeline.py` — add 2 tests: pipeline runs with
  `use_market_value=True`, market offset persists through to predictor predictions.

**Commit:** `feat(wc2026-v3): Wave 1.A — Transfermarkt market value covariate + toggle`

**Gate (Ola 1.A):**
- All 159 v2 tests still green
- 4+ new v3 tests green
- Scraping pipeline produces 128-squad parquet on first run; idempotent on re-run
- Pipeline runs e2e with toggle on/off, both produce valid `CalibratedDIBPPrediction`

---

### Ola 1.C — Hierarchical Bayesian feasibility check (1 day, Days 1-2, parallel to 1.A)

**Goal:** Decide go/no-go for full C spike. Build a toy hierarchical PyMC model on
calibration corpus (115 matches, WC2018+Euro2020 = 2 tournament groups). Verify:
(a) MCMC converges with no divergent transitions (NUTS, default config + non-centered
parameterization), (b) inference latency from disk-cached posterior samples meets
500ms budget per fixture.

**Files to create:**
- `scripts/wc2026_v3/c_feasibility_toy.py` — fits hierarchical attack/defense model:
  ```
  attack_t,team ~ Normal(mu_attack_team, sigma_attack_t)  # per-tournament σ
  mu_attack_team ~ Normal(0, tau_attack_global)
  sigma_attack_t ~ HalfNormal(1)
  tau_attack_global ~ HalfNormal(1)
  ```
  Uses PyMC ≥ 5.x + NumPyro JAX backend if available. Writes posterior samples to
  `data/cache/wc2026_v3/c_feasibility_toy_posterior.npz`.
- `scripts/wc2026_v3/c_feasibility_latency.py` — loads posterior samples from disk,
  computes predictive mean for 50 sample (home,away) pairs, measures wall-clock latency.
  Asserts p95 < 500ms.
- `tests/wc2026_v3/test_c_feasibility.py` — runs the toy fit + latency check as a
  smoke test (marked `pytest.mark.slow`; skipped in fast CI).

**Files to modify:** none in src/ (this is feasibility, not implementation).

**Commit:** `spike(wc2026-v3): Wave 1.C — hierarchical Bayes feasibility (toy + latency)`

**Verdict gate (end of Day 2):**
- GO (proceed to Ola 2.C): MCMC converges (R-hat < 1.05, ESS > 400, 0 divergences)
  AND p95 inference latency < 500ms from on-disk samples.
- NO-GO (kill C, free Days 4-12 for A rigor + D extra polish): convergence failures
  persist after non-centered reparameterization, OR latency > 500ms even with samples
  pre-computed and read from disk.
- Document verdict in `Papers/WC2026_V3_C_FEASIBILITY.md` (1 page max).

---

### Ola 2.A — A paired-ΔBrier ablation on n=199 hold-out (2 days, Days 4-5)

**Goal:** Validate A against same gates as v2 spike. Run walk-forward backtest with
`use_market_value` toggled on vs off; compute paired-ΔBrier with 2000-resample
bootstrap CI; per-tournament breakdown.

**Files to create:**
- `scripts/wc2026_v3/run_a_ablation.py` — drives the existing
  `wc2026_v2/backtest.run_walk_forward_backtest` harness with both configurations,
  produces `data/cache/wc2026_v3/a_ablation_report.json` (Brier, ECE, per-tournament,
  paired-ΔBrier with CI).
- `tests/wc2026_v3/test_a_ablation_artifacts.py` — schema invariants on the JSON
  output (required fields present, bootstrap CI lower ≤ point ≤ upper, n=199 reflected).

**Files to modify:** none.

**Commit:** `feat(wc2026-v3): Wave 2.A — Transfermarkt ablation report on n=199 hold-out`

**Verdict gate (end of Day 5):**
- A PASS: paired-ΔBrier ≥ −0.005 with CI not crossing 0, AND pass on ≥ 2 of 4
  tournaments (gates 3 + 4 from §Quality gate).
- A SHADOW-only: paired-ΔBrier improves but CI crosses 0.
- A KILL: paired-ΔBrier ≤ 0 or wrong-direction. Toggle reverted; A documented as
  ruled out (same fate as v2 DIBP).

---

### Ola 2.C — Hierarchical Bayesian full spike (7 days, Days 6-12, CONDITIONAL on Ola 1.C GO)

**Goal:** Full hierarchical strength prior with per-tournament partial pooling. Replace
`WeightedMLEFitter` Stage 1 with a parallel `HierarchicalStrengthFitter` (NOT extend —
fundamentally different parameter estimation). Inference at predict-time reads
pre-computed posterior samples from disk (offline-only constraint, see eval doc §2.C).

**Skip if Ola 1.C returned NO-GO.** In that case, Days 6-12 reallocate to: extra D
polish (D ships earlier, full integration tests), A robustness checks (sensitivity
analysis over offset coefficient), v3 ensemble doc work.

**Files to create:**
- `src/bip/evaluation/tournaments/wc2026_v2/hierarchical_strength.py` — new module
  parallel to `weighted_strength.py`. Classes:
  - `HierarchicalStrengthFitter` — PyMC-based hierarchical MLE/MCMC
  - `HierarchicalStrengthResult` — interface-compatible with `WeightedMLEResult`
    (exposes `predict_lambdas(home, away) → (λ_h, λ_a)` reading from on-disk samples)
  - `_persist_posterior_samples(trace, path)` — writes NPZ with mean + samples
  - `_load_predictive_lambdas(path, home, away) → (λ_h, λ_a)` — fast read-from-disk
    closed-form predictive mean
- `src/bip/evaluation/tournaments/wc2026_v2/hierarchical_predictor.py` — adapter that
  composes hierarchical_strength → existing dibp → existing beta_calibrator. Mirrors
  `v2_predictor.py` API.
- `tests/wc2026_v3/test_hierarchical_strength.py` — parametrized:
  - Synthetic data with known per-tournament σ → recover within 2× tolerance
  - Empty calibration → graceful prior-only behavior (no NaN propagation)
  - Cold-start team → falls back to global mean prior
  - Latency: predict_lambdas p95 < 100ms (per-fixture; well under 500ms total budget)
- `tests/wc2026_v3/test_hierarchical_predictor.py` — e2e on 5-fixture toy sample.

**Files to modify:**
- `src/bip/evaluation/tournaments/wc2026_v2/pipeline.py` — add `use_hierarchical:
  bool = False` toggle. When True, swaps in `HierarchicalStrengthFitter` for Stage 1
  (NOT extend; mutually exclusive with `use_market_value`'s offset mechanism — see
  Ola 3.E ensemble design).

**Commit chain (4 atomic):**
- Day 6-7: `feat(wc2026-v3): Wave 2.C.1 — hierarchical_strength module + sample I/O`
- Day 8-9: `feat(wc2026-v3): Wave 2.C.2 — hierarchical_predictor + pipeline toggle`
- Day 10: `feat(wc2026-v3): Wave 2.C.3 — hierarchical ablation report (C-only)`
- Day 11-12: `feat(wc2026-v3): Wave 2.C.4 — AFCON-fold targeted backtest + verdict`

**Verdict gate (end of Day 12):**
- C PASS: AFCON-fold Brier drops below 0.21 (lock_v1 is 0.2271, v2 was 0.2590 — both
  fail this fold). AND aggregate paired-ΔBrier ≥ −0.005 with CI not crossing 0.
- C SHADOW-only: AFCON drops but other folds degrade; aggregate is wash.
- C KILL: AFCON Brier does not drop OR aggregate ΔBrier is wrong-direction.
  Toggle reverted; queue Bayesian-pooling as v4 if v3 ensemble ships without C.

---

### Ola 2.D — Pinnacle CLV via Odds API Rookie (3-4 days, Days 4-7, parallel to 2.A/2.C)

**Goal:** Capture Pinnacle 1X2 + AH closing-line snapshots for v3 CLV sink. Independent
of predictor work; ships as infrastructure.

**Files to create:**
- `src/bip/integrations/odds_api_client.py` — httpx + tenacity wrapper:
  - `OddsApiClient(api_key, base_url='https://api.the-odds-api.com/v4')`
  - `.get_event_odds(sport_key, event_id, bookmakers=['pinnacle', 'betfair_ex_eu'],
    markets=['h2h', 'spreads']) → dict`
  - Exponential backoff on 429/5xx; respects 500-req/month Rookie tier ceiling
- `src/bip/integrations/__init__.py` — register module if not present
- `scripts/wc2026_v3/capture_pinnacle_snapshot.py` — single-fixture capture entry point
  (called by scheduler at T-5min before kickoff)
- `tests/wc2026_v3/test_odds_api_client.py` — uses respx (or httpx mock transport)
  to stub API responses; verifies retry behavior, ToS-compliant rate limit, parsing
  of Pinnacle de-vig structure
- `tests/wc2026_v3/test_capture_snapshot.py` — e2e mocked: scheduler triggers capture,
  snapshot written to `data/cache/odds_api/pinnacle/{event_id}.json`

**Files to modify:**
- `src/bip/evaluation/live/engine_v3/clv_sink.py` (READ-ONLY assertion — check current
  signature first). If extension needed (per memory `v3-overhaul-260515-nxn` it accepts
  goals/btts/totals ONLY), add per-source field — keep AH as a new family with explicit
  `family='ah_pinnacle'` tag, opt-in, no behavior change for existing CLV consumers.

**Pre-commit verification (Day 4 morning, BEFORE subscribing):**
- Manually verify The Odds API still lists Pinnacle on `/sports/soccer_fifa_world_cup`
  endpoint via free-tier ping (no auth required for sport listing).
- If coverage missing: D verdict flips to DEFER-WITH-WORKAROUND (Betfair Exchange as
  primary). Document in `Papers/WC2026_V3_D_COVERAGE.md` and continue with Betfair
  source. **Do not waste $20 if coverage is dead.**

**Commit chain (3 atomic):**
- Day 4: `feat(wc2026-v3): Wave 2.D.1 — Odds API client + retry + tests (Pinnacle)`
- Day 5: `feat(wc2026-v3): Wave 2.D.2 — Pinnacle snapshot capture script`
- Day 6-7: `feat(wc2026-v3): Wave 2.D.3 — CLV sink integration + scheduler job`

**Gate (end of Day 7):**
- 5 manual WC2026-fixture snapshots captured successfully (1X2 + AH from Pinnacle)
- All new tests green
- Existing v3 CLV consumers unaffected (regression: family-tag opt-in, default
  behavior unchanged)

---

### Ola 3.E — v3 ensemble integration + combined ablation (3 days, Days 13-15)

**Goal:** Compose the v3 predictor from passing candidates. Branches:
- A PASS + C PASS → `CalibratedHierarchicalDIBPv3Predictor` = hierarchical strength
  (Stage 1') + market-value offsets (Stage 1.5') + DIBP (Stage 2) + beta calibrator
  (Stage 4). Note: when both A and C are on, market offsets are applied to
  hierarchical posterior means.
- A PASS + C KILL → `CalibratedMarketOffsetDIBPv3Predictor` = WeightedMLE (Stage 1)
  + market-value offsets (Stage 1.5) + DIBP + beta calibrator. (= v2 baseline + A only.)
- A KILL + C PASS → `CalibratedHierarchicalDIBPv3Predictor` without offsets.
- A KILL + C KILL → no v3 emission; lock_v1 stays; lock_v3.json archived as failed-spike
  per FAIL branch.

**Files to create:**
- `src/bip/evaluation/tournaments/wc2026_v2/v3_predictor.py` — branched predictor
  composer per above. Single entry point: `build_v3_predictor(a_passed: bool, c_passed:
  bool, **kwargs) → BasePredictor`.
- `scripts/wc2026_v3/run_v3_ablation.py` — runs the full ablation:
  baseline (lock_v1) vs A-only vs C-only vs A+C (or whichever combinations are valid
  given verdicts). Bootstrap CI 2000 resamples seed=42. Writes
  `data/cache/wc2026_v3/v3_ablation_report.json` + auto-generates
  `Papers/WC2026_V3_ABLATION.md`.
- `tests/wc2026_v3/test_v3_predictor.py` — branching coverage:
  - (A=T, C=T) builds hierarchical+offset predictor
  - (A=T, C=F) builds offset-only v3
  - (A=F, C=T) builds hierarchical-only v3
  - (A=F, C=F) raises explicit error (caller must handle FAIL branch)
- `tests/wc2026_v3/test_v3_e2e.py` — e2e on 5-fixture sample, markets sum to 1.0,
  no NaN, all probabilities in [0, 1].

**Files to modify:**
- `src/bip/evaluation/tournaments/wc2026_v2/__init__.py` — export `build_v3_predictor`.

**Commit chain (3 atomic):**
- Day 13: `feat(wc2026-v3): Wave 3.E.1 — v3_predictor branched composer`
- Day 14: `feat(wc2026-v3): Wave 3.E.2 — combined ablation report + auto-doc`
- Day 15: `feat(wc2026-v3): Wave 3.E.3 — v3 e2e fixtures + integration tests`

**Gate (end of Day 15):**
- v3 ablation report compiles; combinatorial coverage of A×C branches tested
- All 159 v2 tests + new v3 tests green
- Anti-Napoli regression suite still green (CI gate per memory
  `verify_executor_test_claims_on_main`)

---

### Ola 3.F — lock_v3.json emission + tamper-verify (1 day, Day 16)

**Goal:** Emit `lock_v3.json` per the verdict branch. SHA-256 content_hash computed
and verified by recomputation in CI test. `calibration_status` field reflects which
gates passed.

**Files to create:**
- `scripts/wc2026_v3/emit_lock_v3.py` — adapts existing
  `scripts/spike/lock_world_cup_2026_xg.py` + the v2 `lock_v2_emitter` pattern.
  Outputs `src/bip/evaluation/tournaments/locked_predictions/world_cup_2026/lock_v3.json`
  with:
  - 72 group-stage WC2026 fixtures (same as lock_v1 and lock_v2)
  - 1X2 + BTTS + OU2.5 predictions per fixture from `build_v3_predictor`
  - `predictor_version: 'v3'`
  - `predictor_components: {a: bool, c: bool}` reflecting Day-5 + Day-12 verdicts
  - `calibration_status: 'gate-pass' | 'shadow-only' | 'below-gate'`
  - `parent_locks: ['lock.json:8c0ce19', 'lock_v2.json:f500783']`
  - SHA-256 `content_hash`
  - Bootstrap CI metadata from v3 ablation report
- `tests/wc2026_v3/test_lock_v3_integrity.py`:
  - SHA-256 hash matches recomputation
  - Same 72 fixtures as lock_v1 (set equality on `(home, away, kickoff_date)` triples)
  - `calibration_status` is one of the 3 allowed values
  - `predictor_components` reflects the actual predictor built
  - Tamper-detection: mutating any prediction field invalidates the hash

**Files to modify:** none (new emitter; v1/v2 locks unchanged).

**Commit:** `feat(wc2026-v3): Ola 3.F — lock_v3.json emission + tamper-verify (verdict: {VERDICT})`

**Gate:** lock_v3.json on disk with valid hash + integrity tests green.

---

### Ola 3.G — Buffer / fix-on-fail / docs / memory (3 days, Days 17-19)

**Day 17:** Documentation
- `Papers/WC2026_V3_RESULTS.md` — methodology, datasets, ablation tables (auto-imported
  from JSON reports), calibration plots, gate verdict, lessons learned. Each numeric
  claim traceable to executed code (script path + commit SHA).

**Day 18:** Memory updates + final test sweep
- Memory file: `project_wc2026_v3_lock_shipped.md` (or `_v3_shadow_failed.md` per
  verdict). Mirror the structure of `project_wc2026_v2_spike_failed.md`.
- Update MEMORY.md index with link.
- `uv run pytest tests/wc2026_v3/ -q` — all v3 tests green
- `uv run pytest tests/ -q` — full suite green
- Anti-Napoli regression suite green
- `tests/models/mundial/test_model.py` green (Sprint 0 wrapper untouched)

**Day 19:** Pure buffer
- Fix-on-fail for any gate that fails on Day 18 sweep
- Re-emit lock_v3.json if late corrections needed
- Final commit + tag if shipping

**Commit:** `docs(wc2026-v3): results doc + memory update + final test sweep`

**Hard stop:** EOD 2026-06-08. If lock_v3.json not on disk with valid hash and
calibration_status field by EOD 2026-06-08, the sprint is declared incomplete and
lock_v1 stays as the only WC2026 production lock through the tournament. v3 work
queues for v4 post-WC scoring window.

---

## Timeline summary

| Ola | Days | Cumulative | Risk | Conditional? |
|-----|------|-----------|------|--------------|
| 0 — Sprint setup + baseline ref | 0.5 | 0.5 | LOW | — |
| 1.A — TM scaffold + scrape + tests | 3 | 3.5 | LOW-MED (subsume risk) | — |
| 1.C — Hierarchical feasibility | 1 | 2 (parallel) | MED (convergence) | — |
| 2.A — A ablation on n=199 | 2 | 5.5 | LOW | — |
| 2.C — Hierarchical full spike | 7 | 12.5 | HIGH (latency + ECE ceiling) | YES (Ola 1.C GO) |
| 2.D — Pinnacle CLV | 3-4 | 8 (parallel) | LOW-MED (ToS, scrape lag) | — |
| 3.E — v3 ensemble + combined ablation | 3 | 15.5 | MED (combinatorial) | — |
| 3.F — lock_v3 emission + tamper-verify | 1 | 16.5 | LOW | — |
| 3.G — Docs + memory + final sweep | 3 | 19.5 | LOW (buffer) | — |

**Critical path:** Ola 0 → 1.A → 2.A → 3.E → 3.F → 3.G = 12.5 days. Ola 1.C + 2.C
run in parallel on the C branch; if C GO, that branch is 12 days (1+7+integration).
Ola 2.D runs parallel to 2.A/2.C, total wall-clock ~16-17 days with 2-3 day buffer.

**Risk pad:** if Ola 2.C overruns past Day 12, kill C mid-stream, ship lock_v3 with
A-only on Day 14-15, advance Ola 3.F to Day 15 to preserve buffer.

---

## What we are explicitly NOT doing

- **B (538-style 25%-club-form anchor)** — data-blocked (StatsBomb open lacks 2025/26
  top-5-league coverage) AND adversarial evidence (SPI lost 6.2% ROI vs Pinnacle on
  36k matches per transferscience.com retrospective). Queue v4 post-WC IF (a) commercial
  club-form data acquired, OR (b) Understat-with-xGA-proxy scraping infrastructure built.
- **E (Sarmanov DC family extension)** — no public Python/R implementation; source paper
  reports AIC-only on women's leagues with no Brier head-to-head; identifiability fragile
  at n=199. Queue v4 IF public impl appears OR intl-tournament Brier benchmark published.
- **Re-litigation of v2 ruled-outs** — DIBP, beta calibration, FIFA-K match-importance
  weighting all closed with bootstrap-CI rigor on 2026-05-23 (see
  [Papers/WC2026_IMPROVEMENT_RESULTS.md](../../Papers/WC2026_IMPROVEMENT_RESULTS.md) §5).
  Do not re-attempt.
- **lock_v1 or lock_v2 overwrites** — both files preserved unchanged for forensic comparability.
- **engine_v3 / core/picks / telegram code paths** — D-09 freeze applies; lock_v3 work
  does NOT touch live engine code.
- **New ECE-reduction ML calibrators** — Walsh-Joshi n<500 ceiling is structural; only
  structural-signal candidates (A, C) can move ECE.

---

## Cross-cutting reminders (from memory + ops conventions)

- **No emojis** in any committed Python output or telegram-bound code paths.
- **No Co-Authored-By trailers** in git commits (per memory `feedback_no_coauthored`).
- **Parametrize boundary tests** for any threshold logic (line edges, decay half-life,
  σ boundaries) — per memory `feedback_test_boundary_cases`.
- **Each numeric claim** in `WC2026_V3_RESULTS.md` must be traceable to executed code
  (script path + commit SHA) or a paper citation. No training-data hallucinations.
- **Lock_v3.json content_hash** verified by recomputation in CI test (mirror v2 pattern).
- **D-09 freeze**: do not touch `engine_v3/`, `core/picks/`, or `core/telegram/`.
- **Verify executor test claims on main** — if any Ola uses git worktrees, re-run the
  test suite + anti-Napoli CI gate on main after merge (per memory
  `feedback_verify_executor_test_claims_on_main`).
- **CLI stdout** in `print()` / log markers — emojis NOT enforced (per memory
  `feedback_no_emojis_in_telegram`, restriction is for tier templates / scoreboard /
  alerts / outcome replies only).
- **Eval doc verdicts hold** unless a Wave produces evidence that flips them. The doc
  is decision-support, not a contract — but flipping a verdict mid-sprint requires
  a memory update + this PLAN amended in the same commit.
