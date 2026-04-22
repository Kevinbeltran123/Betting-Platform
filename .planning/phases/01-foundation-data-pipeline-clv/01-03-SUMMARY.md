---
plan: "01-03"
phase: "01-foundation-data-pipeline-clv"
status: complete
completed_at: "2026-04-22"
tasks_completed: 2/2
commits:
  - ef7c08a
  - 0e2d7d4
key-files:
  created:
    - src/bip/core/types.py
    - src/bip/core/errors.py
    - src/bip/core/logging.py
    - src/bip/core/settings.py
    - src/bip/core/storage/models.py
    - src/bip/core/storage/repositories.py
    - src/bip/core/storage/supabase_client.py
    - src/bip/core/storage/parquet_store.py
  modified:
    - tests/test_repositories.py
---

## Plan 01-03: Core Infrastructure — Complete

**Objective:** Port and adapt the core layer from Football_analysis — types, errors, logging, settings, and all of `core/storage/`.

### What Was Built

**Task 1 — Core Foundation (ef7c08a)**
- `types.py`: 4 `StrEnum` classes (`League`, `PickStatus`, `CalibrationMethod`, `AggregationPeriod`). Market enum intentionally absent — markets are YAML config (CORE-05).
- `errors.py`: 6 exception classes including 3 new ones (`ApiError`, `SchedulerError`, `ClvError`).
- `logging.py`: `configure_logging()` using structlog — JSON in production (non-TTY), pretty in dev (TTY).
- `settings.py`: 7-field `Settings` class via pydantic-settings — added `api_football_key`, `odds_api_key`, `telegram_bot_token`, `log_level` to existing `supabase_url`/`supabase_key`. `parquet_base_path` default changed to `"data/cache"`.

**Task 2 — Storage Layer (0e2d7d4)**
- `models.py`: All 6 Pydantic models (`Prediction`, `Pick`, `OddsSnapshot`, `Result`, `ClvRecord`, `PerformanceMetric`) with `sport: str = "football"` field and `market: str` (not enum). `ClvRecord` has `odds_fetched_at: datetime | None` (D-04c).
- `repositories.py`: 6 typed repository dataclasses with `sport: str | None = None` filter parameters on all `get_by_*` methods.
- `supabase_client.py`: Unchanged factory, namespace updated to `bip`.
- `parquet_store.py`: `PARTITION_COLS = ["sport", "league", "season", "matchday"]` (4-level Hive), uses `pyarrow_options={"partition_cols": ...}` not `partition_by=` (Polars 1.x string partition bug workaround per RESEARCH.md).

### Verification

- `ruff check src/bip/core/` — clean
- `pytest tests/test_repositories.py tests/test_parquet_store.py` — **11/11 passed**
- `import bip.core.types as t; hasattr(t, "Market")` → `False`
- All 6 models have `sport: str = "football"` (confirmed via `grep -c`)

### Deviations

- Test stub `test_repositories.py` used wrong field names (`wins`/`losses`/`voids`) and missing `period_end`. Fixed stub to match model (`won`/`lost`/`void`, added `period_end`).
- `(str, Enum)` changed to `StrEnum` to satisfy ruff `UP042` — behaviorally identical, Python 3.11+ idiom.

## Self-Check: PASSED
