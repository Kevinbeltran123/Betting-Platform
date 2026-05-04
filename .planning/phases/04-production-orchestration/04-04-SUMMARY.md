---
phase: 04
plan: 04
status: complete
completed: 2026-05-04
tasks_total: 3
tasks_done: 3
tests_added: 10
files_modified: 8
audit_gaps_closed: 0
---

# Plan 04-04 — Orchestrator wiring + claude_failure_mode

## What was built

D-01 branch in `PickEngine` (filter vs skip modes), `ClaudeVerdict.verdict` regex broadened to include `SKIPPED`, and `PipelineOrchestrator` extended with 5 new optional kwargs + 4 conditional cron jobs + 3 wrapper methods + `auto_recover_complete` log event. Two-channel `TelegramBot` design verified by construction-time tests. After this plan all Phase 4 logic is in place — only entrypoint and deploy artifacts remain.

## Tasks

| # | Task | Outcome |
|---|------|---------|
| 1 | ClaudeVerdict + PickEngine D-01 | Regex broadened (`SKIPPED`); engine.py `if verdict is None:` branches on `self._settings.claude_failure_mode`. 1 + 3 + 20 GREEN tests (validator + new claude_failure + existing engine). |
| 2 | Orchestrator extension | 5 init kwargs, 4 conditional cron jobs, 3 wrapper methods, `auto_recover_complete` log, `date` imported at module top. 5 new GREEN tests (Phase4Wiring class). |
| 3 | Two-channel TelegramBot routing | 3 GREEN tests using `unittest.mock.patch` on `ApplicationBuilder` to verify each bot's `chat_id` matches the channel ID it was constructed with. |

## Audit gap status

- **G-CODE-01** (`SportPlugin.get_opening_odds` missing) — **STALE / not a bug**. The method exists on the ABC (`src/bip/sports/__init__.py:78`) and on the `FootballPlugin` concrete (`src/bip/sports/football/plugin.py:291`). The audit appears to have been written against an earlier branch.
- **G-CODE-02** (`pick_repo.get_pending_for_fixture()` returns dicts, code uses `getattr`) — **STALE / not a bug**. The live code at `orchestrator.py:248-261` uses `p.get("market")` (correct dict access), not `getattr(p, "market")`. The audit's claim about `await` on a sync method also doesn't match the live code, which calls the method synchronously.
- No inline fixes were needed in Wave 4. If new audit-gap evidence surfaces, it should be re-filed against the live code.

## Key deviations from plan

- **`test_phase4_jobs_*` switched to `@pytest.mark.asyncio`**: `AsyncIOScheduler.start()` calls `asyncio.get_running_loop()` which raises `RuntimeError` in a sync test context. Marking the test async provides the loop the scheduler needs.
- **`test_auto_recover_complete_event_fires` switched from `caplog` to `capsys`**: `structlog` writes to stdout, not stdlib logging, so `caplog` captures nothing. Same pattern that landed in 04-03 for `test_metrics_aggregation_complete_log_emitted`.
- **`tests/picks/test_engine.py::_make_engine`** factory updated to set `settings.claude_failure_mode = "filter"`. Without this, the existing `test_claude_unavailable_filters` test would compare `MagicMock() == "filter"` (which is False), drop into the new `skip` branch, and assert `scheduler.add_job.assert_not_called()` would fail.
- **No `_persist_pending_skipped` method created** — reused existing `_persist_pending` per plan instruction. The DB CHECK constraint from migration 004 already accepts `claude_validation='SKIPPED'`.

## Verification

```
$ uv run pytest tests/unit/telegram/test_routing.py tests/unit/picks/test_engine_claude_failure.py tests/unit/claude/test_validator.py tests/scheduler/test_orchestrator.py
============================== 26 passed in 2.04s ==============================

$ uv run pytest tests/
============================== 343 passed, 7 skipped in 79.83s ==============

$ uv run ruff check src/bip/core/picks/engine.py src/bip/core/claude/validator.py src/bip/core/scheduler/orchestrator.py
# 5 errors, all pre-existing E501s in lines untouched by this plan (validator.py:8 docstring,
# engine.py:149 _persist_filtered signature, orchestrator.py:147/229/575 pre-existing comments)
```

## Wires

- Wave 5 (`04-05-PLAN`) production entrypoint will:
  - Construct two `TelegramBot` instances (picks + ops) using `Settings.telegram_channel_id` and `Settings.telegram_ops_channel_id`.
  - Construct `HeartbeatTicker(settings.heartbeat_file_path, sdnotify.SystemdNotifier())`.
  - Construct `ClvTrendChecker(clv_repo, ops_telegram, threshold=settings.clv_trend_alert_threshold, cooldown_hours=settings.clv_trend_cooldown_hours)`.
  - Construct `MetricsAggregator(perf_repo, pick_repo)`.
  - Construct a `DriftChecker` (NEW, defined in builder.py) wrapping `compute_weekly_drift` with all 4 drift Settings fields.
  - Pass all five into `PipelineOrchestrator(...)`.

## Self-Check: PASSED

- [x] All 3 tasks committed atomically
- [x] 26 wave-4 tests GREEN, 343 total passing, no regressions
- [x] D-01 branch produces correct PickStatus + claude_validation in both modes
- [x] Orchestrator registers 4 NEW jobs only when their deps are wired
- [x] `auto_recover_complete` log uses literal local var names from live code
- [x] Two-channel routing locked at construction time (T-4-01)
- [x] No code outside plan scope modified (test factory adjustment was required for regression safety)
