# Architecture Patterns

**Domain:** Multi-sport betting intelligence platform
**Researched:** 2026-04-22

## Recommended Architecture

### Overview: Three-Layer Pipeline with Plugin Spine

The proposed 3-layer architecture (Data / Intelligence / Delivery) is appropriate but needs one structural refinement: **treat it as a pipeline, not as independent layers**. The critical constraint is the 2h pre-kickoff window -- data must flow unidirectionally through the pipeline within a strict time budget. Each layer should be a processing stage, not a service.

```
                    +-----------------+
                    |   APScheduler   |
                    | (Orchestrator)  |
                    +--------+--------+
                             |
              triggers pipeline per fixture
                             |
          +------------------v------------------+
          |          LAYER 1: DATA              |
          |                                     |
          |  SportPlugin.get_fixtures(date)     |
          |         |                           |
          |  API Client (httpx async)           |
          |         |                           |
          |  SportPlugin.build_features()       |
          |         |                           |
          |  Parquet Cache (read/write)         |
          |         |                           |
          |  Supabase (persist raw + features)  |
          +------------------+------------------+
                             |
                    FeatureSet (Pydantic)
                             |
          +------------------v------------------+
          |       LAYER 2: INTELLIGENCE         |
          |                                     |
          |  SportPlugin.build_claude_context()  |
          |         |                           |
          |  Claude API -> confidence_modifier  |
          |         |                           |
          |  SportPlugin.predict(features)      |
          |         |                           |
          |  ProbabilityMap (calibrated)        |
          |         |                           |
          |  EV Engine (core, sport-agnostic)   |
          |         |                           |
          |  Kelly Sizing (core)                |
          +------------------+------------------+
                             |
                    Pick[] or empty
                             |
          +------------------v------------------+
          |        LAYER 3: DELIVERY            |
          |                                     |
          |  Claude Validator (red flag check)  |
          |         |                           |
          |  Telegram Alert (if pick survives)  |
          |         |                           |
          |  Supabase (log prediction + pick)   |
          +------------------+------------------+
                             |
              (post-match, separate schedule)
                             |
          +------------------v------------------+
          |       FEEDBACK LOOP (async)         |
          |                                     |
          |  Result Collector (API-Football)    |
          |  CLV Recorder (The Odds API)        |
          |  Performance Aggregator             |
          |  Drift Detection (monthly)          |
          +-------------------------------------+
```

### Why This Works (and Known Issues to Avoid)

**Why 3 layers is correct:**
- Clean separation of concerns: data acquisition, intelligence, action
- Each layer has a single failure mode (API down, model error, delivery failure)
- Plugin boundary lives cleanly in Layer 1 and Layer 2 -- sport-specific code stays in `SportPlugin`, core logic stays in `core/`

**Known issues with ML pipelines in this pattern:**
1. **Training-serving skew.** The feature engineering code used in backtesting MUST be the exact same code used in real-time inference. Do NOT have separate training and inference feature pipelines. Use one `build_features()` method for both paths. The existing `football-predictor` already does this correctly -- preserve that pattern.
2. **Leaky time boundaries.** Walk-forward backtesting must use point-in-time features only. The Parquet cache must store features with their computation timestamp, not just the match date. This prevents future data from leaking into historical predictions.
3. **Claude latency variability.** Claude API calls can take 2-15 seconds. In a pipeline with a 2h window processing 20+ fixtures, Claude calls must be batched async, not sequential. Budget 60 seconds max for Claude across all fixtures in a batch.

### Component Boundaries

| Component | Responsibility | Communicates With | Location |
|-----------|---------------|-------------------|----------|
| **Scheduler** | Triggers pipeline runs at 2h and 30min pre-kickoff; triggers post-match jobs | All components (orchestrator) | `core/scheduler.py` |
| **Pipeline Runner** | Executes the 3-layer pipeline for a batch of fixtures | Scheduler (triggered by), Plugin Registry (discovers plugins) | `core/pipeline.py` |
| **Plugin Registry** | Discovers and loads SportPlugin implementations | Pipeline Runner | `core/registry.py` |
| **SportPlugin ABC** | Interface contract for sport-specific code | Pipeline Runner (called by) | `core/plugin.py` |
| **Football Plugin** | Implements SportPlugin for football | API-Football client, Feature Pipeline, ML Models | `sports/football/` |
| **API Client (per sport)** | Fetches fixtures, stats, lineups, odds from external APIs | External APIs (httpx async) | `sports/football/api/` |
| **Feature Pipeline (per sport)** | Transforms raw data into ML features using Polars | Parquet Cache (read/write), API Client (reads raw data) | `sports/football/features/` |
| **Parquet Cache** | Hive-partitioned feature store for historical + computed features | Feature Pipeline (read/write), Backtester (read-only) | `core/storage/parquet_store.py` (reuse from Football_analysis) |
| **ML Models (per sport)** | Ensemble prediction with calibrated probabilities | Feature Pipeline (receives features), EV Engine (sends ProbabilityMap) | `sports/football/models/` |
| **Claude Augmenter** | Generates confidence_modifier from pre-match context | SportPlugin.build_claude_context(), ML Models (feeds modifier as feature) | `core/claude/augmenter.py` |
| **Claude Validator** | Checks picks against learnings red flags | Pick Engine (receives candidate picks), Telegram (blocks/passes) | `core/claude/validator.py` |
| **EV Engine** | Calculates expected value from model probs vs bookmaker odds | ML Models (receives ProbabilityMap), Odds snapshots (receives odds) | `core/ev_engine.py` |
| **Kelly Sizer** | Computes fractional Kelly stake | EV Engine (receives edge), Pick (outputs stake) | `core/kelly.py` |
| **Telegram Bot** | Sends alerts for qualified picks | Pick Engine (receives qualified picks) | `core/telegram/` |
| **CLV Tracker** | Records closing line value post-match | The Odds API (fetches Pinnacle closing), Supabase (stores CLV records) | `core/clv_tracker.py` |
| **Performance Metrics** | Aggregates ROI, CLV, accuracy by league/market/period | Supabase (reads results + CLV), scheduled job | `core/metrics.py` |
| **Supabase Client** | Database operations (predictions, picks, results, CLV, metrics) | All components that persist data | `core/storage/supabase_client.py` |

---

## Data Flow: The Pre-Kickoff Pipeline

### Standard Run (2h before kickoff)

This is the primary pipeline. It runs once per matchday batch.

```
1. Scheduler fires "pre_kickoff_2h" trigger
   |
2. Pipeline Runner queries: which fixtures kick off in 1h50m - 2h10m?
   |
3. For each fixture (async, batched by sport):
   |
   a. plugin.get_fixtures(date) -> list[Fixture]
   |     - API-Football: fixture details, team form, standings
   |     - Cached if already fetched today
   |
   b. plugin.build_features(fixture) -> FeatureSet
   |     - Read historical features from Parquet (rolling averages, H2H)
   |     - Compute live features (form, injuries, motivation)
   |     - lineups NOT yet confirmed at 2h -> use expected lineup model
   |     - Write computed FeatureSet to Parquet cache
   |
   c. plugin.build_claude_context(fixture) -> str
   |     - Generates structured text: form, H2H, injuries, motivation
   |     - Includes any learnings red flags that match this fixture
   |
   d. Claude Augmenter: context_str -> confidence_modifier (-0.15 to +0.15)
   |     - Single API call per fixture
   |     - Structured output (Pydantic model for response parsing)
   |     - Modifier added to FeatureSet as additional feature column
   |
   e. plugin.predict(features_with_modifier) -> ProbabilityMap
   |     - Ensemble: XGBoost + CatBoost + LightGBM + LogReg stacker
   |     - Per-league isotonic calibration applied
   |     - Returns dict[Market, dict[Selection, float]]
   |
   f. EV Engine: ProbabilityMap + live_odds -> list[CandidatePick]
   |     - For each market in plugin.get_available_markets(fixture):
   |       - Fetch current Betano odds (The Odds API or direct)
   |       - Compute edge = model_prob - implied_prob
   |       - Filter: edge >= league_config.edge_threshold[market]
   |
   g. Kelly Sizer: CandidatePick -> Pick with suggested_stake
   |     - Quarter-Kelly (fraction=0.25)
   |     - Cap at max_stake from settings
   |
   h. Claude Validator: Pick -> Pick | None
   |     - Checks pick against learnings/football-learnings.md
   |     - If red flag match -> annotate and suppress
   |     - If pass -> approve for delivery
   |
   i. Telegram: send approved picks
   |
   j. Supabase: persist Prediction, Pick, OddsSnapshot
```

### Lineup-Adjusted Run (30min before kickoff)

```
1. Scheduler fires "pre_kickoff_30m" trigger
   |
2. For each fixture with an existing prediction:
   |
   a. Fetch confirmed lineups from API-Football
   |     - If lineups NOT available: skip (keep 2h prediction)
   |     - If lineups available:
   |
   b. Rebuild features with confirmed lineup data
   |     - Key features affected: expected xG adjustment, missing key players
   |     - Set is_lineup_adjusted = True on FeatureSet
   |
   c. Re-predict with updated features
   |     - Compare new ProbabilityMap with 2h prediction
   |     - If delta > threshold (e.g., >5% prob shift on any market):
   |       - Re-run EV check
   |       - If pick changes (new pick, pick invalidated, or edge gone):
   |         - Send Telegram update: "LINEUP UPDATE: [details]"
   |       - Update Supabase prediction with is_lineup_adjusted=True
```

### Post-Match Feedback Loop

```
1. Scheduler fires "post_match" trigger (3h after last kickoff)
   |
2. Result Collector:
   |  - Fetch match results from API-Football
   |  - Store Result in Supabase
   |  - Mark picks as won/lost/void/push
   |
3. CLV Recorder (runs separately, ~5min before kickoff):
   |  - Fetch Pinnacle closing odds from The Odds API
   |  - Store OddsSnapshot with is_closing=True
   |  - Calculate CLV for each pick: clv = (odds_at_pick / pinnacle_closing) - 1
   |  - Store ClvRecord in Supabase
   |
4. Performance Aggregator (daily, 6AM UTC):
   |  - Aggregate results by league, market, period
   |  - Compute ROI, yield, avg_clv, avg_edge
   |  - Store PerformanceMetric in Supabase
   |
5. Drift Detection (weekly):
   |  - Compare rolling 4-week CLV against historical baseline
   |  - If avg_clv drops below +1%: alert via Telegram
   |  - If calibration degrades (logloss > baseline + 0.03): flag for retraining
```

---

## Parquet Cache Structure for Dual-Use (Backtesting + Inference)

This is a critical architectural decision. The cache must serve two consumers with different access patterns:

### Directory Layout

```
data/parquet/
    features/
        sport=football/
            league=premier_league/
                season=2024-2025/
                    matchday=01/
                        features.parquet    # one file per matchday
                    matchday=02/
                        features.parquet
                    ...
            league=la_liga/
                ...
    raw/
        sport=football/
            league=premier_league/
                season=2024-2025/
                    fixtures.parquet
                    statistics.parquet
                    lineups.parquet
                    odds_snapshots.parquet
    models/
        sport=football/
            v001_2025-08/
                ensemble.pkl
                calibrators/
                    premier_league.pkl
                    la_liga.pkl
                metadata.json         # features used, training window, metrics
            v002_2025-12/
                ...
            active -> v002_2025-12    # symlink to production model
```

### Why This Layout

1. **Matchday partitioning enables walk-forward.** Backtesting reads `matchday <= N` for training, `matchday == N+1` for validation. Polars predicate pushdown skips unneeded matchdays without scanning.

2. **Sport partitioning future-proofs for tennis.** Adding `sport=tennis` requires zero changes to the store -- just new partition values.

3. **Features separate from raw data.** Raw API responses are immutable (never rewritten). Features are recomputed when the feature pipeline changes. Separating them avoids redownloading 4 seasons of API data when you change a rolling window from 5 to 10 matches.

4. **Model versioning via directory, not database.** Models are large binary blobs. Store them as files with metadata.json for provenance. Symlink `active` to the production version. Supabase stores model_version string for audit trail, not the model itself.

### Access Patterns

| Consumer | Pattern | Parquet Feature Used |
|----------|---------|---------------------|
| Walk-forward backtesting | Read all matchdays for a league/season, iterate forward | Hive partition pruning on season + matchday |
| Real-time inference | Read latest matchday + compute live features | Direct file read of most recent partition |
| Feature recompute | Overwrite features/ while preserving raw/ | Partition-level overwrite (existing pattern from ParquetStore) |
| Model training | Read features across multiple seasons | Cross-partition scan with league filter |

### Critical: Point-in-Time Correctness

Every feature row must include:
- `computed_at: datetime` -- when this feature was calculated
- `fixture_id: int` -- which match this is for
- `kickoff_utc: datetime` -- when the match starts
- `is_lineup_adjusted: bool` -- whether confirmed lineups were used

For backtesting, filter `computed_at < kickoff_utc` to ensure no future information leaks.

---

## Claude Integration Pattern

Use Claude in **two distinct roles** with different architectural patterns. Do NOT merge them into one call.

### Role A: Context Augmenter (Pre-Prediction)

**Pattern: Feature generator.** Claude reads structured pre-match context and outputs a numeric `confidence_modifier` that feeds into the ML ensemble as an additional feature.

```python
# core/claude/augmenter.py

class ClaudeAugmenter:
    """Generates confidence_modifier from pre-match context."""

    async def augment(self, context: str, fixture: Fixture) -> float:
        """Returns confidence_modifier in range [-0.15, +0.15]."""
        response = await self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            system=AUGMENTER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": context}],
            # Use structured output to force numeric response
        )
        return self._parse_modifier(response)
```

**Why this pattern:**
- Claude sees qualitative signals the model cannot (motivation, manager changes, derby dynamics)
- Numeric output keeps the pipeline deterministic -- ML model decides weight
- Costs ~$0.01-0.03 per fixture (Sonnet, ~2K input tokens)
- If Claude API is down, modifier defaults to 0.0 -- pipeline continues without it

**Anti-pattern to avoid:** Do NOT use Claude to generate probability estimates directly. Claude is not calibrated. Its "70% chance" means nothing statistically. Use it for qualitative -> quantitative signal conversion only.

### Role B: Pick Validator (Post-Prediction)

**Pattern: Safety gate.** Claude checks a candidate pick against known red flags before delivery.

```python
# core/claude/validator.py

class ClaudeValidator:
    """Validates picks against learnings and red flags."""

    async def validate(self, pick: Pick, context: str) -> ValidationResult:
        """Returns APPROVE, SUPPRESS, or ANNOTATE with reasoning."""
        learnings = self._load_learnings(pick.market, pick.league)
        response = await self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            system=VALIDATOR_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"Pick: {pick}\nContext: {context}\nLearnings: {learnings}"
            }],
        )
        return self._parse_validation(response)
```

**Why this pattern:**
- Learnings file (`football-learnings.md`) captures domain knowledge that is hard to encode as rules
- Claude can pattern-match "this is a trap game" or "newly promoted team away at top-6, historically under-performed" against the learnings
- Validation is a binary gate -- it does not change the pick, only approves or suppresses
- Reasoning is logged to Supabase for audit and future learnings updates

### Cost Budget

At 20 fixtures/day, 2 Claude calls per fixture (augment + validate):
- Sonnet at ~$0.02/call: **$0.80/day, ~$24/month**
- Acceptable for the value delivered

---

## EV Engine and Kelly: Data Flow Pattern

```
ProbabilityMap                    Live Odds
{                                 {
  "1x2": {                          "1x2": {
    "home": 0.45,                      "home": 2.30,
    "draw": 0.28,                      "draw": 3.40,
    "away": 0.27                       "away": 3.10
  },                                 },
  "btts": {                          "btts": {
    "yes": 0.58,                       "yes": 1.85,
    "no": 0.42                         "no": 1.95
  }                                  }
}                                 }
        \                        /
         \                      /
          v                    v
    +---------------------------+
    |       EV Engine           |
    |                           |
    |  For each market:         |
    |    For each selection:    |
    |      implied = 1/odds     |
    |      edge = model - impl  |
    |      ev = (model*odds)-1  |
    |                           |
    |  Filter: edge >= threshold|
    |  (threshold from YAML)    |
    +-------------+-------------+
                  |
          CandidatePick[]
                  |
    +-------------v-------------+
    |       Kelly Sizer         |
    |                           |
    |  kelly_full = edge/(odds-1)|
    |  kelly_frac = full * 0.25 |
    |  stake = bankroll * frac  |
    |  cap at max_stake         |
    +-------------+-------------+
                  |
             Pick[] (with stake)
```

**Key design decision:** The EV Engine is sport-agnostic. It operates on `ProbabilityMap` (a `dict[str, dict[str, float]]`) and `OddsMap` (same structure). The sport plugin decides which markets to populate; the EV Engine processes whatever it receives. This is how tennis can use `match_winner` and `set_spread` without changing the EV Engine.

### Edge Threshold Configuration

Edge thresholds live in the YAML league config (already designed in Football_analysis):

```yaml
# leagues/premier_league.yaml
model_params:
  edge_threshold_btts: 0.05      # 5% min edge for BTTS
  edge_threshold_ah: 0.06        # 6% for Asian Handicap (harder to calibrate)
  edge_threshold_1x2: 0.08       # 8% for 1X2 (3-way market = noisier)
  edge_threshold_corners: 0.07   # 7% for corners (less liquid market)
```

For tennis, the equivalent would be:
```yaml
# sports/tennis/leagues/atp_hard.yaml
model_params:
  edge_threshold_match_winner: 0.05
  edge_threshold_set_spread: 0.06
```

---

## Model Versioning and A/B Testing

### Versioning Scheme

```
models/sport=football/v{NNN}_{YYYY-MM}/
    ensemble.pkl
    calibrators/{league}.pkl
    metadata.json
```

`metadata.json`:
```json
{
  "version": "v002",
  "sport": "football",
  "created_at": "2025-12-15T10:30:00Z",
  "training_window": "2020-08 to 2025-11",
  "feature_set": "core_ext",
  "feature_count": 213,
  "base_learners": ["xgboost", "catboost", "lightgbm"],
  "stacker": "logistic_regression",
  "calibration_method": "isotonic",
  "validation_metrics": {
    "logloss": 0.9484,
    "rps": 0.1915,
    "accuracy": 0.5492
  },
  "clv_baseline": 0.035
}
```

### Shadow Mode A/B Testing

Do NOT run A/B tests in production betting. A wrong model costs money. Instead:

1. **Shadow predictions.** New model runs alongside active model but its predictions are only logged, not acted upon.
2. **CLV comparison.** After 2-4 weeks of shadow data, compare CLV of shadow picks vs active picks.
3. **Promotion criteria:**
   - Shadow model CLV >= active model CLV (or within 0.5%)
   - Shadow model calibration (logloss) <= active model
   - At least 100 shadow picks accumulated
4. **Promotion:** Update `active` symlink. Log promotion in Supabase.

```python
# core/pipeline.py (shadow mode)

active_model = registry.get_active_model(sport="football")
shadow_model = registry.get_shadow_model(sport="football")  # may be None

probs_active = active_model.predict(features)
if shadow_model:
    probs_shadow = shadow_model.predict(features)
    supabase.log_shadow_prediction(fixture_id, probs_shadow, shadow_model.version)

# Only active model drives picks
picks = ev_engine.evaluate(probs_active, odds)
```

### Retraining Triggers

Retrain when ANY of these conditions is met:
- **Calendar:** Start of each season (August) -- mandatory
- **Drift:** Rolling 4-week CLV drops below +1% (was +3.5% baseline)
- **Calibration decay:** Rolling logloss exceeds baseline + 0.03
- **Data change:** New feature added to pipeline

Retraining is **manual** (not automated). The system alerts via Telegram; the operator reviews and triggers `python train.py`.

---

## Deployment Topology: Single VPS with systemd

### Process Architecture

One Python process, not microservices. This is a single-user system processing 5-10 fixtures/day. Microservices would add latency, complexity, and failure modes for zero benefit.

```
VPS (Hetzner CPX21: 3 vCPU, 4GB RAM, ~7 EUR/mo)
|
+-- systemd: betting-platform.service
|   |
|   +-- Python process (main.py)
|       |
|       +-- APScheduler (AsyncIOScheduler)
|       |   |-- job: pre_kickoff_2h     (cron-like, per league schedule)
|       |   |-- job: pre_kickoff_30m    (cron-like, per league schedule)
|       |   |-- job: clv_snapshot       (5min before each kickoff)
|       |   |-- job: post_match_results (3h after last kickoff)
|       |   |-- job: daily_metrics      (06:00 UTC daily)
|       |   |-- job: weekly_drift_check (Monday 07:00 UTC)
|       |
|       +-- python-telegram-bot (async, in same event loop)
|       |
|       +-- httpx.AsyncClient (connection pool, shared)
|
+-- systemd: betting-platform-health.timer
    |-- runs every 5min
    |-- checks: process alive, last heartbeat < 10min ago, disk space
    |-- alerts via Telegram if unhealthy
```

### systemd Service File

```ini
# /etc/systemd/system/betting-platform.service
[Unit]
Description=Betting Intelligence Platform
After=network.target

[Service]
Type=simple
User=betting
WorkingDirectory=/opt/betting-platform
ExecStart=/opt/betting-platform/.venv/bin/python -m core.main
Restart=on-failure
RestartSec=30
Environment=PYTHONPATH=/opt/betting-platform
EnvironmentFile=/opt/betting-platform/.env

# Resource limits
MemoryMax=3G
CPUQuota=250%

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=betting-platform

[Install]
WantedBy=multi-user.target
```

### Why Single Process, Not Microservices

| Concern | Single Process | Microservices |
|---------|---------------|---------------|
| Latency | Function calls (~0ms) | HTTP/gRPC (~5-50ms per hop) |
| Failure modes | 1 (process crash) | N (any service can fail independently) |
| Debugging | One log stream | Distributed tracing needed |
| Deployment | `git pull && systemctl restart` | Container orchestration |
| Memory | Shared model in RAM (~200MB) | Each service loads its own copy |
| Appropriate for | 1 user, 5-10 fixtures/day | Team of engineers, 10K+ requests/sec |

### Health Monitoring

```python
# core/health.py
HEARTBEAT_FILE = Path("/tmp/betting-platform-heartbeat")

async def heartbeat_loop():
    """Write timestamp every 60 seconds."""
    while True:
        HEARTBEAT_FILE.write_text(datetime.utcnow().isoformat())
        await asyncio.sleep(60)
```

External timer checks the heartbeat file age. If stale > 10 minutes, send Telegram alert. This catches hangs that systemd restart cannot detect.

---

## Patterns to Follow

### Pattern 1: Plugin Discovery via Entry Points (Not Import Scanning)

**What:** Register sport plugins using Python packaging entry points or a simple registry dict, not by scanning directories for subclasses.

**When:** When adding new sports without modifying core code.

**Example:**
```python
# core/registry.py
class PluginRegistry:
    _plugins: dict[str, type[SportPlugin]] = {}

    @classmethod
    def register(cls, sport: str):
        def decorator(plugin_cls: type[SportPlugin]):
            cls._plugins[sport] = plugin_cls
            return plugin_cls
        return decorator

    @classmethod
    def get(cls, sport: str) -> SportPlugin:
        return cls._plugins[sport]()

# sports/football/__init__.py
@PluginRegistry.register("football")
class FootballPlugin(SportPlugin):
    ...
```

### Pattern 2: Pydantic for All Cross-Component Data

**What:** Use Pydantic models for all data flowing between components. No raw dicts crossing component boundaries.

**When:** Always. This is non-negotiable for type safety in a pipeline.

**Why:** The existing Football_analysis already uses Pydantic models (Prediction, Pick, OddsSnapshot, etc.). Extend this to FeatureSet, ProbabilityMap, and CandidatePick.

### Pattern 3: Async All the Way Down

**What:** The pipeline is async from scheduler to API calls. No sync blocking in the event loop.

**When:** Any I/O operation (API calls, Supabase queries, file reads for large datasets).

**Why:** The 2h window requires concurrent API calls across fixtures. httpx async + python-telegram-bot async + APScheduler AsyncIOScheduler all share one event loop.

### Pattern 4: Graceful Degradation

**What:** If any non-critical component fails, the pipeline continues with reduced capability.

**When:** Claude API down, The Odds API down, one league's data unavailable.

**Example degradation chain:**
- Claude Augmenter fails -> `confidence_modifier = 0.0`, pipeline continues
- Claude Validator fails -> pick approved by default (log warning)
- The Odds API fails -> no CLV recording, but picks still sent
- API-Football lineups unavailable -> use 2h prediction without lineup adjustment
- One league's API data fails -> skip that league, process others

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Separate Training and Inference Feature Code

**What:** Having one feature pipeline for batch training and a different one for real-time inference.
**Why bad:** Guaranteed training-serving skew. Model sees different features in production than training.
**Instead:** One `build_features()` method. For training, call it on historical data row by row (or vectorized with same logic). For inference, call it on live data. Same code path.

### Anti-Pattern 2: Claude as Probability Source

**What:** Asking Claude "what is the probability of Team A winning?"
**Why bad:** LLMs are not calibrated probabilistic models. Claude's "60%" is vibes, not statistics.
**Instead:** Use Claude for qualitative signal extraction -> numeric modifier. The ensemble model produces calibrated probabilities.

### Anti-Pattern 3: Real-Time Odds in Feature Pipeline

**What:** Using current bookmaker odds as ML features during training.
**Why bad:** Bookmaker odds are the target you are trying to beat. Using them as features is circular. Your model would learn to mimic bookmakers, not beat them.
**Instead:** Use odds ONLY in the EV calculation layer (comparing model output vs bookmaker). Historical closing odds can be used as a calibration reference, not as model features.

### Anti-Pattern 4: Monolith Model File

**What:** One giant `model.py` with training, inference, calibration, feature selection all mixed.
**Why bad:** Impossible to test components independently. Changes to calibration break training.
**Instead:** Separate: `ensemble.py` (model definition), `trainer.py` (training loop), `calibrator.py` (post-training calibration), `predictor.py` (inference-only, loads trained model).

---

## Suggested Build Order

Dependencies dictate build order. You cannot build downstream without upstream.

```
Phase 1: Foundation (no ML, no Claude)
  core/plugin.py          -- SportPlugin ABC
  core/registry.py        -- Plugin discovery
  core/storage/           -- ParquetStore (port from Football_analysis)
  core/storage/supabase   -- Supabase client + migration 002 (add sport column)
  core/settings.py        -- Settings (port + extend)
  sports/football/api/    -- API-Football async client

Phase 2: Feature Pipeline (ML foundation)
  sports/football/features/  -- Feature engineering (port from football-predictor)
  Parquet cache integration  -- Write features to Parquet with point-in-time stamps
  Backtesting framework      -- Walk-forward with Parquet reads

Phase 3: ML Core
  sports/football/models/    -- Ensemble training pipeline
  Calibration per league     -- Isotonic/Platt calibrators
  Model versioning           -- Directory layout + metadata.json

Phase 4: Pick Engine (EV + Delivery)
  core/ev_engine.py          -- EV calculation (port from Claude_Sport_Betting)
  core/kelly.py              -- Kelly sizing (port from Claude_Sport_Betting)
  core/telegram/             -- Telegram bot (pick alerts)

Phase 5: Claude Integration
  core/claude/augmenter.py   -- Confidence modifier
  core/claude/validator.py   -- Pick validation against learnings
  Integration into pipeline  -- Wire Claude into Layer 2 and Layer 3

Phase 6: Orchestration + Deployment
  core/scheduler.py          -- APScheduler with all job triggers
  core/pipeline.py           -- End-to-end pipeline runner
  core/health.py             -- Heartbeat + monitoring
  systemd service            -- VPS deployment
  CLV tracker                -- Post-match feedback loop

Phase 7: Corners Module (specialty market)
  sports/football/corners/   -- Corner timing model
  Corner-specific features   -- Time-window distributions
  Betano market verification -- Confirm available markets

Phase 8: Tennis Scaffold (validates plugin architecture)
  sports/tennis/             -- Skeleton SportPlugin
  Verify: zero core changes  -- If any core changes needed, refactor
```

**Build order rationale:**
- Phase 1 must come first: everything depends on the plugin interface and storage layer
- Phase 2 before 3: features must exist before models can train on them
- Phase 4 before 5: Claude is an enhancement, not a requirement. The system must work without it
- Phase 6 after 4+5: orchestration wires together what already works
- Phase 7 is independent of 5+6: corners module can be built in parallel
- Phase 8 is a validation exercise, not a feature: proves the architecture is correct

---

## Scalability Considerations

| Concern | At 5 leagues | At 15 leagues (+ tennis) | At 50 leagues (multi-sport) |
|---------|-------------|--------------------------|----------------------------|
| API calls | ~50/day | ~200/day | ~1000/day, need rate limiting |
| Parquet size | ~500MB | ~2GB | ~10GB, consider partitioned reads only |
| Inference time | ~2s total | ~8s total | ~30s, may need parallel inference |
| Claude costs | $24/mo | $72/mo | $240/mo, consider batching or caching |
| VPS resources | 1 vCPU sufficient | 2 vCPU recommended | 4 vCPU, 8GB RAM |
| Supabase | Free tier | Pro tier | Pro tier + connection pooling |

The architecture handles 50 leagues without structural changes. The bottleneck at scale is Claude API cost, not compute. At that point, consider caching Claude responses for similar fixture profiles.

---

## Sources

- [Hopsworks FTI Pipeline Architecture](https://www.hopsworks.ai/post/mlops-to-ml-systems-with-fti-pipelines) -- Feature/Training/Inference pipeline pattern
- [Conduktor Real-Time ML Pipelines](https://www.conduktor.io/glossary/real-time-ml-pipelines) -- Streaming feature engineering patterns
- [QuestDB Parquet for Time Series](https://questdb.com/blog/why-parquet-matters-for-time-series-and-finance/) -- Parquet columnar storage for financial/time series data
- [APScheduler Documentation](https://apscheduler.readthedocs.io/en/3.x/) -- Scheduler integration patterns
- [SmartMoneyPath VPS Trading Bot Setup](https://smartmoneypath.io/how-to-run-a-trading-bot-24-7-vps-setup-guide-2026/) -- VPS deployment for automated trading systems
- [Sports-AI CLV Guide](https://www.sports-ai.dev/blog/closing-line-value-and-ai-model-performance) -- CLV as model validation metric
- [OpticOdds Claude MCP Integration](https://next.io/news/betting/qa-opticodds-vp-integrating-betting-odds-claude/) -- LLM integration with betting odds data
- Existing codebase: `Football_analysis/` -- ParquetStore, Pydantic models, league configs, Supabase schema
- Existing codebase: `Claude_Sport_Betting/` -- EV calculator, Kelly criterion, learnings methodology
- Existing codebase: `football-predictor/` -- Ensemble architecture, calibration patterns, walk-forward backtesting
