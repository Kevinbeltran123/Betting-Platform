---
phase: "01-foundation-data-pipeline-clv"
plan: 1
subsystem: "project-scaffold"
tags: [scaffold, pyproject, uv, python312, supabase, migration]
dependency_graph:
  requires: []
  provides:
    - pyproject.toml with pinned production and dev dependencies
    - uv.lock with resolved environment
    - src/bip/ package skeleton (8 __init__.py stubs)
    - supabase/migrations/20260422000000_add_sport_column.sql
    - .env.example with 5 required env vars documented
    - .gitignore excluding .env and cache
  affects: []
tech_stack:
  added:
    - Python 3.12.9 (via uv, from miniconda)
    - pydantic==2.13.3
    - pydantic-settings==2.14.0
    - supabase==2.28.3
    - httpx==0.28.1
    - tenacity==9.1.4
    - APScheduler==3.11.2 (pinned <4.0)
    - polars==1.40.1
    - pyarrow==24.0.0
    - structlog==25.5.0
    - pyyaml==6.0.3
    - pytest + pytest-asyncio + ruff + mypy (dev)
  patterns:
    - hatchling build backend with src layout
    - asyncio_mode=auto for pytest-asyncio 1.x
    - .env.example + .gitignore for secret hygiene
key_files:
  created:
    - pyproject.toml
    - .python-version
    - .env.example
    - .gitignore
    - uv.lock
    - src/bip/__init__.py
    - src/bip/core/__init__.py
    - src/bip/core/storage/__init__.py
    - src/bip/sports/__init__.py
    - src/bip/sports/football/__init__.py
    - src/bip/sports/football/config/__init__.py
    - src/bip/sports/football/config/leagues/.gitkeep
    - src/bip/clv/__init__.py
    - src/bip/scheduler/__init__.py
    - tests/__init__.py
    - data/cache/.gitkeep
    - supabase/migrations/20260422000000_add_sport_column.sql
  modified: []
decisions:
  - "Used hatchling build backend with packages=['src/bip'] for src-layout package discovery"
  - "Pinned APScheduler>=3.11,<4.0 to prevent alpha 4.x from resolving"
  - "asyncio_mode=auto set per pytest-asyncio 1.x requirement (event_loop fixture removed in 1.0+)"
  - "data/cache/.gitkeep force-added despite .gitignore exclusion to preserve directory in git"
metrics:
  duration: "2 minutes"
  completed: "2026-04-22T21:37:01Z"
  tasks_completed: 2
  tasks_total: 2
  files_created: 17
  files_modified: 0
---

# Phase 1 Plan 1: Project Scaffold Summary

**One-liner:** uv/Python 3.12 project scaffold with hatchling src-layout, 11 pinned production deps, APScheduler 3.x locked, asyncio_mode=auto, and migration 002 SQL adding sport column + odds_fetched_at to all 6 Supabase tables.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Initialize pyproject.toml with pinned deps and Python 3.12 | bd10062 | pyproject.toml, .python-version, .env.example, .gitignore, uv.lock |
| 2 | Create full src/bip/ directory skeleton and migration 002 SQL | 25eef19 | 12 files (8 __init__.py, 2 .gitkeep, tests/__init__.py, migration SQL) |

## Verification Results

All plan success criteria met:

- `uv run python --version` returns `Python 3.12.9`
- `uv sync --dev` exited 0; uv.lock generated with 62 packages installed
- `uv run python -c "import bip"` exits 0
- 8 `__init__.py` stubs exist across `src/bip/`
- `supabase/migrations/20260422000000_add_sport_column.sql` contains 6 `ADD COLUMN IF NOT EXISTS sport` statements + `odds_fetched_at TIMESTAMPTZ` + 4 sport-scoped indexes
- `.env.example` documents all 5 env vars: SUPABASE_URL, SUPABASE_KEY, API_FOOTBALL_KEY, ODDS_API_KEY, TELEGRAM_BOT_TOKEN
- `.gitignore` contains `.env` as standalone line
- `pyproject.toml` contains `asyncio_mode = "auto"`, `APScheduler>=3.11,<4.0`, `requires-python = ">=3.12"`

## Deviations from Plan

### Minor Deviations (auto-resolved)

**1. [Rule 3 - Blocking] data/cache/.gitkeep force-added past .gitignore**
- **Found during:** Task 2
- **Issue:** `.gitignore` correctly excludes `data/cache/` (runtime Parquet cache should not be committed). However, the plan requires `data/cache/.gitkeep` to be committed to preserve the empty directory structure in git.
- **Fix:** Used `git add -f data/cache/.gitkeep` to force-add only the sentinel file. Runtime Parquet files written to `data/cache/` will still be ignored.
- **Files modified:** data/cache/.gitkeep
- **Commit:** 25eef19

**2. Python 3.12.13 vs 3.12.9**
- **Found during:** Task 1 (uv sync)
- **Issue:** `uv python install 3.12` installed 3.12.13, but `uv sync` selected the already-available 3.12.9 from miniconda/Anaconda (higher precedence in PATH resolution). Both are Python 3.12.x and satisfy `requires-python = ">=3.12"`.
- **Impact:** None. The plan requirement is "Python 3.12.x" -- any 3.12 patch version is acceptable.
- **No action taken:** Working as expected.

## Known Stubs

All `__init__.py` files are intentional docstring-only stubs. Per plan design, imports are added in Plans 02-04 when actual modules exist. These are not stubs blocking this plan's goal -- the scaffold's purpose is satisfied.

## Threat Flags

No new threat surface beyond the plan's threat model. Verified:
- `.env` correctly excluded by `.gitignore` (T-01-01 mitigated)
- `.env.example` contains only placeholder values (no real keys)
- Migration SQL uses `ADD COLUMN IF NOT EXISTS` (idempotent, T-01-03 accepted)

## Self-Check: PASSED

Files verified:
- pyproject.toml: FOUND
- .python-version: FOUND
- .env.example: FOUND
- .gitignore: FOUND
- uv.lock: FOUND
- src/bip/__init__.py: FOUND
- src/bip/core/__init__.py: FOUND
- src/bip/core/storage/__init__.py: FOUND
- src/bip/sports/__init__.py: FOUND
- src/bip/sports/football/__init__.py: FOUND
- src/bip/sports/football/config/__init__.py: FOUND
- src/bip/clv/__init__.py: FOUND
- src/bip/scheduler/__init__.py: FOUND
- supabase/migrations/20260422000000_add_sport_column.sql: FOUND
- data/cache/.gitkeep: FOUND
- tests/__init__.py: FOUND

Commits verified:
- bd10062: FOUND (chore(01-01): initialize pyproject.toml...)
- 25eef19: FOUND (feat(01-01): create src/bip/ skeleton...)
