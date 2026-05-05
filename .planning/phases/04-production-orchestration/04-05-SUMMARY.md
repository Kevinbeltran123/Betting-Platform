---
phase: 04
plan: 05
status: complete
completed: 2026-05-04
tasks_total: 2
tasks_done: 2
tests_added: 7
files_created: 2
files_modified: 3
---

# Plan 04-05 — Production entrypoint

## What was built

`bip.production` is now a runnable package: `python -m bip.production` instantiates Settings, calls `build_orchestrator(settings)` to construct the entire dependency graph (Supabase client, 3 repos, two TelegramBots, OddsApiClient, ClvRecorder, ClaudeValidator with real learnings, FootballPlugin, LeagueRegistry, shared scheduler, PickEngine, HeartbeatTicker, ClvTrendChecker, MetricsAggregator, DriftChecker, sd_notifier), wires it into `PipelineOrchestrator(drift_checker=...)`, registers SIGTERM/SIGINT handlers, signals systemd READY=1, and blocks on stop_event.

## Tasks

| # | Task | Outcome |
|---|------|---------|
| 1 | `build_orchestrator` factory + `DriftChecker` class | Returns 4-tuple `(orchestrator, picks_bot, ops_bot, sd_notifier)`. Two TelegramBots bound to picks/ops channel_ids. DriftChecker passed via `drift_checker=` kwarg. ClaudeValidator + PickEngine constructed with REAL args (no None placeholders). T-4-06 verified: no Settings instance to logger. 4 GREEN tests. |
| 2 | `__main__.py` asyncio entrypoint | SIGTERM+SIGINT registered via `loop.add_signal_handler` (NotImplementedError-wrapped for Windows). `sd_notifier.notify('READY=1')` after orchestrator.start(). `_shutdown` calls orch.shutdown() (sync) → both bots.shutdown() (async) → set stop_event. 3 GREEN tests. |

## Key files

- `src/bip/production/__init__.py` (replaced — exports `build_orchestrator`, `DriftChecker`)
- `src/bip/production/builder.py` (NEW — 220 lines, `DriftChecker` + `_load_learnings` + `build_orchestrator`)
- `src/bip/production/__main__.py` (NEW — `main()` + `_shutdown()`)
- `tests/unit/production/test_builder.py` (skip → 4 GREEN)
- `tests/unit/production/test_main.py` (skip → 3 GREEN)

## Verification

```
$ uv run pytest tests/unit/production/
============================== 10 passed in 3.85s ==============================

$ uv run pytest tests/
============================== 350 passed, 0 skipped in 78.19s ==============

$ uv run python -c "from bip.production.builder import build_orchestrator; from bip.production import __main__"
# imports clean

$ uv run ruff check src/bip/production/ tests/unit/production/
All checks passed!

$ grep -r "logger.*settings\b" src/bip/production/  # T-4-06 check
src/bip/production/__main__.py:8:  # in docstring only — not actual code
src/bip/production/builder.py:142: # in docstring only — not actual code
```

## Key deviations

- **`FootballPlugin(settings=settings)`**: the live constructor (`src/bip/sports/football/plugin.py:53`) takes `(settings, prediction_repo)`, not `(api_client, league_registry)` as the planning doc speculated. Adjusted to live signature; `prediction_repo` left at default `None`.
- **`shared_scheduler` reassignment**: `PipelineOrchestrator.__init__` constructs its own `AsyncIOScheduler`. To keep PickEngine and orchestrator on ONE scheduler instance, builder constructs a `shared_scheduler` for PickEngine then reassigns `orchestrator.scheduler = shared_scheduler`. Acceptable v1 hack; a follow-up could add a `scheduler=` kwarg to the orchestrator's `__init__`.
- **Mock variable naming**: ruff's N806 rule rejects `MockBot`/`MockClaude` PascalCase. Renamed to `mock_bot`/`mock_claude`/`mock_orch`/`mock_odds` to satisfy project lint rules.

## Wires

- Wave 6 plan 04-06 systemd unit will `ExecStart=/opt/bip/.venv/bin/python -m bip.production` — points directly at `__main__`.
- Wave 6 install.sh creates `/var/run/bip/` (mode 0750 owned by `bip:bip`) so HeartbeatTicker.tick() can `Path.touch()` without crashing on `FileNotFoundError`.
- Wave 7 smoke-test runbook will exercise the full chain: deploy → start → READY=1 → heartbeat ticks → ops channel receives test alert.

## Self-Check: PASSED

- [x] All 2 tasks committed atomically
- [x] 7 wave-5 tests GREEN, 350 total passing, 0 skipped, 0 regressions
- [x] DriftChecker constructed AND passed via drift_checker= kwarg
- [x] Two TelegramBot instances bound to picks/ops channel_ids (D-03)
- [x] sd_notifier.notify('READY=1') called AFTER orchestrator.start()
- [x] T-4-06 verified — Settings instance never passed to logger
- [x] `python -m bip.production` is invocable (import surface clean)
