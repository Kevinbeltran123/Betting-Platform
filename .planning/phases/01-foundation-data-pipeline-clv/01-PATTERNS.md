# Phase 1: Foundation + Data Pipeline + CLV - Pattern Map

**Mapped:** 2026-04-22
**Files analyzed:** 15 new/modified files
**Analogs found:** 13 / 15

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/bip/core/types.py` | utility | transform | `Football_analysis/src/football_betting/shared/types.py` | exact |
| `src/bip/core/errors.py` | utility | transform | `Football_analysis/src/football_betting/shared/errors.py` | exact |
| `src/bip/core/logging.py` | utility | transform | `Football_analysis/src/football_betting/shared/logging.py` | role-match (replace body) |
| `src/bip/core/settings.py` | config | request-response | `Football_analysis/src/football_betting/config/settings.py` | exact |
| `src/bip/core/storage/models.py` | model | CRUD | `Football_analysis/src/football_betting/storage/models.py` | exact |
| `src/bip/core/storage/repositories.py` | service | CRUD | `Football_analysis/src/football_betting/storage/repositories.py` | exact |
| `src/bip/core/storage/supabase_client.py` | utility | request-response | `Football_analysis/src/football_betting/storage/supabase_client.py` | exact |
| `src/bip/core/storage/parquet_store.py` | service | file-I/O | `Football_analysis/src/football_betting/storage/parquet_store.py` | exact (extend) |
| `src/bip/sports/__init__.py` (`SportPlugin` ABC) | provider | event-driven | *(no direct analog — new pattern)* | none |
| `src/bip/sports/football/config/league_config.py` | config | transform | `Football_analysis/src/football_betting/config/league_config.py` | exact |
| `src/bip/sports/football/config/league_registry.py` | config | transform | `Football_analysis/src/football_betting/config/league_registry.py` | exact |
| `src/bip/sports/football/config/leagues/*.yaml` (5 files) | config | transform | `Football_analysis/.../config/leagues/premier_league.yaml` | exact |
| `src/bip/sports/football/client.py` (`ApiFootballClient`) | service | request-response | *(no direct analog — new)* | none |
| `src/bip/clv/client.py` (`OddsApiClient`) | service | request-response | *(no direct analog — new)* | none |
| `src/bip/scheduler/orchestrator.py` | service | event-driven | *(no direct analog — new)* | none |
| `supabase/migrations/20260422000000_add_sport_column.sql` | migration | CRUD | `Football_analysis/supabase/migrations/20260323000000_initial_schema.sql` | role-match |
| `tests/conftest.py` | test | transform | `Football_analysis/tests/conftest.py` | exact |
| `tests/test_storage/test_parquet_store.py` | test | file-I/O | `Football_analysis/tests/test_storage/test_parquet_store.py` | exact (extend) |
| `tests/test_storage/test_repositories.py` | test | CRUD | `Football_analysis/tests/test_storage/test_repositories.py` | exact (extend) |

---

## Pattern Assignments

### `src/bip/core/types.py` (utility, transform)

**Analog:** `Football_analysis/src/football_betting/shared/types.py`
**Action:** Port verbatim. Remove `Market` enum entirely (CORE-05 — markets move to YAML). Keep `League`, `PickStatus`, `CalibrationMethod`, `AggregationPeriod`.

**Full source to copy** (lines 1-50), with one deletion:
```python
"""Shared enums and type aliases used across the system."""

from enum import Enum


# DO NOT PORT: Market enum — replaced by YAML config (CORE-05)
# class Market(str, Enum): ...   <-- DELETE THIS


class League(str, Enum):
    """Target leagues for prediction."""

    premier_league = "premier_league"
    la_liga = "la_liga"
    bundesliga = "bundesliga"
    serie_a = "serie_a"
    ligue_1 = "ligue_1"


class PickStatus(str, Enum):
    """Status of a betting pick."""

    pending = "pending"
    won = "won"
    lost = "lost"
    void = "void"
    push = "push"


class CalibrationMethod(str, Enum):
    """Probability calibration methods."""

    isotonic = "isotonic"
    platt = "platt"


class AggregationPeriod(str, Enum):
    """Time periods for performance aggregation."""

    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    season = "season"
    all_time = "all_time"
```

**Import change:** `from football_betting.shared.types import ...` → `from bip.core.types import ...`

---

### `src/bip/core/errors.py` (utility, transform)

**Analog:** `Football_analysis/src/football_betting/shared/errors.py`
**Action:** Port verbatim. Add three new exception classes for new capabilities.

**Full source** (lines 1-12), extended:
```python
"""Custom exceptions for the betting intelligence platform."""


class ConfigurationError(Exception):
    """Raised when configuration loading or validation fails."""


class StorageError(Exception):
    """Raised when storage layer operations fail."""


class DataValidationError(Exception):
    """Raised when data validation fails."""


# New in bip (no analog in Football_analysis):
class ApiError(Exception):
    """Raised when an external API call fails after retries."""


class SchedulerError(Exception):
    """Raised when APScheduler job registration or execution fails."""


class ClvError(Exception):
    """Raised when CLV calculation or recording fails."""
```

---

### `src/bip/core/logging.py` (utility, transform)

**Analog:** `Football_analysis/src/football_betting/shared/logging.py` (lines 1-26)
**Action:** Copy the file location and module role; REPLACE the body entirely with structlog configuration. The analog uses stdlib `logging` — this is one of the deliberate REPLACE patterns from RESEARCH.md.

**Analog body (lines 1-26) — DO NOT copy this body, only the module role:**
```python
# Football_analysis uses stdlib logging.StreamHandler + Formatter
# bip replaces this with structlog JSON configuration
def get_logger(name: str) -> logging.Logger: ...
```

**Target pattern (structlog — from RESEARCH.md Pattern 7):**
```python
"""Structured logging setup using structlog."""

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


# Usage anywhere in the package — replaces get_logger():
# logger = structlog.get_logger(__name__)
```

---

### `src/bip/core/settings.py` (config, request-response)

**Analog:** `Football_analysis/src/football_betting/config/settings.py`
**Action:** Copy verbatim. Add four new fields: `api_football_key`, `odds_api_key`, `telegram_bot_token` (Phase 3 placeholder), `log_level`.

**Full analog source** (lines 1-18):
```python
"""Global application settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with env var loading via pydantic-settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    supabase_url: str
    supabase_key: str
    parquet_base_path: str = "data/parquet"
    log_level: str = "INFO"
```

**Extended target (`src/bip/core/settings.py`):**
```python
"""Global application settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with env var loading via pydantic-settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Ported from Football_analysis (unchanged)
    supabase_url: str
    supabase_key: str
    parquet_base_path: str = "data/cache"   # note: changed default to data/cache

    # New in bip
    api_football_key: str
    odds_api_key: str
    telegram_bot_token: str = ""            # Phase 3 — empty is valid in Phase 1
    log_level: str = "INFO"
```

---

### `src/bip/core/storage/models.py` (model, CRUD)

**Analog:** `Football_analysis/src/football_betting/storage/models.py`
**Action:** Port all 6 models. Apply two mandatory changes to every model: (1) add `sport: str = "football"` field; (2) change `market: Market` → `market: str` (CORE-05, RESEARCH.md Pitfall 7).

**Import pattern** (analog lines 1-12 — modified):
```python
"""Pydantic data models for Supabase entities.

These are the Python-side representations of the 6 Supabase tables.
Each model provides validation and a to_supabase_dict() method for inserts.
"""

from datetime import date, datetime

from pydantic import BaseModel, Field

# CHANGED: removed Market import (CORE-05); kept PickStatus, AggregationPeriod
from bip.core.types import AggregationPeriod, PickStatus
```

**Core model pattern** (analog lines 14-33 — `Prediction`, showing both changes):
```python
class Prediction(BaseModel):
    """Model output for a match/market combination."""

    fixture_id: int
    league: str
    sport: str = "football"          # ADD THIS to all 6 models
    market: str                      # CHANGED from Market enum to str
    home_team: str
    away_team: str
    kickoff_utc: datetime
    probabilities: dict
    model_version: str
    is_lineup_adjusted: bool = False

    def to_supabase_dict(self) -> dict:
        """Convert to dict for Supabase insert."""
        data = self.model_dump()
        # REMOVED: data["market"] = self.market.value  (market is now str)
        data["kickoff_utc"] = self.kickoff_utc.isoformat()
        return data
```

**`to_supabase_dict()` pattern** (analog lines 27-32): The pattern is `self.model_dump()` then override any fields needing serialization. For `market: str`, the enum serialization line (`data["market"] = self.market.value`) is removed. For datetime fields, `.isoformat()` conversion is kept. For enum fields that remain (`PickStatus`, `AggregationPeriod`), keep `.value` serialization.

**`ClvRecord` model** — add `odds_fetched_at: datetime | None = None` field (required by D-04c):
```python
class ClvRecord(BaseModel):
    """Per-bet CLV (Closing Line Value) calculation."""

    pick_id: int
    fixture_id: int
    sport: str = "football"          # ADD
    market: str                      # CHANGED from Market
    odds_at_pick: float
    pinnacle_closing_odds: float | None = None
    implied_prob_at_pick: float
    implied_prob_closing: float | None = None
    clv_percentage: float | None = None
    odds_fetched_at: datetime | None = None   # NEW (D-04c)

    def to_supabase_dict(self) -> dict:
        data = self.model_dump()
        # market is str, no .value conversion needed
        if self.odds_fetched_at:
            data["odds_fetched_at"] = self.odds_fetched_at.isoformat()
        return data
```

---

### `src/bip/core/storage/repositories.py` (service, CRUD)

**Analog:** `Football_analysis/src/football_betting/storage/repositories.py`
**Action:** Port all 6 repository classes. Update imports. Add `sport` filter parameter to `get_by_*` methods where relevant.

**Import pattern** (analog lines 1-26 — modified):
```python
"""Repository classes for Supabase CRUD operations."""

from __future__ import annotations

from dataclasses import dataclass

from supabase import Client

from bip.core.errors import StorageError           # CHANGED namespace
from bip.core.storage.models import (              # CHANGED namespace
    ClvRecord,
    OddsSnapshot,
    PerformanceMetric,
    Pick,
    Prediction,
    Result,
)
```

**Core repository pattern** (analog lines 28-84 — `PredictionRepository`):
```python
@dataclass
class PredictionRepository:
    """Repository for the predictions table."""

    client: Client

    def insert(self, prediction: Prediction) -> dict:
        """Insert a prediction and return the created record."""
        try:
            response = (
                self.client.table("predictions")
                .insert(prediction.to_supabase_dict())
                .execute()
            )
            return response.data[0]
        except Exception as e:
            raise StorageError(
                f"Failed to insert into predictions: {e}"
            ) from e

    def get_by_fixture(
        self, fixture_id: int, market: str | None = None, sport: str | None = None
    ) -> list[dict]:
        """Get predictions for a fixture, optionally filtered by market and sport."""
        try:
            query = (
                self.client.table("predictions")
                .select("*")
                .eq("fixture_id", fixture_id)
            )
            if market is not None:
                query = query.eq("market", market)
            if sport is not None:
                query = query.eq("sport", sport)      # NEW: sport filter
            return query.execute().data
        except Exception as e:
            raise StorageError(
                f"Failed to select from predictions: {e}"
            ) from e
```

**Error handling pattern** (applies to every repo method, analog lines 36-46):
```python
try:
    response = self.client.table("table_name").operation(...).execute()
    return response.data[0]   # or response.data for list returns
except Exception as e:
    raise StorageError(f"Failed to <operation> <table>: {e}") from e
```

**Upsert pattern** (analog lines 317-332 — `PerformanceMetricRepository`):
```python
def upsert(self, metric: PerformanceMetric) -> dict:
    try:
        response = (
            self.client.table("performance_metrics")
            .upsert(
                metric.to_supabase_dict(),
                on_conflict="league,market,period,period_start",
            )
            .execute()
        )
        return response.data[0]
    except Exception as e:
        raise StorageError(f"Failed to upsert into performance_metrics: {e}") from e
```

---

### `src/bip/core/storage/supabase_client.py` (utility, request-response)

**Analog:** `Football_analysis/src/football_betting/storage/supabase_client.py`
**Action:** Port verbatim. Update import path only.

**Full analog source** (lines 1-14 — modify 2 lines):
```python
"""Supabase client factory.

Creates a Supabase Client from application settings.
The caller is responsible for caching the instance if needed.
"""

from supabase import Client, create_client

from bip.core.settings import Settings        # CHANGED namespace


def get_supabase_client(settings: Settings) -> Client:
    """Create and return a Supabase client from settings."""
    return create_client(settings.supabase_url, settings.supabase_key)
```

---

### `src/bip/core/storage/parquet_store.py` (service, file-I/O)

**Analog:** `Football_analysis/src/football_betting/storage/parquet_store.py`
**Action:** Port verbatim. Extend `PARTITION_COLS` from `["league", "season"]` to `["sport", "league", "season", "matchday"]`. Add `write_features` / `read_features` public methods for the feature cache. Keep all private `_write` / `_read` helpers unchanged.

**Import pattern** (analog lines 1-19 — updated namespace):
```python
"""Hive-partitioned Parquet storage for feature data.

Uses Polars for all Parquet I/O with Hive-style partitioning
(sport=X/league=Y/season=Z/matchday=N/) as specified in DATA-02.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import polars as pl

from bip.core.errors import StorageError       # CHANGED namespace
```

**PARTITION_COLS change** (analog line 39 → extended):
```python
# ANALOG:
PARTITION_COLS = ["league", "season"]

# TARGET (4-level Hive):
PARTITION_COLS = ["sport", "league", "season", "matchday"]
```

**Core `_write` method** (analog lines 96-132 — copy verbatim, this is the critical pattern):
```python
def _write(self, df: pl.DataFrame, subdir: str) -> None:
    """Write a DataFrame as Hive-partitioned Parquet files.

    Before writing, removes existing partition directories that overlap
    with the incoming data to prevent duplicates (overwrite semantics).
    """
    if df.is_empty():
        return

    missing = [c for c in self.PARTITION_COLS if c not in df.columns]
    if missing:
        msg = f"DataFrame missing required partition columns: {missing}"
        raise StorageError(msg)

    target_dir = self.base_path / subdir

    # Remove existing partition dirs that will be overwritten
    partitions = df.select(self.PARTITION_COLS).unique()
    for row in partitions.iter_rows(named=True):
        partition_path = target_dir
        for col in self.PARTITION_COLS:
            partition_path = partition_path / f"{col}={row[col]}"
        if partition_path.exists():
            shutil.rmtree(partition_path)

    # Write with Hive partitioning — use pyarrow_options, NOT partition_by= (bug)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        df.write_parquet(
            target_dir,
            use_pyarrow=True,
            pyarrow_options={"partition_cols": self.PARTITION_COLS},
        )
    except Exception as exc:
        msg = f"Failed to write Parquet to {target_dir}: {exc}"
        raise StorageError(msg) from exc
```

**Core `_read` method** (analog lines 134-167 — copy verbatim, add sport/matchday filters):
```python
def _read(
    self,
    subdir: str,
    *,
    sport: str | None = None,
    league: str | None = None,
    season: str | None = None,
    matchday: int | None = None,
) -> pl.DataFrame:
    target_dir = self.base_path / subdir

    if not target_dir.exists() or not list(target_dir.rglob("*.parquet")):
        return pl.DataFrame()

    try:
        lf = pl.scan_parquet(
            target_dir / "**/*.parquet",
            hive_partitioning=True,
        )
        if sport is not None:
            lf = lf.filter(pl.col("sport") == sport)
        if league is not None:
            lf = lf.filter(pl.col("league") == league)
        if season is not None:
            lf = lf.filter(pl.col("season") == season)
        if matchday is not None:
            lf = lf.filter(pl.col("matchday") == matchday)
        return lf.collect()
    except Exception as exc:
        msg = f"Failed to read Parquet from {target_dir}: {exc}"
        raise StorageError(msg) from exc
```

**Critical anti-pattern reminder:** NEVER use `df.write_parquet(partition_by=self.PARTITION_COLS)` — use `pyarrow_options={"partition_cols": ...}` as shown above. See RESEARCH.md Pitfall 3.

---

### `src/bip/sports/__init__.py` — `SportPlugin` ABC (provider, event-driven)

**Analog:** None — this is a new pattern. Use RESEARCH.md Pattern 1 directly.

**Full pattern from RESEARCH.md (Pattern 1 — authoritative):**
```python
"""SportPlugin ABC — all sports must implement this interface.

Defined here (sports/__init__.py) per D-02a.
core/ calls only this interface — zero sport-specific code in core/.
"""

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


class FeatureMatrix(BaseModel):
    fixture_id: int
    sport: str
    league: str
    computed_at: datetime        # CRITICAL: point-in-time correctness (DATA-05)
    features: dict[str, float]


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
    """Plugin interface all sports must implement."""

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
        """Return market keys this sport supports (loaded from YAML)."""
        ...
```

---

### `src/bip/sports/football/config/league_config.py` (config, transform)

**Analog:** `Football_analysis/src/football_betting/config/league_config.py`
**Action:** Port verbatim. Update namespace in any internal imports.

**Full analog source** (lines 1-76 — copy nearly verbatim):
```python
"""Pydantic models for league configuration."""

from pydantic import BaseModel, field_validator


class ApiMappings(BaseModel):
    """External API identifier mappings for a league."""

    api_football_league_id: int
    odds_api_sport_key: str
    team_name_mappings: dict[str, str] = {}


class SeasonStructure(BaseModel):
    """Season calendar and structure for a league."""

    start_month: int
    end_month: int
    typical_matchdays: int
    winter_break: bool = False

    @field_validator("start_month", "end_month")
    @classmethod
    def validate_month(cls, v: int) -> int:
        if not 1 <= v <= 12:
            raise ValueError(f"Month must be between 1 and 12, got {v}")
        return v


class ModelParams(BaseModel):
    """Model configuration parameters per league."""

    calibration_method: str = "isotonic"
    edge_threshold_btts: float = 0.05
    edge_threshold_ah: float = 0.06
    edge_threshold_ou: float = 0.05
    edge_threshold_1x2: float = 0.08
    edge_threshold_corners: float = 0.07
    min_sample_size: int = 500

    @field_validator("calibration_method")
    @classmethod
    def validate_calibration_method(cls, v: str) -> str:
        allowed = {"isotonic", "platt"}
        if v not in allowed:
            raise ValueError(f"calibration_method must be one of {allowed}, got '{v}'")
        return v

    @field_validator(
        "edge_threshold_btts", "edge_threshold_ah", "edge_threshold_ou",
        "edge_threshold_1x2", "edge_threshold_corners",
    )
    @classmethod
    def validate_edge_threshold(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"Edge threshold must be between 0.0 and 1.0, got {v}")
        return v


class LeagueConfig(BaseModel):
    """Complete configuration for a single league."""

    name: str
    slug: str
    country: str
    api_mappings: ApiMappings
    season_structure: SeasonStructure
    model_params: ModelParams = ModelParams()
```

---

### `src/bip/sports/football/config/league_registry.py` (config, transform)

**Analog:** `Football_analysis/src/football_betting/config/league_registry.py`
**Action:** Port verbatim. Update two import lines.

**Import changes** (analog lines 9-14):
```python
# ANALOG:
from football_betting.config.league_config import LeagueConfig
from football_betting.shared.logging import get_logger

# TARGET:
from bip.sports.football.config.league_config import LeagueConfig
import structlog

logger = structlog.get_logger(__name__)   # replaces get_logger(__name__)
```

**Core registry pattern** (analog lines 18-67 — copy verbatim, structlog call syntax change):
```python
class LeagueRegistry:
    def __init__(self, config_dir: Path) -> None:
        if not config_dir.is_dir():
            raise FileNotFoundError(f"League config directory not found: {config_dir}")

        self._leagues: dict[str, LeagueConfig] = {}

        for yaml_file in sorted(config_dir.glob("*.yaml")):
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
            config = LeagueConfig(**data)
            self._leagues[config.slug] = config
            logger.info("league_loaded", name=config.name, slug=config.slug)
            # NOTE: structlog uses keyword args, not % formatting

    def get(self, slug: str) -> LeagueConfig:
        if slug not in self._leagues:
            available = ", ".join(sorted(self._leagues.keys()))
            raise KeyError(f"League '{slug}' not configured. Available: {available}")
        return self._leagues[slug]

    def all_leagues(self) -> list[LeagueConfig]:
        return list(self._leagues.values())

    def slugs(self) -> list[str]:
        return list(self._leagues.keys())
```

---

### `src/bip/sports/football/config/leagues/*.yaml` (5 config files)

**Analog:** `Football_analysis/src/football_betting/config/leagues/premier_league.yaml`
**Action:** Copy all 5 files verbatim — no changes needed.

**YAML structure pattern** (premier_league.yaml — authoritative format):
```yaml
name: "Premier League"
slug: "premier_league"
country: "England"

api_mappings:
  api_football_league_id: 39
  odds_api_sport_key: "soccer_epl"
  team_name_mappings:
    "Tottenham Hotspur": "Tottenham"
    # ... team name normalization entries

season_structure:
  start_month: 8
  end_month: 5
  typical_matchdays: 38
  winter_break: false

model_params:
  calibration_method: "isotonic"
  edge_threshold_btts: 0.05
  edge_threshold_ah: 0.06
  edge_threshold_ou: 0.05
  edge_threshold_1x2: 0.08
  edge_threshold_corners: 0.07
  min_sample_size: 500
```

---

### `src/bip/sports/football/client.py` — `ApiFootballClient` (service, request-response)

**Analog:** None in Football_analysis — new file. Use RESEARCH.md Pattern 2 directly.

**Full pattern from RESEARCH.md (Pattern 2 — authoritative):**
```python
"""API-Football v3 async client with tenacity retry."""

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

import structlog

logger = structlog.get_logger(__name__)


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

All other `ApiFootballClient` methods (lineups, stats, corners) follow the same `@retry` + `await self._client.get(...)` + `response.raise_for_status()` + `return response.json()` pattern.

---

### `src/bip/clv/client.py` — `OddsApiClient` (service, request-response)

**Analog:** None — new file. Use RESEARCH.md Pattern 5, combined with Pattern 2 retry structure.

**Pattern (combines RESEARCH.md Pattern 2 retry structure + Pattern 5 endpoint):**
```python
"""The Odds API v4 async client for Pinnacle closing odds."""

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

import structlog

logger = structlog.get_logger(__name__)


# Reuse the same retryable predicate as ApiFootballClient
def is_retryable_http_error(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {429, 500, 502, 503, 504}
    return isinstance(exc, (httpx.ConnectError, httpx.TimeoutException))


class OddsApiClient:
    BASE_URL = "https://api.the-odds-api.com"

    def __init__(self, api_key: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=httpx.Timeout(30.0),
        )
        self._api_key = api_key

    @retry(
        retry=retry_if_exception(is_retryable_http_error),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def fetch_pinnacle_closing_odds(
        self,
        sport_key: str,   # e.g., "soccer_epl"
        event_id: str,    # The Odds API event UUID
        market_key: str,  # e.g., "h2h" for 1X2
    ) -> dict | None:
        """Fetch Pinnacle odds for a specific event and market."""
        response = await self._client.get(
            f"/v4/sports/{sport_key}/events/{event_id}/odds",
            params={
                "apiKey": self._api_key,
                "bookmakers": "pinnacle",
                "markets": market_key,
                "oddsFormat": "decimal",
            },
        )
        response.raise_for_status()
        data = response.json()
        for bookmaker in data.get("bookmakers", []):
            if bookmaker["key"] == "pinnacle":
                return bookmaker
        return None

    async def aclose(self) -> None:
        await self._client.aclose()
```

**Market key mapping** (from RESEARCH.md Pattern 5):
- `"onextwo"` → `"h2h"`
- `"btts"` → `"btts"`
- `"ou"` → `"totals"`
- `"ah"` → `"alternate_spreads"`

---

### `src/bip/scheduler/orchestrator.py` (service, event-driven)

**Analog:** None — new file. Use RESEARCH.md Pattern 3 directly.

**Full pattern from RESEARCH.md (Pattern 3 — authoritative):**
```python
"""APScheduler 3.x AsyncIOScheduler pipeline orchestrator.

CRITICAL: Uses APScheduler 3.x API (AsyncIOScheduler + add_job).
Do NOT use 4.x API (AsyncScheduler + add_schedule).
"""

from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

import structlog

logger = structlog.get_logger(__name__)


class PipelineOrchestrator:
    def __init__(self, plugin) -> None:
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self.plugin = plugin

    def start(self) -> None:
        # Daily fixture-fetch + job registration at 06:00 UTC (D-03a)
        self.scheduler.add_job(
            self._daily_orchestrator,
            trigger=CronTrigger(hour=6, minute=0, timezone="UTC"),
        )
        # Nightly CLV reconciliation at 03:00 UTC (D-04b)
        self.scheduler.add_job(
            self._reconcile_clv,
            trigger=CronTrigger(hour=3, minute=0, timezone="UTC"),
        )
        self.scheduler.start()

    async def _daily_orchestrator(self) -> None:
        """Fetch today's fixtures and register per-fixture DateTrigger jobs."""
        fixtures = await self.plugin.get_fixtures(date=datetime.now(timezone.utc))
        for fixture in fixtures:
            kickoff = fixture.kickoff_utc
            now = datetime.now(timezone.utc)

            t_minus_2h = kickoff - timedelta(hours=2)
            if t_minus_2h > now:
                self.scheduler.add_job(
                    self._run_pipeline,
                    trigger=DateTrigger(run_date=t_minus_2h),
                    args=[fixture, "t_minus_2h"],
                )

            t_minus_30m = kickoff - timedelta(minutes=30)
            if t_minus_30m > now:
                self.scheduler.add_job(
                    self._run_pipeline,
                    trigger=DateTrigger(run_date=t_minus_30m),
                    args=[fixture, "t_minus_30m"],
                )

            t_plus_105m = kickoff + timedelta(minutes=105)   # CLV snapshot (D-04a)
            if t_plus_105m > now:
                self.scheduler.add_job(
                    self._record_clv,
                    trigger=DateTrigger(run_date=t_plus_105m),
                    args=[fixture],
                )

    def get_registered_jobs(self) -> list:
        """Check existing jobs — used for auto-recovery (D-03b)."""
        return self.scheduler.get_jobs()

    def shutdown(self) -> None:
        self.scheduler.shutdown(wait=True)
```

---

### `supabase/migrations/20260422000000_add_sport_column.sql` (migration, CRUD)

**Analog:** `Football_analysis/supabase/migrations/20260323000000_initial_schema.sql`
**Action:** Do NOT copy the existing migration. Use it only to confirm table names. Write a new migration that only ADDs columns — never re-creates tables.

**Table names confirmed from analog** (lines 8, 33, 63, 84, 110, 134):
- `predictions`, `picks`, `odds_snapshots`, `results`, `clv_records`, `performance_metrics`

**Pattern from RESEARCH.md Pattern 6 — authoritative:**
```sql
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
    -- Also add odds_fetched_at (D-04c):
ALTER TABLE clv_records
    ADD COLUMN IF NOT EXISTS odds_fetched_at TIMESTAMPTZ;

ALTER TABLE performance_metrics
    ADD COLUMN IF NOT EXISTS sport VARCHAR(20) NOT NULL DEFAULT 'football';

-- Sport-scoped indexes for query performance
CREATE INDEX IF NOT EXISTS idx_predictions_sport ON predictions (sport);
CREATE INDEX IF NOT EXISTS idx_picks_sport ON picks (sport);
CREATE INDEX IF NOT EXISTS idx_clv_sport ON clv_records (sport);
CREATE INDEX IF NOT EXISTS idx_perf_sport ON performance_metrics (sport);
```

---

## Test Pattern Assignments

### `tests/conftest.py`

**Analog:** `Football_analysis/tests/conftest.py`
**Action:** Port and extend.

**Port verbatim** (lines 1-37), with namespace updates:
```python
"""Shared test fixtures."""

import os
import shutil
from pathlib import Path

import pytest


LEAGUES_DIR = (
    Path(__file__).parent.parent
    / "src" / "bip" / "sports" / "football" / "config" / "leagues"
)


@pytest.fixture
def tmp_leagues_dir(tmp_path: Path) -> Path:
    """Create a temp directory with copies of the real league YAML files."""
    leagues_dest = tmp_path / "leagues"
    shutil.copytree(LEAGUES_DIR, leagues_dest)
    return leagues_dest


@pytest.fixture
def league_registry(tmp_leagues_dir: Path):
    """Return a LeagueRegistry loaded from tmp_leagues_dir."""
    from bip.sports.football.config.league_registry import LeagueRegistry
    return LeagueRegistry(tmp_leagues_dir)


@pytest.fixture
def settings(monkeypatch):
    """Return Settings with test env vars set."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key-12345")
    monkeypatch.setenv("API_FOOTBALL_KEY", "test-api-football-key")
    monkeypatch.setenv("ODDS_API_KEY", "test-odds-api-key")

    from bip.core.settings import Settings
    return Settings()
```

**pyproject.toml test config** (required — from RESEARCH.md Pitfall 2):
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

---

### `tests/test_storage/test_parquet_store.py`

**Analog:** `Football_analysis/tests/test_storage/test_parquet_store.py`
**Action:** Port and extend for 4-level partitioning.

**Fixture pattern** (analog lines 17-20 — update store fixture):
```python
@pytest.fixture
def store(tmp_path: Path) -> ParquetStore:
    """ParquetStore backed by a temporary directory."""
    from bip.core.storage.parquet_store import ParquetStore
    return ParquetStore(base_path=tmp_path)
```

**Sample DataFrame must include 4 partition columns** (add `sport`, `matchday`):
```python
@pytest.fixture
def sample_features() -> pl.DataFrame:
    return pl.DataFrame({
        "fixture_id": [1001, 1002, 1003],
        "sport": ["football", "football", "football"],   # NEW
        "league": ["premier_league", "premier_league", "la_liga"],
        "season": ["2024-2025", "2024-2025", "2024-2025"],
        "matchday": [20, 20, 19],                        # NEW
        "home_xg": [1.8, 0.9, 2.1],
        "away_xg": [1.2, 1.5, 0.8],
    })
```

**Test class structure** (from analog lines 86-219 — copy test patterns, adapt column names):
- `TestWriteFeatures` — mirrors `TestWriteMatches`: tests Hive dir creation, round-trip, overwrite semantics
- `TestReadFeatures` — mirrors `TestReadMatches`: tests no-filter, sport filter, league filter, empty store

**Hive directory assertion pattern** (analog lines 92-100):
```python
def test_creates_hive_partitioned_directory(self, store, sample_features):
    store.write_features(sample_features)
    features_dir = store.base_path / "features"
    parquet_files = list(features_dir.rglob("*.parquet"))
    assert len(parquet_files) > 0

    partition_dirs = {p.parent.relative_to(features_dir) for p in parquet_files}
    # Verify 4-level nesting: sport=football/league=X/season=Y/matchday=N/
    assert any("sport=football" in str(d) for d in partition_dirs)
    assert any("league=premier_league" in str(d) for d in partition_dirs)
    assert any("matchday=20" in str(d) for d in partition_dirs)
```

---

### `tests/test_storage/test_repositories.py`

**Analog:** `Football_analysis/tests/test_storage/test_repositories.py`
**Action:** Port verbatim. Update namespace. Remove `Market` enum from sample fixtures (use strings). Add `sport="football"` to sample model instances.

**Mock client pattern** (analog lines 33-73 — copy verbatim):
```python
@pytest.fixture
def mock_client():
    """Create a mock Supabase client with fluent API chain support."""
    client = MagicMock()
    return client


def _setup_chain(client, data=None):
    """Set up the fluent method chain to return specified data."""
    if data is None:
        data = [{"id": 1}]
    response = MagicMock()
    response.data = data
    builder = MagicMock()
    builder.execute.return_value = response
    builder.insert.return_value = builder
    builder.select.return_value = builder
    builder.update.return_value = builder
    builder.upsert.return_value = builder
    builder.eq.return_value = builder
    builder.order.return_value = builder
    builder.limit.return_value = builder
    client.table.return_value = builder
    return builder
```

**Sample fixture update** (analog lines 79-91 — `market: Market.btts` → `market: str`):
```python
@pytest.fixture
def sample_prediction():
    from bip.core.storage.models import Prediction
    return Prediction(
        fixture_id=12345,
        league="premier_league",
        sport="football",              # NEW
        market="btts",                 # CHANGED from Market.btts
        home_team="Arsenal",
        away_team="Chelsea",
        kickoff_utc=datetime(2026, 4, 22, 15, 0, 0),
        probabilities={"yes": 0.65, "no": 0.35},
        model_version="v1.0",
    )
```

---

## Shared Patterns

### Namespace Rename
**Source:** All Football_analysis `src/football_betting/` files
**Apply to:** Every ported file — change all import paths
```python
# BEFORE (Football_analysis):
from football_betting.shared.errors import StorageError
from football_betting.config.settings import Settings
from football_betting.storage.models import Prediction

# AFTER (bip):
from bip.core.errors import StorageError
from bip.core.settings import Settings
from bip.core.storage.models import Prediction
```

### Structured Logging
**Source:** RESEARCH.md Pattern 7 (no analog in Football_analysis)
**Apply to:** All modules that currently call `get_logger(__name__)`

```python
# BEFORE (Football_analysis):
from football_betting.shared.logging import get_logger
logger = get_logger(__name__)
logger.info("Loaded league config: %s (%s)", config.name, config.slug)

# AFTER (bip):
import structlog
logger = structlog.get_logger(__name__)
logger.info("league_loaded", name=config.name, slug=config.slug)
# Note: structlog uses keyword args for structured context
```

### Error Handling
**Source:** `Football_analysis/src/football_betting/storage/repositories.py` (lines 36-46)
**Apply to:** All repository methods, all async client methods
```python
try:
    # ... operation
    return response.data[0]
except Exception as e:
    raise StorageError(f"Failed to <verb> <table_or_resource>: {e}") from e
```

### Retry Decorator
**Source:** RESEARCH.md Pattern 2 (no analog in Football_analysis)
**Apply to:** All `ApiFootballClient` and `OddsApiClient` methods
```python
@retry(
    retry=retry_if_exception(is_retryable_http_error),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    stop=stop_after_attempt(5),
    reraise=True,
)
async def method(self, ...) -> dict:
    ...
```

### Pydantic Model Validation
**Source:** `Football_analysis/src/football_betting/config/league_config.py` (lines 26-65)
**Apply to:** All Pydantic models with constrained fields — use `@field_validator` with `@classmethod`
```python
@field_validator("field_name")
@classmethod
def validate_field_name(cls, v: type) -> type:
    if not condition:
        raise ValueError(f"Message, got {v}")
    return v
```

### `to_supabase_dict()` Serialization
**Source:** `Football_analysis/src/football_betting/storage/models.py` (lines 27-32, 52-57, 70-76)
**Apply to:** All 6 storage models in `bip/core/storage/models.py`
```python
def to_supabase_dict(self) -> dict:
    data = self.model_dump()
    # Convert datetime fields to ISO strings
    data["kickoff_utc"] = self.kickoff_utc.isoformat()
    # For remaining enum fields (PickStatus, AggregationPeriod), use .value
    data["status"] = self.status.value
    # market is now str — NO .value conversion needed
    return data
```

---

## No Analog Found

Files with no close match in the Football_analysis codebase (use RESEARCH.md patterns instead):

| File | Role | Data Flow | Pattern Source |
|------|------|-----------|----------------|
| `src/bip/sports/__init__.py` (`SportPlugin` ABC) | provider | event-driven | RESEARCH.md Pattern 1 |
| `src/bip/sports/football/client.py` (`ApiFootballClient`) | service | request-response | RESEARCH.md Pattern 2 |
| `src/bip/clv/client.py` (`OddsApiClient`) | service | request-response | RESEARCH.md Pattern 5 + Pattern 2 retry |
| `src/bip/scheduler/orchestrator.py` | service | event-driven | RESEARCH.md Pattern 3 |
| `src/bip/core/logging.py` (structlog) | utility | transform | RESEARCH.md Pattern 7 |
| `tests/test_plugin_contract.py` | test | transform | D-02e spec only — no analog |
| `tests/test_scheduler.py` | test | event-driven | D-03 spec only — no analog |
| `tests/test_clv_recorder.py` | test | CRUD | CLV-02 spec only — no analog |
| `tests/test_api_football_client.py` | test | request-response | httpx mock pattern (see below) |

**httpx mock pattern for client tests** (from standard pytest-httpx usage):
```python
# Install: uv add --dev pytest-httpx
import pytest
from pytest_httpx import HTTPXMock

@pytest.mark.asyncio
async def test_get_fixtures_retries_on_429(httpx_mock: HTTPXMock):
    httpx_mock.add_response(status_code=429)   # first call — rate limited
    httpx_mock.add_response(status_code=200, json={"response": []})  # retry succeeds
    client = ApiFootballClient(api_key="test-key")
    result = await client.get_fixtures(league_id=39, date="2026-04-22")
    assert result == {"response": []}
```

---

## Metadata

**Analog search scope:** `Football_analysis/src/football_betting/` (all 14 Python source files read)
**Test files scanned:** `Football_analysis/tests/` (4 test files read)
**Migration files scanned:** `Football_analysis/supabase/migrations/` (1 SQL file read)
**League YAML files scanned:** 5 files (structure confirmed from premier_league.yaml)
**Files with zero analog (pure new code):** 4 (SportPlugin ABC, ApiFootballClient, OddsApiClient, PipelineOrchestrator)
**Pattern extraction date:** 2026-04-22
