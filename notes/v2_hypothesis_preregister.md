# WC2026 Patterns v2 — Hypothesis Pre-Registration

**Locked 2026-05-24, before any v2 test was run.** This file enumerates every
hypothesis whose result will be reported. Any pattern surfaced that is NOT in
this list will be flagged `[POST-HOC]` and validated independently in hold-out
before being reported as a real finding.

**Splits.** Reused from v1 (no re-shuffle):
- Discovery: `wc_2018` + `euro_2020`, n=115.
- Hold-out: `wc_2022` + `afcon_2023` + `euro_2024` + `copa_2024`, n=199.

**Stats.** Bootstrap n=2000, seed=42 (matches v1). Benjamini-Hochberg FDR at
q=0.10 over the FULL pre-registered set (including negatives). Cell minimum
n=30 for STRONG/MODERATE verdict; n<30 → exploratory only.

**Session-1 scope.** Tier-S lenses 1, 3, 4, 5. Lens 2 (blowout taxonomy) and
Tier-A/B lenses deferred to session 2.

**Favorite definition.** `tm_ratio = max(home_mv, away_mv) / min(home_mv, away_mv)`.
Tier assignment:
- Tier-A: `tm_ratio >= 3.0` (clear favorite, top of gap distribution)
- Tier-B: `1.8 <= tm_ratio < 3.0`
- Tier-C: `1.3 <= tm_ratio < 1.8`
- Tier-D: `1.0 < tm_ratio < 1.3` (parity / no clear favorite)
- Tier-N: missing market value for either side

Thresholds chosen as exponential ramps so each tier has roughly comparable n.
(Final tier sizes confirmed in `01_inspect_tier_distribution.py`; pre-registration
locked at the bracket boundaries above. If a tier has n<30 in discovery, its
specific sub-tests are marked exploratory rather than promoted/demoted.)

---

## Lens 1 — Favorite-draws taxonomy

**Operational target.** Draw-no-bet / live-draw / 1X2-draw markets where
Pinnacle prices the draw based on predictor-implied probability.

| ID    | Test                                                                                              | Direction expected  | Min n |
|-------|---------------------------------------------------------------------------------------------------|---------------------|-------|
| L1.1  | `P(draw \| Tier-A)` vs predictor-implied draw mass over same fixtures                              | empirical > implied | 30    |
| L1.2  | `P(draw \| Tier-A ∧ HT-tied)` vs `P(draw \| Tier-A ∧ HT-decided)`                                  | tied > decided      | 30/30 |
| L1.3  | `P(draw \| Tier-A ∧ knockout)` vs `P(draw \| Tier-A ∧ group)`                                      | knockout > group    | 30/30 |
| L1.4  | `P(favorite wins \| Tier-A ∧ AFCON)` vs `P(favorite wins \| Tier-A ∧ non-AFCON)`                   | AFCON < non-AFCON   | 15/30 |
| L1.5  | `P(draw \| Tier-D)` vs base rate (33% global)                                                     | Tier-D ≥ base       | 30    |
| L1.6  | Interaction: `P(draw \| Tier-A ∧ MD3 ∧ both-need-result-or-both-qualified)` vs all Tier-A MD3      | exploratory only    | 15    |

**Note on L1.4.** AFCON n is sub-30 by construction. Listed as exploratory.

---

## Lens 3 — HT → FT 9-state conditional matrix

**Operational target.** HT/FT combo bets and exact-score props where the
predictor only emits pre-match marginals.

We use 4 HT bins (matches v1 P9): `0-0`, `1-0`, `0-1`, `1-1`. Sub-stratify by
favorite identity to get 9 effective states: favorite-up, tied, favorite-down
× HT goals-bin (treating 1-1 separately).

| ID    | Test                                                                                                                   | Direction expected            | Min n |
|-------|------------------------------------------------------------------------------------------------------------------------|-------------------------------|-------|
| L3.1  | `P(favorite wins FT \| HT 0-0)` vs predictor pre-match `P(favorite wins)`                                              | empirical < implied (drift)   | 30    |
| L3.2  | `P(draw FT \| HT 1-1)` vs predictor pre-match `P(draw)`                                                                | empirical > implied           | 30    |
| L3.3  | `P(BTTS FT \| HT 0-0)` vs predictor pre-match `P(BTTS)`                                                                | empirical < implied           | 30    |
| L3.4  | `P(FT 1-1 specific) \| HT 1-1)` vs other FT outcomes given HT 1-1                                                       | descriptive only              | 30    |
| L3.5  | HT favorite-up 1-0 vs HT underdog-up 1-0: divergence in `P(losing side equalizes)`                                     | underdog-up > favorite-up     | 25/15 |

**Note on L3.5.** Underdog leading n is small (~15-25). Marked exploratory if
n<30; promoted if hold-out replicates with comparable n.

---

## Lens 4 — Survival to first goal (Kaplan-Meier)

**Operational target.** Time-of-first-goal Under/Over X minutes props,
typically priced as O25.5min, O35.5min, O45.5min.

| ID    | Test                                                                                              | Test type     | Min n |
|-------|---------------------------------------------------------------------------------------------------|---------------|-------|
| L4.1  | KM curves for time-to-first-goal: group vs knockout                                              | log-rank      | 30/30 |
| L4.2  | KM curves for time-to-first-goal: Tier-A asymmetric vs Tier-D parity matches                     | log-rank      | 30/30 |
| L4.3  | `P(no goal by min 25) \| Tier-A` vs base rate (no-tier-conditioning)                              | bootstrap diff| 30    |
| L4.4  | `P(no goal by min 45 — HT 0-0) \| Tier-A` vs Tier-D                                              | bootstrap diff| 30/30 |
| L4.5  | Median time-to-first-goal: AFCON vs non-AFCON                                                    | log-rank      | 30/30 |

**Censoring.** Matches with no goals at all (FT 0-0) are right-censored at
min 90 + observed stoppage. Extra time excluded for survival (regulation
window only).

---

## Lens 5 — Negative-space mapping

**Operational target.** Filter rules added on top of pick gate. Patterns that
explain *where the predictor systematically fails* become exclusion zones for
pre-match picks.

**Predictor.** lock_v1's bivariate Poisson with xG blend (ρ=0.0, α=0.20), the
locked SOTA per `[[wc2026-v3-final]]`. Strictly leave-one-tournament-out: each
fixture is scored using a predictor trained only on tournaments earlier than
the fixture's tournament. (No fold-internal contamination.)

| ID    | Test                                                                                              | Decision rule           | Min n |
|-------|---------------------------------------------------------------------------------------------------|-------------------------|-------|
| L5.1  | Worst-decile Brier_1X2 over 314 matches: fraction that is AFCON                                  | ≥ 1.5× baseline → flag  | 31    |
| L5.2  | Worst-decile Brier_1X2: fraction that is MD3 (final group MD)                                    | ≥ 1.5× baseline → flag  | 31    |
| L5.3  | Worst-decile Brier_1X2: fraction with `tm_ratio < 1.3` (parity)                                  | ≥ 1.5× baseline → flag  | 31    |
| L5.4  | Worst-decile Brier_1X2: fraction that is an upset (loser had higher MV)                          | ≥ 1.5× baseline → flag  | 31    |
| L5.5  | Worst-decile Brier_1X2: fraction with HT 1-1 (regime-flip)                                       | ≥ 1.5× baseline → flag  | 31    |
| L5.6  | Worst-decile Brier_1X2: fraction that is host nation                                             | exploratory             | 31    |

**Decision rule.** A subgroup is "flagged" if its representation in the
worst-decile (n≈31 of 314) exceeds 1.5× its baseline representation in the
full corpus. Direction: only worsening (over-representation) flagged; under-
representation noted but not treated as a finding.

**Combined slice tests.** Pairs of two flagged variables tested for
interaction effects in worst-decile (Bonferroni-adjusted within the L5 family).

---

## Out-of-scope for session 1 (deferred to session 2)

- **Lens 2** Blowout taxonomy (favorite wins by 3+) — requires squad-value
  knee analysis, queued.
- **Lens 6** Goal-rebound (2-step conditional) — queued.
- **Lens 7** Late-equalizer conditional — queued.
- **Lens 8** Penalty kick conditionals — needs penalty event extraction.
- **Lens 9** Corner clustering (autocorrelation) — queued.
- **Lens 10** Card cascade — queued.
- **Lens 11** Already-qualified MD3 interaction — covered partially by L1.6.
- **Lens 12-15** Host/cross-region/warm-up/big-game — Tier-B, queued for v3 if
  v2 surfaces clear winners.

---

## Reporting commitments

- All numeric claims will cite bootstrap CI from `_lib.bootstrap_diff_ci`.
- FDR-BH is applied across the FULL Tier-S test set (Lenses 1+3+4+5 above),
  treating each ID as one test. Null results are reported in `§6 Falsified`.
- A pattern is `STRONG` if discovery survives FDR AND hold-out replicates with
  CI overlap and same sign.
- A pattern is `MODERATE` if either (a) discovery survives FDR but hold-out
  attenuates (sign preserved, CI overlaps null), or (b) descriptive table with
  n≥60.
- A pattern is `WEAK` if discovery survives nominal p<0.10 but not BH-FDR.
- A pattern is `NULL` if discovery doesn't reach nominal p<0.10.

Pre-reg locked.
