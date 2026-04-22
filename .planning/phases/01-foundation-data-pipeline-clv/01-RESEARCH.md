# Phase 1: Foundation + Data Pipeline + CLV - Research

**Researched:** 2026-04-22
**Domain:** Python async data pipeline, plugin architecture, APScheduler 3.x, Polars Hive Parquet, Supabase, The Odds API CLV
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01: Code Migration Strategy**
Copy Football_analysis source files into the new repo and adapt in-place. Do NOT use a local editable dependency.
- Copy: `storage/models.py`, `repositories.py`, `supabase_client.py`, `shared/types.py`, `config/settings.py`, `config/league_config.py`, `config/league_registry.py`, league YAML configs (5 files), Supabase migration SQL.
- Rename package namespace: `football_betting` → new platform package name (e.g., `bip` or `betting_intelligence`).
- Add `sport: str = "football"` field to all 6 Pydantic models in the same commit as the copy.
- Football_analysis is retired once the new platform is green on the same Supabase instance.

**D-02: SportPlugin ABC Design**
- D-02a: `SportPlugin` defined as ABC (`abc.ABC` + `@abstractmethod`) in `sports/__init__.py`. Not a `typing.Protocol`.
- D-02b: All return types are typed Pydantic `BaseModel` subclasses — no `dict` or `Any` returns at the plugin boundary.
- D-02c: `ProbabilityMap` is sport-agnostic:
  ```python
  class ProbabilityMap(BaseModel):
      fixture_id: int
      market: str
      probabilities: dict[str, float]
      model_version: str
      computed_at: datetime
  ```
- D-02d: `FixtureData`, `FeatureMatrix`, `ClaudeContext` are typed Pydantic models.
- D-02e: Interface contract tests in Phase 1 (`tests/test_plugin_contract.py`).

**D-03: APScheduler Job Strategy**
- D-03a: Per-fixture DateTrigger jobs (two per fixture: kickoff - 2h and kickoff - 30min).
- D-03b: Auto-recovery on startup: if today's jobs are missing, re-run orchestrator for fixtures not yet kicked off.
- D-03c: MemoryJobStore — no persistence needed.
- D-03d: Uses `AsyncIOScheduler` (not `BackgroundScheduler`).

**D-04: CLV Snapshot Timing**
- D-04a: Fixed-delay: kickoff + 105 minutes (primary CLV snapshot via DateTrigger).
- D-04b: Nightly reconciliation at 03:00 UTC (CronTrigger) for `clv_records WHERE pinnacle_closing_odds IS NULL`.
- D-04c: `odds_fetched_at` timestamp logged alongside `pinnacle_closing_odds`.
- D-04d: No polling (exceeds 500-request Rookie tier budget).

### Claude's Discretion
- Exact Pydantic field names for `FixtureData`, `FeatureMatrix`, `ClaudeContext`.
- New platform package name (`bip`, `betting_intelligence`, or similar).
- Exact directory layout within `src/` (follow Football_analysis pattern).
- Whether `Settings` is extended in-place or split into `CoreSettings` + sport-specific overrides.

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within Phase 1 scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CORE-01 | `SportPlugin` ABC in `sports/__init__.py` with all required methods | D-02a/b/c/d fully specified; ABC + abstractmethod pattern verified in Pydantic v2 docs |
| CORE-02 | `core/` layer contains zero sport-specific code | Architectural responsibility map confirms tier separation |
| CORE-03 | Supabase migration 002 adds `sport VARCHAR(20) NOT NULL DEFAULT 'football'` to all 6 tables | Existing migration SQL read; ALTER TABLE approach confirmed |
| CORE-04 | Football plugin implements full `SportPlugin` interface and passes contract tests | Contract test pattern documented in Code Examples |
| CORE-05 | Markets defined as runtime YAML config — no hardcoded market enum in core | Market YAML structure and runtime loader pattern documented |
| DATA-01 | Async API-Football v3 client with tenacity retry/backoff | httpx + tenacity async patterns verified via Context7 + WebSearch |
| DATA-02 | Feature engineering with Polars; Parquet cache Hive-partitioned by `sport/league/season/matchday` | Polars write_parquet pyarrow_options pattern verified; 4-level partition design documented |
| DATA-03 | League config YAML loader extended from Football_analysis configs | Existing configs read; extension pattern for sport field documented |
| DATA-04 | APScheduler 3.11.x AsyncIOScheduler pipeline at T-2h and T-30min | APScheduler 3.x API verified; DateTrigger + CronTrigger patterns documented |
| DATA-05 | Integration test validates no future data leaks | computed_at timestamp enforcement pattern + test assertion strategy documented |
| CLV-01 | The Odds API v4 client fetches Pinnacle closing odds | Odds API v4 response format verified; endpoint URLs documented |
| CLV-02 | CLV recorded in `clv_records` table: `(odds_at_pick / closing_odds - 1) × 100` | Formula and model fields verified against existing schema |
| CLV-03 | CLV trend alert if rolling 50-pick average CLV < +1% | SQL query pattern documented; alert logic deferred to Phase 4 |
| CLV-04 | Performance metrics aggregated in `performance_metrics` table | Existing schema verified; sport column addition documented |
</phase_requirements>

---

## Summary

Phase 1 is a code migration and infrastructure build. The dominant workload is (1) porting approximately 14 existing Football_analysis Python files into a new package namespace with sport-agnostic extensions, (2) constructing the `SportPlugin` ABC atop those ported files, (3) wiring an async API-Football ingestion client, (4) extending the Hive-partitioned Parquet store from `sport/league/season/matchday`, and (5) adding a CLV recording client against The Odds API v4 with APScheduler-driven timing.

The existing Football_analysis codebase is well-structured and production-ready for porting: all 6 Supabase models use `BaseModel` + `to_supabase_dict()`, repositories use `@dataclass(client: Client)`, and the Parquet store already implements Hive partitioning via `pyarrow_options`. The new platform adds a `sport` dimension to every table and partition, replaces the hardcoded `Market` enum with YAML-driven runtime config (CORE-05), and wraps all async I/O calls in tenacity retry decorators.

The critical technical risks are: (a) the APScheduler 3.x vs 4.x distinction — Context7 docs show 4.x API (`AsyncScheduler.add_schedule`) but CLAUDE.md locks to 3.x (`AsyncIOScheduler.add_job`); (b) the `write_parquet(pyarrow_options={"partition_cols": ...})` string column issue in Polars — the existing Football_analysis workaround (shutil.rmtree + manual partition deletion before write) should be carried forward intact; (c) pytest-asyncio has jumped to 1.3.0 from the CLAUDE.md-documented 0.25.x, with breaking changes (removal of `event_loop` fixture).

**Primary recommendation:** Use `bip` as the package name (`src/bip/`). Port the 14 source files first in a single wave, extend with `sport` field, then build the ABC and new components atop the stable ported base.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Plugin contract (`SportPlugin` ABC) | Application core | — | Interface definition sits in `core/`, sport plugins implement it; no network or storage |
| Fixture ingestion (API-Football) | Application/async client | — | HTTP calls are an infrastructure concern; the football plugin calls the client |
| Feature engineering (Polars) | Football plugin | — | Sport-specific feature logic lives in `sports/football/`; core receives only `FeatureMatrix` |
| Parquet feature cache | Infrastructure/storage | — | `ParquetStore` is sport-agnostic; receives labeled DataFrames from any plugin |
| Supabase persistence | Infrastructure/storage | — | Repositories in `core/storage/` accept any sport-tagged model |
| CLV recording | Application core | Odds API client | CLV calculation and storage is sport-agnostic; only odds fetching is external |
| APScheduler orchestration | Application core | — | Scheduler drives all plugins the same way via the `SportPlugin` interface |
| Market YAML config | Football plugin config | — | Market definitions are sport-specific; core reads them via protocol |
| Structlog configuration | Application core | — | Logging infrastructure shared across all layers |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.12 | Runtime | CLAUDE.md locked; 10-15% faster CPython than 3.11; all ML libraries support it |
| uv | 0.11.6 | Package manager | CLAUDE.md locked; already installed (`uv 0.11.6`) |
| Pydantic | 2.13.3 | Data models + validation | CLAUDE.md locked; all domain models inherit `BaseModel` |
| pydantic-settings | 2.14.0 | Config from env/dotenv | CLAUDE.md locked; `Settings` pattern already established in Football_analysis |
| supabase-py | 2.28.3 | Supabase client | CLAUDE.md locked; already used in Football_analysis |
| httpx | 0.28.1 | Async HTTP client | CLAUDE.md locked; API-Football + Odds API + Anthropic SDK use it |
| tenacity | 9.1.4 | Retry/backoff | CLAUDE.md locked; decorator-based retry for all external API calls |
| APScheduler | 3.11.2 | Job scheduling | CLAUDE.md explicitly locks to 3.x NOT 4.x (4.x is still alpha) |
| Polars | 1.40.1 | DataFrame operations | CLAUDE.md locked; feature engineering + Parquet I/O |
| PyArrow | 24.0.0 | Parquet I/O backend | Required by Polars write_parquet pyarrow_options path |
| structlog | 25.5.0 | Structured JSON logging | CLAUDE.md locked; replaces stdlib logging |
| PyYAML | 6.x | League config loading | Already in Football_analysis pyproject.toml; no alternative needed |

### Supporting (Dev)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.0.3 | Test runner | All tests |
| pytest-asyncio | 1.3.0 | Async test support | httpx client tests, APScheduler tests |
| ruff | 0.15.11 | Linting + formatting | All code quality; replaces flake8 + black + isort |
| mypy | 1.15.x | Type checking | Strict mode; Pydantic v2 plugin |

**Version verification:** All versions above confirmed via `pypi.org/pypi/{package}/json` on 2026-04-22. [VERIFIED: PyPI registry]

**Important version note:** pytest-asyncio has jumped from 0.25.x (documented in CLAUDE.md) to **1.3.0** as the current stable release. The 1.x series has **breaking changes** — `event_loop` fixture removed, `asyncio_mode` must be explicitly configured. See Pitfalls section.

### Installation

```bash
uv init betting-intelligence-platform
uv python pin 3.12
uv add pydantic==2.13.3 pydantic-settings==2.14.0 supabase==2.28.3 \
       httpx==0.28.1 tenacity==9.1.4 "APScheduler>=3.11,<4.0" \
       polars==1.40.1 pyarrow==24.0.0 structlog==25.5.0 pyyaml
uv add --dev pytest pytest-asyncio ruff mypy
```

---

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                     APScheduler AsyncIOScheduler                      │
│   CronTrigger 06:00 UTC      DateTrigger per-fixture                 │
│   (daily orchestrator)        T-2h, T-30min, T+105min                │
└────────────────┬─────────────────────┬────────────────┬──────────────┘
                 │                     │                │
                 v                     v                v
        ┌────────────────┐   ┌──────────────────┐  ┌─────────────────┐
        │ Orchestrator   │   │ Data Pipeline    │  │ CLV Recorder    │
        │ (core/orch.py) │   │ (football plugin)│  │ (core/clv.py)   │
        └───────┬────────┘   └────────┬─────────┘  └────────┬────────┘
                │                     │                      │
                │ registers jobs       │                      │
                v                     v                      v
        ┌────────────────┐   ┌────────────────────┐  ┌──────────────────┐
        │ LeagueRegistry │   │ ApiFootballClient  │  │ OddsApiClient    │
        │ (YAML configs) │   │ (httpx + tenacity) │  │ (httpx+tenacity) │
        └────────────────┘   └────────┬───────────┘  └────────┬─────────┘
                                      │                        │
                                      v                        v
                             ┌─────────────────┐    ┌──────────────────┐
                             │ FeatureEngineer │    │ Pinnacle closing  │
                             │ (Polars DataFrames)  │ odds JSON        │
                             └────────┬────────┘    └────────┬─────────┘
                                      │                      │
                              ┌───────┴───────┐              │
                              │               │              │
                              v               v              v
                     ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
                     │ ParquetStore │  │ Supabase     │  │ Supabase     │
                     │ (Hive cache) │  │ predictions/ │  │ clv_records  │
                     │ sport/league │  │ picks tables │  │ table        │
                     │ /season/day  │  └──────────────┘  └──────────────┘
                     └──────────────┘
```

### Recommended Project Structure

```
src/bip/
├── __init__.py
├── core/
│   ├── __init__.py
│   ├── types.py          # Ported from shared/types.py; Market enum REMOVED (CORE-05)
│   ├── errors.py         # Ported from shared/errors.py
│   ├── logging.py        # Replaced with structlog configuration
│   ├── settings.py       # Ported + extended (api_football_key, odds_api_key, telegram_token)
│   └── storage/
│       ├── __init__.py
│       ├── models.py     # Ported + sport field added to all 6 models
│       ├── repositories.py  # Ported + sport filter in queries where needed
│       ├── supabase_client.py  # Ported unchanged
│       └── parquet_store.py    # Extended: 4-level partition (sport/league/season/matchday)
├── sports/
│   ├── __init__.py       # SportPlugin ABC (D-02a)
│   └── football/
│       ├── __init__.py
│       ├── plugin.py     # FootballPlugin implements SportPlugin
│       ├── client.py     # ApiFootballClient (httpx + tenacity)
│       ├── features.py   # FeatureEngineer (Polars)
│       └── config/
│           ├── __init__.py
│           ├── league_config.py   # Ported from Football_analysis
│           ├── league_registry.py  # Ported from Football_analysis
│           └── leagues/           # 5 YAML files (ported)
│               ├── premier_league.yaml
│               ├── la_liga.yaml
│               ├── bundesliga.yaml
│               ├── serie_a.yaml
│               └── ligue_1.yaml
├── clv/
│   ├── __init__.py
│   ├── client.py         # OddsApiClient (httpx + tenacity)
│   └── recorder.py       # CLV calculation + Supabase insert
└── scheduler/
    ├── __init__.py
    └── orchestrator.py   # AsyncIOScheduler wiring
tests/
├── conftest.py
├── test_plugin_contract.py     # CORE-04 — interface contract tests
├── test_feature_pipeline.py    # DATA-05 — no future data leaks
├── test_parquet_store.py       # Ported + extended for sport dimension
├── test_repositories.py        # Ported with mocked client
├── test_clv_recorder.py        # CLV-01, CLV-02
└── test_scheduler.py           # DATA-04 — DateTrigger/CronTrigger registration
supabase/
└── migrations/
    ├── 20260323000000_initial_schema.sql   # Existing (do not touch)
    └── 20260422000000_add_sport_column.sql  # Migration 002
data/
└── cache/   # Parquet files land here
```

### Pattern 1: SportPlugin ABC

**What:** Abstract Base Class enforcing the plugin contract. All sports implement it; `core/` calls it.
**When to use:** Any new sport integration must subclass `SportPlugin`.

```python
# Source: Pydantic v2 docs — abc.ABC + abstractmethod pattern
# https://github.com/pydantic/pydantic/blob/main/docs/concepts/models.md
import abc
from datetime import datetime
from pydantic import BaseModel


class FixtureData(BaseModel):
    fixture_id: int
    league: str
    sport: str
    home_team: str
    away_team: str
    kickoff_utc: datetime
    # Additional fields at Claude's discretion


class FeatureMatrix(BaseModel):
    fixture_id: int
    sport: str
    league: str
    computed_at: datetime        # CRITICAL: point-in-time correctness (DATA-05)
    features: dict[str, float]  # Feature name -> value


class ProbabilityMap(BaseModel):
    fixture_id: int
    market: str
    probabilities: dict[str, float]  # e.g., {"1": 0.45, "X": 0.28, "2": 0.27}
    model_version: str
    computed_at: datetime


class ClaudeContext(BaseModel):
    fixture_id: int
    sport: str
    summary: str


class SportPlugin(abc.ABC):
    """Plugin interface all sports must implement.
    Defined in sports/__init__.py per D-02a."""

    @abc.abstractmethod
    async def get_fixtures(self, date: datetime) -> list[FixtureData]:
        """Fetch today's fixtures from the sport's data provider."""
        ...

    @abc.abstractmethod
    async def build_features(self, fixture: FixtureData) -> FeatureMatrix:
        """Build a point-in-time safe feature matrix for a fixture."""
        ...

    @abc.abstractmethod
    async def predict(self, features: FeatureMatrix, market: str) -> ProbabilityMap:
        """Run the model and return probability map for the market."""
        ...

    @abc.abstractmethod
    async def build_claude_context(self, fixture: FixtureData) -> ClaudeContext:
        """Build context for Claude AI enrichment (Role B/C)."""
        ...

    @abc.abstractmethod
    def get_available_markets(self) -> list[str]:
        """Return market keys this sport supports."""
        ...
```

### Pattern 2: Async httpx + tenacity for API-Football

**What:** AsyncClient with per-request retry using tenacity's `@retry` decorator.
**When to use:** All external API calls (API-Football, The Odds API).

```python
# Source: tenacity docs [VERIFIED: Context7 /jd/tenacity]
# Source: httpx docs [VERIFIED: Context7 /encode/httpx]
import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)


def is_retryable_http_error(exc: BaseException) -> bool:
    """Retry on 429 (rate limit), 500, 502, 503, 504."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {429, 500, 502, 503, 504}
    return isinstance(exc, (httpx.ConnectError, httpx.TimeoutException))


class ApiFootballClient:
    BASE_URL = "https://v3.football.api-sports.io"

    def __init__(self, api_key: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={"x-apisports-key": api_key},
            timeout=httpx.Timeout(30.0),
        )

    @retry(
        retry=retry_if_exception(is_retryable_http_error),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def get_fixtures(self, league_id: int, date: str) -> dict:
        """GET /fixtures?league={id}&date={YYYY-MM-DD}"""
        response = await self._client.get(
            "/fixtures",
            params={"league": league_id, "date": date},
        )
        response.raise_for_status()
        return response.json()

    async def aclose(self) -> None:
        await self._client.aclose()
```

**API-Football authentication:** `x-apisports-key: {key}` header on every request. [VERIFIED: WebSearch + api-sports.io docs]

### Pattern 3: APScheduler 3.x AsyncIOScheduler

**What:** AsyncIOScheduler (3.x API, NOT 4.x) with DateTrigger for per-fixture jobs and CronTrigger for daily orchestration.
**When to use:** All scheduled pipeline execution.

**CRITICAL:** APScheduler 3.x uses `AsyncIOScheduler` + `add_job()`. APScheduler 4.x uses `AsyncScheduler` + `add_schedule()`. These are completely different APIs. CLAUDE.md locks to 3.x.

```python
# Source: APScheduler 3.x docs [VERIFIED: apscheduler.readthedocs.io/en/3.x]
# Source: Ryan Haas article [CITED: ryanhaas.us/post/asynchronous-scheduling-with-apscheduler/]
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger


class PipelineOrchestrator:
    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler(timezone="UTC")

    def start(self) -> None:
        # Daily fixture-fetch + job registration at 06:00 UTC
        self.scheduler.add_job(
            self._daily_orchestrator,
            trigger=CronTrigger(hour=6, minute=0, timezone="UTC"),
        )
        self.scheduler.start()

    async def _daily_orchestrator(self) -> None:
        """Fetch today's fixtures and register per-fixture jobs."""
        fixtures = await self.plugin.get_fixtures(date=datetime.now(timezone.utc))
        for fixture in fixtures:
            kickoff = fixture.kickoff_utc
            now = datetime.now(timezone.utc)

            # T-2h job (data refresh + prediction)
            t_minus_2h = kickoff - timedelta(hours=2)
            if t_minus_2h > now:
                self.scheduler.add_job(
                    self._run_pipeline,
                    trigger=DateTrigger(run_date=t_minus_2h),
                    args=[fixture, "t_minus_2h"],
                )

            # T-30min job (lineup-adjusted re-prediction)
            t_minus_30m = kickoff - timedelta(minutes=30)
            if t_minus_30m > now:
                self.scheduler.add_job(
                    self._run_pipeline,
                    trigger=DateTrigger(run_date=t_minus_30m),
                    args=[fixture, "t_minus_30m"],
                )

            # CLV snapshot at kickoff + 105 min (D-04a)
            t_plus_105m = kickoff + timedelta(minutes=105)
            if t_plus_105m > now:
                self.scheduler.add_job(
                    self._record_clv,
                    trigger=DateTrigger(run_date=t_plus_105m),
                    args=[fixture],
                )

    def get_registered_jobs(self) -> list:
        """Check existing jobs (for auto-recovery D-03b)."""
        return self.scheduler.get_jobs()

    def shutdown(self) -> None:
        self.scheduler.shutdown(wait=True)
```

### Pattern 4: Hive-Partitioned Parquet (4-Level)

**What:** Extend the existing Football_analysis ParquetStore from 2-level (`league/season`) to 4-level (`sport/league/season/matchday`) partitioning.
**When to use:** All feature cache writes.

**Key finding:** The existing `parquet_store.py` uses `pyarrow_options={"partition_cols": PARTITION_COLS}` with manual `shutil.rmtree` for overwrite semantics. This is the correct approach. The newer `partition_by` native parameter has an active string column bug in Polars 1.x where string values become "..." in directory names. [CITED: github.com/pola-rs/polars/issues/15181]

```python
# Source: Existing Football_analysis parquet_store.py — extended pattern
# Hive layout: data/cache/features/sport=football/league=premier_league/season=2024-2025/matchday=20/
import shutil
from pathlib import Path
import polars as pl


class FeatureParquetStore:
    PARTITION_COLS = ["sport", "league", "season", "matchday"]

    def __init__(self, base_path: Path | str) -> None:
        self.base_path = Path(base_path)

    def write_features(self, df: pl.DataFrame) -> None:
        """Write features with 4-level Hive partitioning."""
        if df.is_empty():
            return
        missing = [c for c in self.PARTITION_COLS if c not in df.columns]
        if missing:
            raise StorageError(f"Missing partition columns: {missing}")

        target_dir = self.base_path / "features"
        # Remove existing partitions that will be overwritten
        partitions = df.select(self.PARTITION_COLS).unique()
        for row in partitions.iter_rows(named=True):
            partition_path = target_dir
            for col in self.PARTITION_COLS:
                partition_path = partition_path / f"{col}={row[col]}"
            if partition_path.exists():
                shutil.rmtree(partition_path)

        target_dir.mkdir(parents=True, exist_ok=True)
        df.write_parquet(
            target_dir,
            use_pyarrow=True,
            pyarrow_options={"partition_cols": self.PARTITION_COLS},
        )

    def read_features(
        self,
        sport: str | None = None,
        league: str | None = None,
        season: str | None = None,
        matchday: int | None = None,
    ) -> pl.DataFrame:
        """Read features with optional partition filters."""
        target_dir = self.base_path / "features"
        if not target_dir.exists() or not list(target_dir.rglob("*.parquet")):
            return pl.DataFrame()

        lf = pl.scan_parquet(target_dir / "**/*.parquet", hive_partitioning=True)
        if sport is not None:
            lf = lf.filter(pl.col("sport") == sport)
        if league is not None:
            lf = lf.filter(pl.col("league") == league)
        if season is not None:
            lf = lf.filter(pl.col("season") == season)
        if matchday is not None:
            lf = lf.filter(pl.col("matchday") == matchday)
        return lf.collect()
```

### Pattern 5: The Odds API v4 CLV Client

**What:** Fetch Pinnacle closing odds post-match for CLV calculation.
**When to use:** CLV snapshot job at kickoff + 105 minutes.

```python
# Source: The Odds API v4 docs [VERIFIED: the-odds-api.com/liveapi/guides/v4/]
# Endpoint: GET /v4/sports/{sport_key}/events/{event_id}/odds
# Bookmakers parameter: &bookmakers=pinnacle
# Odds format: &oddsFormat=decimal

async def fetch_pinnacle_closing_odds(
    sport_key: str,  # e.g., "soccer_epl"
    event_id: str,   # The Odds API event UUID
    market_key: str, # e.g., "h2h" for 1X2
) -> dict | None:
    """Fetch Pinnacle odds for a specific event and market."""
    response = await self._client.get(
        f"/v4/sports/{sport_key}/events/{event_id}/odds",
        params={
            "bookmakers": "pinnacle",
            "markets": market_key,
            "oddsFormat": "decimal",
        },
    )
    response.raise_for_status()
    data = response.json()
    # Response structure:
    # data["bookmakers"][0]["markets"][0]["outcomes"]
    # Each outcome: {"name": "Arsenal", "price": 2.10}
    for bookmaker in data.get("bookmakers", []):
        if bookmaker["key"] == "pinnacle":
            return bookmaker
    return None
```

**The Odds API market key mapping** (1X2 = "h2h", BTTS = "btts", O/U = "totals") [CITED: the-odds-api.com/liveapi/guides/v4/]

**Historical endpoint** (for reconciliation): `GET /v4/historical/sports/{sport}/events/{eventId}/odds?date={ISO8601}` — costs 10 credits per region per market vs 1 credit for current odds. Use sparingly. [VERIFIED: The Odds API docs]

### Pattern 6: Supabase Migration 002

```sql
-- supabase/migrations/20260422000000_add_sport_column.sql
-- Migration 002: Add sport column to all 6 tables
-- Default 'football' makes existing Football_analysis rows valid

ALTER TABLE predictions
    ADD COLUMN IF NOT EXISTS sport VARCHAR(20) NOT NULL DEFAULT 'football';

ALTER TABLE picks
    ADD COLUMN IF NOT EXISTS sport VARCHAR(20) NOT NULL DEFAULT 'football';

ALTER TABLE odds_snapshots
    ADD COLUMN IF NOT EXISTS sport VARCHAR(20) NOT NULL DEFAULT 'football';

ALTER TABLE results
    ADD COLUMN IF NOT EXISTS sport VARCHAR(20) NOT NULL DEFAULT 'football';

ALTER TABLE clv_records
    ADD COLUMN IF NOT EXISTS sport VARCHAR(20) NOT NULL DEFAULT 'football';

ALTER TABLE performance_metrics
    ADD COLUMN IF NOT EXISTS sport VARCHAR(20) NOT NULL DEFAULT 'football';

-- Index for sport-scoped queries
CREATE INDEX IF NOT EXISTS idx_predictions_sport ON predictions (sport);
CREATE INDEX IF NOT EXISTS idx_picks_sport ON picks (sport);
CREATE INDEX IF NOT EXISTS idx_clv_sport ON clv_records (sport);
CREATE INDEX IF NOT EXISTS idx_perf_sport ON performance_metrics (sport);
```

### Pattern 7: structlog Configuration

```python
# Source: structlog docs [VERIFIED: Context7 /hynek/structlog]
import sys
import structlog

def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog for JSON in production, pretty in terminal."""
    shared_processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]
    if sys.stderr.isatty():
        processors = shared_processors + [structlog.dev.ConsoleRenderer()]
    else:
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(__import__("logging"), log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

# Usage anywhere in the package:
logger = structlog.get_logger(__name__)
logger.info("fixture_fetched", fixture_id=12345, league="premier_league", sport="football")
```

### Pattern 8: Market YAML Config (CORE-05)

CORE-05 requires market definitions as runtime YAML — no hardcoded `Market` enum in `core/`. The existing `Market` enum (btts, ah, ou, onextwo, corners) in `shared/types.py` must **NOT** be copied into `core/` — it belongs in `sports/football/config/` as YAML.

```yaml
# sports/football/config/markets/markets.yaml
markets:
  - key: "btts"
    display: "Both Teams to Score"
    edge_threshold: 0.05
    kelly_max: 0.25
    odds_api_key: "btts"
  - key: "ou"
    display: "Over/Under 2.5"
    edge_threshold: 0.05
    kelly_max: 0.25
    odds_api_key: "totals"
  - key: "onextwo"
    display: "1X2 Match Result"
    edge_threshold: 0.08
    kelly_max: 0.25
    odds_api_key: "h2h"
  - key: "ah"
    display: "Asian Handicap"
    edge_threshold: 0.06
    kelly_max: 0.25
    odds_api_key: "alternate_spreads"
  - key: "corners"
    display: "Corners"
    edge_threshold: 0.07
    kelly_max: 0.25
    odds_api_key: null
```

### Pattern 9: Point-in-Time Correctness Test (DATA-05)

**What:** Integration test asserting that every feature in `FeatureMatrix` has a source event with timestamp <= `computed_at`.
**When to use:** CI gate — must pass before any ML training.

```python
# Conceptual test pattern — implementation at Claude's discretion
# Source: Standard ML feature engineering practice [ASSUMED]
def test_no_future_data_leakage(feature_pipeline, historical_fixtures):
    """Assert all features are computable from data available at prediction time."""
    for fixture in historical_fixtures:
        prediction_time = fixture.kickoff_utc - timedelta(hours=2)
        features = feature_pipeline.build_features_at_time(
            fixture, available_through=prediction_time
        )
        assert features.computed_at <= prediction_time, (
            f"Feature leakage detected for fixture {fixture.fixture_id}: "
            f"computed_at={features.computed_at} > prediction_time={prediction_time}"
        )
        # Verify no column uses data from after prediction_time
        # (implementation checks data source timestamps in feature engineering code)
```

The key enforcement mechanism: `FeatureMatrix.computed_at` is set to the time the features were computed, not the fixture time. Historical feature rebuilds must pass `available_through` cutoff to filter source data.

### Anti-Patterns to Avoid

- **Using APScheduler 4.x API:** `AsyncScheduler`, `add_schedule()`, `run_until_stopped()` are 4.x-only. 3.x uses `AsyncIOScheduler`, `add_job()`, `start()`. Context7 docs show 4.x by default — verify version pinning.
- **Using `partition_by` native in write_parquet:** Polars 1.x has an active bug where string partition columns produce "..." directory names. Use `pyarrow_options={"partition_cols": [...]}` instead (the existing Football_analysis approach). [CITED: github.com/pola-rs/polars/issues/15181]
- **Hardcoding market enum in core/:** CORE-05 requires runtime YAML config. Do not copy the `Market(str, Enum)` from `shared/types.py` into `core/`.
- **Using `event_loop` fixture in pytest:** Removed in pytest-asyncio 1.0+. Use `asyncio_mode = "auto"` in pyproject.toml and pytest fixtures instead.
- **Using synchronous Supabase client in async context:** The existing `supabase-py` 2.x client is sync-first. Do not call it from within `asyncio.run()` or async test fixtures without wrapping in `asyncio.to_thread()` or using the async client variant.
- **Setting `is_closing=True` prematurely:** Only The Odds API response at the CLV snapshot time qualifies as closing odds. Pre-kickoff odds snapshots must have `is_closing=False`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Retry logic with backoff | Custom while loop + sleep | tenacity `@retry` decorator | Handles jitter, max attempts, exception types, async |
| Hive-partitioned Parquet | Manual directory creation + file writing | Polars `write_parquet(pyarrow_options={"partition_cols": ...})` | Handles schema, naming, nested dirs |
| Structured logging | Custom JSON formatter | structlog | async-native, context vars, TTY detection |
| Settings from env | `os.environ.get()` | pydantic-settings `BaseSettings` | Type coercion, validation, dotenv, nested models |
| HTTP connection pooling | New session per request | `httpx.AsyncClient` (persistent instance) | Connection reuse, timeout config, HTTP/2 |
| Job scheduling | `asyncio.sleep` loops | APScheduler 3.x `AsyncIOScheduler` | Cron expressions, DateTrigger, missed job handling |
| Database upsert conflict handling | Manual SELECT then INSERT | supabase `table.upsert(on_conflict=...)` | Atomic, handles race conditions |

**Key insight:** The sports betting domain has enough inherent complexity (CLV math, point-in-time correctness, rate limit navigation) that every infrastructure concern must use a battle-tested library. Hand-rolled retry logic and scheduler loops are the most common source of silent data quality failures.

---

## Runtime State Inventory

> This section is included because Phase 1 involves a namespace rename (`football_betting` → `bip`) and Supabase schema migration.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Supabase: all 6 tables have existing rows with no `sport` column | ALTER TABLE ADD COLUMN with DEFAULT 'football' — existing rows automatically valid |
| Live service config | Supabase RLS policies on 6 tables — verified they use `FOR ALL USING (true)` | No change needed; policies apply to new column automatically |
| OS-registered state | None — Football_analysis has no systemd, cron, or Task Scheduler entries | None |
| Secrets/env vars | `.env` in Football_analysis has `SUPABASE_URL`, `SUPABASE_KEY` — new platform adds `API_FOOTBALL_KEY`, `ODDS_API_KEY`, `TELEGRAM_BOT_TOKEN` | Create new `.env` for bip; do not copy Football_analysis `.env` (different project root) |
| Build artifacts | Football_analysis has `uv.lock` and hatchling build; new platform gets fresh `pyproject.toml` | `uv init` creates fresh lockfile; no artifact migration needed |

**Note on Football_analysis retirement:** Football_analysis is NOT deleted during Phase 1. It runs in parallel until the new platform is validated green on the same Supabase instance. The `sport='football'` default on the migration ensures both systems can coexist.

---

## Common Pitfalls

### Pitfall 1: APScheduler 3.x vs 4.x API Confusion
**What goes wrong:** Code written against Context7/online examples silently uses the 4.x API (`AsyncScheduler`, `add_schedule`), which doesn't import correctly from `apscheduler.schedulers.asyncio` (3.x module).
**Why it happens:** Context7 APScheduler docs default to showing the 4.x API. Version 3.11.2 and 4.x are pinned to different PyPI entries. `pip install APScheduler` with no version pin gets 3.11.2 currently, but the online docs often show 4.x.
**How to avoid:** Pin `"APScheduler>=3.11,<4.0"` in `pyproject.toml`. Import from `apscheduler.schedulers.asyncio.AsyncIOScheduler` (not `apscheduler.AsyncScheduler`).
**Warning signs:** `ImportError: cannot import name 'AsyncScheduler' from 'apscheduler'` — you're running 3.x but wrote 4.x imports.

### Pitfall 2: pytest-asyncio event_loop Fixture Removed
**What goes wrong:** Tests that define or depend on `@pytest.fixture def event_loop()` fail with `fixture 'event_loop' is not available` or deprecation errors.
**Why it happens:** pytest-asyncio 1.0+ removed the `event_loop` fixture entirely. The CLAUDE.md documents `pytest-asyncio==0.25.x` but the current PyPI release is `1.3.0`.
**How to avoid:** Use `asyncio_mode = "auto"` in `pyproject.toml`. Do not define `event_loop` fixture. Each test gets its own event loop automatically.
**Configuration:**
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

### Pitfall 3: Polars write_parquet String Partition Bug
**What goes wrong:** Writing features with string partition columns (sport, league) produces directory names like `sport=[? "foot"?]` instead of `sport=football`.
**Why it happens:** Polars native `partition_by` parameter maps `pl.Utf8` to Arrow `large_string`, which serializes as "..." in path names.
**How to avoid:** Use `pyarrow_options={"partition_cols": PARTITION_COLS}` (not `partition_by=`) — same as the existing Football_analysis code. Always call `shutil.rmtree` on existing partition dirs before writing to prevent duplicates.
**Warning signs:** Directory names with special characters or triple dots after `write_parquet`.

### Pitfall 4: CLV Data Freshness — Pinnacle Closing Line Timing
**What goes wrong:** CLV is measured against odds captured 1-5 minutes after kickoff (website scraping delay in The Odds API) rather than true closing line.
**Why it happens:** The Odds API scrapes Pinnacle's website — not a direct API feed. Delay is 1-5 minutes per CLAUDE.md.
**How to avoid:** Use kickoff + 105 minutes for the snapshot (D-04a), not kickoff. At +105 minutes the match is over (90 + extra time + buffer) and Pinnacle's closing line is definitively settled. Log `odds_fetched_at` to measure actual delay empirically.
**Warning signs:** `odds_fetched_at` timestamps clustering before match finish time.

### Pitfall 5: Supabase Sync Client in Async Context
**What goes wrong:** Calling `supabase.table(...).insert(...).execute()` from inside an `async def` function blocks the event loop, causing scheduler jobs to stall.
**Why it happens:** `supabase-py` 2.x's primary client is sync. Calling sync I/O from async code without `asyncio.to_thread()` blocks the event loop.
**How to avoid:** Wrap Supabase calls in `asyncio.to_thread(repo.insert, model)` when called from async functions, or use `supabase.AsyncClient` if the library supports it in v2.28.3.
**Warning signs:** Scheduler jobs that start but take suspiciously long with no network errors.

### Pitfall 6: Market Enum Leaking into core/
**What goes wrong:** CORE-02 fails — `core/` references `Market.btts` or similar sport-specific constants, violating sport-agnosticism.
**Why it happens:** The existing `shared/types.py` has `Market` enum; it's easy to copy it into `core/types.py` by default.
**How to avoid:** `core/types.py` must NOT contain `Market`. Only `PickStatus`, `AggregationPeriod`, `CalibrationMethod`, `League` (if needed), and generic error types belong in `core/`. Market definitions live in `sports/football/config/markets.yaml`.

### Pitfall 7: CORE-05 Market YAML vs Model Enum
**What goes wrong:** `models.py` still has `market: Market` typed to the old enum, which creates a dependency on the football-specific market list.
**Why it happens:** The existing Pydantic models use `market: Market` (not `market: str`).
**How to avoid:** When porting `models.py`, change `market: Market` to `market: str` in all 6 models. The string is validated by The Odds API and league YAML configs at the application layer, not the storage layer.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| APScheduler 0.25.x event_loop fixture | pytest-asyncio 1.x asyncio_mode=auto | May 2025 (1.0 release) | Must update pyproject.toml config; event_loop fixture removed |
| Polars `write_parquet(partition_by=...)` string columns (buggy) | `write_parquet(pyarrow_options={"partition_cols": ...})` | Bug open as of 1.40.1 | Existing Football_analysis code already uses the correct approach |
| `CalibratedClassifierCV(cv="prefit")` | Removed in scikit-learn 1.8 | Dec 2025 | Phase 1 unaffected; ML calibration is Phase 2 |
| stdlib `logging` | `structlog` + JSON + contextvars | 2023+ | New logging.py replaces old get_logger() |
| `Market(str, Enum)` hardcoded | Runtime YAML market config | Phase 1 design | CORE-05 — models change from `market: Market` to `market: str` |

---

## Existing Code Analysis (What We're Porting)

This section documents exactly what was found in Football_analysis so executors don't need to re-read it.

### Files to Copy + Adapt

| Source File | Destination | Changes Required |
|-------------|-------------|------------------|
| `shared/types.py` | `core/types.py` | Remove `Market` enum (CORE-05); keep `PickStatus`, `CalibrationMethod`, `AggregationPeriod`; `League` enum is debatable — keep as helper |
| `shared/errors.py` | `core/errors.py` | Add `ApiError`, `SchedulerError`, `ClvError`; keep `StorageError`, `ConfigurationError`, `DataValidationError` |
| `shared/logging.py` | `core/logging.py` | REPLACE entirely with structlog configuration (Pattern 7 above) |
| `config/settings.py` | `core/settings.py` | Add: `api_football_key: str`, `odds_api_key: str`, `telegram_bot_token: str`, `log_level: str = "INFO"`; keep `supabase_url`, `supabase_key`, `parquet_base_path` |
| `config/league_config.py` | `sports/football/config/league_config.py` | No structural changes; keep as-is |
| `config/league_registry.py` | `sports/football/config/league_registry.py` | Update import path from `football_betting.*` → `bip.*` |
| `config/leagues/*.yaml` (5 files) | `sports/football/config/leagues/` | No changes; copy verbatim |
| `storage/models.py` | `core/storage/models.py` | (1) Add `sport: str = "football"` to all 6 models; (2) Change `market: Market` → `market: str` everywhere; (3) Update imports |
| `storage/repositories.py` | `core/storage/repositories.py` | Update imports; consider adding `sport` filter to `get_by_*` methods |
| `storage/supabase_client.py` | `core/storage/supabase_client.py` | Update import path only |
| `storage/parquet_store.py` | `core/storage/parquet_store.py` | Extend: add `sport` and `matchday` to `PARTITION_COLS`; keep pyarrow_options approach |

### Existing pyproject.toml (Football_analysis)

```toml
# Already in Football_analysis — these versions inform what already works
dependencies = [
    "supabase>=2.28.3",
    "psycopg[binary]>=3.3.3",   # psycopg — needed for Supabase migrations
    "polars>=1.39.3",
    "pyarrow>=23.0.1",          # Note: current is 24.0.0
    "pydantic>=2.12.5",
    "pydantic-settings>=2.13.1",
    "pyyaml>=6.0.3",
]
```

New platform adds: `httpx`, `tenacity`, `APScheduler<4.0`, `structlog`, `python-telegram-bot` (Phase 3).

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | API-Football v3 Pro plan returns `fixture.fixture.id` as the numeric fixture ID | Architecture Patterns (Pattern 2) | Client code would use wrong field to extract ID; easily caught in first live test |
| A2 | The Odds API event ID can be correlated to API-Football fixture ID via kickoff time + team names | CLV client pattern | CLV recording fails silently; need to store both IDs at pick time |
| A3 | `supabase-py` 2.28.3 sync client can safely be wrapped with `asyncio.to_thread()` without connection pool exhaustion | Pitfall 5 | Event loop stalls or connection leaks; may need `AsyncClient` variant |
| A4 | `matchday` partition in Parquet is integer (1-38 for PL); stored as string in partition path | ParquetStore extension | Partition filter type mismatch; must cast consistently |
| A5 | pytest-asyncio 1.3.0 `asyncio_mode = "auto"` works with APScheduler 3.x test patterns | Validation Architecture | Test setup requires more boilerplate; investigate before writing tests |

---

## Open Questions

1. **The Odds API event ID mapping to API-Football fixture ID**
   - What we know: Both APIs have their own event IDs; they don't share a common ID.
   - What's unclear: What is the most reliable join key? (kickoff time + team names, or a pre-fetch mapping step?)
   - Recommendation: During the CLV client build, implement a fixture-to-event mapping store. At pick creation time, fetch the Odds API event ID and store it in `picks` table alongside `fixture_id`. This avoids the mapping problem at CLV snapshot time.

2. **supabase-py 2.28.3 async client availability**
   - What we know: supabase-py has both sync and async client interfaces in recent versions.
   - What's unclear: Whether `create_async_client()` in 2.28.3 is stable enough for production.
   - Recommendation: Check `supabase.acreate_client` existence at Wave 0. Use `asyncio.to_thread()` as the safe fallback.

3. **Pinnacle closing line coverage for all 5 leagues**
   - What we know: The Odds API scrapes Pinnacle; CLAUDE.md notes coverage may degrade.
   - What's unclear: Does Pinnacle have closing odds for Ligue 1 and Serie A consistently?
   - Recommendation: Test API coverage for all 5 leagues before Phase 2 begins. Document gaps in `data/clv-coverage-test.md`.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | Runtime | Needs install via uv | 3.6.15 (system pyenv) | `uv python install 3.12` |
| uv | Package manager | Available | 0.11.6 | — |
| git | VCS | Available | 2.53.0 | — |
| Node.js | ctx7 CLI research tool | Available | 22.22.0 | — |
| PostgreSQL client | Supabase migrations | Not checked | — | Use Supabase dashboard SQL editor |
| API-Football API key | DATA-01 | Not verified | — | Requires Pro plan setup before implementation |
| The Odds API key | CLV-01 | Not verified | — | Requires Rookie plan signup ($20/mo) |

**Missing dependencies with no fallback:**
- Python 3.12 (system has 3.6.15 only) — must install via `uv python install 3.12` before any implementation

**Missing dependencies with fallback:**
- API-Football key — development can use mock responses; live testing requires the key
- The Odds API key — CLV client can be built and tested with fixture data before live key

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` — `[tool.pytest.ini_options]` section |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -v` |

**pyproject.toml test config (required):**
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CORE-01 | `SportPlugin` ABC has all required abstract methods | unit | `pytest tests/test_plugin_contract.py -x` | Wave 0 |
| CORE-02 | `core/` imports have zero sport-specific references | static/lint | `ruff check src/bip/core/` | Wave 0 |
| CORE-03 | Migration 002 SQL applies without error | manual (Supabase) | Manual — apply via Supabase dashboard | N/A |
| CORE-04 | `FootballPlugin` implements all `SportPlugin` methods | unit | `pytest tests/test_plugin_contract.py -x` | Wave 0 |
| CORE-05 | Markets loaded from YAML, not imported from enum | unit | `pytest tests/test_market_config.py -x` | Wave 0 |
| DATA-01 | `ApiFootballClient.get_fixtures()` retries on 429 | unit (mocked) | `pytest tests/test_api_football_client.py -x` | Wave 0 |
| DATA-02 | `FeatureParquetStore.write_features()` creates correct 4-level Hive dirs | unit | `pytest tests/test_parquet_store.py -x` | Wave 0 |
| DATA-03 | `LeagueRegistry` loads all 5 leagues from YAML | unit | `pytest tests/test_league_registry.py -x` | Wave 0 (ported) |
| DATA-04 | `AsyncIOScheduler` registers DateTrigger jobs for T-2h and T-30min | unit | `pytest tests/test_scheduler.py -x` | Wave 0 |
| DATA-05 | Feature matrix `computed_at` <= prediction time for all features | integration | `pytest tests/test_feature_pipeline.py::test_no_future_data_leakage -x` | Wave 0 |
| CLV-01 | `OddsApiClient.fetch_pinnacle_closing_odds()` returns Pinnacle odds | unit (mocked) | `pytest tests/test_clv_client.py -x` | Wave 0 |
| CLV-02 | `clv_percentage = (odds_at_pick / closing_odds - 1) * 100` | unit | `pytest tests/test_clv_recorder.py -x` | Wave 0 |
| CLV-03 | Rolling 50-pick average CLV calculation | unit | `pytest tests/test_clv_recorder.py::test_rolling_average -x` | Wave 0 |
| CLV-04 | `PerformanceMetric.to_supabase_dict()` includes `sport` field | unit | `pytest tests/test_repositories.py -x` | Wave 0 (ported) |

### Wave 0 Gaps (must be created before implementation)

- [ ] `tests/conftest.py` — shared fixtures (ported + extended from Football_analysis)
- [ ] `tests/test_plugin_contract.py` — CORE-01, CORE-04 contract tests
- [ ] `tests/test_parquet_store.py` — DATA-02, 4-level partition tests (ported + extended)
- [ ] `tests/test_repositories.py` — CLV-04, sport field tests (ported + extended)
- [ ] `tests/test_scheduler.py` — DATA-04 APScheduler tests
- [ ] `tests/test_api_football_client.py` — DATA-01 retry tests with httpx mock
- [ ] `tests/test_clv_client.py` — CLV-01 Odds API tests
- [ ] `tests/test_clv_recorder.py` — CLV-02, CLV-03 calculation tests
- [ ] `tests/test_feature_pipeline.py` — DATA-05 point-in-time test
- [ ] `tests/test_market_config.py` — CORE-05 YAML market config tests
- [ ] `pyproject.toml` — with `asyncio_mode = "auto"` and `testpaths = ["tests"]`

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | N/A — no user authentication in Phase 1 |
| V3 Session Management | No | N/A — no user sessions |
| V4 Access Control | Partial | Supabase RLS policies (already `allow_all` — acceptable for single-tenant) |
| V5 Input Validation | Yes | Pydantic v2 validates all API responses before use |
| V6 Cryptography | No | API keys in `.env` — not encrypting at rest in Phase 1 |
| V7 Error Handling | Yes | Custom error hierarchy (`StorageError`, `ApiError`) prevents stack trace leakage in logs |
| V9 Communications | Yes | httpx enforces HTTPS for all external API calls |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| API key in source code | Information Disclosure | `pydantic-settings` loads from `.env`; `.env` in `.gitignore` |
| Supabase key exposed in logs | Information Disclosure | structlog context — never log `Settings` object directly |
| Malformed API response crashes pipeline | Denial of Service | Pydantic validation + tenacity retry — invalid responses raise typed exceptions |
| Future data leakage in features | Tampering (model integrity) | `computed_at` enforcement + DATA-05 integration test |
| CLV calculation on stale odds | Tampering (CLV integrity) | `odds_fetched_at` timestamp + nightly reconciliation (D-04b) |

---

## Sources

### Primary (HIGH confidence)

- [Context7 /encode/httpx] — async client patterns, transport configuration
- [Context7 /jd/tenacity] — async retry, wait_exponential, stop_after_attempt
- [Context7 /pola-rs/polars] — hive partitioning, scan_parquet, write_parquet
- [Context7 /hynek/structlog] — JSON configuration, async ainfo, ProcessorFormatter
- [Context7 /supabase/supabase-py] — upsert, table operations, client creation
- [Context7 /pydantic/pydantic] — ABC + abstractmethod with BaseModel
- [Context7 /agronholm/apscheduler] — scheduler API (NOTE: Context7 shows 4.x API; 3.x API verified separately)
- [PyPI registry] — version verification for all 12 packages (confirmed 2026-04-22)
- Football_analysis source files — read directly; all patterns verified in production code

### Secondary (MEDIUM confidence)

- [apscheduler.readthedocs.io/en/3.x] — APScheduler 3.x AsyncIOScheduler API (403 on direct fetch; confirmed via WebSearch patterns)
- [ryanhaas.us/post/asynchronous-scheduling-with-apscheduler/] — AsyncIOScheduler + DateTrigger + CronTrigger code examples
- [the-odds-api.com/liveapi/guides/v4/] — Odds API v4 endpoint structure, bookmaker parameter, historical endpoint
- [docs.pola.rs/user-guide/io/hive/] — partition_by API, scan_parquet hive_partitioning

### Tertiary (LOW confidence / flagged)

- [github.com/pola-rs/polars/issues/15181] — String partition bug; solution referenced but comments not fully scraped
- [pytest-asyncio 1.3 migration] — event_loop removal confirmed via WebSearch; full migration guide not fetched

---

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — all versions verified via PyPI registry on 2026-04-22
- Architecture: HIGH — based on verified existing Football_analysis code + locked decisions from CONTEXT.md
- APScheduler 3.x patterns: MEDIUM — API confirmed via multiple web sources but official docs returned 403
- Parquet pitfalls: MEDIUM — bug documented in GitHub issues; workaround is existing production code
- CLV client: MEDIUM — Odds API response format verified from official docs; event ID mapping is ASSUMED
- Pitfalls: HIGH — directly derived from verified library behaviors and existing code analysis

**Research date:** 2026-04-22
**Valid until:** 2026-05-22 (stable stack; APScheduler 4.x promotion to stable is the only watch item)
