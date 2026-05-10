# Spike — Live edge with Sportmonks (14d trial)

**Branch:** main (commits authored 2026-05-09)
**Trial window:** 2026-05-09 → 2026-05-23
**Driver:** operator authorised "via libre" exploration after rolling-origin CV closed the WC2026 calibration spike with `1X2 Brier=0.2156 [CI 0.2027-0.2290]`. Pre-match edge against modern bookmakers is structurally hard; live edge is mathematically more accessible because bookmaker pricing models run with tight latency budgets.

---

## Decision log

| Date | Decision | Why |
|---|---|---|
| 2026-05-09 | Pick Sportmonks over OpenLigaDB / Betradar / OptaScout for the trial | Pro tier with `inplayOdds`, `predictions`, `xGFixture`, `pressure` already attached to operator's account; no integration risk for 14d window |
| 2026-05-09 | Use semicolon (`;`) include separator instead of comma | httpx URL-encodes commas → Sportmonks reads `participants,state,scores` as a single literal include name, returning 404 |
| 2026-05-09 | Trust Sportmonks predictions as a strong baseline rather than re-implement | They emit 29 markets (1X2, BTTS, OU 1.5/2.5/3.5, HT/FT, First Half Winner, Correct Score, Double Chance, per-team OU 0.5-3.5, Team To Score First, ValueBet). Competing head-on with their pre-match ML is a losing battle |
| 2026-05-09 | Use Dixon-Robinson scaling for live remaining-time markets, not naive Sportmonks pre-match overlay | Bug found at session start: `_fulltime_result` was returning Sportmonks pre-match P(home)=0.44 at minute 99 of a 1-2 game where reality was P(away)=0.95+. Bivariate Poisson grid over (additional_home_goals, additional_away_goals) + add to current score → realistic conditional probabilities |
| 2026-05-09 | Per-team λ derived from Sportmonks OU 0.5: `λ_full = -ln(1 − P(over_0.5))` | Closed-form invertible from the data Sportmonks already emits. No need for separate xG endpoint (which returned empty for our recon fixture) |
| 2026-05-09 | Fixed-position xG-proxy weights for shot-quality fallback | Big chance ≈ 0.20 incremental over inside-box ≈ 0.05 incremental over shots-on-target ≈ 0.07. Used only when Sportmonks does NOT populate xGFixture for the league — a backstop, not primary signal |
| 2026-05-09 | ¼ Kelly with 1.5% stake cap as default | Carry-over from CLAUDE.md account-safety mandate (`MAX_KELLY_FRACTION` already in Settings model) |
| 2026-05-09 | Edge threshold 3% pre-match, lower for live exploration | Live odds margin tends to be tighter (single bookmaker, mansionbet). Real-world Betano margins higher → edge will compress when re-tested against the actual bookmaker |
| 2026-05-09 | Capture loop is separate from live_picks runner | Captures all in-play snapshots regardless of whether picks emit. Gives backtest a corpus of replayable matches. ~21 calls/round × 120 rounds/h = 2,520 calls/h, under the 3,000 cap |

---

## Architecture

```
Sportmonks v3 API
  │
  ├── /livescores/inplay     ──► live fixture list (poll cada 10s)
  ├── /fixtures/{id}          ──► snapshot with includes
  │                                (statistics, predictions, trends,
  │                                 pressure, events, lineups)
  ├── /predictions/...        ──► 29 markets pre-built
  └── /odds/inplay/fixtures   ──► live bookmaker odds (42 markets)
        │
        ▼
src/bip/sports/football/sportmonks/
    client.py     — async httpx wrapper, rate-limit aware
    schemas.py    — Pydantic v2 frozen models, extra='ignore'
    types.py      — StatType / PredictionType / MarketID enums (verified
                    against /core/types pull, 725 types in catalog)
    cache.py      — file-system snapshot store
        │
        ▼
src/bip/evaluation/live/
    match_state.py    — LiveMatchState frozen dataclass
                          (score, minute, stats indexed by type_id,
                           pressure window, predictions cache,
                           goal/red-card events)
    predictor.py      — LiveMatchPredictor
                        ├── Sportmonks pre-match probs (the prior)
                        ├── Dixon-Robinson scaling for live remainder
                        │     λ_team_remaining = -ln(1-P(over_0.5)) × (90-min)/90
                        │     Bivariate Poisson grid (ρ=0.04 default)
                        │     P(final outcome | current_score, λ_remaining)
                        ├── Pressure nudge (±5pp cap, |diff|>25 trigger)
                        └── BTTS conditioning on which team has scored
    value_detector.py — ValueDetector → LivePick
                        ├── EV = P × decimal_odd − 1
                        ├── ¼ Kelly stake, capped 1.5% bankroll
                        └── Filter: suspended/stopped, odd∈[1.20, 8.00]
        │
        ▼
scripts/spike/sportmonks/
    live_picks.py     — one-shot or loop scanner; markdown + JSON reports
    capture_loop.py   — background snapshot recorder
    backtest.py       — replay cached snapshots, grade vs final outcome
```

---

## Validation results (2026-05-09 night)

### Live scan #1 (single shot, edge ≥ 1%)
- 8 fixtures in play
- 13 value picks emitted across 4 fixtures
- Top: Lanús vs Argentinos Juniors min 56, **EV +145%** (Doble Oportunidad X2 @ 3.75 vs our 0.94 prob)
- Caveat: Single bookmaker (mansionbet) via Sportmonks bookmaker_id=2. Real-world Betano edges will be 30-60% smaller after margin compression.

### Dixon-Robinson sanity
| Scenario | Pre-fix predictor | Post-fix predictor (Dixon-Robinson) |
|---|---|---|
| 0-0 minute 5 (balanced match) | P(home) ≈ 0.40 (correct) | P(home) ≈ 0.40 (unchanged) |
| 1-2 minute 99 (1-2 game) | **P(home) ≈ 0.44 (WRONG)** | **P(home) = 0.001, P(away) = 0.998** |
| 1-0 minute 85 (home leads) | P(home) ≈ 0.55 (under) | P(home) ≈ 0.78 (correct) |

### Tests
- 55 new Layer-1 tests across schemas, match_state, predictor, value_detector
- Suite total: 878 passing (was 823), 6 xfailed unchanged

---

## What's working

1. **End-to-end pipeline runs in ~5 seconds** for 8 in-play fixtures (Sportmonks API + pre-built predictions + Dixon-Robinson + value detection + reports)
2. **Predictor is realistic in late-game scenarios** — properly conditions on (current_score, remaining_minutes)
3. **Sportmonks predictions are pre-built and cover all markets** — no need to build separate models for HT/FT, First Half Winner, OU 1.5, etc. We add value via live state conditioning, not by competing on the ML
4. **Capture loop accumulates snapshots** at 30s cadence, ~3-5s API time per fixture, well under rate limits
5. **Backtest framework works** — needs only completed-match snapshots to start producing real ROI / hit-rate numbers

---

## What's NOT yet validated

1. **Real edge against operator's actual bookmaker** (Betano). Sportmonks bookmaker_id=2 is mansionbet; their margins differ. Need to add a second odds source (The Odds API or scraping Betano) for true edge measurement.
2. **Pick survival under live limits**: bookmakers limit accounts that hit live edges fast. Manual placement is required for the trial; automated alerts come post-validation.
3. **Real-data backtest** — current cache has only partial-match snapshots from 2026-05-09 reconnaissance. Need 2-3 days of capture_loop running during European prime-time to accumulate completed matches for grading.
4. **xG signal quality** — `xGFixture` include returned empty for our reconnaissance fixture. Big Chances Created/Missed proxy is reasonable but unverified against ground truth.

---

## Outstanding work for the trial window (2026-05-09 → 2026-05-23)

| # | Task | Hours | Priority |
|---|---|---|---|
| 1 | Run capture loop continuously for 3-5 days during European matches (Sun afternoons + UCL/UEL nights) | 0 (background) | HIGH — unlocks backtest |
| 2 | Add Betano scraper or Pinnacle live odds source as a second feed for honest edge measurement | 6h | HIGH |
| 3 | Validate xGFixture include on a top-5 European league fixture (Premier, La Liga, etc.) | 1h | MEDIUM |
| 4 | Run backtest after 100+ completed-match snapshots accumulated → first honest ROI verdict | 2h (after data) | HIGH |
| 5 | Telegram alert wiring (re-use Phase 3 plumbing from main BIP roadmap) | 4h | LOW (manual placement OK during trial) |
| 6 | Stop-loss + bankroll tracker integration | 3h | LOW |

---

## How to run

```bash
# One-shot scan with default thresholds
uv run python -m scripts.spike.sportmonks.live_picks

# Tighter edge filter (more conservative)
uv run python -m scripts.spike.sportmonks.live_picks --min-edge 5.0

# Loop every 60 seconds for 1 hour
uv run python -m scripts.spike.sportmonks.live_picks --interval 60 --duration 3600

# Background capture for 4 hours, snapshot every 30s
uv run python -m scripts.spike.sportmonks.capture_loop --interval 30 --duration 14400

# Replay everything cached and grade against final outcomes
uv run python -m scripts.spike.sportmonks.backtest
```

Output:
- `reports/sportmonks_live/picks_*.md` — human-readable picks per scan
- `reports/sportmonks_live/picks_*.json` — machine-readable for downstream
- `reports/sportmonks_backtest/backtest_*.json` — backtest aggregate metrics
- `data/cache/sportmonks/snapshots/{fixture_id}/{ts}.json` — replay corpus

---

## Decision after trial (2026-05-23)

If 100+ completed-match backtest shows:
- **ROI ≥ +5% net of bookmaker margin** AND **Win rate within ±2pp of expected** → upgrade to Sportmonks Pro paid plan + add Betano scraper + Telegram alerting (Phase 3 wiring)
- **ROI ≥ +1% but variance high** → continue capturing, evaluate after 30d
- **ROI ≤ 0%** → cancel trial before charge, archive spike, re-evaluate predictor architecture

The trial is a no-loss experiment: best case, we have a working live-edge system; worst case, we know empirically that this combination of Sportmonks predictions + Dixon-Robinson scaling + ValueDetector doesn't beat the books, and we save €120/mo by not subscribing.
