---
spike: tournament-evaluator
slug: national-team-tournament-evaluator
status: phase-0-discovery
created: 2026-05-07
operator: Kevin Beltrán
branch: spike/national-team-tournament-evaluator
graduates_to: TBD (Phase 5 BIP feature OR evaluation-only OR archived)
---

# Spike — National-Team Tournament Stats Evaluator

> **Side-track experimental.** No formal GSD phase entry. Lives under `.planning/spikes/` and only graduates to the ROADMAP if post-Mundial 2026 results justify it.

## 0. Goal

Build a **per-match stats predictor for national-team tournaments** (World Cup 2026 first, then reusable for Euro / Copa América / Africa Cup) that fuses two data sources with explicit weights:

- **A — Team baseline**: per-90 rates from qualifying-stage matches (CONMEBOL, UEFA, AFC, CONCACAF qualifiers) — corners, fouls, shots, shots-on-target, expected goals.
- **B — Player recent form**: per-90 personal rates from each squad member's club football (last N matches), league-strength-adjusted.

The blending formula is:

```
match_prediction = α · TEAM_BASELINE_qualifiers + (1 − α) · LINEUP_AGGREGATE_recent_form
```

where `α` starts at ~0.3–0.4 (player form dominates) and is tuned during Phase 4 backtest.

## 1. Output

Per WC fixture (e.g. Brasil vs Argentina, 2026-06-15):

**Team-level:**
- λ goals (Bivariate Poisson), λ corners (independent Poisson per team), λ shots-on-target per team
- P(BTTS), P(Over 2.5 goals), P(home win / draw / away win)

**Lineup-level (11 starters per side):**
- λ shots per starter
- λ shots-on-target per starter
- P(anytime goalscorer) per starter
- λ fouls committed per starter

Output format: JSON (machine-readable, locked + committed for prospective test) + Markdown report.

## 2. Architecture (Option B — `evaluation/` top-level module)

```
src/bip/evaluation/                         # NEW top-level module (peer of core/, sports/, train/)
├── __init__.py
├── tournaments/
│   ├── models.py                           # Pydantic: Tournament, Group, Match, Squad, Player, Lineup
│   ├── loader.py                           # YAML config loader
│   ├── configs/
│   │   ├── world_cup_2026.yaml             # 48 equipos, 12 grupos de 4
│   │   ├── world_cup_2022.yaml             # backtest
│   │   ├── world_cup_2018.yaml             # backtest
│   │   ├── euro_2024.yaml                  # backtest
│   │   ├── copa_america_2024.yaml          # backtest
│   │   └── _qualifying_leagues.yaml        # API-Football league IDs for each qualifier
│   ├── data/
│   │   ├── qualifying_loader.py            # pull qualifier fixtures + stats per team
│   │   ├── club_form_loader.py             # pull last-N club matches per player
│   │   ├── identity_matcher.py             # canonical player_id ↔ source IDs
│   │   └── league_strength.py              # multipliers EPL=1.0, La Liga=0.97, ...
│   ├── baselines/
│   │   ├── team_rates.py                   # per-90, opponent-adjusted aggregation
│   │   └── opponent_strength.py            # uses ELO from Phase 1
│   ├── players/
│   │   ├── recent_form.py                  # last-N rolling rates per player
│   │   └── lineup_predictor.py             # most-frequent XI heuristic + confirmed-lineups override
│   ├── models/
│   │   ├── base.py                         # Predictor ABC
│   │   ├── elo_logistic.py                 # baseline (sanity)
│   │   ├── bivariate_poisson.py            # penaltyblog wrapper
│   │   └── ensemble_adapter.py             # reusa bip.train con NT features
│   ├── predict/
│   │   ├── match_predictor.py              # composition blender α·team + (1-α)·lineup
│   │   └── output.py                       # JSON + Markdown emitters
│   └── backtest/
│       ├── walk_forward.py                 # point-in-time historical replay
│       └── metrics.py                      # log-loss, Brier, MAE, Poisson deviance, calibration
├── reports/                                # gitignored — regenerable
└── locked_predictions/                     # COMMITTED — pre-tournament locked JSONs

tests/evaluation/
├── test_loader.py
├── test_team_rates.py
├── test_player_form.py
├── test_blender.py
├── test_simulator_tiebreakers.py
└── test_models/
```

**Why peer of `sports/`, not under `sports/football/`:** the spike does not feed picks to the BIP pipeline. It is a measurement harness that consumes `bip.train` models + `bip.sports.football` data sources. Keeping it separate prevents the tournament-format complexity (which fires every 2-4 years) from contaminating the picks pipeline that runs daily.

**G-CODE-04/05 alignment:** the existing audit flagged that `core/scheduler.py` and `core/pipeline.py` were promised by ARCHITECTURE.md but never materialized. The `evaluation/` module avoids this trap by **not** introducing a new ABC or registry — it imports from existing layers and exposes a CLI entrypoint, nothing more.

## 3. Discovery findings (Phase 0 output)

### 3.1 Existing API-Football capabilities (from `src/bip/sports/football/client.py`)

The client currently exposes **7 methods**:

| Endpoint | Method | Use today |
|---|---|---|
| `/fixtures` | `get_fixtures(league_id, date)` | Daily fixture pull |
| `/fixtures/lineups` | `get_lineups(fixture_id)` | T-30min lineup confirmation |
| `/fixtures/statistics` | `get_statistics(fixture_id)` | Match-stats aggregation (corners, fouls, shots) |
| `/injuries` | `get_injuries(league_id, season)` | Pre-kickoff injury check |
| `/fixtures/headtohead` | `get_h2h(team1_id, team2_id)` | H2H feature engineering |
| `/odds` | `get_odds(fixture_id OR league_id+season, bookmaker)` | Pinnacle CLV pull |

### 3.2 Gaps for the spike (NEW endpoints required in Phase 1)

| Endpoint | Needed for | Estimated LOC | Schema notes |
|---|---|---|---|
| `/players/statistics?id={pid}&season={yr}` | Player season aggregates per club | ~30 | Returns `games`, `shots(total,on)`, `goals`, `passes(key,accuracy)`, `fouls(drawn,committed)`, `cards(yellow,red)`, `penalty`, `dribbles`, `tackles` |
| `/fixtures/players?fixture={fid}` | Per-match player stats (for last-N rolling) | ~30 | Returns same shape as above but per-match. Required for rolling form. |
| `/players/squads?team={tid}` | Current national-team roster | ~25 | Returns 23-30 player IDs + positions. Needed pre-tournament. |
| `/teams/statistics?league={lid}&season={yr}&team={tid}` | Team aggregates over qualifier season | ~30 | Returns `fixtures(played,wins,draws,losses,goals_for/against)`, `clean_sheet`, `cards`, `penalty`. Note: corners NOT in this endpoint — must aggregate via `/fixtures/statistics`. |
| `/leagues?id={lid}` | League metadata (country, type=Cup vs League) | ~20 | For league-strength normalization. |

**Total new client surface:** ~135 LOC + ~100 LOC of tests. Mocked fixtures for each endpoint (3-5 per endpoint) per project convention.

### 3.3 Data coverage uncertainties (resolve in Phase 1 with live calls)

- **Player coverage in lower leagues**: API-Football Pro nominally covers 1100+ leagues. But shots-on-target / fouls / key-passes granularity may be missing for J-League, Saudi Pro Leagues, MLS reserves. Verify against 10-team roster sample.
- **xG/xA**: API-Football v3 does **NOT** provide xG/xA natively. Decision deferred — see §3.4.
- **Qualifier coverage**: CONMEBOL and UEFA qualifiers are well-covered. AFC qualifiers (Asian) and CAF (African) qualifiers likely have lineup-data gaps. Verify before relying on them for team baseline.
- **Position labels**: `/fixtures/players` returns `position` as `G/D/M/F` — coarse. For lineup-aggregate weighting we may want to default-merge M with attacking-M based on heatmap data. NOT available natively. **Workaround**: use `position` from `/players/squads` plus club-position from FBref if needed.

### 3.4 Augmentation decision (FBref / StatsBomb open-data / accept gap)

**Decision matrix:**

| Source | What it adds | Friction | Verdict for v1 spike |
|---|---|---|---|
| **API-Football Pro alone** | Goals, shots, SoT, fouls, cards, key-passes, tackles, dribbles, minutes | ZERO (already have) | **YES — primary source** |
| **FBref scraping** | xG, xA, progressive-passes, pressures, SCA/GCA, true heatmap-position | Scraping rate-limit (1 req/3s polite), HTML parsing fragility, ToS gray area | **DEFER to v2** if Phase 4 backtest reveals insufficient calibration |
| **StatsBomb open-data** | Event-level data for past WCs (2018, 2022) including xG by shot-type | Free + clean format | **OPT-IN for Phase 4 backtest only** — validates calibration on WC2022 with high-fidelity ground truth |

**Rationale for deferring FBref:** Poisson modeling on shots and SoT (which we DO have) is the established approach for goal expectation. xG is an enhancement, not a prerequisite. The spike should ship with the smallest possible source surface and graduate to FBref only if calibration on WC2022 is unacceptable.

### 3.5 League-strength multipliers (deferred to Phase 2 with operator input)

The blending of player rates across leagues requires multipliers (per-90 rates in Saudi Pro are NOT comparable to EPL rates). Public sources for league strength:

| Source | Pros | Cons |
|---|---|---|
| Club Elo (clubelo.com) | Updated weekly, league-aggregate ratings derivable | Manual scrape, no official API |
| FiveThirtyEight SPI | Per-league offensive/defensive ratings | Discontinued in 2023 |
| eloratings.net | National-team Elo, indirect club inference | National only |
| Operator domain knowledge | Highest fidelity for "what really matters" | Subjective, harder to defend |

**Decision:** Phase 2 will start with a YAML-configured multiplier table seeded from Club Elo aggregate (top 200 teams) with operator override. The first 10 lines of that YAML are a meaningful Learning-Mode contribution from Kevin.

## 4. Phase plan

| # | Phase | Hours | Hard deadline | Depends on |
|---|---|---|---|---|
| 0 | Discovery (this doc) | ~6h | 2026-05-12 | — |
| 1 | Data ingestion + identity matching | ~8h | 2026-05-20 | Phase 0 |
| 2 | Modeling (3 baselines + blender) | ~12h | 2026-05-30 | Phase 1 |
| 3 | Match output generator | ~4h | 2026-06-03 | Phase 2 |
| 4 | Backtest WC2022 + Euro2024 + Copa2024 | ~8h | 2026-06-08 *(can slip post-Mundial)* | Phase 3 |
| 5 | Mundial 2026 LOCKED predictions | ~3h | **2026-06-08 HARD** | Phase 3 (Phase 4 optional gating) |
| Post | Score predictions vs reality, decide graduation | ~4h | After 2026-07-19 | Phase 5 |

**Mundial 2026 kickoff:** 2026-06-11. Lock by 2026-06-08 gives 3 days for review and avoids being influenced by line movement on opening odds.

**If Phase 4 slips past Mundial:** acceptable. Phase 5 ships uncalibrated predictions with explicit caveat in the locked JSON; Phase 4 results retroactively grade them.

## 5. Risks

| ID | Risk | Mitigation |
|---|---|---|
| R-01 | Player identity reconciliation across sources eats >30% of Phase 1 | Canonical player_id = (api_football_id, FBref_id?, name, dob). Fuzzy match on name+dob+club. Manual override CSV for borderline cases. Don't try to be clever — start with API-Football IDs only and only add FBref if augmentation triggers. |
| R-02 | Lineup prediction wrong 30%+ of the time → predictions become "correct model, wrong inputs" | Use confirmed lineups from `/fixtures/lineups` 60min before kickoff. For locked predictions before Mundial 2026, use most-frequent qualifier XI as proxy and explicitly tag prediction confidence as "lineup-uncertain". |
| R-03 | Sample size for player rates: bench players have <500 minutes → noise dominates | Filter starters to those with ≥600 minutes in last 12 months. Bench predictions use position-average rates instead of personal rates. |
| R-04 | Qualifier opponent strength varies wildly (Brazil-Bolivia ≠ Brazil-Argentina) | Opponent-adjusted rates: per-match observed minus opponent's defensive rate, with shrinkage to global mean for n<5 matches against opponent class. |
| R-05 | API-Football rate limit (300 req/min Pro) crushed by mass player pull | Rate-budget Phase 1 ingestion: 10 teams × 23 players × 3 calls = 690 calls. ~3 minutes single-thread. Acceptable. Cache aggressively to parquet — never re-pull. |
| R-06 | Mundial 2026 format new (12 groups of 4) → no historical analog for backtest | Backtest **stats predictions per match**, not bracket simulation. Match-level metrics (goals, corners, SoT) translate directly across formats. The format only affects which matches are played, not how to predict any one match. |
| R-07 | Spike grows beyond 41 hours and bleeds into Mundial start | If at end of Phase 2 (2026-05-30) timeline shows >5h overrun, drop ensemble_adapter.py (XGB/CatBoost/LGBM) and ship with only Bivariate Poisson + ELO baselines. |

## 6. Out of scope (explicit non-goals)

- **Betting picks**: this spike does NOT generate picks for the BIP Telegram alert pipeline. Output is research/analytics, not actionable wagers.
- **Live in-play prediction**: pre-match only.
- **Tournament outcome simulation** (who wins the cup): the original v1 plan included Monte Carlo bracket simulation. **Removed** — operator scope clarification confirmed the goal is per-match stats, not bracket outcomes. May add in v2.
- **Referee modeling**: cards/fouls predictions ignore referee strictness. Documented gap.
- **Player injury imputation**: if a starter goes down 24h before kickoff, manual lineup override required. No auto-handling.
- **Multi-tournament concurrent runs** (Mundial + Copa same week): not a 2026 concern.

## 7. Success criteria

For Phase 5 (locked predictions to be valuable):

- **Coverage**: ≥90% of group-stage matches (96 matches) have predictions for goals + corners + lineup SoT.
- **Calibration baseline (post-Mundial)**: log-loss for BTTS within 0.05 of bookmaker market median; Brier for anytime-goalscorer top-3 within 0.02.
- **Honest gap reporting**: any match where prediction confidence is low (lineup-uncertain, sub-600-min starters) is flagged in the JSON.

For graduation to BIP Phase 5 feature (post-Mundial decision):

- Locked predictions must beat ELO-baseline Brier by ≥3% across goals/corners/SoT to justify carrying the codebase forward.
- If only Bivariate Poisson beats baseline, the ensemble_adapter is dropped.
- If neither beats baseline, the spike archives as a "tried, didn't work" learnings doc and `evaluation/` module is removed.

## 8. Decisions log (this spike)

| Date | Decision | Reason |
|---|---|---|
| 2026-05-07 | Architecture: `src/bip/evaluation/` peer module (Option B) | Keeps tournament-format complexity out of picks pipeline; doesn't amplify Plugin Registry debt (G-CODE-05/06) |
| 2026-05-07 | Three baseline models: ELO+logistic, BivariatePoisson, ensemble adapter | Smallest sample where overfitting risk is real → comparison is the only honest answer |
| 2026-05-07 | Granularity: equipo + 11 titulares (NOT 23 convocados) | Bench predictions are noise dominated; titulares give 80% of the signal |
| 2026-05-07 | Priority markets: goles+BTTS, córners (totales y por equipo), SoT + goleadores | Operator priority; covers liquid markets (goals) and inefficient markets (player props) |
| 2026-05-07 | xG/xA augmentation: deferred to v2 | API-Football lacks xG natively; FBref scraping adds friction without proving Phase 1 value |
| 2026-05-07 | Source surface: API-Football alone for v1; StatsBomb open-data only for Phase 4 historical validation | Smallest possible scope; augmentation gated by calibration results |
| 2026-05-07 | Locked predictions deadline: 2026-06-08 | 3 days before Mundial kickoff, prevents being influenced by opening-odds movement |

## 9. Open questions for the operator (Learning-Mode contributions)

These are the points where operator domain input shapes the model — collect during Phases 1-2:

1. **League strength multipliers** (Phase 2): seed the `league_strength.py` YAML with your subjective ranking. ~10 lines, pure domain knowledge.
2. **Lineup heuristic priors** (Phase 2): when most-frequent-XI is ambiguous (3+ candidates with similar minutes), what's the tiebreaker? Form? Manager pattern recognition?
3. **Confidence threshold for "lineup-uncertain" tag** (Phase 3): when do we explicitly down-rank a prediction because the XI is unstable?
4. **α blending coefficient** (Phase 2): the team-baseline-vs-player-form weight. Initial value 0.3 is a guess. Backtest will tune it.

## 10. References

- [API-Football v3 docs](https://www.api-football.com/documentation-v3) — endpoint reference
- [penaltyblog Bivariate Poisson](https://github.com/martineastwood/penaltyblog) — football match modeling
- [StatsBomb open-data](https://github.com/statsbomb/open-data) — WC2018, WC2022, Euro2020, Euro2024 event data
- [Club Elo](http://clubelo.com) — league-strength inference
- [Existing BIP audit findings](.planning/AUDIT-GAPS.md) — informed the "Option B" architecture decision (no new plugin/registry deuda)
