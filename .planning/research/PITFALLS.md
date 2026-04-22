# Domain Pitfalls

**Domain:** Multi-sport betting intelligence platform (football ML ensemble + Claude AI + Telegram alerts + timed corners)
**Researched:** 2026-04-22

---

## Critical Pitfalls

Mistakes that cause rewrites, wasted months, or financial loss. Each validated against project-specific context.

---

### Pitfall 1: Measuring Accuracy Instead of CLV (The Vanity Metric Trap)

**What goes wrong:** You build a model that achieves 55% accuracy on match outcomes, celebrate, deploy it -- and lose money. Accuracy measures prediction correctness; CLV measures whether you found prices the market undervalued. A model can be 52% accurate but +4% CLV (profitable) or 58% accurate but -2% CLV (unprofitable because it only picks heavy favorites the market already priced correctly).

**Why it happens:** Accuracy is easy to compute and emotionally satisfying. CLV requires Pinnacle closing lines, vig removal, and careful temporal alignment -- much harder infrastructure. Teams optimize the easy metric.

**Consequences:** Months of development on a model that looks good in backtests but generates zero edge against efficient markets. The PROJECT.md correctly identifies CLV > +3% against Pinnacle as the real target, but the entire pipeline must be built to optimize for this from day one, not bolted on later.

**Warning signs:**
- Backtest reports show accuracy/logloss but no CLV column
- Model selection optimized on logloss instead of simulated CLV-weighted ROI
- No Pinnacle closing odds in training/validation pipeline

**Prevention:**
- Phase 1: Include CLV recording infrastructure from the start (The Odds API for Pinnacle closing lines)
- Every backtest fold must compute simulated CLV, not just accuracy
- Model selection criterion: positive CLV on out-of-sample folds, not lowest logloss

**Detection:** If your backtest shows positive ROI but you haven't computed CLV against Pinnacle, the ROI number is meaningless.

**Phase:** Phase 1 (Core Infrastructure) -- CLV tracking is not a "nice to have"; it is the primary success metric.

**Confidence:** HIGH -- validated by existing project experience and systematic review (arxiv.org/abs/2410.21484) showing most ML betting models fail to beat bookmaker odds when properly evaluated.

---

### Pitfall 2: In-Sample Calibration Masquerading as Improvement

**What goes wrong:** Isotonic calibration on the same validation set used for evaluation shows dramatic logloss improvement (your existing project saw 4-6% per-league gains). But `calibrate_by_league_wf()` with TimeSeriesSplit produced logloss 0.97 to 1.6+ -- catastrophic overfitting. The calibration "learned" the validation set rather than genuine probability corrections.

**Why it happens:** Isotonic regression is non-parametric and has effectively unlimited capacity. With fewer than 200 samples per fold per league (common for single-season league data), it memorizes rather than generalizes. This is documented in scikit-learn's own calibration docs: "Isotonic Regression is more prone to overfitting, and thus performs worse than Platt Scaling, when data is scarce."

**Consequences:** Model appears brilliantly calibrated in backtests, fails immediately in production. You ship a system that makes worse predictions than the uncalibrated model.

**Warning signs:**
- Calibration improvement exceeds 3% on validation set -- likely in-sample leakage
- Isotonic calibration with fewer than 500 samples per bin
- No held-out test set separate from calibration set

**Prevention:**
- Use Platt (sigmoid) calibration for per-league calibration where league sample sizes are under 300
- Reserve a true hold-out set that calibration never touches
- Walk-forward calibration: calibrate on fold N, evaluate on fold N+1 (never same fold)
- Compare calibrated vs uncalibrated on the hold-out; if calibrated is worse, ship uncalibrated

**Detection:** Run calibration on random data. If isotonic calibration "improves" random predictions, your sample size is too small for isotonic.

**Phase:** Phase 2 (ML Core) -- calibration strategy must be decided before training pipeline is built.

**Confidence:** HIGH -- directly validated by your own `calibrate_by_league_wf()` failure documented in MEMORY.md.

---

### Pitfall 3: Betano Account Restriction Within Weeks

**What goes wrong:** Consistent winning patterns trigger Betano's automated restriction algorithms. Reports show limits dropped to under $2 per bet within days of profitable patterns being detected. A Brazilian court case (2025) even ruled against Betano for restricting an account to R$5 wagers without explanation.

**Why it happens:** Betano is a soft bookmaker. Their business model depends on recreational bettors. Their algorithms flag: (1) consistently beating opening lines, (2) betting only on value spots with no "recreational noise," (3) rapid withdrawals after wins, (4) concentration in niche/low-margin markets, (5) stake patterns that suggest Kelly criterion or similar optimization.

**Consequences:** Your entire delivery pipeline becomes useless if the account you're alerting for gets restricted. This is an existential risk for the project.

**Warning signs:**
- Maximum allowed stake decreases
- Certain markets become unavailable
- Withdrawal processing slows
- Only parlays/accumulators available

**Prevention:**
- Quarter-Kelly maximum (already in PROJECT.md -- good)
- Rotate markets: do not only bet corners or only 1X2. Mix in some recreational-looking bets
- Vary stake amounts: never bet exact calculated amounts. Round to natural-looking numbers ($10, $15, $25 -- not $13.47)
- Stagger withdrawals: leave float in account, withdraw periodically not after every win
- Track win rate per market; if any market exceeds 60% hit rate, reduce volume on that market
- Have a contingency plan: identify 2-3 backup bookmakers before restriction happens

**Detection:** Monitor accepted stake amounts weekly. Any decrease is an early warning.

**Phase:** Phase 4 (Pick Engine + Delivery) -- stake rotation and "camouflage" logic must be built into the alert system.

**Confidence:** HIGH -- multiple sources confirm soft bookmaker restriction patterns, plus Betano-specific reports on SportsBookReview forums.

---

### Pitfall 4: Data Leakage in Football Feature Engineering

**What goes wrong:** Subtle future information leaks into training features. Unlike simple "using match result as a feature" (obvious), football-specific leakage is insidious:

1. **Aggregate season stats that include the target match:** Computing "team average goals this season" using all matches including the one you're predicting.
2. **Elo/rating features computed with future matches:** Rating systems that update with results not yet available at prediction time.
3. **Odds features that moved post-prediction:** Using closing odds as features when you'd only have opening/early odds at prediction time.
4. **Injury data available only on matchday:** Using confirmed lineups (available 1h pre-match) in a model trained on data where you used lineup info that was actually post-match confirmed.
5. **Transfer window knowledge:** Using squad data that reflects January transfers for October predictions.

**Why it happens:** Feature engineering pipelines process entire seasons at once for efficiency. The temporal boundary between "known" and "future" is different for every feature type.

**Consequences:** Model shows 60%+ accuracy in backtests, drops to 50-52% in live deployment. The gap between backtest and production is entirely explained by leakage.

**Warning signs:**
- Model accuracy drops significantly (5%+) when moving from backtest to live
- Features with suspiciously high importance that are time-dependent
- Backtest accuracy varies dramatically by how far ahead you predict

**Prevention:**
- Implement a strict `as_of_date` parameter in every feature computation
- Feature pipeline must accept a cutoff date and only use data available before that date
- Odds features: use only opening odds or odds captured at a fixed time before kickoff (e.g., T-2h)
- Automated leakage detection: compare feature distributions between train and test splits; if test features are "better" (lower variance, higher signal), suspect leakage

**Detection:** Run your model with features lagged by one additional matchday. If performance barely changes, your original features likely contained leakage from the target matchday.

**Phase:** Phase 2 (ML Core) -- feature pipeline must enforce temporal boundaries from first implementation.

**Confidence:** HIGH -- well-documented in ML literature and directly relevant to the Polars/Parquet cache approach planned.

---

### Pitfall 5: Walk-Forward Backtesting That Produces Optimistic Results

**What goes wrong:** Even with proper walk-forward structure, backtests systematically overestimate performance through several mechanisms:

1. **Backtesting against closing lines:** Your model picks a bet, but in backtest you evaluate against the closing line. In reality, you would bet at the opening or early line -- which may be different by 2-5%.
2. **Hyperparameter selection across the entire walk-forward:** You choose learning rate, tree depth, etc., by looking at performance across ALL folds -- this is a form of overfitting to the walk-forward structure.
3. **Survivorship bias in market selection:** You backtest the corners market because you know it exists now. You don't backtest the markets that Betano removed or changed rules for.
4. **Ignoring execution realities:** Backtest assumes you can bet the exact line at the exact time. In practice, odds change between alert delivery and bet placement.

**Why it happens:** Each bias is small (1-3% each), but they compound. A model with +5% edge in backtest may have +0% or negative edge after accounting for all biases.

**Consequences:** You deploy a system confident in its backtest edge, only to find flat or negative real-money performance.

**Warning signs:**
- Backtest ROI exceeds +10% -- suspiciously high for football markets
- Performance is uniform across all walk-forward folds (real performance is noisy)
- No slippage/execution cost in simulation

**Prevention:**
- Backtest against OPENING odds, not closing odds -- this is what you can actually bet
- Include 1-2% slippage per bet to simulate odds movement between alert and placement
- Hyperparameter selection: use nested walk-forward (inner loop for hyperparams, outer loop for evaluation)
- Report confidence intervals, not point estimates -- use bootstrap across folds
- Minimum 200 bets per market type before trusting any signal

**Detection:** If your backtest ROI is more than 3x your CLV, something is wrong with your backtest methodology.

**Phase:** Phase 2 (ML Core) -- backtesting framework must include slippage and use opening odds from day one.

**Confidence:** HIGH -- validated by multiple sports betting backtesting guides and the project's own experience.

---

### Pitfall 6: Corner Timing Models That Don't Generalize

**What goes wrong:** The timed corners module (0-15, 15-30... 75-90 min windows) faces a domain-specific challenge: corner kick timing has low predictive signal. Research shows out-of-sample R-squared of only 17-22% for corner prediction models, and models trained on one league lose profitability when applied to another without retraining.

**Specific failure modes:**
1. **Clustering effect:** Corners arrive in bursts (a corner often leads to another corner quickly). Standard Poisson models underfit this clustering; compound Poisson or negative binomial models are needed.
2. **Score-dependent dynamics:** Corner frequency changes dramatically based on the current score (trailing team attacks more). Your model must condition on game state, but game state is unknown pre-match.
3. **Tactical substitution effects:** Managers substitute at 60-70 min, changing corner generation patterns. Pre-match features cannot capture in-game tactical shifts.
4. **League-specific corner cultures:** Premier League averages 10-11 corners/game; La Liga averages 9-10. Training a single model across leagues without league-specific parameters will underfit all leagues.

**Why it happens:** Corner timing is inherently high-variance. The signal-to-noise ratio is much worse than 1X2 or over/under markets.

**Consequences:** Building a sophisticated timed corners model that performs no better than naive baselines (league average per window). Significant development time for minimal or zero edge.

**Warning signs:**
- Model R-squared under 15% on out-of-sample data
- Performance varies wildly across leagues
- Model predictions cluster around the league mean (not adding information)

**Prevention:**
- Start with strong baselines: per-team, per-league average corners per window. If your model cannot beat this by at least 5% MAE, do not deploy it
- Use compound Poisson or negative binomial distributions, not standard Poisson
- Verify Betano actually offers timed corner window markets BEFORE building the model (PROJECT.md notes this -- critical)
- Consider the market: if Betano corner markets have wide margins (vig > 8%), edge must be proportionally larger
- Build incrementally: total corners model first, then time-window decomposition only if total model shows edge

**Detection:** Compare your model's out-of-sample predictions against a "league average per window" baseline. If you're within 2% MAE, you have no usable edge.

**Phase:** Phase 3 (Timed Corners) -- must validate market availability and baseline performance before committing to full build.

**Confidence:** MEDIUM -- based on academic research (arxiv.org/abs/2112.13001, SFU corner kick analysis), but limited real-world corner timing model deployments to reference.

---

## Moderate Pitfalls

---

### Pitfall 7: CLV Tracking Implementation Errors

**What goes wrong:** CLV computation has several subtle failure modes:

1. **Not removing vig from closing line:** Comparing your bet odds against the raw Pinnacle closing line (which includes vig) understates your CLV. You must compute vig-free closing probabilities.
2. **Wrong closing line timing:** "Closing line" means the final line before kickoff. If you capture Pinnacle odds 2 hours before kickoff, that's not the closing line.
3. **Applying CLV to inefficient markets:** CLV is meaningful for 1X2 and totals on Pinnacle. It is unreliable for corners, BTTS, and props where Pinnacle either doesn't offer the market or has insufficient liquidity. Treating corner CLV as equivalent to 1X2 CLV is a mistake.
4. **Small sample overconfidence:** CLV needs 200+ bets minimum to be meaningful. Celebrating +5% CLV on 30 bets is noise, not signal.

**Prevention:**
- Use The Odds API to capture Pinnacle odds at kickoff (not hours before)
- Always convert to vig-free implied probabilities before comparing
- Tag each bet's market type; only compute CLV for markets where Pinnacle has efficient pricing
- Display CLV with confidence intervals: +3% CLV on 50 bets has wide error bars

**Phase:** Phase 1 (Core Infrastructure) and Phase 4 (Pick Engine).

**Confidence:** HIGH -- validated by Unabated's detailed CLV methodology article.

---

### Pitfall 8: Claude API as a Production Bottleneck

**What goes wrong:** The project plans two Claude integration points: (B) confidence_modifier feature and (C) pick validator. Both are on the critical path for every alert. Failure modes:

1. **Latency:** Claude API median response time is 2-5 seconds for Haiku, 5-15 seconds for Sonnet. If the pipeline runs at T-30min before kickoff, adding 10-20 seconds of Claude latency per fixture across 10-15 fixtures means 2-5 minutes of sequential Claude calls.
2. **Cost runaway:** Each fixture requires 2 Claude calls (modifier + validator). With 5 leagues, ~50 fixtures/week, that's ~100 calls/week. At Sonnet pricing ($3/$15 per M tokens), a 2000-token prompt + 500-token response = ~$0.008/call = ~$0.80/week. Manageable. But if prompts grow (e.g., including full match context), costs can 10x without monitoring.
3. **Non-determinism:** Claude's confidence_modifier will vary across identical prompts. This makes backtesting impossible unless you cache Claude responses or use seed parameters.
4. **Prompt injection via data:** If match previews or injury reports fed to Claude contain adversarial text, Claude could output manipulated confidence_modifiers. Low probability in sports data, but non-zero.
5. **API downtime:** Anthropic API has had outages. If Claude is on the critical path, an outage means no alerts.

**Prevention:**
- Batch Claude calls with asyncio (parallel, not sequential)
- Set hard token budget per call (max_tokens=200 for modifier, max_tokens=500 for validator)
- Cache Claude responses by fixture ID for backtest reproducibility
- Implement fallback: if Claude API fails, proceed without modifier (use 0 adjustment)
- Use Haiku for the confidence_modifier (fast, cheap); Sonnet only for the validator where reasoning quality matters
- Monitor monthly Claude spend; alert if exceeding $20/month

**Phase:** Phase 3 (Claude Integration) -- design the fallback and caching strategy before implementation.

**Confidence:** MEDIUM -- based on 2026 LLM pricing benchmarks and Anthropic API documentation.

---

### Pitfall 9: API-Football Data Quality and Coverage Gaps

**What goes wrong:** API-Football is the planned data source, but it has documented issues:

1. **Missing corner timing data:** API-Football provides match events (goals, cards, substitutions) with minute markers, but corner timing granularity varies by league and season. Some leagues may not have per-minute corner data, only totals.
2. **Delayed statistics:** Post-match statistics can take 30 minutes to several hours to appear. For a pre-kickoff pipeline this is less critical, but for CLV recording (post-match closing line capture), timing matters.
3. **Inconsistent field availability:** Not all fixtures have all fields. Injuries, lineups, and H2H data availability varies by league tier. Lower leagues in the "5 top European leagues" scope (Ligue 1) may have sparser data than Premier League.
4. **API rate limits on Pro tier:** 100 requests/day on free tier is insufficient (already noted). Pro tier (300 req/day) may also be tight if pulling fixtures + stats + lineups + corners + injuries + H2H for 50+ fixtures/week.
5. **Historical data gaps:** Corner timing by minute may not be available for older seasons, limiting training data for the corners model.

**Prevention:**
- Before Phase 3 (Corners): verify API-Football actually provides minute-level corner data for all 5 leagues for at least 3 seasons. If not, this is a blocker.
- Implement null-handling in every feature: no feature should crash on missing data
- Cache aggressively in Polars/Parquet: request once, store forever
- Calculate API budget: fixtures/week * endpoints/fixture * weeks/season; ensure Pro tier is sufficient
- Have fallback data sources identified (Sportmonks, football-data.org) for gaps

**Phase:** Phase 1 (Data Pipeline) -- validate data availability before building models that depend on it.

**Confidence:** MEDIUM -- based on API-Football documentation and Sportmonks comparison articles. Specific corner timing availability needs direct verification.

---

### Pitfall 10: Telegram Alert Delivery Timing Failures

**What goes wrong:** Telegram Bot API has strict rate limits that cause delayed delivery:

1. **Rate limiting:** 30 messages/second global limit per bot token. With multiple users, sending rich formatted messages with images or formatted tables can hit limits quickly.
2. **Delivery delay:** Real-world reports show alerts arriving 4-10 minutes late under load. For a betting alert at T-30min, a 10-minute delay means 20 minutes of odds movement before the user sees the alert.
3. **Silent failures:** Telegram does not guarantee delivery. If the user's client is offline, messages queue but may be lost if the queue overflows.
4. **Formatting breaks:** Telegram MarkdownV2 parsing is notoriously fragile. Special characters in team names (e.g., "Atletico Madrid" with accent, team names with apostrophes) can break message formatting silently.

**Prevention:**
- Use a message queue (even a simple asyncio.Queue) to rate-limit outgoing messages
- Implement delivery confirmation: after sending, check message was delivered via getUpdates
- Test MarkdownV2 formatting with all team names in your 5 leagues before deployment
- Include timestamp in every alert so user knows when the analysis was generated vs when they received it
- Consider HTML formatting mode instead of MarkdownV2 (more forgiving with special characters)

**Phase:** Phase 4 (Pick Engine + Delivery).

**Confidence:** HIGH -- Telegram rate limiting is well-documented; python-telegram-bot GitHub issues confirm delivery delay patterns.

---

## Minor Pitfalls

---

### Pitfall 11: SportPlugin ABC Over-Engineering

**What goes wrong:** Building the plugin architecture before having a second sport to validate it against. The ABC interface gets designed around football's quirks, then when tennis is scaffolded in Phase 6, it doesn't fit and requires interface changes.

**Prevention:**
- Design the ABC with the tennis scaffold in mind from day one (even if tennis is out of scope for implementation)
- Keep the interface minimal: `get_features()`, `predict()`, `get_markets()` -- do not add football-specific methods to the base class
- Accept that the first refactor of the ABC is expected when the second sport is added

**Phase:** Phase 1 (Core Infrastructure).

---

### Pitfall 12: Supabase Cold Start and Connection Limits

**What goes wrong:** Supabase free/Pro tier has connection limits (direct connections limited to 60 on Pro). If APScheduler jobs overlap (e.g., T-2h and T-30min windows for different fixtures), concurrent connections spike.

**Prevention:**
- Use connection pooling (Supavisor/PgBouncer built into Supabase)
- Ensure scheduler jobs don't overlap; stagger execution windows
- Batch database writes rather than per-fixture inserts

**Phase:** Phase 1 (Core Infrastructure).

---

### Pitfall 13: Model Versioning Without Reproducibility

**What goes wrong:** You store model versions in Supabase but cannot reproduce a prediction from 3 weeks ago because you didn't version the feature pipeline, calibration parameters, and Claude prompt alongside the model weights.

**Prevention:**
- Version tuple: (model_weights, feature_pipeline_hash, calibration_params, claude_prompt_version)
- Every prediction logged with the full version tuple
- Pin library versions in uv.lock for exact reproducibility

**Phase:** Phase 2 (ML Core).

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation | Severity |
|---|---|---|---|
| Phase 1: Core Infrastructure | CLV tracking deferred as "later" work | Build CLV recording from day one; it is the primary metric | Critical |
| Phase 1: Data Pipeline | API-Football corner timing data unavailable | Verify data availability before Phase 3 commitment | Critical |
| Phase 2: ML Core | Isotonic calibration overfits per-league | Use Platt for leagues with <300 validation samples | Critical |
| Phase 2: ML Core | Walk-forward tests against closing odds | Must use opening odds and include slippage | Critical |
| Phase 2: ML Core | Feature leakage via aggregate season stats | Enforce `as_of_date` in every feature computation | Critical |
| Phase 3: Corners | Building model before verifying Betano market exists | Confirm market availability as Phase 3 prerequisite | Critical |
| Phase 3: Corners | Low signal-to-noise in corner timing data | Require model to beat league-average baseline by 5%+ MAE | Moderate |
| Phase 3: Claude Integration | API latency blocks alert delivery | Async parallel calls + fallback without Claude | Moderate |
| Phase 3: Claude Integration | Non-deterministic outputs break backtests | Cache responses by fixture ID | Moderate |
| Phase 4: Pick Engine | Betano restricts account within weeks | Stake rotation, market diversity, withdrawal pacing | Critical |
| Phase 4: Telegram | Delivery delays of 5-10 minutes | Rate-limited queue, timestamp in alerts, HTML mode | Moderate |
| Phase 5: Monitoring | Tracking accuracy instead of CLV | Dashboard primary metric = CLV, not win rate | Moderate |
| Phase 6: Tennis Scaffold | ABC interface too football-specific | Design minimal interface considering tennis from start | Minor |

---

## Anti-Patterns to Explicitly Avoid

### 1. The Martingale Corner Trap
**What it is:** Escalating corner bet sizes after losses because "the model says there's edge."
**Why deadly:** Corner markets have high variance (R-squared 17-22%). Even a correct model will have long losing streaks. Martingale-style sizing guarantees account depletion.
**Rule:** Quarter-Kelly maximum on ALL markets, especially corners. If the model says 8% edge but your bankroll can't sustain 10 consecutive losses at that stake, reduce the stake.

### 2. The Accuracy Leaderboard
**What it is:** Comparing models by accuracy rather than profitability/CLV.
**Why deadly:** A model that predicts every home win at 45% and every away win at 22% can have great accuracy but zero betting edge. The market already prices these probabilities.
**Rule:** Model comparison metric = CLV on out-of-sample bets where EV filter would have triggered a bet.

### 3. The "Claude Knows Football" Assumption
**What it is:** Trusting Claude's confidence_modifier as genuine domain expertise rather than pattern matching on training data.
**Why deadly:** Claude has no access to current form, injuries, or tactical changes. Its "analysis" is based on general knowledge and whatever context you provide. If the context is wrong, the modifier is wrong.
**Rule:** Claude's modifier is bounded to +/-15% for a reason. Always validate that the modifier distribution is centered near zero across many fixtures. If Claude consistently adjusts up or down, it's biased, not insightful.

### 4. The Feature Factory
**What it is:** Adding hundreds of features (squad value, weather, referee stats, social media sentiment) hoping more data = better model.
**Why deadly:** Each feature is a potential leakage vector and overfitting opportunity. The existing project found that `core_ext` (213 features) outperforms `full` (which adds squad+tactic features but drops to 65% row coverage).
**Rule:** Fewer, well-validated features > many noisy features. Every feature must pass: (1) available at prediction time, (2) not redundant with existing features, (3) improves CV score on held-out data.

---

## Sources

- [Systematic Review of ML in Sports Betting](https://arxiv.org/abs/2410.21484) -- comprehensive review of why ML models fail in betting markets
- [AI Models Fail to Beat Premier League Odds](https://mlq.ai/news/ai-models-fail-to-beat-premier-league-betting-odds-in-new-research/) -- 8 frontier AI models all lost money on 2023-24 PL
- [scikit-learn Probability Calibration docs](https://scikit-learn.org/stable/modules/calibration.html) -- isotonic vs Platt failure modes
- [Corner Kick Forecasting (Compound Poisson)](https://arxiv.org/abs/2112.13001) -- corner prediction model challenges
- [Corner Kick Timing Analysis (SFU)](https://www.sfu.ca/~tswartz/papers/ckick.pdf) -- event history analysis of corner timing
- [Frailty Model for Corner Kick Analysis](https://arxiv.org/html/2602.22684) -- recent (2026) academic work on corner timing
- [Bundesliga Simple Models Study (2026)](https://journals.sagepub.com/doi/10.1177/22150218261416681) -- isotonic calibration in football prediction
- [Getting Precise About CLV (Unabated)](https://unabated.com/articles/getting-precise-about-closing-line-value) -- CLV calculation methodology and common errors
- [Betano Account Limits (SBR Forum)](https://www.sportsbookreview.com/forum/sportsbooks-industry/3729222-betano-warning-wager-limits-lowered-1-50-over-4000-rollover-remaining.html) -- real user reports of Betano restrictions
- [Bookmaker Gubbing Detection Patterns](https://exchange-betting.com/knowledge-base/what-is-gubbing-in-betting-and-how-to-avoid-it/) -- how bookmakers detect winning patterns
- [Telegram Bot API Rate Limits](https://gramio.dev/rate-limits) -- current rate limit documentation
- [python-telegram-bot Flood Limits Issue](https://github.com/python-telegram-bot/python-telegram-bot/issues/3018) -- delivery delay patterns
- [LLM API Latency Benchmarks 2026](https://www.kunalganglani.com/blog/llm-api-latency-benchmarks-2026) -- Claude latency measurements
- [OWASP LLM Prompt Injection 2025](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) -- prompt injection in production pipelines
- [Reduce LLM Cost and Latency Guide 2026](https://www.getmaxim.ai/articles/reduce-llm-cost-and-latency-a-comprehensive-guide-for-2026/) -- cost control strategies
