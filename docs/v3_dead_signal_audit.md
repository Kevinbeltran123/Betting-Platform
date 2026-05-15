# v3 Engine Dead-Signal Audit

**Scope:** All 13 archetype detectors (A1..A12 + A2b) plus 5 cross-cutting
GSV fields that are permanently zero or unpopulated in production.

**Data source:** Day-4 production sample (n=31 Sportmonks live fixtures,
2026-05-13); `Papers/V3_DAY3_DIAGNOSIS.md`; `Papers/V3_DAY4_FIXES.md`.

**Status legend:**

| Symbol | Meaning |
|--------|---------|
| REAL | GSV field populated from live Sportmonks data — signal is live |
| HEURISTIC-PROXY | Derived from available data (not a direct feed); may be noisy |
| DEAD | Field defaults to a value that makes the gating predicate permanently false — archetype never fires in production |
| SUPPRESSED | Detector removed from `_ARCHETYPE_DETECTORS`; function intact |

---

## Detector Table

| ID | Archetype | Rule | Key GSV Fields Gated | Population Status | Notes |
|----|-----------|------|----------------------|-------------------|-------|
| A1 | RED_CARD_AWAY_EARLY | `numerical.red_cards_away >= 1`, `time.minute < 30`, `xg.xg_diff >= -0.4` | `numerical.red_cards_away`, `time.minute`, `xg.xg_diff` | REAL | Red card events parsed from Sportmonks live event stream. xG is HEURISTIC-PROXY (derived from shots+insidebox). Gate fires in production when an early away red occurs. |
| A2 | DOMINANT_LOSING_NAPOLI | `score.dominant_losing`, `time.minute in [25,45]`, `xg.xg_vs_score_divergence >= 0.3` | `score.dominant_team_id`, `score.dominant_losing`, `xg.xg_vs_score_divergence` | REAL / HEURISTIC-PROXY | `dominant_team_id` derived from bookmaker-implied probability gap (market signal) or lambda prior. `xg_vs_score_divergence` = xg_diff minus expected-given-score-diff (table-anchored). Fires. |
| A2b | DOMINANT_LOSING_NAPOLI (BTTS companion) | same as A2 + `dom_goals == 0`, `underdog_goals >= 1`, `time.minute in [30,45]` | same as A2 plus `score.home_goals`, `score.away_goals` | REAL / HEURISTIC-PROXY | Fires as companion to A2 when underdog has scored exactly once and dominant has zero. Shares the A2 dominant_team_id derivation path. |
| A3 | LATE_CAGEY_ZERO_ZERO | `is_late_cagey_zero_zero` compound | `score.home_goals`, `score.away_goals`, `time.minute >= 75`, `tactical.game_phase == "cagey_closed"` | HEURISTIC-PROXY | `game_phase` derived from xG-per-minute and possession heuristics (no direct Sportmonks tactical feed). Fires when score and minute conditions met + game_phase inferred correctly. |
| A4 | LEAD_TWO_DEFENSIVE_SUB | `score.goal_diff >= 2`, `time.minute in [55,75]`, `roster.recent_subs_5min` contains `role_signal=="defensive"` | `score.goal_diff`, `time.minute`, `roster.recent_subs_5min[].role_signal` | **DEAD (role_signal)** | `role_signal` on `SubstitutionEvent` defaults to `"unknown"` — Sportmonks substitution events carry player IDs but no positional role. The filter `s.role_signal == "defensive"` will never be satisfied. Gate never fires unless `role_signal` is wired (requires a player-position API lookup or heuristic from player stats). |
| A5 | REGRESSION_TO_XG | `score.goal_diff == 0`, `time.minute >= 60`, `abs(xg.xg_diff) >= 0.7` | `score.goal_diff`, `time.minute`, `xg.xg_diff` | REAL / HEURISTIC-PROXY | xG is HEURISTIC-PROXY (shots-based). Gate fires. |
| A6 | CARDS_MOMENTUM_STRICT_REF | `cards.yellows[0]+cards.yellows[1] >= 5`, `time.minute >= 70`, `cards.ref_card_rate_prior >= 5.0` | `cards.yellows`, `time.minute`, `cards.ref_card_rate_prior` | **DEAD (ref_card_rate_prior)** | `ref_card_rate_prior` defaults to `0.0` (`gsv.py:174`). No referee historical data source is wired. The predicate `>= 5.0` is **never met**. A6 never fires in production. See recommendation (a). |
| A7 | UNDERDOG_LEADS_SIEGE | `abs(score.goal_diff) == 1`, `time.minute >= 70`, `tactical.{home,away}_phase in {"parking_bus","collapsing"}` | `score.dominant_team_id`, `score.goal_diff`, `time.minute`, `tactical.home_phase` / `tactical.away_phase` | HEURISTIC-PROXY | Tactical phase derived from shot-rate + possession heuristics. Has fired; quality depends on heuristic accuracy. |
| A8 | OPEN_GAME_FORMATIONS | `is_open_game` (3+ goals before 60') | `score.home_goals`, `score.away_goals`, `time.minute`, `roster.formation_home`, `roster.formation_away` | REAL (primary) + **DEAD branch** | Core gate (`is_open_game`) is REAL. The `has_aggressive_formation` branch (`formation_home in {"4-3-3","3-4-3",...}`) is **dead** — Sportmonks live feed always returns `"unknown"` for formations (31/31 Day-4 fixtures). The branch only affects `confidence_prior` (0.65 vs 0.55), not whether the archetype fires. Low severity but wastes conditional evaluation. |
| A9 | KEY_PLAYMAKER_OFF | `any(roster.key_player_off)` | `roster.key_player_off` | **DEAD (key_player_off)** | `key_player_off` defaults to `(False, False)` (`gsv.py:189`). No heuristic or lookup populates it — the GSVBuilder has no code path that sets `key_player_off=True`. The predicate `any(...)` is **never met**. A9 never fires. See recommendation (a). |
| A10 | SECOND_HALF_RESET | `time.period == "2H"`, `time.minute in [46,50]`, `score.dominant_losing`, `xg.xg_vs_score_divergence >= 0.5` | `time.period`, `time.minute`, `score.dominant_losing`, `xg.xg_vs_score_divergence`, `roster.formation_changes` | REAL / HEURISTIC-PROXY + **DEAD branch** | Core gate fires. `formation_changes` branch is **dead** — Sportmonks does not emit formation-change events on the live fixture stream (0/31 Day-4 fixtures). Only affects `confidence_prior` (0.68 vs 0.60), not firing. Same pattern as A8. |
| A11 | NUMERICAL_SUSTAINED | `numerical.numerical_advantage > 0`, `time.minute >= 30`, `score.dominant_losing == False` | `numerical.numerical_advantage`, `time.minute`, `score.dominant_losing` | REAL — **SUPPRESSED** | Fields are populated. Detector fires correctly. Removed from `_ARCHETYPE_DETECTORS` due to net-negative EV both sample days (D3: -5.79u wr=0.50 n=42; D4: -1.00u; MES anti-predictive on corners). Function and `__all__` export retained. |
| A12 | CRUISE_MODE | `abs(score.goal_diff) == 1`, `time.minute >= 80`, `tactical.{home,away}_phase in {"controlling","parking_bus"}`, `xg_per_min_last_15 <= 0.05` | `score.goal_diff`, `time.minute`, `tactical.home_phase`/`away_phase`, `xg.xg_per_min_home_last_15`, `xg.xg_per_min_away_last_15` | HEURISTIC-PROXY | Tactical phase and xG-per-min both derived from shot-rate heuristics. Has fired; quality depends on heuristic accuracy. |

---

## Hard-Dead Signal Summary

Five signals are permanently null/zero in production and create irrecoverable dead branches:

| Signal | GSV Path | Default | Gating Predicate | Archetype Affected | Impact |
|--------|----------|---------|------------------|--------------------|--------|
| `ref_card_rate_prior` | `cards.ref_card_rate_prior` | `0.0` | `>= 5.0` | A6 | **A6 never fires.** Ref historical cards per game not sourced. |
| `key_player_off` | `roster.key_player_off` | `(False, False)` | `any(...)` | A9 | **A9 never fires.** No player-importance lookup wired. |
| `formation_home` / `formation_away` | `roster.formation_home/away` | `"unknown"` | `in {"4-3-3",...}` | A8 branch, A10 branch | Confidence-prior branch only — does NOT prevent firing. Low severity. |
| `elo_diff` | `PreMatchPriors.elo_diff` | `0.0` | `abs(elo) >= 25.0` | `_choose_dominant_team_id` ELO tier | **ELO dominant-team tier permanently dead.** Falls through to market/lambda signal. |
| `role_signal` | `roster.recent_subs_5min[].role_signal` | `"unknown"` | `== "defensive"` | A4 | **A4 never fires.** No positional role source for substitution events. |

---

## Recommendations

### (a) Kill or feed A6 and A9

**A6 (CARDS_MOMENTUM_STRICT_REF)** and **A9 (KEY_PLAYMAKER_OFF)** are completely inert.

- **Kill option:** Remove from `_ARCHETYPE_DETECTORS` (same treatment as A11). Keep functions for
  reference. Document that the market (cards) or thesis (under/creator) requires a data feed
  that doesn't exist yet.
- **Feed option:** For A6 — source referee historical cards-per-game from a static lookup table
  (referee name from Sportmonks match details) populated from API-Football or scraped data.
  For A9 — derive from player substitution events + a player-importance score (minutes played
  season YTD, key_passes ranking). Both require a one-time data pipeline; without it, kill.

**Recommended near-term: Kill both until the data feed is ready.** One dead archetype contributes
zero picks and consumes zero marginal cost; the risk is misleading `generate_theses` coverage
stats (we appear to have 12 live detectors when we have 10).

### (b) Remove dead formation/elo branches or wire real data

**A8 and A10 formation branches:** Both check `formation_home in {"4-3-3",...}` or
`formation_changes` — both always evaluate to False. These branches only affect `confidence_prior`
(±0.08 delta), not the firing decision. Options:

- **Simplify (low risk):** Remove the branch; use the lower confidence_prior unconditionally.
  This matches observed production behavior and removes dead code.
- **Wire (future):** Sportmonks `/api/v3/fixtures/{id}?include=lineup` returns formations after
  kickoff. Query it once at lineup confirmation (~15 min before KO) and cache. Not in production
  today; add when the lineup endpoint is wired for A8/A10 intent.

**ELO tier in `_choose_dominant_team_id`:** `PreMatchPriors.elo_diff` defaults to 0.0 and the
threshold is 25.0. The ELO tier is the highest-priority dominant-team resolver but always falls
through. Options:

- **Populate:** Source ELO from a static file (club-ELO API, open dataset) or compute from
  league-standings points. The resolver is already written — just needs the data.
- **Remove the tier:** If no feed is planned, remove the ELO branch to match actual behavior.
  Currently the market-signal tier handles 100% of cases and has performed acceptably.

**Recommended:** Populate ELO from a static dataset (low effort, highest-priority resolver is
correct to put ELO first when available). Remove the dead formation branches until the lineup
endpoint is wired.

### (c) Heuristic proxies — acceptable vs risky

| Signal | Proxy Used | Acceptable? | Risk |
|--------|-----------|-------------|------|
| xg_diff | shots * shot-quality weights | ACCEPTABLE | xG is routinely approximated; stable across top leagues. |
| xg_vs_score_divergence | xg_diff minus conditional-on-score table anchor | ACCEPTABLE | Table anchored empirically; known residual ~0.3 xG MAE. |
| xg_per_min_last_15 | corner and shot events in last 15 min | ACCEPTABLE | Sufficient granularity for cruise-mode threshold. |
| tactical.game_phase / home_phase / away_phase | shot-rate + possession bins | RISKY | Binary bins are noisy at bin edges. A3 and A12 fire on this; A7 also depends on it. Monitor precision: if the archetype fires correctly <40% in CLV measurement, the heuristic needs tightening or a confidence-prior reduction. |
| dominant_team_id (market-signal tier) | implied-probability gap from bookmaker odds | ACCEPTABLE | Market is the sharpest available signal. Gap threshold (4 pp) is empirically tuned. |
| numerical_advantage | derived from red_card_events list | ACCEPTABLE | Directly counted from live event stream; no approximation. |

**Summary:** The xG and numerical proxies are acceptable. Tactical phase is the highest-risk
heuristic — it drives A3, A7, and A12, all of which produce corners or goals picks. Prioritize
CLV measurement for these three archetypes once the CLV sink (Wave 2 #1) is live.
