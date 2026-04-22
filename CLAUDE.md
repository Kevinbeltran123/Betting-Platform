<!-- GSD:project-start source:PROJECT.md -->
## Project

**betting-intelligence-platform**

A unified, multi-sport betting intelligence platform built for scalability from day 1. Initially covering football across 5 top European leagues, it merges two existing systems — an ML prediction engine and a Claude-powered analysis methodology — into a single production pipeline. The system detects statistical edge using an ML ensemble, enriches analysis with Claude AI, and delivers Telegram alerts for qualified picks; the human makes the final betting decision.

**Core Value:** Find and deliver bets with genuine statistical edge (CLV > +3% against Pinnacle closing lines) — if there's no edge, send nothing.

### Constraints

- **Tech Stack**: Python 3.11+, uv, Polars, Pydantic v2, Supabase PostgreSQL — match existing Football_analysis stack exactly.
- **No GPU**: All ML training on CPU (gradient boosting); inference must be < 500ms per fixture.
- **API Limits**: API-Football Pro required (100 req/day free tier insufficient for corners history). The Odds API Rookie tier ($20/mo) sufficient for CLV-only use.
- **Account Safety**: Max 1/4 Kelly on Betano, vary stake patterns, rotate markets. Monitor CLV trend — if drops below +1%, pause and audit.
- **Semi-manual**: System sends Telegram alerts; human places bets. No automated bet placement.
- **Corners market verification**: Confirm exact Betano corner time-window markets available before building Phase 3.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Overview
## Core Framework
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Python | 3.12 | Runtime | 3.12 is the sweet spot: all ML libraries support it, free-threading not needed. 3.11 works but 3.12 has measurable perf gains (10-15% faster CPython). 3.13+ has free-threading but CatBoost/XGBoost wheels lag behind. | HIGH |
| uv | 0.11.x | Package/project manager | De facto standard replacing pip/poetry in 2025-2026. 100x faster resolution, lockfile support, Python version management built in. No alternative worth considering. | HIGH |
| Pydantic | 2.13.x | Data validation & models | Already in use in Football_analysis. v2 is mature and stable. Use for all domain models, API response parsing, config validation. | HIGH |
| pydantic-settings | 2.14.x | Configuration management | Loads from .env, env vars, YAML. Already proven in existing codebase. Replaces custom config loading. | HIGH |
## Data APIs
### Primary: API-Football v3 (Pro Plan)
| Attribute | Detail |
|-----------|--------|
| Version | v3 (current) |
| Plan | Pro ($79/mo) -- required for corners history, lineups, injuries |
| Rate limit | 300 req/min (Pro) |
| Data | Fixtures, live scores, stats, lineups, player stats, corners, injuries, H2H, standings |
| Confidence | HIGH -- already validated in existing project |
### Sharp Odds: The Odds API v4 (REVISED STRATEGY)
| Attribute | Detail |
|-----------|--------|
| Version | v4 |
| Plan | Rookie ($20/mo, 500 requests) |
| Primary use | CLV benchmark via Pinnacle closing lines |
| Confidence | MEDIUM -- see critical note below |
- Pinnacle odds via The Odds API are website-scraped, not direct API feed
- Expect 1-5 minute delay vs real-time (acceptable for CLV -- we only need closing lines)
- For CLV measurement (post-kickoff snapshot), delay is irrelevant
- The Odds API Rookie tier ($20/mo, 500 requests) is sufficient for CLV-only usage across 5 leagues
- Betfair Exchange (available via The Odds API: `betfair_ex_eu`) -- second-sharpest market
- OddsPapi (350+ bookmakers including Pinnacle, SingBet) -- alternative API if The Odds API Pinnacle coverage drops
### Alternative APIs Evaluated (Not Recommended for Now)
| API | Why Not |
|-----|---------|
| OddsPapi | Good backup but newer, less battle-tested. Per-request pricing can get expensive at scale. Keep as fallback. |
| SharpAPI | Enterprise-focused, expensive ($99+/mo). Overkill for CLV-only usage. |
| SportsGameOdds | Includes closing odds and historical data, but pricing unclear and API maturity uncertain. |
| football-data.org | Free tier useful but no odds data, limited stats. Redundant with API-Football. |
## ML Pipeline
### Ensemble Models
| Library | Version | Purpose | Why | Confidence |
|---------|---------|---------|-----|------------|
| XGBoost | 3.2.0 | Gradient boosting (primary) | Latest stable. Breaking change from 2.x: removed `DeviceQuantileDMatrix`, `manylinux2014` dropped. CPU-only usage unaffected. Requires Python >=3.10. | HIGH |
| CatBoost | 1.2.10 | Gradient boosting (categorical) | Feb 2026 release. Now supports Polars input directly (new in recent versions). Handles categorical features natively -- valuable for league/team encoding. | HIGH |
| LightGBM | 4.6.0 | Gradient boosting (fast training) | Feb 2025 release, stable. Fastest training of the three. Good for rapid iteration and walk-forward backtesting. | HIGH |
| scikit-learn | 1.8.0 | ML utilities, calibration, stacking | Dec 2025 release. **Key change:** `CalibratedClassifierCV(cv="prefit")` removed (you already handle this with `_IsotonicCalibrator`). New: `method="temperature"` for temperature scaling calibration -- worth evaluating vs isotonic. | HIGH |
- `method="temperature"` in `CalibratedClassifierCV` -- simpler than isotonic, less prone to overfitting with small samples (<200 per league). Evaluate alongside existing isotonic and Platt calibration.
- Array API support (PyTorch tensors) -- not needed for this project but future-proofs.
### Feature Engineering
| Library | Version | Purpose | Why | Confidence |
|---------|---------|---------|-----|------------|
| Polars | 1.40.x | DataFrame operations | 10-50x faster than pandas for feature engineering. Lazy evaluation for complex pipelines. Already proven in existing codebase. | HIGH |
| PyArrow | 19.x | Parquet I/O, Arrow memory | Required by Polars for Parquet read/write. Pin to match Polars' PyArrow dependency. | HIGH |
| NumPy | 2.2.x | Numerical operations | Required by all ML libraries. v2.x is now standard. | HIGH |
| SciPy | 1.15.x | Statistical functions | Poisson distributions, optimization for Dixon-Coles. Required by penaltyblog. | HIGH |
### Statistical Models
| Library | Version | Purpose | Why | Confidence |
|---------|---------|---------|-----|------------|
| penaltyblog | 1.9.0 | Dixon-Coles, Poisson, Bivariate Poisson | Feb 2026 release. Actively maintained (6 releases in 2025-2026). Cython-optimized. Includes Dixon-Coles, Bivariate Poisson, Conway-Maxwell Poisson, Bayesian variants. **Best option for football statistical models in Python -- no viable alternative.** | HIGH |
- Rolling your own Dixon-Coles: You already have a bivariate Poisson implementation in football-predictor. penaltyblog's Cython-optimized version is faster and more robust. Use penaltyblog for production, keep custom implementation as reference.
- `footballmodels` (GitHub): Abandoned, last commit 2022.
- `fpl` / `socceraction`: Different domain (expected goals, not match outcome modeling).
## AI Integration
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Anthropic Python SDK | latest (0.50+) | Claude API access | Direct SDK for claude-sonnet-4-6. Structured output via tool_use for `confidence_modifier` extraction. | HIGH |
| claude-sonnet-4-6 | - | Context augmentation + pick validation | Cost-effective for structured analysis tasks. ~$3/1M input tokens. Role B (confidence modifier) and Role C (pick validator) don't need Opus-level reasoning. | HIGH |
- Role B (confidence modifier): Structured numeric output from pre-match context. Deterministic extraction task.
- Role C (pick validator): Pattern matching against known red flags. Doesn't require deep reasoning.
- Cost: ~50 picks/day x 2 calls x ~2K tokens = ~200K tokens/day = ~$0.60/day. Negligible.
## Delivery
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| python-telegram-bot | 22.7 | Telegram alerts | Jan 2026 release. Async-native (asyncio). Mature, well-documented. Handles message formatting, inline buttons, rate limiting. | HIGH |
## Scheduling
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| APScheduler | 3.11.x | Job scheduling | **Use 3.x, NOT 4.x.** APScheduler 4.0 is still alpha (4.0.0a6 as of April 2025). Complete rewrite with breaking API changes (Job split into Task/Schedule/Job, async-first). Not production-ready. | HIGH |
| Option | Verdict | Rationale |
|--------|---------|-----------|
| APScheduler 3.x | **USE THIS** | In-process scheduler. No external dependencies (no Redis, no broker). Perfect for single-VPS. Supports cron triggers, interval triggers, timezone-aware scheduling. Battle-tested. |
| Celery | AVOID | Requires Redis/RabbitMQ broker. Overkill for single-VPS with <100 scheduled jobs. Adds operational complexity (worker processes, broker monitoring). |
| RQ (Redis Queue) | AVOID | Requires Redis. Simpler than Celery but still external dependency. Only needed if you need distributed task queues. |
| Huey | AVOID | Lighter than Celery but still needs Redis/SQLite backend. No advantage over APScheduler for in-process scheduling. |
| cron (system) | AVOID | No Python-level control, hard to manage dynamically scheduled jobs (fixtures at varying times). |
| `asyncio` native scheduling | CONSIDER LATER | For simple periodic tasks, `asyncio.create_task` + sleep loop works. But APScheduler adds cron expressions, missed job handling, persistence. Worth the dependency. |
- `BackgroundScheduler` (thread-based) or `AsyncIOScheduler` (if running in asyncio loop with telegram bot)
- `CronTrigger` for daily fixture fetching (e.g., 06:00 UTC)
- `DateTrigger` for per-fixture pre-kickoff runs (2h and 30min before)
- `MemoryJobStore` is fine (no persistence needed -- jobs are regenerated daily from fixture list)
## Infrastructure & Storage
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Supabase PostgreSQL | - | Primary database | Already has schema for 6 tables. Migration 002 adds `sport` column. Free tier sufficient for this scale. | HIGH |
| Parquet files (local) | - | Feature cache, training data | Polars + PyArrow for fast read/write. Avoids DB round-trips for ML pipeline. Store in `data/cache/`. | HIGH |
## HTTP & Networking
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| httpx | 0.28.1 | Async HTTP client | Async-native, HTTP/2 support, connection pooling. Used for API-Football, The Odds API, Anthropic SDK (uses httpx internally). One client for everything. | HIGH |
| tenacity | 9.x | Retry logic | Exponential backoff for API calls. Decorator-based, clean integration with httpx. | HIGH |
## Development & Quality
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| ruff | 0.11.x | Linting + formatting | Replaces flake8 + black + isort. 100x faster. De facto Python linting standard in 2025-2026. | HIGH |
| pytest | 8.x | Testing | Standard. Use with `pytest-asyncio` for async test support. | HIGH |
| pytest-asyncio | 0.25.x | Async test support | Required for testing httpx clients, telegram bot, APScheduler async. | HIGH |
| mypy | 1.15.x | Type checking | Strict mode. Pydantic v2 has excellent mypy plugin support. | MEDIUM |
## What NOT to Use
| Technology | Why Not |
|------------|---------|
| APScheduler 4.x | Alpha (4.0.0a6). Complete rewrite, breaking API, no migration path from 3.x yet. Wait for stable release. |
| Celery / RQ | External broker dependency (Redis). Single-VPS deployment doesn't need distributed task queues. |
| pandas | Polars is 10-50x faster for the same operations. pandas is legacy for new projects in 2026. |
| FastAPI / web server | No web UI in v1. Telegram-only delivery. Adding a web server adds attack surface and operational complexity for zero value. |
| TensorFlow / PyTorch | Gradient boosting outperforms neural nets on tabular sports data with <100K rows. GPU adds complexity for no gain. |
| Docker (initially) | Single-VPS, single-process Python app. Docker adds indirection. Use when deploying to cloud or adding services. `uv` handles reproducible environments. |
| Airflow / Prefect | Workflow orchestrators are overkill. APScheduler handles the 10-20 daily scheduled jobs fine. |
| scikit-learn CalibratedClassifierCV(cv="prefit") | Removed in 1.8. Use direct IsotonicRegression or explore new `method="temperature"`. |
| OddsPapi (as primary) | Newer API, less battle-tested. Keep as fallback if The Odds API Pinnacle coverage degrades. |
| Python 3.13+ | CatBoost wheel support lags. 3.12 is the safe, performant choice. |
## Missing from Original Stack (Additions)
| Library | Version | Purpose | Why Add |
|---------|---------|---------|---------|
| tenacity | 9.x | Retry/backoff for API calls | Production essential. API-Football and The Odds API both rate-limit aggressively. |
| structlog | 25.x | Structured logging | JSON-structured logs for debugging picks pipeline. Better than stdlib logging for tracing pick-to-alert flow. |
| ruff | 0.11.x | Linting + formatting | Code quality from day 1. Single tool replaces 3+ legacy tools. |
| pytest + pytest-asyncio | 8.x / 0.25.x | Testing | Untested ML pipeline = unreliable picks. Test calibration, EV calculation, Kelly sizing. |
| Library | Version | Purpose | When |
|---------|---------|---------|------|
| joblib | 1.4.x | Parallel model training | If walk-forward backtesting becomes slow (>5 min). Parallel fold execution. |
| orjson | 3.10.x | Fast JSON parsing | If API response parsing becomes a bottleneck. 2-10x faster than stdlib json. |
## Installation
# Initialize project
# Core dependencies
# Dev dependencies
## Open Questions
## Sources
- [APScheduler PyPI](https://pypi.org/project/APScheduler/) -- version and release info
- [APScheduler Migration Guide](https://apscheduler.readthedocs.io/en/master/migration.html) -- 3.x to 4.0 breaking changes
- [APScheduler 4.0 Progress Tracking](https://github.com/agronholm/apscheduler/issues/465) -- alpha status
- [penaltyblog PyPI](https://pypi.org/project/penaltyblog/) -- v1.9.0, Feb 2026
- [penaltyblog GitHub](https://github.com/martineastwood/penaltyblog) -- feature list, models
- [penaltyblog Model Comparison](https://pena.lt/y/2025/03/10/which-model-should-you-use-to-predict-football-matches/) -- Dixon-Coles vs alternatives
- [Pinnacle API Shutdown](https://odds-api.io/blog/pinnacle-api-shutdown-alternatives) -- July 2025 closure
- [The Odds API Bookmakers](https://the-odds-api.com/sports-odds-data/bookmaker-apis.html) -- Pinnacle still available via website scraping
- [XGBoost 3.0 Release Notes](https://xgboost.readthedocs.io/en/latest/changes/v3.0.0.html) -- breaking changes
- [XGBoost 3.2 PyPI](https://pypi.org/project/xgboost/) -- latest stable
- [scikit-learn 1.8 Highlights](https://scikit-learn.org/stable/auto_examples/release_highlights/plot_release_highlights_1_8_0.html) -- temperature scaling, array API
- [python-telegram-bot v22.7](https://pypi.org/project/python-telegram-bot/) -- latest release
- [Polars 1.40 PyPI](https://pypi.org/project/polars/) -- latest stable
- [CatBoost 1.2.10 Releases](https://github.com/catboost/catboost/releases) -- Polars support
- [LightGBM 4.6 PyPI](https://pypi.org/project/lightgbm/) -- latest stable
- [Pydantic v2.13](https://pypi.org/project/pydantic/) -- latest release
- [pydantic-settings v2.14](https://pypi.org/project/pydantic-settings/) -- latest release
- [uv](https://docs.astral.sh/uv/) -- package manager docs
- [httpx](https://www.python-httpx.org/) -- async HTTP client
- [OddsPapi](https://oddspapi.io/blog/the-odds-api-alternative-comparison/) -- alternative odds API
- [Odds API Pricing Comparison 2026](https://oddspapi.io/blog/odds-api-pricing-2026-comparison/) -- market overview
- [API-Football Pricing](https://www.api-football.com/pricing) -- Pro plan details
- [API-Football v3 Docs](https://www.api-football.com/documentation-v3) -- endpoints reference
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

## Conventions

- Never include Co-Authored-By trailers in git commits.

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
