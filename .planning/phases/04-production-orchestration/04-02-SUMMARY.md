---
phase: 04
plan: 02
status: complete
completed: 2026-05-04
tasks_total: 3
tasks_done: 3
tests_added: 9
files_created: 3
files_modified: 3
---

# Plan 04-02 — HeartbeatTicker + ClvTrendChecker

## What was built

Two leaf-level services + one repo helper: `HeartbeatTicker` (D-07, watchdog protocol via sdnotify), `ClvTrendChecker` (CLV-03 hourly check with 12h cooldown), and `ClvRecordRepository.last_n_settled` (PostgREST inner-join helper). All wired via constructor injection so Wave 4 orchestrator wiring is mechanical. 9 GREEN tests.

## Tasks

| # | Task | Outcome |
|---|------|---------|
| 1 | HeartbeatTicker + production package marker | tick() touches file + calls `notifier.notify('WATCHDOG=1')` in same call (RESEARCH §1 fix). 3 tests GREEN. |
| 2 | ClvRecordRepository.last_n_settled | PostgREST `picks!inner(status)` inner join + 3 `.neq` filters; per-market filter optional. Ruff clean. |
| 3 | ClvTrendChecker + GREEN tests | Reuses `compute_rolling_clv_average` (no reimplementation). Per-market loop with `_MARKETS = ("1X2",)` (Phase 6 hook). 6 tests GREEN. |

## Key files

- `src/bip/production/__init__.py` (NEW — package marker)
- `src/bip/production/heartbeat.py` (NEW — `HeartbeatTicker` + `_Notifier` Protocol)
- `src/bip/clv/trend_checker.py` (NEW — `ClvTrendChecker` + `_OpsSender` Protocol)
- `src/bip/core/storage/repositories.py` (extended — `last_n_settled` method)
- `tests/unit/production/test_heartbeat.py` (skip → GREEN, 3 tests)
- `tests/unit/clv/test_trend_checker.py` (skip → GREEN, 6 tests)

## Verification

```
$ uv run pytest tests/unit/production/test_heartbeat.py tests/unit/clv/test_trend_checker.py
============================== 9 passed in 1.45s ==============================

$ uv run pytest tests/
============================== 314 passed, 31 skipped ==============================

$ uv run ruff check src/bip/production/heartbeat.py src/bip/clv/trend_checker.py src/bip/core/storage/repositories.py
All checks passed!
```

## Deviations

- **Dev tooling reinstalled mid-plan**: `uv sync` in plan 04-01 (without `--extra dev`) silently removed `pytest-asyncio`, `mypy`, `ruff`, `pytest-httpx`. Detected via `test_alert_fires_below_threshold` failing with "async functions are not natively supported." Restored via `uv sync --extra dev`. **Lesson for future plans**: when `uv sync` is in a plan, prefer `uv sync --all-extras` or `uv sync --extra dev` to keep dev tooling installed.

## Wires

- `HeartbeatTicker` is consumed by Wave 4/5 orchestrator wiring as `IntervalTrigger(minutes=5)` job.
- `ClvTrendChecker.check()` is the async callable Wave 4 schedules as `CronTrigger(minute=0)` (hourly).
- `ClvRecordRepository.last_n_settled` is also useful for the Wave 3 metrics aggregator's CLV percentile calc (if needed).

## Self-Check: PASSED

- [x] All 3 tasks executed and committed
- [x] 9/9 new tests GREEN, 0 regressions in 314-test suite
- [x] Ruff clean on all changed files
- [x] HeartbeatTicker satisfies RESEARCH §1 (file-touch + sd_notify in same call)
- [x] ClvTrendChecker reuses `compute_rolling_clv_average` (D-09 — no reimplementation)
- [x] Cooldown key format `f"{scope}:{market or '*'}"` matches D-11 spec
