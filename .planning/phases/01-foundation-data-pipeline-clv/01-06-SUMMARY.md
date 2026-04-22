---
phase: "01-foundation-data-pipeline-clv"
plan: 6
subsystem: "clv"
tags: [clv, odds-api, pinnacle, tenacity, pydantic, rolling-average]
dependency_graph:
  requires:
    - "01-03 (ClvRecord, ClvRecordRepository, ClvError — all in core/storage)"
    - "01-04 (parallel wave, no file overlap)"
    - "01-05 (parallel wave, no file overlap)"
  provides:
    - "OddsApiClient with fetch_pinnacle_closing_odds in src/bip/clv/client.py"
    - "MARKET_KEY_MAP translating internal keys to Odds API keys"
    - "calculate_clv_percentage(odds_at_pick, closing_odds) implementing CLV-02 formula"
    - "compute_rolling_clv_average(clv_values) using last 50 picks (CLV-03)"
    - "ClvRecorder writing ClvRecord with odds_fetched_at to Supabase (D-04c)"
  affects:
    - "Plan 07 (scheduler calls ClvRecorder post-match)"
    - "tests/test_clv_client.py"
    - "tests/test_clv_recorder.py"
tech_stack:
  added:
    - "httpx.AsyncClient for Odds API (apiKey query param, not header)"
    - "tenacity stop_after_attempt(3) for Rookie tier budget (vs 5 for API-Football)"
  patterns:
    - "async context manager (__aenter__/__aexit__/aclose)"
    - "_is_retryable_http_error module-level predicate for tenacity retry_if_exception"
    - "structlog.get_logger(__name__) keyword-style logging"
key_files:
  created:
    - src/bip/clv/client.py
    - src/bip/clv/recorder.py
decisions:
  - "Use ClvRecordRepository (actual class name) not ClvRepository (plan template alias)"
  - "stop_after_attempt(3) for Odds API (500 req/mo Rookie budget) vs stop_after_attempt(5) for API-Football"
  - "ruff UP017: datetime.UTC alias instead of timezone.utc"
metrics:
  duration: "8 minutes"
  completed: "2026-04-22T23:00:00Z"
  tasks_completed: 2
  tasks_total: 2
  files_created: 2
  files_modified: 0
---

# Phase 1 Plan 6: CLV Client and Recorder Summary

**One-liner:** OddsApiClient fetches Pinnacle closing odds via The Odds API v4 with tenacity retry (attempt=3); ClvRecorder calculates clv_percentage=(odds/closing-1)*100 and persists ClvRecord with odds_fetched_at; compute_rolling_clv_average uses last 50 picks for trend monitoring.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | OddsApiClient with Pinnacle fetch, MARKET_KEY_MAP, retry | 041b5bb | src/bip/clv/client.py |
| 2 | calculate_clv_percentage, compute_rolling_clv_average, ClvRecorder | eaf54da | src/bip/clv/recorder.py |

## Verification Results

- `OddsApiClient` has `__aenter__`, `__aexit__`, `aclose`, `fetch_pinnacle_closing_odds`, `map_market_key`
- `apiKey` sent as query parameter (not header) — matches Odds API v4 auth
- `stop_after_attempt(3)` confirmed — Rookie tier budget protection
- `MARKET_KEY_MAP["onextwo"] == "h2h"`, `MARKET_KEY_MAP["ou"] == "totals"`
- `calculate_clv_percentage(2.10, 2.00)` returns `5.0` (CLV-02 formula verified)
- `compute_rolling_clv_average([-5.0]*50 + [4.0]*50)` returns `4.0` (last-50 window confirmed)
- `ClvRecorder` uses `ClvRecordRepository` (actual class name in repositories.py)
- `odds_fetched_at` stored in `ClvRecord` (D-04c compliance)
- `ruff check src/bip/clv/` — 0 errors
- `pytest tests/test_clv_client.py tests/test_clv_recorder.py` — **12/12 passed**

## Deviations from Plan

**Minor:** Plan template referenced `ClvRepository` as the repository class name, but `repositories.py` (from Plan 03) uses `ClvRecordRepository`. Used the actual class name. No behavioral impact.

## Threat Surface Scan

- T-06-01 (division by zero): Mitigated — `if closing_odds <= 0: raise ClvError(...)` guard before division
- T-06-02 (API key disclosure): Mitigated — `self._api_key` never logged; structlog events only log `sport_key`, `event_id`, `market_key`
- T-06-03 (stale Pinnacle odds): Mitigated — `odds_fetched_at` stored per D-04c
- T-06-04 (429 rate limit DoS): Mitigated — `stop_after_attempt(3)` raises `ApiError` after 3 retries; Plan 07 scheduler handles deferral

## Self-Check: PASSED

All acceptance criteria met. 12 CLV tests green. ruff clean. No open stubs.
