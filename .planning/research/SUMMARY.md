# Research Summary -- betting-intelligence-platform

**Project:** betting-intelligence-platform
**Domain:** Multi-sport betting intelligence (football-first, plugin architecture)
**Researched:** 2026-04-22
**Confidence:** HIGH

## TL;DR

- **CLV infrastructure must be in Phase 1**, not deferred. It is the primary success metric and every downstream decision (model selection, calibration strategy, market focus) depends on it. All four research documents independently confirmed this.
- **Python 3.12, not 3.11.** PROJECT.md says "3.11+"; research confirms 3.12 is the correct pin. All ML libraries support it, 10-15% perf gain over 3.11, and 3.13+ is blocked by CatBoost wheel lag.
- **Timed corners needs a hard go/no-go gate before Phase 3 engineering.** Verify exact Betano time-window corner markets AND API-Football minute-level corner data availability for 3+ seasons across all 5 leagues. Without both, the module has no viable deployment target.
- **Claude Role C (validator) should ship before Role B (confidence modifier).** Role C is a safety gate on existing picks -- low risk, immediate value. Role B adds a novel ML feature that requires backtesting validation before production use.
- **Account longevity (Betano) is an existential risk.** Stake rounding, market rotation, and withdrawal pacing must ship in Phase 1's delivery layer, not as a "later" enhancement.

## Stack Recommendations

### Confirmed Choices

The core stack from PROJECT.md is validated. Python gradient boosting ensemble + Polars + Supabase is the standard 2025-2026 sports betting ML stack.

**Core technologies (confirmed with version pins):**
- **Python 3.12** (not 3.11): all ML libraries green, measurable perf gains, CatBoost blocks 3.13+
- **uv 0.11.x**: de facto package manager, replaces pip/poetry
- **XGBoost 3.2.0 + CatBoost 1.2.10 + LightGBM 4.6.0**: ensemble trio, all stable on 3.12
- **scikit-learn 1.8.0**: `CalibratedClassifierCV(cv="prefit")` removed (already handled), new `method="temperature"` worth evaluating
- **Polars 1.40.x + PyArrow 19.x**: feature engineering, 10-50x faster than pandas
- **penaltyblog 1.9.0**: Dixon-Coles, Bivariate Poisson, Cython-optimized, actively maintained (6 releases in 2025-2026). Best option for football statistical models -- no viable alternative.
- **APScheduler 3.11.x**: NOT 4.x (still alpha 4.0.0a6). In-process scheduler, no Redis/broker needed.
- **python-telegram-bot 22.7**: async-native, de facto standard
- **httpx 0.28.1**: async HTTP client for all API calls
- **Anthropic SDK (latest)**: claude-sonnet-4-6 for both Role B and Role C

### Changes from PROJECT.md

| Item | PROJECT.md | Research Recommendation |
|------|-----------|------------------------|
| Python version | 3.11+ | **Pin to 3.12** (not 3.11, not 3.13) |
| APScheduler | unspecified | **3.11.x** (avoid 4.x alpha) |
| Pinnacle odds | implied direct API | **The Odds API v4** (Pinnacle shut down public API July 2025; website-scraped odds still available via The Odds API with 1-5 min delay -- acceptable for CLV) |

### Additions (not in PROJECT.md)

- **tenacity 9.x**: retry/backoff for API calls -- production essential
- **structlog 25.x**: structured JSON logging for pick-to-alert tracing
- **ruff 0.11.x**: linting + formatting (replaces flake8 + black + isort)
- **pytest 8.x + pytest-asyncio 0.25.x**: testing framework

## Feature Priorities

### Must Have (Table Stakes)

1. **Calibrated probability outputs** -- calibration > accuracy for betting (69.86% higher returns per ScienceDirect research)
2. **EV calculation + bet filtering** (min 5% edge) -- core value proposition
3. **CLV tracking against Pinnacle** -- single best predictor of long-term profitability
4. **Quarter-Kelly stake sizing** with account longevity protections (rounding, rotation)
5. **Walk-forward backtesting** -- only honest evaluation method
6. **Multi-market probability support** (1X2, O/U, BTTS, AH)
7. **Automated pre-match data pipeline** (2h and 30min pre-kickoff)
8. **Structured pick logging** with model version and feature hash

### Should Have (Differentiators)

1. **Claude AI pick validation (Role C)** -- red flag detection against learnings.md, ships before Role B
2. **Account longevity protection system** -- stake rounding, market rotation, withdrawal pacing
3. **CLV decomposition** (by league, market, timing, model version)
4. **Consensus scoring** (ensemble + goals model agreement)
5. **Model versioning with A/B shadow testing**
6. **Sport-agnostic plugin architecture** validated with tennis scaffold

### Defer to Phase 3+

1. **Claude AI confidence modifier (Role B)** -- requires backtesting validation first
2. **Timed corners module** -- requires market verification gate
3. **Steam move detection** (Pinnacle line movement monitoring)

### Anti-Features (Do Not Build)

- Web dashboard/UI, automated bet placement, real-time in-play pipeline
- Multi-bookmaker arbitrage, progressive staking systems, social/multi-user features
- Sentiment analysis, GPU deep learning, odds scraping from websites

## Architecture Decisions

### Three-Layer Pipeline with Plugin Spine

The architecture is a **unidirectional pipeline** (Data -> Intelligence -> Delivery), not independent services. The 2h pre-kickoff window is the hard constraint -- data must flow through all three layers within this time budget.

**Single process + systemd deployment is correct.** One Python process on a Hetzner CPX21 VPS (3 vCPU, 4GB RAM, ~7 EUR/mo). No microservices, no Docker initially, no container orchestration. For a single-user system processing 5-10 fixtures/day, microservices add latency and failure modes for zero benefit.

**Major components:**

1. **APScheduler (AsyncIOScheduler)** -- orchestrates all jobs (pre-kickoff, CLV snapshot, post-match, metrics)
2. **Plugin Registry** -- discovers SportPlugin implementations via decorator registration
3. **Football Plugin** -- implements SportPlugin ABC (API client, feature pipeline, ML models)
4. **EV Engine** -- sport-agnostic, operates on ProbabilityMap + OddsMap
5. **Kelly Sizer** -- quarter-Kelly with account longevity rounding
6. **Claude Augmenter** (Role B) -- pre-prediction confidence modifier as ML feature
7. **Claude Validator** (Role C) -- post-prediction safety gate against red flags
8. **CLV Tracker** -- records Pinnacle closing odds, computes per-bet and aggregate CLV
9. **Telegram Bot** -- async alert delivery in same event loop as scheduler
10. **Parquet Store** -- Hive-partitioned feature cache for dual-use (backtesting + inference)

**Key patterns to follow:**
- Pydantic for all cross-component data (no raw dicts crossing boundaries)
- Async all the way down (httpx + telegram bot + APScheduler share one event loop)
- Graceful degradation (Claude down -> modifier=0.0, Odds API down -> no CLV but picks still send)
- One `build_features()` method for both training and inference (prevents training-serving skew)

**Key anti-patterns to avoid:**
- Separate training and inference feature code (guaranteed skew)
- Claude as probability source (LLMs are not calibrated)
- Real-time bookmaker odds as ML features (circular -- you'd learn to mimic bookmakers)

## Critical Pitfalls to Avoid

Ranked by severity and probability of occurrence:

### 1. Measuring Accuracy Instead of CLV (CRITICAL)

A model can be 52% accurate but +4% CLV (profitable) or 58% accurate but -2% CLV (unprofitable). The entire pipeline must optimize for CLV from day one. Every backtest fold must compute simulated CLV. Model selection criterion: positive CLV on OOS folds. **Prevention:** CLV recording infrastructure in Phase 1.

### 2. In-Sample Calibration Masquerading as Improvement (CRITICAL)

Isotonic calibration overfits with <200 samples per fold per league. The existing project's `calibrate_by_league_wf()` produced logloss 0.97 -> 1.6+ (catastrophic). **Prevention:** Use Platt (sigmoid) calibration for per-league calibration where league sample sizes are under 300. PROJECT.md assumes isotonic everywhere -- this must be corrected.

### 3. Betano Account Restriction (CRITICAL, EXISTENTIAL)

Consistent winning patterns trigger automated restriction within weeks. Reports show limits dropped to under $2/bet. **Prevention:** Stake rounding to nearest 5, market rotation, occasional recreational-looking bets, max 75% of offered limits, staggered withdrawals. Must be in Phase 1 delivery layer.

### 4. Data Leakage in Feature Engineering (CRITICAL)

Football-specific leakage is insidious: aggregate season stats including target match, Elo ratings computed with future matches, odds features that moved post-prediction. **Prevention:** Strict `as_of_date` parameter in every feature computation. One `build_features()` for training and inference.

### 5. Walk-Forward Backtesting Producing Optimistic Results (CRITICAL)

Backtests systematically overestimate: testing against closing lines (not opening), hyperparameter selection across all folds, ignoring execution slippage. **Prevention:** Backtest against OPENING odds with 1-2% slippage from day 1. Do not retrofit this later.

## What Research Changed

Research challenged or modified several PROJECT.md assumptions:

| PROJECT.md Assumption | Research Finding | Action |
|----------------------|-----------------|--------|
| Python 3.11+ | **Pin to 3.12.** 3.11 works but 3.12 has 10-15% perf gains. 3.13+ blocked by CatBoost. | Update constraint |
| Isotonic calibration per league | **Use Platt for leagues with <300 validation samples.** Isotonic overfits catastrophically with small samples. | Correct calibration strategy |
| Role B and Role C ship together | **Ship Role C (validator) first.** Role B (confidence modifier) needs backtesting to prove it improves calibration. Role C is independent of model training. | Reorder Claude integration |
| Timed corners as Phase 3 | **Add hard go/no-go gate.** Must verify (a) exact Betano time-window markets and (b) API-Football minute-level corner data for 3+ seasons before committing. | Add prerequisite gate |
| CLV tracking as one of many features | **CLV is THE primary metric.** Must be in Phase 1, not Phase 4. All model selection and calibration decisions depend on CLV. | Elevate to Phase 1 |
| Account longevity as nice-to-have | **Existential risk.** Betano restricts accounts within weeks. Stake camouflage must ship with first pick. | Elevate to Phase 1 delivery |
| Pinnacle direct API | **Pinnacle shut down public API July 2025.** Use The Odds API v4 which still provides Pinnacle odds via website scraping (1-5 min delay, acceptable for CLV). | Update data source strategy |
| APScheduler version unspecified | **Use 3.11.x, NOT 4.x.** 4.0 is still alpha with breaking API changes. | Pin version |

## Open Questions for Roadmap

### Hard Gates (Must Resolve Before Phase Commitment)

1. **Timed corners market verification (before Phase 3):** Does Betano offer time-window-specific corner props (e.g., "first corner before 10 min"), or only standard O/U and half-specific markets? If only standard markets, the timed-window model's alpha opportunity shrinks significantly.

2. **API-Football corner timing data (before Phase 3):** Does API-Football provide minute-level corner event data for all 5 leagues for at least 3 seasons? If not, training data is insufficient for the corners model.

3. **The Odds API Pinnacle freshness (Phase 1 validation):** Post-shutdown, Pinnacle odds come from website scraping. Measure actual closing line delay during data pipeline setup. If >10 minutes consistently, pivot to Betfair Exchange as CLV benchmark.

### Decisions to Make During Implementation

4. **Temperature scaling vs isotonic vs Platt:** scikit-learn 1.8 adds `method="temperature"` (1 parameter, less overfitting). Empirically test all three during ML phase. Recommendation: Platt for <300 samples, isotonic for >500, temperature as a new candidate for all sizes.

5. **APScheduler AsyncIOScheduler vs BackgroundScheduler:** If running telegram bot's asyncio event loop, must use AsyncIOScheduler. Needs integration testing -- two async loops can conflict.

6. **Claude model for Role B:** Research suggests Haiku for confidence_modifier (fast, cheap, deterministic extraction task) and Sonnet for validator (reasoning quality matters). Cost difference is marginal at this volume (~$0.80/day total).

7. **CatBoost Polars direct input:** CatBoost 1.2.10 claims Polars support. Verify end-to-end to avoid unnecessary Polars-to-NumPy conversions in the feature pipeline.

## Implications for Roadmap

### Suggested Phase Structure

Based on dependency analysis across all four research documents:

### Phase 1: Foundation + Data Pipeline + CLV

**Rationale:** Everything downstream depends on the plugin interface, storage layer, data pipeline, and CLV infrastructure. CLV must be recorded from the very first prediction to establish baselines.

**Delivers:**
- SportPlugin ABC + Plugin Registry
- Football Plugin: API-Football async client, fixture/stats/lineups/injuries/H2H
- Parquet Store (Hive-partitioned, port from Football_analysis)
- Supabase client + migration 002 (sport column)
- Settings/config (pydantic-settings, YAML league configs)
- CLV recording infrastructure (The Odds API integration, Pinnacle closing line capture)
- Validate Pinnacle data freshness via The Odds API

**Addresses features:** Automated pre-match data pipeline, structured pick logging foundation, CLV tracking infrastructure
**Avoids pitfalls:** CLV deferred as "later" work (Pitfall 1), API-Football data gaps discovered late (Pitfall 9)

### Phase 2: ML Core + Backtesting

**Rationale:** Features must exist before models can train. Backtesting framework must include slippage and opening odds from day one -- retrofitting this is a common and costly mistake.

**Delivers:**
- Feature engineering pipeline for football (port from football-predictor, Polars)
- Parquet cache integration with point-in-time stamps (`as_of_date`, `computed_at`)
- Walk-forward backtesting with opening odds + 1-2% slippage
- XGBoost + CatBoost + LightGBM ensemble training
- Calibration: Platt for leagues <300 samples, isotonic for >500, evaluate temperature scaling
- Model versioning (directory layout + metadata.json)
- ProbabilityMap output conforming to SportPlugin interface

**Addresses features:** Calibrated probability outputs, walk-forward backtesting, multi-market probability support
**Avoids pitfalls:** In-sample calibration overfitting (Pitfall 2), data leakage (Pitfall 4), optimistic backtests (Pitfall 5)

### Phase 3: Pick Engine + Delivery (with Account Protection)

**Rationale:** EV engine and Kelly sizing require calibrated probabilities from Phase 2. Account longevity features MUST ship with the first pick -- not as a later enhancement.

**Delivers:**
- EV Engine (sport-agnostic, port from Claude_Sport_Betting)
- Kelly Sizer (quarter-Kelly, max stake cap)
- Account longevity layer: stake rounding to nearest 5, market rotation tracking, max 75% of offered limits
- Telegram Bot: pick alerts with odds, edge, stake, confidence, reasoning
- Claude Validator (Role C): red flag check against learnings.md before delivery
- Supabase: persist predictions, picks, odds snapshots
- Post-match result collection and CLV recording loop

**Addresses features:** EV calculation + filtering, Kelly sizing, Telegram alerts, Claude pick validation (Role C), account longevity protection
**Avoids pitfalls:** Betano account restriction (Pitfall 3), Telegram delivery timing (Pitfall 10)

### Phase 4: Orchestration + Production Deployment

**Rationale:** Orchestration wires together what already works from Phases 1-3. Do not attempt to deploy before all pipeline stages are individually tested.

**Delivers:**
- APScheduler 3.11.x: pre_kickoff_2h, pre_kickoff_30m, clv_snapshot, post_match, daily_metrics, weekly_drift_check
- End-to-end pipeline runner (core/pipeline.py)
- Graceful degradation (Claude down, Odds API down, one league fails)
- Health monitoring (heartbeat file + systemd timer)
- systemd service file for Hetzner VPS
- Performance metrics aggregation (ROI, CLV by league/market/period)
- CLV trend alerting (rolling 30-day CLV < +1% triggers pause)

**Addresses features:** Performance tracking, CLV decomposition, drift detection
**Avoids pitfalls:** Claude API as production bottleneck (Pitfall 8)

### Phase 5: Claude Confidence Modifier (Role B) + Shadow Testing

**Rationale:** Role B adds a novel ML feature. It must be validated via backtesting before production use. Ship Role C first (Phase 3), validate Role B in shadow mode, then promote.

**Delivers:**
- Claude Augmenter: confidence_modifier (-0.15 to +0.15) as ML feature
- Response caching by fixture ID for backtest reproducibility
- Shadow mode: Role B predictions logged but not acted upon
- Backtesting comparison: ensemble with modifier vs without
- Promotion gate: modifier must improve OOS CLV to go live
- Model retraining with modifier as feature (if validated)

**Addresses features:** Claude AI confidence modifier (Role B), model A/B shadow testing
**Avoids pitfalls:** "Claude Knows Football" assumption (Anti-Pattern 3), non-deterministic outputs breaking backtests (Pitfall 8)

### Phase 6: Timed Corners Module (Conditional)

**Rationale:** Highest alpha potential but highest uncertainty. Hard go/no-go gate required BEFORE engineering investment.

**Go/no-go prerequisites (resolve before committing):**
1. Betano offers time-window-specific corner props (not just standard O/U)
2. API-Football provides minute-level corner data for 5 leagues, 3+ seasons
3. Baseline model (per-team, per-league average corners per window) shows >5% MAE improvement is plausible

**Delivers (if gate passes):**
- Corner timing data ingestion by time window
- Compound Poisson or negative binomial distribution model (not standard Poisson)
- Per-team corner timing profiles
- EV check for corner window picks
- Integration into pick engine and Telegram alerts

**Addresses features:** Timed corners module, novel niche edge
**Avoids pitfalls:** Corner models that don't generalize (Pitfall 6), building before market verification

### Phase 7: Tennis Scaffold (Architecture Validation)

**Rationale:** Validates that SportPlugin ABC is truly sport-agnostic. If any core changes are needed, this reveals architectural debt early.

**Delivers:**
- Tennis SportPlugin skeleton
- Verification: zero core/ changes required
- If refactor needed, do it now before more sports are added

### Phase Ordering Rationale

- **Phase 1 -> 2 -> 3:** Strict dependency chain. Data pipeline feeds features, features feed models, models feed picks.
- **CLV in Phase 1, not Phase 4:** All model selection, calibration decisions, and market focus decisions downstream depend on CLV measurement. Without it, you cannot evaluate anything honestly.
- **Account longevity in Phase 3, not deferred:** The first pick delivered without stake camouflage starts the clock on account restriction. This is an existential risk.
- **Role C before Role B:** Role C is a safety gate on existing picks (low risk, immediate value). Role B is a novel ML feature requiring validation (high risk if unvalidated).
- **Corners last and conditional:** Highest engineering investment, highest uncertainty, requires external validation (Betano markets, API-Football data). Gate before committing.

### Research Flags

**Phases likely needing `/gsd-research-phase` during planning:**
- **Phase 2 (ML Core):** Calibration strategy selection (Platt vs isotonic vs temperature) needs empirical testing. Walk-forward with slippage is non-trivial.
- **Phase 5 (Claude Role B):** Novel integration -- no established patterns for LLM confidence modifiers in ML ensembles. Needs careful backtesting design.
- **Phase 6 (Corners):** Academic research exists but real-world deployment references are sparse. Go/no-go gate is the research.

**Phases with standard patterns (skip research-phase):**
- **Phase 1 (Foundation):** Well-documented async API client + Parquet store + Supabase patterns. Existing code to port.
- **Phase 3 (Pick Engine):** EV calculation and Kelly sizing are textbook. Telegram bot integration is well-documented.
- **Phase 4 (Orchestration):** APScheduler 3.x + systemd is a standard deployment pattern.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All libraries verified with version pins, PyPI release dates, compatibility matrices. Pinnacle API shutdown confirmed with documented workaround. |
| Features | HIGH | Grounded in existing project experience, academic research, and professional betting community consensus. CLV methodology validated by Unabated, Pikkit, betstamp. |
| Architecture | HIGH | Three-layer pipeline is standard for ML inference systems. Single-process deployment appropriate for scale. Existing codebase validates component boundaries. |
| Pitfalls | HIGH | Top 5 pitfalls validated by project's own history (calibration overfitting), academic literature (ML betting models fail to beat odds), and real user reports (Betano restrictions). |

**Overall confidence:** HIGH

### Gaps to Address

1. **Pinnacle closing line delay via The Odds API:** Unknown exact delay post-API-shutdown. Must measure empirically in Phase 1. Fallback: Betfair Exchange CLV.
2. **API-Football corner timing granularity:** Documentation says events endpoint includes minute markers, but per-league coverage varies. Must verify for all 5 leagues before Phase 6.
3. **Betano exact corner market offerings:** Must be verified manually (not available via API). This is the Phase 6 go/no-go gate.
4. **Temperature scaling performance:** New in scikit-learn 1.8. No prior evidence from this project's data. Must test empirically against Platt and isotonic.
5. **CatBoost Polars direct input:** Claimed in release notes but not verified end-to-end with this feature pipeline.
6. **APScheduler AsyncIOScheduler + telegram bot event loop integration:** Two async systems sharing one event loop can conflict. Needs integration testing in Phase 4.

## Sources

### Primary (HIGH confidence)
- [ScienceDirect: Calibration vs Accuracy](https://www.sciencedirect.com/science/article/pii/S266682702400015X) -- calibration-optimized models generate 69.86% higher returns
- [Unabated: Getting Precise About CLV](https://unabated.com/articles/getting-precise-about-closing-line-value) -- CLV calculation methodology
- [scikit-learn 1.8 Release Notes](https://scikit-learn.org/stable/auto_examples/release_highlights/plot_release_highlights_1_8_0.html) -- temperature scaling, CalibratedClassifierCV changes
- [APScheduler PyPI / Migration Guide](https://pypi.org/project/APScheduler/) -- 3.x vs 4.x alpha status
- [penaltyblog 1.9.0](https://pypi.org/project/penaltyblog/) -- actively maintained, Cython-optimized
- [Pinnacle API Shutdown](https://odds-api.io/blog/pinnacle-api-shutdown-alternatives) -- July 2025 closure, The Odds API workaround
- [Systematic Review of ML in Sports Betting](https://arxiv.org/abs/2410.21484) -- why ML models fail to beat bookmaker odds
- Project's own MEMORY.md -- `calibrate_by_league_wf()` failure, calibration overfitting documentation

### Secondary (MEDIUM confidence)
- [Swartz et al. (SFU): Corner Kick Timing](https://www.sfu.ca/~tswartz/papers/ckick.pdf) -- temporal distribution of corners
- [ArXiv: Forecasting Corner Kicks](https://arxiv.org/pdf/2112.13001) -- corner prediction modeling
- [Betano Account Limits (SBR Forum)](https://www.sportsbookreview.com/forum/sportsbooks-industry/3729222-betano-warning-wager-limits-lowered-1-50-over-4000-rollover-remaining.html) -- real user restriction reports
- [Hopsworks FTI Pipeline Architecture](https://www.hopsworks.ai/post/mlops-to-ml-systems-with-fti-pipelines) -- Feature/Training/Inference pipeline pattern

### Tertiary (LOW confidence)
- CatBoost 1.2.10 Polars direct input -- claimed in release notes, not independently verified
- Temperature scaling for football calibration -- new method, no prior results from this domain

---
*Research completed: 2026-04-22*
*Ready for roadmap: yes*
