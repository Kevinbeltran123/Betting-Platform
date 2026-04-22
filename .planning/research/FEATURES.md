# Feature Landscape

**Domain:** Multi-sport betting intelligence platform (football-first, plugin architecture)
**Researched:** 2026-04-22
**Overall confidence:** HIGH (grounded in existing project context, academic research, and professional betting community consensus)

## Table Stakes

Features users expect. Missing = system is not credible as a serious betting tool.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Calibrated probability outputs | Calibration > accuracy for betting (69.86% higher returns vs accuracy-optimized models per ScienceDirect research). Without calibration, EV calculations are garbage. | Med | Isotonic calibration per league already proven in football-predictor (4-6% improvement). Walk-forward validation mandatory to avoid in-sample leakage. |
| Expected Value (EV) calculation | Core of any edge-detection system. No EV = no way to know if a bet has edge. | Low | `edge = model_prob - implied_prob`. Min threshold (+5% per PROJECT.md) filters noise. Already exists in Claude_Sport_Betting repo. |
| CLV tracking against Pinnacle | The single best predictor of long-term profitability. Sharps consistently beating closing line by +1-2% are profitable. Without CLV, you cannot distinguish skill from luck. | Med | Record bet odds at placement, fetch Pinnacle closing odds post-match via The Odds API. +3% CLV target per PROJECT.md is ambitious but correct for non-major-market bets. |
| Kelly criterion stake sizing | Professional standard for bankroll growth optimization. Without it, stake sizing is arbitrary. | Low | Quarter-Kelly max (PROJECT.md constraint). Must handle edge uncertainty -- fractional Kelly protects against probability estimation errors. |
| Walk-forward backtesting | Only honest evaluation method. Any model without proper temporal validation is suspect. | High | Time-series splits respecting match dates. No future data leakage. Rolling window or expanding window. Already implemented in football-predictor. |
| Multi-market probability support | Serious bettors need 1X2, O/U, BTTS, AH at minimum. Single-market = toy system. | Med | `ProbabilityMap` in SportPlugin interface (PROJECT.md) handles this. Each market needs its own calibration. |
| Automated pre-match data pipeline | Manual data collection does not scale. Pipeline must run autonomously before kickoff. | Med | APScheduler at 2h and 30min pre-kickoff (PROJECT.md). API-Football v3 for fixtures, stats, lineups, injuries, H2H. |
| Performance tracking (ROI by market, league, time) | Cannot improve what you do not measure. Bettors need to know where edge exists and where it does not. | Med | Aggregate by: market type, league, month, model version. ROI alone is noisy short-term; pair with CLV for signal. |
| Structured pick logging | Every pick must be recorded with full context: odds, edge, model version, reasoning. Reproducibility is non-negotiable. | Low | Supabase predictions + picks tables (existing schema). Add model_version and feature_hash for reproducibility. |
| Bet filtering (minimum edge threshold) | Sending low-edge picks destroys bankroll. System must enforce discipline the human cannot. | Low | Min 5% edge (PROJECT.md). Also filter by: minimum sample size for model confidence, league coverage quality. |

## Differentiators

Features that set this platform apart from typical betting tools and tipster services.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Claude AI pick validation (red flag detection) | No other system uses LLM to cross-reference picks against accumulated domain knowledge (learnings.md). Catches edge cases statistical models miss: manager changes, derby psychology, end-of-season motivation. | Med | Role C in PROJECT.md. Key: Claude validates against known red flags, does not generate picks. Structured output required (pass/fail + reasoning). Log reasoning to Supabase for audit. |
| Claude AI confidence modifier as ML feature | Novel: LLM reasoning becomes a numeric feature (-15% to +15%) fed into the ensemble. Combines qualitative context with quantitative model. | High | Role B in PROJECT.md. Risk: prompt sensitivity, cost per call, latency. Must validate that this feature actually improves calibration in backtesting before shipping to production. |
| Timed corners module | Genuinely novel niche. Academic research confirms corner distribution is non-uniform across time windows (Swartz et al., SFU). Few if any commercial systems model corner timing by window. | High | Academic backing: temporal patterns exist in corner kicks driven by pressing style, score differential, home/away, red card differential. Betano offers first-corner timing and half-specific corner markets. This is the highest-alpha opportunity in the platform. |
| Account longevity protection system | Most betting systems optimize for edge but ignore that soft books (Betano) limit winners within weeks. Building account protection INTO the system is rare and valuable. | Med | Features: stake rounding to nearest 5, market rotation, occasional "recreational" bet suggestions, max 75% of offered limits, alert when CLV trend might trigger review. Critical for Betano specifically. |
| Sport-agnostic plugin architecture | Most betting systems are sport-specific monoliths. Plugin architecture means adding tennis/NBA without rewriting core EV engine, CLV tracker, or delivery. | Med | SportPlugin ABC (PROJECT.md). Validate with tennis scaffold. Key: core layer must have zero sport-specific code. Markets defined in YAML, not hardcoded enums. |
| CLV decomposition reporting | Beyond simple CLV tracking: break down CLV by market, league, time-of-bet (how early before kickoff), and model version. Identifies WHERE edge comes from, not just IF it exists. | Med | Most tools show aggregate CLV. Decomposition reveals: "Your 1X2 edge is +4.2% CLV in La Liga but -0.8% in Premier League." Actionable for market selection. |
| Consensus scoring (ensemble + goals model agreement) | Already designed in PROJECT.md (consensus_1x2_max, consensus_ou25, consensus_btts). When ensemble and goals model agree, confidence increases. When they disagree, flag for review. | Low | Builds on existing football-predictor consensus signal. Simple but effective meta-feature. |
| Model versioning with feature hashing | Track exactly which model version + feature set produced each pick. When model is retrained, compare CLV of new vs old version on overlapping period. | Low | Store model version, feature_set hash, calibration method in picks table. Enables A/B comparison of model iterations. |

## Anti-Features

Features to explicitly NOT build. Each represents wasted effort or active harm.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Web dashboard / UI | PROJECT.md correctly scopes this out. Building UI before the model proves profitable is premature optimization. Telegram alerts are sufficient for a single-user system. UI adds weeks of work with zero edge improvement. | Telegram alerts only. If you need historical analysis, query Supabase directly or build a simple Streamlit dashboard later. |
| Automated bet placement | Legal risk, account ban risk, and removes the human judgment layer that catches system failures. Betano TOS prohibit automation. | Send Telegram alerts with all context; human places bet. The 30-second manual step is a feature, not a bug. |
| Real-time in-play pipeline | Massive engineering complexity (websockets, sub-second latency, live odds streaming). In-play models require fundamentally different architecture. Pre-match is where the proven edge exists. | Pre-kickoff pipeline only (2h and 30min windows). In-play is a separate future project, not a phase of this one. |
| Accuracy as primary metric | Research is unambiguous: calibration-optimized models generate 69.86% higher returns than accuracy-optimized ones. Chasing accuracy leads to overfit models that look great in backtests but lose money. | Use log loss, Brier score, and calibration curves as primary metrics. Track accuracy only as a secondary sanity check. |
| Multi-bookmaker arbitrage detection | Arbing is the fastest path to account limitation. Betano will restrict you within days. It also requires maintaining odds feeds from many books simultaneously. | Single-book value betting against Betano. Use Pinnacle only as CLV reference (read-only via The Odds API). |
| Complex staking systems (Martingale, progressive) | All progressive staking systems increase variance without increasing edge. They feel sophisticated but are mathematically inferior to Kelly. | Quarter-Kelly with fractional adjustment based on edge confidence. Simple, proven, optimal. |
| Social features / leaderboards / multi-user | This is a personal edge-detection tool, not a tipster platform. Social features attract recreational bettors and dilute focus. Building for multiple users multiplies complexity 10x. | Single-user system. If you want to share picks later, export to a Telegram channel -- do not build user management. |
| Sentiment analysis from social media | Low signal-to-noise ratio. Twitter/Reddit sentiment about football matches is dominated by fan bias, not information. Academic evidence for sentiment edge is weak and inconsistent. | Claude AI reading structured pre-match reports (team news, press conferences) is far more valuable than Twitter sentiment scores. |
| GPU-based deep learning models | Gradient boosting (XGBoost + CatBoost + LightGBM) is SOTA for tabular sports data. Deep learning adds complexity without proven improvement for structured betting features. No CUDA dependency = simpler deployment. | Stick with gradient boosting ensemble. CPU training, <500ms inference (PROJECT.md constraint). |
| Odds scraping from bookmaker websites | Fragile, legally grey, and unnecessary. API-Football and The Odds API provide structured odds data. Scraping breaks with every site redesign. | Use The Odds API (Rookie tier, $20/mo) for Pinnacle closing odds. Use API-Football for fixture data. Both are stable, documented APIs. |
| Historical database of all odds movements | Storing every odds movement for every match across every bookmaker is a data engineering project in itself. Overkill for v1. | Store: (1) odds at time of pick, (2) Pinnacle closing odds. Two snapshots per pick is sufficient for CLV calculation. |

## Feature Dependencies

```
Calibrated probability outputs
  --> EV calculation (requires calibrated probs to compute edge)
    --> Kelly stake sizing (requires accurate edge estimate)
    --> Bet filtering (requires edge threshold)
      --> Telegram alert delivery (requires qualified pick)
        --> CLV tracking (requires pick record + closing odds)
          --> CLV decomposition reporting (requires CLV history)

Walk-forward backtesting
  --> Model validation (proves calibration works OOS)
    --> Production deployment confidence

API-Football data pipeline
  --> Feature engineering
    --> ML ensemble training
      --> Calibrated probability outputs

Corner timing data ingestion
  --> Corner distribution model
    --> Corner EV calculation
      --> Corner picks in Telegram alerts

Claude AI confidence modifier (Role B)
  --> Must be validated in backtesting BEFORE production use
  --> Depends on: feature engineering pipeline, API-Football data

Claude AI pick validation (Role C)
  --> Depends on: qualified pick from EV filter
  --> Independent of model training (operates on pick output)

Account longevity protection
  --> Depends on: stake sizing (applies rounding/variation to Kelly output)
  --> Independent of model (operates on delivery layer)

Sport plugin architecture
  --> Must be built FIRST (core layer)
    --> Football plugin implements interface
      --> Tennis scaffold validates interface
```

## CLV Tracking: What Serious Bettors Need

Based on research into Pikkit, betstamp, and professional betting community practices:

### Essential CLV Features (Table Stakes)
1. **Per-bet CLV**: Compare locked odds vs Pinnacle closing line for every pick
2. **Aggregate CLV %**: Overall CLV across all bets (the single number that matters)
3. **CLV by market type**: 1X2, O/U, BTTS, AH separately (edge varies by market)
4. **% of bets beating closing line**: Simple win rate against the close
5. **Time-windowed CLV**: Daily, weekly, monthly, all-time views

### Differentiating CLV Features
1. **CLV by league**: Identify which leagues your model has genuine edge in
2. **CLV by bet timing**: Does betting 2h before kickoff yield better CLV than 30min?
3. **CLV by model version**: Track if model updates improve or degrade edge
4. **CLV trend alerting**: If rolling 30-day CLV drops below +1%, auto-alert to pause and audit (PROJECT.md constraint)
5. **Expected profit from CLV**: Convert CLV % to expected long-term profit projection

### CLV Benchmarks (from research)
- **+1% to +2% CLV**: Sharp territory for major markets (1X2, spreads)
- **+3% to +5% CLV**: Expected for prop/niche markets (corners, BTTS) due to wider vig
- **+3% CLV target** (PROJECT.md): Appropriate given the market mix (includes niche corners)

## Telegram Alert Format: What Works

Based on research into professional betting Telegram bots and tipster channels:

### Essential Alert Fields
```
MATCH: Team A vs Team B
LEAGUE: Premier League
KICKOFF: 2026-04-22 20:00 UTC

MARKET: Over 2.5 Goals
ODDS: 1.95 @ Betano
EDGE: +7.2% vs model probability
MODEL PROB: 58.3%

STAKE: 1.8% bankroll (quarter-Kelly)
CONFIDENCE: HIGH (ensemble + goals model agree)

REASONING: [1-2 sentence Claude summary]
```

### Important But Secondary
- Model version identifier
- Number of historical similar picks and their CLV
- Red flags checked and passed (from Claude validator)

### What to EXCLUDE from Alerts
- Full model feature breakdown (noise for decision-making)
- Historical ROI claims (biases the human toward overconfidence)
- Multiple bookmaker odds comparison (you bet on Betano only)
- Countdown timers or urgency language (anti-pattern from tipster culture)

## Timed Corners Module: Prior Art and Opportunity

### Academic Research (MEDIUM confidence)
- **Swartz et al. (SFU)**: Event history analysis of corner kick timing. Corner occurrence is associated with: half (1st vs 2nd), home/away, score differential, pre-match odds, red card differential.
- **ArXiv 2112.13001**: Forecasting number of corner kicks using statistical models. Establishes that corners are predictable from team-level features.
- **ResearchGate (2024)**: Temporal pattern analysis identifying behavioral patterns in specific time windows (15-40 min intervals).

### Market Opportunity
- Betano offers: total corners O/U, first-half/second-half corners, first corner timing (before/after X minutes), corner race markets.
- **Timed corner windows (0-15, 15-30, etc.) are NOT standard bookmaker markets.** The closest is first-half/second-half corners O/U.
- **Opportunity**: If Betano offers any time-window-specific corner props (verify before building Phase 3), this module has genuine edge potential because:
  1. Few bettors model corner timing distribution
  2. Academic research confirms the signal exists
  3. Pressing style, motivation, and tactical setup create predictable patterns
  4. Bookmaker pricing in niche markets is less efficient

### Risk
- **CRITICAL**: Verify exact Betano corner time-window markets before investing in Phase 3. If Betano only offers standard O/U corners and half-specific markets, the timed-window model still has value for those markets but the alpha opportunity is smaller.

## Bankroll Management: Essential vs Nice-to-Have

### Essential
| Feature | Why | Complexity |
|---------|-----|------------|
| Quarter-Kelly sizing | Optimal growth with controlled variance | Low |
| Bankroll tracking | Know current bankroll to size bets correctly | Low |
| Max exposure limits | Never risk more than X% of bankroll on a single day/market | Low |
| Stake rounding (account longevity) | Round to nearest 5 to avoid algorithmic detection by Betano | Low |

### Nice-to-Have (Phase 2+)
| Feature | Why | Complexity |
|---------|-----|------------|
| Drawdown alerts | Notify if bankroll drops X% from peak -- triggers audit | Low |
| Market rotation tracking | Ensure you are not hammering same market type repeatedly (Betano detection risk) | Med |
| Recreational bet suggestions | Occasionally suggest a "fun" low-edge bet on a popular match to warm account | Med |
| Risk-of-ruin calculator | Given current edge and Kelly fraction, estimate probability of losing X% of bankroll | Low |

## Syndicate-Level Features Individual Bettors Miss

Based on research into professional betting syndicate operations:

| Feature | What Syndicates Do | Applicable Here? | Notes |
|---------|-------------------|-------------------|-------|
| Line shopping across 20+ books | Place bets at best available odds across many accounts | NO | Single book (Betano). Use Pinnacle only for CLV reference. |
| Steam move detection | Monitor when sharp money moves a line at Pinnacle, then bet before soft books adjust | MAYBE (Phase 2+) | Could monitor Pinnacle line movements via The Odds API and alert when Betano hasn't adjusted yet. High-value feature but complex. |
| Odds timing optimization | Bet at optimal time before kickoff when edge is largest | YES | Track CLV by bet timing. Data will reveal whether 2h or 30min pre-kickoff yields better CLV. Adjust pipeline timing accordingly. |
| Cross-market correlation | If 1X2 model says home win, corners model should reflect attacking home team. Flag contradictions. | YES | Consensus scoring (already planned). Low complexity, high value for quality control. |
| Model ensembling with market-specific weights | Different model weights for different markets (1X2 vs O/U vs corners) | YES | Already doing this with separate calibration per market. Extend to market-specific ensemble weights. |
| Systematic edge decay monitoring | Track how quickly edge disappears after model update -- if edge decays in weeks, model is overfitting to temporary patterns | YES | Compare CLV of model version over time. If CLV degrades monotonically after training, the model found noise, not signal. |

## MVP Recommendation

### Phase 1 Priority (Must Ship)
1. **Calibrated ML ensemble** (1X2, O/U, BTTS) -- table stakes, proven baseline exists
2. **EV calculation + bet filtering** -- core value proposition
3. **Telegram alert delivery** -- minimum viable output channel
4. **CLV tracking (basic)** -- per-bet CLV + aggregate, validates edge exists
5. **Quarter-Kelly stake sizing with rounding** -- bankroll management + account protection

### Phase 2 Priority (Validates Platform)
1. **Claude AI pick validation (Role C)** -- differentiator, lower risk than Role B
2. **Asian Handicap market** -- extends market coverage
3. **CLV decomposition** (by league, market, timing) -- identifies where edge lives
4. **Account longevity features** (market rotation tracking, exposure alerts)

### Phase 3 Priority (Novel Edge)
1. **Timed corners module** -- highest alpha potential, requires market verification
2. **Claude AI confidence modifier (Role B)** -- requires backtesting validation first
3. **Steam move detection** (Pinnacle line movement alerts)

### Defer Indefinitely
- Web UI, auto-placement, in-play, multi-user, sentiment analysis, deep learning

## Sources

- [ScienceDirect: Calibration vs Accuracy for Sports Betting](https://www.sciencedirect.com/science/article/pii/S266682702400015X) -- calibration-optimized models generate 69.86% higher returns
- [Pikkit CLV Tracker](https://pikkit.com/closing-line-value) -- CLV feature reference
- [betstamp CLV Education](https://betstamp.com/education/what-is-closing-line-value-clv) -- CLV benchmarks
- [Swartz et al. (SFU): Corner Kick Timing](https://www.sfu.ca/~tswartz/papers/ckick.pdf) -- temporal distribution of corners
- [ArXiv: Forecasting Corner Kicks](https://arxiv.org/pdf/2112.13001) -- corner prediction modeling
- [ResearchGate: Corner Kick Timing Analysis](https://www.researchgate.net/publication/384900352_On_the_time_of_corner_kicks_in_soccer_an_analysis_of_event_history_data) -- event history analysis
- [RebielBetting: Avoiding Bookmaker Limitations](https://www.rebelbetting.com/blog/how-to-avoid-bookmaker-limitations) -- account longevity strategies
- [Smart Betting Club: Account Longevity](https://smartbettingclub.com/blog/how-to-make-your-bookmaker-accounts-last-longer/) -- soft book survival tactics
- [Tradematesports: Bankroll Management](https://www.tradematesports.com/en/blog/bankroll-management-sports-betting) -- Kelly criterion in practice
- [OpticOdds: Calibration Over Accuracy](https://opticodds.com/blog/calibration-the-key-to-smarter-sports-betting) -- model evaluation best practices
