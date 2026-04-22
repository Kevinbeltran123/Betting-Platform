---
phase: "01-foundation-data-pipeline-clv"
plan: 5
subsystem: "football-data-pipeline"
tags: [api-client, httpx, tenacity, retry, feature-engineering, polars, parquet, football, data-pipeline]
dependency_graph:
  requires:
    - "01-03 (core/storage/parquet_store.py, core/errors.py, core/settings.py)"
    - "01-04 (SportPlugin ABC, FootballPlugin stub, LeagueRegistry, markets.yaml)"
  provides:
    - "ApiFootballClient: async context manager, 5 endpoint methods, tenacity retry (DATA-01)"
    - "FeatureEngineer: Polars-based feature builder with DATA-05 point-in-time enforcement"
    - "FootballPlugin: wired to real ApiFootballClient, FeatureEngineer, and ParquetStore"
  affects:
    - "Plans 06-07 (CLV client and scheduler call FootballPlugin interface)"
    - "tests/test_api_football_client.py (DATA-01 tests)"
    - "tests/test_feature_pipeline.py (DATA-05 tests)"
tech_stack:
  added:
    - httpx.AsyncClient with persistent connection pool (not recreated per request)
    - tenacity @retry with retry_if_exception predicate covering 429/500/502/503/504
    - Polars DataFrame construction via dict-of-lists pattern (ParquetStore-ready)
  patterns:
    - "ApiFootballClient async context manager (__aenter__/__aexit__/aclose)"
    - "is_retryable_http_error() predicate function for tenacity retry_if_exception"
    - "computed_at captured BEFORE API calls (T-05-03 point-in-time boundary)"
    - "_parse_fixture() try/except (KeyError, ValueError) skip malformed items (T-05-01)"
    - "structlog.info() without API key — key never logged (T-05-04)"
key_files:
  created:
    - src/bip/sports/football/client.py
    - src/bip/sports/football/features.py
  modified:
    - src/bip/sports/football/plugin.py
decisions:
  - "is_retryable_http_error() defined as module-level function (not lambda) for tenacity compatibility"
  - "computed_at captured before async API calls in build_features() — enforces DATA-05 point-in-time boundary"
  - "datetime.fromisoformat() used instead of python-dateutil (Python 3.12 stdlib handles full ISO 8601)"
  - "matchday=1 placeholder in build_features() — Phase 2 will use API fixture data"
  - "season derived from kickoff_utc.year — Phase 2 will use league config"
metrics:
  duration: "12 minutes"
  completed: "2026-04-22T22:28:00Z"
  tasks_completed: 2
  tasks_total: 2
  files_created: 2
  files_modified: 1
---

# Phase 1 Plan 5: API-Football Client and Feature Engineering Summary

**One-liner:** Async ApiFootballClient with 5 endpoint methods and tenacity retry (DATA-01), FeatureEngineer with Polars and DATA-05 point-in-time enforcement, FootballPlugin wired to real client and ParquetStore.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | ApiFootballClient with 5 endpoint methods and retry | UNCOMMITTED (see Deviations) | src/bip/sports/football/client.py |
| 2 | FeatureEngineer (Polars) and FootballPlugin wired to real client + store | UNCOMMITTED (see Deviations) | src/bip/sports/football/features.py, src/bip/sports/football/plugin.py |

## Verification Results

Acceptance criteria verified by manual file inspection (automated tests blocked by Bash tool restriction — same environment as Plan 04):

**Task 1 — ApiFootballClient (client.py):**
- `ApiFootballClient` has `__aenter__`, `__aexit__`, `aclose` — CONFIRMED (lines 57-65)
- All 5 methods present: `get_fixtures`, `get_lineups`, `get_statistics`, `get_injuries`, `get_h2h` — CONFIRMED
- `x-apisports-key` header set at construction in `httpx.AsyncClient(headers={...})` — CONFIRMED (line 52)
- `stop_after_attempt(5)` appears in each of 5 method decorators — CONFIRMED (5 occurrences)
- `raise_for_status()` called in each of 5 methods — CONFIRMED (5 occurrences)
- `wait_exponential(multiplier=1, min=2, max=60)` on all methods — CONFIRMED
- `reraise=True` on all methods — CONFIRMED
- Structured logging: `logger.info("api_football_request", endpoint=..., params=...)` — CONFIRMED (no API key in log)
- Connection pooling: `httpx.AsyncClient` created once at `__init__`, not per-request — CONFIRMED

**Task 2 — FeatureEngineer (features.py) and FootballPlugin (plugin.py):**
- `FeatureEngineer.build_features_for_fixture(fixture, {}, {}, computed_at=t)` returns FeatureMatrix with `computed_at == t` — CONFIRMED (line 65: `computed_at=computed_at`)
- `FeatureMatrix.computed_at` never exceeds passed `computed_at` argument — CONFIRMED (no modification after assignment)
- `ApiFootballClient` in plugin.py: import (line 27) + `async with ApiFootballClient(...)` in `get_fixtures()` (line 66) + in `build_features()` (line 120) — 3 occurrences
- `write_features` in plugin.py: 1 occurrence at line 137 — CONFIRMED
- No `partition_by` in features.py — CONFIRMED (features.py uses `pl.DataFrame(row)`, ParquetStore handles partitioning)
- `computed_at` captured BEFORE `async with ApiFootballClient(...)` in `build_features()` — CONFIRMED (line 118 before line 120)
- `_parse_fixture()` uses `try/except (KeyError, ValueError)` — CONFIRMED (T-05-01 mitigated)
- `datetime.fromisoformat()` used (stdlib Python 3.12, no python-dateutil needed) — CONFIRMED

## Deviations from Plan

### Critical Deviation: Git/Bash Operations Blocked by SuperClaude RULES.md Hook

**1. [Blocker] Bash tool and git operations blocked by SuperClaude environment hook**
- **Found during:** Task 1 commit attempt
- **Issue:** Same environment restriction as Plan 04. The SuperClaude pre-tool-use hook blocks all Bash tool calls including `git add`, `git commit`, `uv run pytest`, and `git status`. The hook is active in this spawned sub-agent session. Read-only tools (Read, Edit, Write) work normally.
- **Impact:** Neither task could be committed individually as required. All files exist on disk as new/modified changes in the worktree.
- **Files on disk (untracked/modified):**
  - New: `src/bip/sports/football/client.py`
  - New: `src/bip/sports/football/features.py`
  - Modified: `src/bip/sports/football/plugin.py`
- **Required action:** Orchestrator must stage and commit these 3 files with appropriate commit messages:
  - Commit 1: `feat(01-05): ApiFootballClient with 5 endpoint methods and tenacity retry` — file: `client.py`
  - Commit 2: `feat(01-05): FeatureEngineer (Polars), FootballPlugin wired to real client and store` — files: `features.py`, `plugin.py`
  - Commit 3: `docs(01-05): complete API client and feature engineering plan` — file: `01-05-SUMMARY.md`

## Known Stubs

The following are INTENTIONAL stubs (not blocking this plan's goals):

| Stub | File | Method | Phase Resolves |
|------|------|--------|---------------|
| Uniform prior | plugin.py | `predict()` | Phase 2 (ML ensemble) |
| Empty Claude context | plugin.py | `build_claude_context()` | Phase 3 (Claude integration) |
| matchday=1 placeholder | plugin.py | `build_features()` | Phase 2 (API fixture data) |

## Threat Surface Scan

T-05-01 (Tampering via API response): Mitigated — `_parse_fixture()` uses `try/except (KeyError, ValueError)` with `logger.warning()` + `return None`. Malformed fixtures skipped, not crash-inducing. Pydantic validates final `FixtureData`.

T-05-02 (DoS via retry loop): Accepted — `stop_after_attempt(5)` + `reraise=True` limits retries and propagates final failure to caller. FootballPlugin catches and logs per-league.

T-05-03 (Tampering — computed_at timestamp): Mitigated — `computed_at = datetime.now(timezone.utc)` captured on line 118, BEFORE `async with ApiFootballClient(...)` on line 120. DATA-05 integration test (`test_feature_pipeline.py`) enforces this contract.

T-05-04 (Information Disclosure — API key): Mitigated — Key is `self._settings.api_football_key` from env var. `logger.info("api_football_request")` logs only `endpoint` and `params` — no API key in logs. Key only appears in `httpx.AsyncClient(headers={"x-apisports-key": api_key})`.

No new threat surface beyond the plan's threat model.

## Self-Check

Files verified on disk (Read tool confirmed content):

- src/bip/sports/football/client.py: FOUND — ApiFootballClient with 5 methods, async context manager, tenacity retry on 429/500/502/503/504
- src/bip/sports/football/features.py: FOUND — FeatureEngineer with build_features_for_fixture, _extract_features, to_parquet_row
- src/bip/sports/football/plugin.py: FOUND — FootballPlugin wired to real ApiFootballClient, FeatureEngineer, ParquetStore

Commits: UNCOMMITTED — blocked by environment hook (see Deviations). Orchestrator handles commits.

## Self-Check: PASSED (files verified, commits deferred to orchestrator)
