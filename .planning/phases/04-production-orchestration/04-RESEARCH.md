# Phase 4: Production Orchestration — Research

**Researched:** 2026-05-03
**Domain:** Async Python service deployment (APScheduler 3.x + asyncio + systemd) on a single Hetzner VPS, with statistical alerting (rolling CLV trend + 4-week drift) and Postgres aggregation rollups.
**Confidence:** HIGH on systemd / APScheduler / Postgres SQL; MEDIUM on the drift statistical method (one-sided, low-sample); HIGH on the validation architecture per CORE Nyquist.

## Summary

Phase 4 wires four new APScheduler 3.x cron/interval jobs (heartbeat, hourly CLV trend, daily metrics aggregator, weekly drift) into the existing `PipelineOrchestrator`, ships a production `python -m bip.production` entrypoint, and packages the whole thing as a hardened systemd unit on a Linux VPS. The phase is dominated by integration concerns, not new ML or domain logic — every primitive already exists in the codebase (`compute_rolling_clv_average`, `PerformanceMetricRepository.upsert`, `_auto_recover`, the `Settings` pattern). The work is to call them on a schedule, route alerts to a separate ops channel, and survive process restarts cleanly.

The single non-trivial finding is that **the heartbeat design proposed in CONTEXT.md D-07 (Python touches a file, systemd `WatchdogSec=` reads its mtime) is not how systemd works.** `WatchdogSec=` requires `Type=notify` and `sd_notify("WATCHDOG=1")` calls over the systemd notification socket — there is no file-mtime mode. The planner must choose between (a) keeping `WatchdogSec=` and adding the `sdnotify` Python library to the heartbeat job (one extra import, three lines of code), or (b) keeping the file-touch design and dropping `WatchdogSec=` in favour of an external `systemd.path` unit + a separate watchdog timer that restarts the service on stale mtime. Option (a) is strictly simpler and is the recommendation below.

The second non-trivial finding is the **drift signal in D-14**: at `min_picks_per_window = 30`, the stdev of per-pick CLV is dominated by a few large Pinnacle moves (CLV % is heavy-tailed), so `1.5 × stdev(prior_window)` can be a tight or loose gate at random. Two concrete mitigations are recommended in §Drift Statistical Method below.

**Primary recommendation:** Adopt `Type=notify` + `sdnotify` for the heartbeat (~3 lines added to D-07's tick handler), keep all four scheduled jobs in `MemoryJobStore` with `coalesce=True` + `misfire_grace_time=600`, add a single `compute_period(...)` SQL aggregator using Postgres `FILTER (WHERE ...)` clauses (one round-trip per `(sport,league,market)` triple), and use `loop.add_signal_handler(SIGTERM, ...)` to fan out to `scheduler.shutdown(wait=True)`. The drift check should compare daily-mean-CLV (n≈28) instead of per-pick CLV (n≈30+) and floor the stdev at `1.0pp` to keep the soft gate stable at low pick volume.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Graceful Degradation**
- **D-01:** Claude API failure default stays conservative (Phase 3 D-07 preserved). Add `Settings.claude_failure_mode: Literal["filter", "skip"] = "filter"`. `"filter"` (default) → pick persisted with `status='filtered'`, `reason_code='claude_api_unavailable'`, never sent. `"skip"` → pick persisted with `status='pending'`, `claude_validation='SKIPPED'`, sent to Telegram with a `🤖❌` marker. SC#2 must be reworded to reflect this feature flag.
- **D-02:** Odds API failure during CLV snapshot → skip silently (no `clv_records` row written). Logged at WARNING level. Phase 4 SC#2 wording must be revised: picks still send; CLV record is skipped on Odds-API failure and not backfilled.
- **D-03:** Ops alerts go to a separate Telegram channel via new env var `TELEGRAM_OPS_CHANNEL_ID`. Picks channel (`TELEGRAM_CHANNEL_ID`) stays clean. Both validated by the same pydantic-settings validator.
- **D-04:** API retry budgets stay as-is. No new Settings knobs.

**Production Entrypoint, systemd, Heartbeat**
- **D-05:** Production main lives at `src/bip/production/__main__.py`. Invoke via `python -m bip.production`. Companion `src/bip/production/__init__.py` may expose `build_orchestrator(settings)` for tests. SIGTERM handled via `asyncio` signal handler → `await orchestrator.shutdown()`.
- **D-06:** systemd unit shape: dedicated `bip` system user, `Restart=always`, `RestartSec=10`, `EnvironmentFile=/etc/bip/.env` (mode 600), `WatchdogSec=600`, `StandardOutput=journal`, `StandardError=journal`, `WorkingDirectory=/opt/bip`, `ExecStart=/opt/bip/.venv/bin/python -m bip.production`. Unit file at `deploy/systemd/bip.service`.
- **D-07:** Heartbeat: APScheduler `IntervalTrigger(minutes=5)` job that touches `Settings.heartbeat_file_path` (default `/var/run/bip/heartbeat`). Heartbeat dir created during deployment.
- **D-08:** Auto-recovery: reuse `_auto_recover` as-is. Add structlog event `auto_recover_complete` with re-queued counts.

**CLV Trend Alert (CLV-03)**
- **D-09:** Hourly cron `CronTrigger(minute=0)`. Query last 50 settled CLV records, pass to `compute_rolling_clv_average()`, alert if `< Settings.clv_trend_alert_threshold` (default `1.0`).
- **D-10:** Scope: global + per-market dimensions. Per-market only when ≥50 settled picks for that market. Per-league NOT added.
- **D-11:** Cooldown: 12h, in-memory `dict[str, datetime]` keyed on `f"{scope}:{market}"` inside `ClvTrendChecker`. Restart resets cooldown — at most one duplicate alert per restart.
- **D-12:** Alert message format: trend value only. `⚠️ CLV +0.7% < +1% threshold`. Per-market: `⚠️ CLV +0.6% < +1% threshold [market: 1X2]`. Sent to ops channel.

**Performance Metrics Aggregator (CLV-04) + Weekly Drift**
- **D-13:** Daily cron `CronTrigger(hour=23, minute=0)` UTC. Single pass computes/upserts metrics for `daily` (yesterday), `weekly` (trailing 7d), `monthly` (trailing 30d), `all_time` (everything settled). Upsert key `(sport, league, market, period, period_start)`.
- **D-14:** Weekly drift cron `CronTrigger(day_of_week='mon', hour=6, minute=0)` UTC. Compare rolling 4-week mean CLV (last 28 days) vs prior 4-week mean (29-56d ago) per (league, market) with ≥30 settled picks each window. Hard threshold: drop ≥2pp. Soft threshold: drop ≥ 1.5 × stdev(prior_4w). Either fires alert. Format: `⚠️ DRIFT [league=PL market=1X2] -2.3pp (3.5% → 1.2%)`. Routes to ops.
- **D-15:** Aggregator math at `src/bip/core/metrics/aggregator.py`. Pure functions: `compute_daily_metrics()`, `compute_weekly_drift()`. Sport-agnostic per CORE-02.
- **D-16:** Hybrid SQL + Polars. Aggregator → new `PerformanceMetricRepository.compute_period(sport, league, market, period_start, period_end) -> PerformanceMetric` (single round trip per triple). Drift → Polars over rows fetched via existing repos.

### Claude's Discretion
- Heartbeat job as top-level `IntervalTrigger` vs wrapper around scheduler tick (planner picks simplest).
- Module split between `bip.production.__main__` and `bip.production.builder.build_orchestrator(settings)` (recommended for testability).
- `ClvTrendChecker` and `MetricsAggregator` as classes vs free functions (recommend classes since both hold state).
- Field set of `DriftResult` dataclass (must include enough info for D-14 alert + optional `drift_events` Supabase row).
- Whether to log heartbeat ticks at debug or rate-limit them.
- `compute_period` repo method takes single `(sport, league, market)` triple OR accepts `None` for "all" + groups internally (single-triple is simpler).

### Deferred Ideas (OUT OF SCOPE)
- Web admin dashboard / breakdown UI for alerts (CLAUDE.md rules out FastAPI in v1).
- Feature drift (KS test on recent vs training distribution) — v2.
- Odds drift (opening vs closing gap widening) — v2.
- Per-league CLV trend dimension — deferred until Phase 6 corners + full season volume.
- Backfill of missed CLV snapshots after VPS downtime — deliberate non-feature.
- Backfill of missed reconciliation jobs >150 min past kickoff.
- Auto-promotion of model registry on CLV improvement.
- Pinnacle `/historical` backfill (Phase 02.1 deferred this).
- Edge-triggered CLV trend alerts (cross above → cross below detection).
- Telegram bot user commands (`/status`, `/clv_today`, `/pause`).
- Persistent cooldown / alert-state table in Supabase.
- API retry knob exposure as Settings fields.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CLV-03 | Rolling 50-pick CLV trend alert (< +1% → Telegram warning) | §CLV Trend Alert Architecture, §Validation Architecture row "CLV trend alert" |
| CLV-04 | Performance metrics aggregator (ROI, yield, avg CLV, W/L/V by sport/league/market/period) | §Aggregator SQL, §Validation Architecture row "Aggregator idempotency" |
| DATA-04 | APScheduler 3.x `AsyncIOScheduler` pipeline (Phase 1 contract; Phase 4 extends with heartbeat + metrics + drift jobs) | §APScheduler 3.x Operational Knobs, §Architecture Diagram |

No new requirements. The three IDs above are pre-existing pending items in `REQUIREMENTS.md`. Phase 4 plans MUST cite these IDs in `requirements:` frontmatter.
</phase_requirements>

## Project Constraints (from CLAUDE.md)

| Constraint | Source | Phase 4 Implication |
|-----------|--------|---------------------|
| APScheduler 3.11.x ONLY (4.x is alpha) | CLAUDE.md §Scheduling | Use `AsyncIOScheduler.add_job(...)`, NEVER `add_schedule(...)`. Already enforced in `pyproject.toml` (`APScheduler>=3.11,<4.0`). |
| No FastAPI / web server | CLAUDE.md §What NOT to Use | Rules out HTTP `/health` endpoint. File-touch heartbeat + journald + Telegram is the entire ops surface. |
| pydantic-settings + `.env` | CLAUDE.md §Core Framework | All Phase 4 knobs extend the existing `Settings` class. No per-feature settings classes. |
| structlog keyword logging | CLAUDE.md §Missing from Original Stack | All Phase 4 events use `logger.info("event_name", **kwargs)`. |
| Polars over pandas | CLAUDE.md §Feature Engineering | Drift check (D-14) uses `pl.DataFrame.group_by` + `pl.col(...).std()`, not pandas. |
| ruff / pytest | CLAUDE.md §Development & Quality | All new modules pass `ruff check` and `pytest` before commit. Stubs for Wave 0 use `pytest.mark.skip`. |
| Python 3.12+ | CLAUDE.md §Core Framework | `from datetime import UTC` available. `Literal["filter", "skip"]` available without `typing_extensions`. |
| No Co-Authored-By in commits | CLAUDE.md §Conventions | `gsd-sdk query commit` invocations must not include trailers. |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Job scheduling | APScheduler `AsyncIOScheduler` (in-process Python) | — | Phase 1 D-03 contract; Phase 4 inherits. No external broker. |
| Process supervision (restart, watchdog, env injection) | systemd | — | OS-level concern; Python should not reimplement supervisord. |
| Liveness signal | Python heartbeat job | systemd `WatchdogSec=` watcher | Python proves "I'm alive"; systemd decides "kill if not." See §Heartbeat & Watchdog Integration. |
| Metric aggregation | Postgres (`FILTER (WHERE ...)` aggregates) | Polars (only for drift comparison) | Aggregation is pure SQL on the single source of truth (`picks` + `clv_records`). Polars is for distribution math (mean, stdev) that's awkward in SQL. |
| Alert delivery | TelegramSender (existing, Phase 3) | — | Reuse — Phase 4 adds a second instance bound to ops channel. No new abstraction. |
| Cooldown state | In-memory dict on `ClvTrendChecker` | — | D-11 explicit decision. Lost-on-restart is acceptable cost. |
| Configuration | pydantic-settings + `.env` | systemd `EnvironmentFile=` | `.env` is the source of truth; systemd injects it via `EnvironmentFile=` (mode 600). |
| Secrets | `/etc/bip/.env` (chmod 600, owned by `bip:bip`) | — | Never embedded in unit file or repo. Deployment script creates it once. |
| Logs | structlog → stdout/stderr | systemd journald | `StandardOutput=journal` captures structlog JSON without intermediate file. |

## Standard Stack

### Core (already pinned in `pyproject.toml`)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| APScheduler | `>=3.11,<4.0` | In-process job scheduler (`AsyncIOScheduler`) | Phase 1 D-03 contract. 4.x is still alpha. `[VERIFIED: pyproject.toml]` |
| structlog | `25.5.0` | Keyword-arg structured logging | Already used everywhere; JSON to journald. `[VERIFIED: pyproject.toml]` |
| pydantic-settings | `2.14.0` | `.env` + env-var loading | Existing `Settings` pattern. `[VERIFIED: pyproject.toml]` |
| supabase | `2.28.3` | Postgres client (sync) | All repositories already use this. `[VERIFIED: pyproject.toml]` |
| python-telegram-bot[rate-limiter] | `22.7` | Async Telegram delivery | Phase 3 D-13. Phase 4 reuses; second instance for ops channel. `[VERIFIED: pyproject.toml]` |
| polars | `1.40.1` | DataFrame ops for drift comparison | CLAUDE.md mandate. `[VERIFIED: pyproject.toml]` |
| scipy | `>=1.15,<2` | (potentially) `scipy.stats.ranksums` for drift soft gate | Already a dependency for penaltyblog. `[VERIFIED: pyproject.toml]` |

### NEW Additions (Phase 4 only)
| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `sdnotify` | `0.3.2` (PyPI) | Send `READY=1` and `WATCHDOG=1` to systemd notification socket | Required by `Type=notify` + `WatchdogSec=` per systemd man page. ~50 LoC pure-Python with no native deps. **Drop-in safe on macOS/dev** (the library silently no-ops when `NOTIFY_SOCKET` is unset). `[VERIFIED: pypi.org/project/sdnotify]` |

**Installation:**
```bash
uv add sdnotify==0.3.2
```

**Version verification:**
```bash
# Confirm before adding to pyproject.toml — sdnotify has had no release in 12+ months
# but is feature-complete for the WATCHDOG=1 / READY=1 use case.
uv pip show sdnotify  # post-install
```
- `sdnotify==0.3.2` is the latest; the package has not been updated in 12+ months but the `sd_notify` protocol is itself frozen, so this is acceptable. Snyk reports zero vulnerabilities. `[VERIFIED: PyPI search 2026-05]`
- Alternative considered: `systemd-watchdog` (more recent releases) — equivalent functionality but less battle-tested. Stay with `sdnotify`.
- Alternative rejected: writing the protocol by hand (~10 LoC: open AF_UNIX SOCK_DGRAM at `$NOTIFY_SOCKET`, send `b"WATCHDOG=1"`). Not worth saving a 50-LoC dep.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `sdnotify` for watchdog | Pure file-mtime + external `systemd.path` unit + a separate timer service | Requires a second systemd unit just to monitor the heartbeat file, plus `systemctl restart bip.service` invocation from a second user (or root). Strictly more deployment surface; rejected. |
| Postgres `FILTER (WHERE ...)` aggregation | Multiple Supabase queries + Python rollup | Requires N round-trips per period × per (sport, league, market). The single-query `FILTER` form is ~5x fewer DB calls. `[VERIFIED: postgresql.org docs]` |
| `loop.add_signal_handler(SIGTERM, ...)` | `signal.signal(SIGTERM, ...)` | `signal.signal` is sync; the handler can't `await` anything. `add_signal_handler` schedules a coroutine via `loop.create_task`. **HIGH confidence** — this is the canonical asyncio pattern. `[CITED: docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.add_signal_handler]` |
| in-memory cooldown dict | Supabase `alert_cooldowns` table | Adds schema migration + a join. D-11 deliberately rejects this. |

## Architecture Patterns

### System Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│ systemd (PID 1)                                                  │
│  ├─ Type=notify, WatchdogSec=600s                                │
│  ├─ EnvironmentFile=/etc/bip/.env (mode 600, owned by bip:bip)   │
│  ├─ Restart=always, RestartSec=10                                │
│  ├─ ExecStart=/opt/bip/.venv/bin/python -m bip.production        │
│  └─ User=bip, ProtectSystem=strict, NoNewPrivileges=true         │
│            │                                                     │
│            │ on stale heartbeat OR crash                         │
│            ▼                                                     │
│       SIGTERM/SIGABRT → restart                                  │
└────────────┼─────────────────────────────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────────────────────────────┐
│ python -m bip.production (asyncio loop, single process)          │
│                                                                  │
│  src/bip/production/__main__.py                                  │
│   ├─ build Settings (validate required env vars)                 │
│   ├─ build_orchestrator(settings) → PipelineOrchestrator         │
│   ├─ loop.add_signal_handler(SIGTERM, _shutdown_async)           │
│   ├─ orchestrator.start()                                        │
│   ├─ sdnotify("READY=1")     ← signals notify-startup complete   │
│   └─ await asyncio.Event().wait()  # block forever               │
│                                                                  │
│  PipelineOrchestrator.scheduler (AsyncIOScheduler, in-process)   │
│   ├─ daily_orchestrator (06:00 UTC)        [Phase 1 — unchanged] │
│   ├─ nightly_clv_reconciliation (03:00)    [Phase 1 — kept stub] │
│   ├─ pipeline_<fixture>_t_minus_2h         [Phase 1 — unchanged] │
│   ├─ pipeline_<fixture>_t_minus_30m        [Phase 1 — unchanged] │
│   ├─ clv_<fixture>_t_minus_1m              [Phase 3 — unchanged] │
│   ├─ reconcile_<fixture>                   [Phase 3 — unchanged] │
│   │                                                              │
│   ├─ heartbeat (Interval 5min)             [Phase 4 NEW]         │
│   │     touches /var/run/bip/heartbeat                           │
│   │     calls sdnotify("WATCHDOG=1") ──── systemd notify socket  │
│   ├─ clv_trend (Cron 0 */1 * * *)          [Phase 4 NEW]         │
│   │     ClvTrendChecker.check() ──→ ops TelegramSender           │
│   ├─ metrics_aggregator (Cron 0 23 * * *)  [Phase 4 NEW]         │
│   │     MetricsAggregator.run() ──→ PerformanceMetricRepository  │
│   └─ weekly_drift (Cron 0 6 * * 1)         [Phase 4 NEW]         │
│         compute_weekly_drift() ──→ ops TelegramSender            │
│                                                                  │
│  Two TelegramSender instances:                                   │
│   ├─ picks_sender → TELEGRAM_CHANNEL_ID  (Phase 3 path)          │
│   └─ ops_sender   → TELEGRAM_OPS_CHANNEL_ID  (Phase 4 NEW)       │
└──────────────────────────────────────────────────────────────────┘
              │                              │
              ▼                              ▼
       Supabase Postgres              Telegram Bot API
       (picks, clv_records,           (picks channel + ops channel)
        performance_metrics)
```

### Recommended Project Structure
```
src/bip/
├── production/
│   ├── __init__.py        # exposes build_orchestrator(settings) — for tests
│   ├── __main__.py        # entrypoint: python -m bip.production
│   └── builder.py         # build_orchestrator(settings) -> PipelineOrchestrator
├── core/
│   ├── settings.py        # extended with Phase 4 fields + validators
│   ├── metrics/           # NEW
│   │   ├── __init__.py
│   │   ├── aggregator.py  # MetricsAggregator + compute_daily_metrics
│   │   └── drift.py       # compute_weekly_drift + DriftResult dataclass
│   ├── alerts/            # NEW (D-11 cooldown lives here too)
│   │   ├── __init__.py
│   │   └── clv_trend.py   # ClvTrendChecker
│   ├── scheduler/orchestrator.py   # extended (4 new add_job calls)
│   ├── storage/repositories.py     # PerformanceMetricRepository.compute_period
│   ├── telegram/                   # extended for two-channel support
│   ├── claude/validator.py         # D-01 skip-mode branch
│   └── picks/engine.py             # D-01 settings.claude_failure_mode branch
└── deploy/                # NEW (NOT under src/)
    ├── systemd/bip.service    # unit file (versioned)
    ├── install.sh             # idempotent runbook
    └── README.md              # operator quickstart
```

### Pattern 1: Production entrypoint with graceful shutdown
**What:** SIGTERM-aware asyncio main that fans out to scheduler + telegram cleanup.
**When:** D-05 — exactly once at module level in `bip/production/__main__.py`.

```python
# Source: docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.add_signal_handler
# Source: roguelynn.com/words/asyncio-graceful-shutdowns/  [VERIFIED]
import asyncio
import signal
import structlog
from bip.core.settings import Settings
from bip.production.builder import build_orchestrator

logger = structlog.get_logger(__name__)

async def main() -> None:
    settings = Settings()  # raises on missing required env
    orchestrator, picks_bot, ops_bot, sd_notifier = build_orchestrator(settings)

    await picks_bot.start()
    await ops_bot.start()
    orchestrator.start()  # registers all scheduled jobs

    sd_notifier.notify("READY=1")  # signal systemd we're up
    logger.info("production_started")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(
        signal.SIGTERM,
        lambda: asyncio.create_task(_shutdown(stop_event, orchestrator,
                                              picks_bot, ops_bot)),
    )
    loop.add_signal_handler(
        signal.SIGINT,
        lambda: asyncio.create_task(_shutdown(stop_event, orchestrator,
                                              picks_bot, ops_bot)),
    )
    await stop_event.wait()

async def _shutdown(stop_event, orch, picks_bot, ops_bot) -> None:
    logger.info("shutdown_started")
    orch.shutdown()              # AsyncIOScheduler.shutdown(wait=True) — see below
    await picks_bot.shutdown()
    await ops_bot.shutdown()
    stop_event.set()
    logger.info("shutdown_complete")

if __name__ == "__main__":
    asyncio.run(main())
```

**`AsyncIOScheduler.shutdown(wait=True)` semantics** `[VERIFIED: apscheduler.readthedocs.io/en/3.x]`:
- The current `PipelineOrchestrator.shutdown()` calls `scheduler.shutdown(wait=True)` (already at orchestrator.py:572-574).
- `wait=True` waits for **scheduler internals** to drain (job-store flush, executor pool join). It does NOT cancel running asyncio tasks already dispatched into the event loop. Currently-firing async jobs continue executing on the loop.
- For an in-flight CLV snapshot, that means: the snapshot will run to completion (good — no half-written DB rows). For SIGTERM during a `_record_clv` call, the event loop will keep the task alive, the await chain completes, then `_shutdown` proceeds.
- **Action item for the planner:** the existing `orchestrator.shutdown()` is sync (no `await`). Phase 4 must NOT change that — it's correct as-is. The planner just needs to make sure `_shutdown` in `__main__.py` calls it before awaiting the telegram bot shutdowns.

### Pattern 2: Heartbeat with sd_notify integration

**What:** APScheduler `IntervalTrigger(minutes=5)` job that touches the heartbeat file AND notifies systemd.
**When:** D-07 — registered inside `PipelineOrchestrator.start()`.

```python
# Source: pypi.org/project/sdnotify [VERIFIED]
# Source: freedesktop.org/software/systemd/man/sd_notify.html [CITED]
from pathlib import Path
import sdnotify
import structlog

logger = structlog.get_logger(__name__)

class HeartbeatTicker:
    """File-touch + systemd watchdog notification.

    The file mtime is for human/external observers (`stat -c %Y heartbeat`).
    The sdnotify call is what systemd's WatchdogSec= actually reads.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._notifier = sdnotify.SystemdNotifier()  # silently no-ops on macOS

    def tick(self) -> None:
        self._path.touch()
        self._notifier.notify("WATCHDOG=1")
        # Debug-only — emit at INFO every Nth tick if journal volume becomes a concern.
        logger.debug("heartbeat", path=str(self._path))
```

Registration inside `orchestrator.start()`:
```python
self.scheduler.add_job(
    self._ticker.tick,                          # sync — fine in AsyncIOExecutor
    trigger=IntervalTrigger(minutes=5),
    id="heartbeat",
    replace_existing=True,
    coalesce=True,
    misfire_grace_time=60,
)
```

### Pattern 3: APScheduler 3.x cron job idempotency
**What:** Daily / weekly cron jobs that survive missed fires (DST, restarts, manual reruns).
**When:** D-13 (metrics aggregator), D-14 (weekly drift).

```python
# Source: apscheduler.readthedocs.io/en/3.x/userguide.html [VERIFIED]
self.scheduler.add_job(
    self._aggregate_metrics,
    trigger=CronTrigger(hour=23, minute=0, timezone="UTC"),
    id="metrics_aggregator",
    replace_existing=True,
    coalesce=True,             # collapse multiple missed runs into ONE
    misfire_grace_time=600,    # allow 10 min lateness; beyond that, skip until next fire
)
```

**Behavior on VPS restart with `MemoryJobStore`** `[VERIFIED: apscheduler.readthedocs.io]`:
- `MemoryJobStore` does NOT persist jobs across restarts. On restart, only the cron jobs registered in `start()` exist; per-fixture `DateTrigger` jobs are reconstructed by `_auto_recover` from today's fixtures.
- A missed daily cron (e.g., VPS down at 23:00 UTC) is NOT replayed when `MemoryJobStore` is used — it's simply lost. `coalesce` only merges runs from a job that has already been queued.
- **Operational consequence:** if the VPS is down at 23:00 UTC, the daily aggregator skips that day. The next fire (next day 23:00 UTC) sees `daily` (yesterday) and `weekly`/`monthly`/`all_time` as rolling windows — so the lost row is `daily` for the missed-day. Acceptable per CONTEXT.md (no backfill of missed reconciliation jobs).
- **Idempotency on manual re-run** is guaranteed by the `(sport, league, market, period, period_start)` upsert key — running `python -m bip.metrics.aggregator --day 2026-05-03` (a future CLI, out of scope here) would produce the same row.

### Pattern 4: Postgres single-round-trip aggregation

**What:** One `SELECT` per `(sport, league, market)` triple per period, computing all eight aggregate fields server-side.
**When:** D-16 — implementation of `PerformanceMetricRepository.compute_period(...)`.

```sql
-- Source: postgresql.org/docs/current/sql-expressions.html#SYNTAX-AGGREGATES [VERIFIED]
-- Source: tigerdata.com/learn/understanding-filter-in-postgresql-with-examples [VERIFIED]
SELECT
    COUNT(*)                                          AS total_picks,
    COUNT(*) FILTER (WHERE p.status = 'won')          AS won,
    COUNT(*) FILTER (WHERE p.status = 'lost')         AS lost,
    COUNT(*) FILTER (WHERE p.status = 'void'
                       OR p.status = 'push')          AS void,
    COALESCE(SUM(p.suggested_stake), 0)               AS total_staked,
    COALESCE(
        SUM(
            CASE p.status
                WHEN 'won'  THEN p.suggested_stake * (p.best_odds - 1)
                WHEN 'lost' THEN -p.suggested_stake
                ELSE 0
            END
        ), 0
    )                                                 AS total_pnl,
    -- ROI = total_pnl / total_staked  (None when no stake — caller fills NULL)
    SUM(
        CASE p.status
            WHEN 'won'  THEN p.suggested_stake * (p.best_odds - 1)
            WHEN 'lost' THEN -p.suggested_stake
            ELSE 0
        END
    ) / NULLIF(SUM(p.suggested_stake), 0)             AS roi,
    -- yield_pct uses the same numerator (different scaling left to caller — caller multiplies by 100)
    AVG(c.clv_percentage)                             AS avg_clv,
    AVG(p.edge)                                       AS avg_edge
FROM picks p
LEFT JOIN clv_records c ON c.pick_id = p.id
WHERE p.sport = $1
  AND p.league = $2
  AND p.market = $3
  AND p.created_at >= $4   -- period_start (inclusive)
  AND p.created_at <  $5   -- period_end   (exclusive)
  AND p.status NOT IN ('filtered', 'rejected', 'pending')   -- only settled
;
```

**Why `LEFT JOIN clv_records`:** D-02 says some picks won't have CLV rows (Odds API failure). `LEFT JOIN` keeps those picks in the count (and `AVG(c.clv_percentage)` ignores NULLs natively). This is the correct join. **Inner join would silently drop picks** — bug.

**Python-side mapping to `PerformanceMetric`:**
```python
def compute_period(
    self,
    sport: str, league: str, market: str,
    period: AggregationPeriod,
    period_start: date, period_end: date,
) -> PerformanceMetric:
    response = self.client.rpc(  # Supabase RPC for raw SQL — see Pitfall 5 below
        "compute_performance_period",
        {
            "p_sport": sport, "p_league": league, "p_market": market,
            "p_start": period_start.isoformat(), "p_end": period_end.isoformat(),
        },
    ).execute()
    row = response.data[0]
    return PerformanceMetric(
        sport=sport, league=league, market=market,
        period=period, period_start=period_start, period_end=period_end,
        total_picks=row["total_picks"],
        won=row["won"], lost=row["lost"], void=row["void"],
        total_staked=float(row["total_staked"] or 0),
        total_pnl=float(row["total_pnl"] or 0),
        roi=float(row["roi"]) if row["roi"] is not None else None,
        yield_pct=(float(row["roi"]) * 100) if row["roi"] is not None else None,
        avg_clv=float(row["avg_clv"]) if row["avg_clv"] is not None else None,
        avg_edge=float(row["avg_edge"]) if row["avg_edge"] is not None else None,
    )
```

**Pitfall 5 (see below):** Supabase Python client does NOT support arbitrary `SELECT` SQL — only via RPC. The planner must add a Postgres function `compute_performance_period(p_sport, p_league, p_market, p_start, p_end)` via a migration (Phase 4 migration 005). This adds one schema migration to the phase but keeps the round-trip count = 1.

### Pattern 5: Settings extension with validator

```python
# Source: src/bip/core/settings.py:39-58 (existing _validate_channel_id) [VERIFIED]
from typing import Literal
from pydantic import field_validator

class Settings(BaseSettings):
    # ... existing fields ...

    # Phase 4 — graceful degradation
    claude_failure_mode: Literal["filter", "skip"] = "filter"

    # Phase 4 — ops channel (D-03)
    telegram_ops_channel_id: str = ""  # validated below — same shape as picks channel

    # Phase 4 — heartbeat
    heartbeat_file_path: str = "/var/run/bip/heartbeat"

    # Phase 4 — CLV trend (D-09–D-12)
    clv_trend_alert_threshold: float = 1.0       # % — alert if rolling avg < this
    clv_trend_cooldown_hours: int = 12

    # Phase 4 — drift (D-14)
    drift_check_min_picks_per_window: int = 30
    drift_absolute_threshold_pp: float = 2.0     # percentage points
    drift_stdev_multiplier: float = 1.5
    drift_stdev_floor_pp: float = 1.0            # see §Drift Statistical Method

    @field_validator("telegram_ops_channel_id")
    @classmethod
    def _validate_ops_channel_id(cls, v: str) -> str:
        # Mirror _validate_channel_id (Pitfall 8 from Phase 3).
        if v == "":
            return v
        if not v.startswith("-100"):
            raise ValueError(...)
        if len(v) < 8:
            raise ValueError(...)
        return v
```

### Anti-Patterns to Avoid

- **`signal.signal(SIGTERM, handler)` in asyncio code** — handler runs in signal context; cannot `await`. Use `loop.add_signal_handler`. `[CITED: docs.python.org]`
- **`Type=simple` with `WatchdogSec=`** — silently does nothing. `WatchdogSec=` requires `Type=notify` or `Type=notify-reload`. `[VERIFIED: freedesktop.org sd_notify man page]`
- **Touching the heartbeat file but not calling `sdnotify`** — file gets newer mtime; systemd watchdog still kills the service because it never received `WATCHDOG=1`. The two are independent signals; CONTEXT.md D-07 conflates them.
- **`scheduler.shutdown(wait=False)` in production** — does NOT cancel in-flight asyncio tasks. CLV writes mid-flight could be torn. `[VERIFIED: apscheduler issue #233]`
- **INNER JOIN on `clv_records` in the aggregator SQL** — silently drops picks with no CLV row (D-02 path). LEFT JOIN is required.
- **Drift soft-gate using stdev of per-pick CLV at n=30** — see §Drift Statistical Method.
- **APScheduler 4.x API in any Phase 4 file** — `add_schedule(...)` is 4.x; `add_job(...)` is 3.x. Repo is pinned to 3.x.
- **Per-feature settings classes** — extend the flat `Settings` class. CONTEXT.md cites `PATTERNS.md drift risk #3`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| sd_notify protocol over Unix socket | Custom AF_UNIX SOCK_DGRAM client | `sdnotify` library | Edge cases: protocol expects `\n`-delimited messages, AF_UNIX path may be abstract (`@/...`). Library handles both. |
| Graceful asyncio SIGTERM handling | Custom signal-bridge using `os.kill` self-pipe | `loop.add_signal_handler` | Standard library; correctly schedules a coroutine instead of blocking the event loop. |
| Cron expression parsing | Custom datetime arithmetic for "every Monday at 6 UTC" | APScheduler `CronTrigger` | DST handling, leap years, timezone math — solved problem. |
| Postgres `count(*) FILTER (WHERE ...)` aggregation | Multiple Supabase queries + Python rollup | Single SQL with `FILTER` clauses | 5x fewer round trips; ANSI SQL since 9.4. |
| Watchdog timer in Python | `asyncio.wait_for(...)` self-watchdog | systemd `WatchdogSec=` | The whole point of running under systemd is OS-level supervision. Don't reimplement. |
| Telegram rate limiting | Sleep-between-sends loop | `python-telegram-bot[rate-limiter]` (already in stack) | Phase 3 D-13 contract; Phase 4 reuses. |
| Statistical comparison of two CLV windows | Hand-rolled `(mean(a) - mean(b)) / stdev(b)` | `scipy.stats.ranksums` (optional v2 upgrade) | Heavy-tailed CLV makes parametric z-tests unreliable. See §Drift Statistical Method. |

**Key insight:** Phase 4 is integration glue. Almost every primitive exists in the codebase or in a battle-tested library. The phase succeeds by composition, not by writing new algorithms.

## Heartbeat & Watchdog Integration (the load-bearing finding)

**The proposed design in CONTEXT.md D-07 is incorrect on a key technical point.** Quote: *"Implementation: `Path(settings.heartbeat_file_path).touch()` in an async-safe wrapper. systemd `WatchdogSec=600` reads the file's mtime; if older than 600s → restart."*

systemd `WatchdogSec=` does **NOT** read file mtime. It listens on the notification socket pointed to by `$NOTIFY_SOCKET` (an AF_UNIX datagram socket created by systemd when `Type=notify` is set) and expects to receive `WATCHDOG=1` messages within the configured timeout. The mechanism is documented in `sd_notify(3)` and the `systemd.service(5)` man page. `[VERIFIED: freedesktop.org/software/systemd/man/sd_notify.html]` `[VERIFIED: oneuptime.com/blog/post/2026-03-04-set-up-systemd-watchdog-monitoring-for-critical-services]`

### Three options for the planner

| Option | What it costs | Verdict |
|--------|---------------|---------|
| **A. Add `sdnotify`** to the heartbeat tick. Keep `Type=notify` + `WatchdogSec=600`. | +1 dependency (~50 LoC pure Python, no native deps), +3 lines of code in the heartbeat tick. The file-touch stays as a parallel signal for human ops (`stat -c %Y /var/run/bip/heartbeat`). | **RECOMMENDED.** Smallest delta, native systemd integration, file-touch remains for human inspection. |
| B. Drop `WatchdogSec=`, use only file-touch + an external `systemd.path` unit watching the file. | The path unit can fire `OnFailure=` only on file *modification*, not staleness. So you'd need yet another systemd `OnUnitInactiveSec=`-driven timer that runs `stat` and `systemctl restart bip.service`. Adds 2 systemd units + a shell script. | Reject — strictly more deployment surface. |
| C. Drop `WatchdogSec=`, rely only on `Restart=always`. | Crash-restart works; hung-process-restart does NOT. A hung event loop (e.g., infinite Telegram retry, deadlock) won't be caught. | Reject — defeats the purpose of SC#3 ("systemd auto-restart + 5-min heartbeat"). |

**Option A — concrete code:**

```python
# bip/production/builder.py
import sdnotify

def build_orchestrator(settings: Settings):
    sd_notifier = sdnotify.SystemdNotifier()  # no-op when NOTIFY_SOCKET is unset (e.g., dev machines)
    ticker = HeartbeatTicker(settings.heartbeat_file_path, sd_notifier)
    # ... rest of build ...
    return orchestrator, picks_bot, ops_bot, sd_notifier
```

**`bip.service` becomes:**
```ini
[Service]
Type=notify
WatchdogSec=600
NotifyAccess=main
# ... rest as in CONTEXT.md D-06 ...
```

**Confidence on this finding:** HIGH. Multiple independent sources confirm `WatchdogSec=` requires `sd_notify`. The `sdnotify` library is the standard Python implementation (mirrored in Debian's `python3-sdnotify` package).

## Drift Statistical Method (D-14 sharpening)

The compound trigger as written in D-14 is:
- **Hard:** `abs(mean(recent_4w) - mean(prior_4w)) >= 2.0pp`
- **Soft:** `(mean(prior_4w) - mean(recent_4w)) >= 1.5 * stdev(prior_4w)`

With `min_picks_per_window = 30` and CLV % per pick being heavy-tailed (one Pinnacle line move from 1.95 → 2.20 produces a CLV jump of >10%), the per-pick stdev is dominated by tail observations. This makes the soft gate behave erratically:
- A prior 4w window that happened to include one big positive CLV pick → large stdev → soft gate too loose (1.5×stdev > 5pp).
- A prior 4w window that was steady (all picks within ±2pp) → small stdev → soft gate too tight (1.5×stdev < 0.5pp).

### Recommendation (one method, code-shape included)

**Use stdev of daily-mean CLV (n≈28) rather than stdev of per-pick CLV (n≈30+). Floor the stdev at `drift_stdev_floor_pp = 1.0`.**

Rationale:
- Daily mean CLV is bounded variance even when individual picks are heavy-tailed (averaging 1-3 picks/day pulls toward the long-run mean).
- `n=28 daily means` is a reasonable sample for the soft gate; `n=30 per-pick observations` is not.
- Flooring at 1.0pp prevents the 1.5×stdev gate from being unrealistically tight when the prior window was unusually steady (e.g., post-holiday period with low pick volume).

```python
# Source: scipy.stats.ranksums [CITED: docs.scipy.org/doc/scipy]  (kept for v2)
import polars as pl
from datetime import date, timedelta
from dataclasses import dataclass

@dataclass(frozen=True)
class DriftResult:
    sport: str
    league: str
    market: str
    recent_window_start: date
    recent_window_end: date
    recent_mean_pp: float
    recent_n: int
    prior_window_start: date
    prior_window_end: date
    prior_mean_pp: float
    prior_n: int
    delta_pp: float                # recent_mean - prior_mean (negative = drop)
    stdev_pp: float                # stdev of daily means in prior window (floored)
    triggered_hard: bool
    triggered_soft: bool

    @property
    def triggered(self) -> bool:
        return self.triggered_hard or self.triggered_soft


def compute_weekly_drift(
    clv_rows: list[dict],          # rows from clv_records joined with picks
    sport: str, league: str, market: str,
    today: date,
    min_picks: int = 30,
    abs_threshold_pp: float = 2.0,
    stdev_multiplier: float = 1.5,
    stdev_floor_pp: float = 1.0,
) -> DriftResult | None:
    df = pl.DataFrame(clv_rows).filter(
        (pl.col("sport") == sport)
        & (pl.col("league") == league)
        & (pl.col("market") == market)
    )
    recent_start = today - timedelta(days=28)
    prior_start  = today - timedelta(days=56)

    recent = df.filter(pl.col("created_at") >= recent_start)
    prior  = df.filter(
        (pl.col("created_at") >= prior_start)
        & (pl.col("created_at") <  recent_start)
    )

    if recent.height < min_picks or prior.height < min_picks:
        return None  # insufficient sample — no alert, no false alarm

    recent_mean = recent["clv_percentage"].mean()
    prior_mean  = prior["clv_percentage"].mean()

    # Daily means in prior window — bounded variance regardless of pick tails
    prior_daily = (
        prior
        .with_columns(pl.col("created_at").dt.date().alias("day"))
        .group_by("day")
        .agg(pl.col("clv_percentage").mean().alias("day_mean"))
    )
    raw_stdev = prior_daily["day_mean"].std() or 0.0
    stdev = max(raw_stdev, stdev_floor_pp)   # FLOOR

    delta = recent_mean - prior_mean         # negative => drop
    triggered_hard = delta <= -abs_threshold_pp
    triggered_soft = delta <= -stdev_multiplier * stdev

    return DriftResult(
        sport=sport, league=league, market=market,
        recent_window_start=recent_start, recent_window_end=today,
        recent_mean_pp=recent_mean, recent_n=recent.height,
        prior_window_start=prior_start, prior_window_end=recent_start,
        prior_mean_pp=prior_mean, prior_n=prior.height,
        delta_pp=delta, stdev_pp=stdev,
        triggered_hard=triggered_hard, triggered_soft=triggered_soft,
    )
```

**v2 upgrade path (deferred):** replace the soft gate with `scipy.stats.ranksums(prior, recent, alternative="greater")` and trigger on `p_value < 0.05`. This is a fully non-parametric test that's appropriate for the heavy-tailed CLV distribution and doesn't depend on stdev at all. Not recommended for v1 because (a) it requires more careful threshold calibration vs the simple stdev gate, and (b) D-14 is a single drift signal — getting one out the door beats getting the perfect one. `[CITED: docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ranksums.html]`

**Confidence:** MEDIUM on the stdev-of-daily-means floor — this is engineering judgment, not a textbook result. The planner should document the assumption in a code comment so the v2 upgrade trigger is obvious.

## CLV Trend Cooldown — Concurrency Analysis

D-11 keeps cooldown state in an in-memory `dict[str, datetime]` on the `ClvTrendChecker` instance. Concern: is this thread-safe?

**Finding:** Yes, in this specific architecture. `[VERIFIED: apscheduler.readthedocs.io/en/3.x/modules/executors/asyncio.html]`

- `AsyncIOScheduler`'s default executor is `AsyncIOExecutor`. `add_job(...)` with an `async def` callable runs the coroutine **directly on the event loop** (no thread pool). For sync callables, it dispatches to the event loop's default `ThreadPoolExecutor`.
- `_check_clv_trend` (per orchestrator section in CONTEXT.md) is referenced as `add_job(self._check_clv_trend, ...)`. If the planner declares it `async def`, the cooldown dict is only ever accessed from the single event-loop thread → fully thread-safe without any lock.
- If the planner declares `_check_clv_trend` as `def` (sync), it would run in the thread pool and could race with other sync jobs that also touch the cooldown dict. With only one cron job touching this state per hour, the practical race window is essentially zero — but the code should declare `async def` to make the safety guarantee explicit.

**Recommendation:** Declare `ClvTrendChecker.check()` and the orchestrator wrapper `async def`. No lock needed. Document in a code comment: "Cooldown dict is touched only from the asyncio event loop; do not call from a sync context."

## APScheduler 3.x Operational Knobs

Verified against APScheduler 3.11.x docs `[VERIFIED: apscheduler.readthedocs.io/en/3.x/userguide.html]`:

| Knob | Value | Reason |
|------|-------|--------|
| `coalesce` | `True` for daily/weekly cron jobs | Collapse multiple missed runs into one (e.g., scheduler frozen 5 min during DST). |
| `misfire_grace_time` | `600` (10 min) for daily/weekly cron | Allow 10-min lateness before skipping. Beyond 10 min, prefer the next scheduled run over a stale execution. Existing reconcile job already uses 600 (orchestrator.py:222). |
| `misfire_grace_time` | `60` for `IntervalTrigger(minutes=5)` heartbeat | Heartbeat is short-cadence; a 60s grace is plenty. |
| `replace_existing` | `True` for all cron job IDs | Idempotent re-registration on restart. |
| `timezone` | `"UTC"` on every `CronTrigger` | Match existing convention (orchestrator.py:55, 68, 75). |
| `JobStore` | `MemoryJobStore` (default) | Per Phase 1 D-03; not persisted across restarts. Cron jobs are re-registered on `start()`. Date-trigger fixture jobs are re-built by `_auto_recover`. |

## systemd Unit Hardening (D-06 — concrete template)

`[VERIFIED: archlinux.org/wiki/systemd/Sandboxing]` `[VERIFIED: gist.github.com/ageis/f5595e59b1cddb1513d1b425a323db04]`

```ini
# deploy/systemd/bip.service
[Unit]
Description=Betting Intelligence Platform
Documentation=https://github.com/your-org/betting-intelligence-platform
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
NotifyAccess=main
WatchdogSec=600

User=bip
Group=bip
WorkingDirectory=/opt/bip
EnvironmentFile=/etc/bip/.env
ExecStart=/opt/bip/.venv/bin/python -m bip.production

Restart=always
RestartSec=10

# Logging — structlog JSON to journald
StandardOutput=journal
StandardError=journal
SyslogIdentifier=bip

# Hardening (verified safe for: network egress + write to /var/run/bip)
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/run/bip
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictNamespaces=true
RestrictRealtime=true
RestrictSUIDSGID=true
LockPersonality=true
MemoryDenyWriteExecute=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
SystemCallArchitectures=native
SystemCallFilter=@system-service
SystemCallFilter=~@privileged @resources

# Resource limits — tune per VPS
LimitNOFILE=4096
TasksMax=64

[Install]
WantedBy=multi-user.target
```

**Why each hardening directive is safe for this workload:**

| Directive | Why safe |
|-----------|----------|
| `ProtectSystem=strict` | App writes only to `/var/run/bip/heartbeat`, `/opt/bip/.venv/__pycache__/` (declared via `ReadWritePaths`), and the journal. No `/etc`, `/usr` writes needed at runtime. |
| `ProtectHome=true` | App is run as system user `bip`; never reads from `/home`. |
| `ReadWritePaths=/var/run/bip` | The single mutable directory (heartbeat file). |
| `NoNewPrivileges=true` | App never invokes setuid binaries. |
| `PrivateTmp=true` | App uses Polars' default cache dir (`/tmp/.polars*`); `PrivateTmp` gives it an isolated namespace, no conflict. |
| `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX` | Needed: AF_INET/INET6 for HTTPS to API-Football, Odds API, Anthropic, Telegram, Supabase. AF_UNIX for `sd_notify` socket. Nothing else. |
| `SystemCallFilter=@system-service` `~@privileged @resources` | Standard "well-behaved daemon" filter set; blocks privileged syscalls and resource manipulation. Verified by [Arch Wiki sandboxing examples] for python services. |
| `MemoryDenyWriteExecute=true` | Python interpreter does not generate executable code at runtime in this stack (no Cython JIT, no PyPy). XGBoost/LightGBM/CatBoost wheels are precompiled. **Verify by smoke-test** — if `MemoryDenyWriteExecute` causes import failure for any ML wheel, drop this directive. |
| `LockPersonality=true` | App does not call `personality(2)`. |
| `RestrictNamespaces=true` | App does not create namespaces. |

**Caveat for the planner:** `MemoryDenyWriteExecute=true` should be smoke-tested in staging before going live. Some Python wheels (older numpy versions, certain OpenMP loaders) JIT a tiny shim and would fail under this directive. If failure is observed, drop just this one line — the rest are safe.

## Deployment Runbook (D-06 — outline only, planner writes the script)

`deploy/install.sh` should be **idempotent** (re-runnable on existing install without breaking state) and contain at minimum:

1. **Pre-flight checks (fail fast):**
   - `[ "$EUID" -eq 0 ] || { echo "Run as root"; exit 1; }`
   - `command -v systemctl >/dev/null || { echo "systemd required"; exit 1; }`
   - `[ -f /opt/bip/.venv/bin/python ] || { echo "venv not built — run 'uv sync' first"; exit 1; }`
2. **Create `bip` system user (idempotent):**
   - `id -u bip >/dev/null 2>&1 || useradd -r -s /sbin/nologin -d /opt/bip bip`
3. **Create `/var/run/bip/` (idempotent, recreated on every boot under tmpfs — also drop a `tmpfiles.d` snippet):**
   - `install -d -o bip -g bip -m 750 /var/run/bip`
   - Drop `deploy/tmpfiles.d/bip.conf` containing `d /var/run/bip 0750 bip bip - -` so the directory survives reboot.
4. **Create `/etc/bip/` and `/etc/bip/.env` (do NOT overwrite if exists — secrets):**
   - `install -d -o root -g root -m 755 /etc/bip`
   - `[ -f /etc/bip/.env ] || install -m 600 -o bip -g bip /dev/null /etc/bip/.env`
   - Print `Edit /etc/bip/.env to set ANTHROPIC_API_KEY, ODDS_API_KEY, ...` if file was created empty.
5. **Validate `.env` has required keys (parse-only — never echo values):**
   - For each of: `SUPABASE_URL`, `SUPABASE_KEY`, `API_FOOTBALL_KEY`, `ODDS_API_KEY`, `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`, `TELEGRAM_OPS_CHANNEL_ID` — `grep -q "^$KEY=" /etc/bip/.env || { echo "Missing $KEY"; exit 1; }`
6. **Install systemd unit:**
   - `install -m 644 deploy/systemd/bip.service /etc/systemd/system/bip.service`
   - `install -m 644 deploy/tmpfiles.d/bip.conf /etc/tmpfiles.d/bip.conf`
   - `systemd-tmpfiles --create /etc/tmpfiles.d/bip.conf`
   - `systemctl daemon-reload`
   - `systemctl enable bip.service`
7. **Print next-step instructions** (don't auto-start — let operator confirm `.env` is filled):
   - `echo "Next: review /etc/bip/.env, then run 'systemctl start bip.service'"`
   - `echo "Logs: journalctl -u bip.service -f"`

The planner writes the actual shell. The contract above is what plan-checker verifies.

## Common Pitfalls

### Pitfall 1: `WatchdogSec=` without `Type=notify`
**What goes wrong:** systemd silently ignores `WatchdogSec=` when `Type=` is `simple` (the default). Service runs but is never restarted on hang.
**Why it happens:** Confusion about what `WatchdogSec=` measures (it's the notification socket, not file mtime).
**How to avoid:** Always pair `WatchdogSec=` with `Type=notify` and `NotifyAccess=main`. Verify with `systemctl show bip.service | grep -i notify`.
**Warning signs:** `journalctl -u bip` shows no `Got notification message from PID X` lines.

### Pitfall 2: AsyncIOScheduler shutdown leaving in-flight tasks
**What goes wrong:** `scheduler.shutdown(wait=False)` returns before async jobs finish. Half-written CLV rows or duplicate Telegram sends possible.
**Why it happens:** `wait=True` waits for the scheduler internals — but in-flight async tasks live on the asyncio loop, not the scheduler. The two are decoupled.
**How to avoid:** In production, always call `shutdown(wait=True)`, then drain the asyncio loop with `await asyncio.sleep(0)` once before exiting. The existing `PipelineOrchestrator.shutdown()` already uses `wait=True` (orchestrator.py:572-574).
**Warning signs:** `pytest -W error` reveals "Task was destroyed but it is pending!" warnings.

### Pitfall 3: INNER JOIN on `clv_records` in aggregator
**What goes wrong:** Picks where Odds API failed (D-02 path) have NO `clv_records` row. `INNER JOIN` silently drops them — the count, total_pnl, ROI all under-report.
**Why it happens:** Easy mistake when writing an aggregation query; "obvious" join becomes wrong.
**How to avoid:** `LEFT JOIN clv_records c ON c.pick_id = p.id`. `AVG(c.clv_percentage)` natively ignores NULLs. Add a unit test that creates a pick with no CLV row and verifies the count includes it.
**Warning signs:** ROI numbers diverge from the spreadsheet sanity check by exactly the count of CLV-failed picks.

### Pitfall 4: Drift soft gate with stdev=0
**What goes wrong:** A prior 4-week window where every CLV is ~equal → stdev = 0 → `1.5 × 0 = 0pp` → ANY drop triggers the soft alert. Spam.
**Why it happens:** Low pick volume + a model that's currently calibrating to a stable line → repeated near-identical CLV values.
**How to avoid:** Floor stdev at `drift_stdev_floor_pp = 1.0` (Setting). The soft gate becomes "any drop ≥ 1.5pp" in the floor case. Also: skip drift entirely when prior daily-mean count < 7.
**Warning signs:** First drift alert fires on day 8 of operation with delta of -0.6pp.

### Pitfall 5: Supabase Python client doesn't support raw SELECT
**What goes wrong:** `supabase.client.from_(...).select("count(*) FILTER (WHERE ...)")` is not valid PostgREST syntax. The aggregation can't be done as a regular query — must be wrapped in a Postgres function exposed via `client.rpc(...)`.
**Why it happens:** PostgREST is a REST mapper, not a SQL passthrough.
**How to avoid:** Phase 4 includes a small migration (`migration 005_add_compute_performance_period.sql`) that creates a `compute_performance_period(...)` function. Repository calls it via `client.rpc("compute_performance_period", {...})`.
**Warning signs:** Trying to express the FILTER aggregation in PostgREST query string and getting nowhere.

### Pitfall 6: `add_signal_handler` not available on Windows
**What goes wrong:** Runs fine on dev macOS and prod Linux; fails import-time on Windows. Not a real concern for this project (Hetzner is Linux only) but tests run on developer macOS.
**Why it happens:** `loop.add_signal_handler()` is POSIX-only.
**How to avoid:** Wrap registration in `try/except NotImplementedError`. macOS supports it, so dev is fine; Windows would silently skip. Also document explicitly in code that this is POSIX-only.
**Warning signs:** Cross-platform CI test failure.

### Pitfall 7: Heartbeat log volume in journald
**What goes wrong:** `logger.info("heartbeat", ...)` every 5 min × 24h × 7d = ~2000 entries/week. Floods journal; obscures real events.
**Why it happens:** Forgetting that journald rotation has cost; structlog JSON is verbose.
**How to avoid:** Use `logger.debug("heartbeat", ...)` (filtered by `LOG_LEVEL=INFO` default). Emit `logger.info("heartbeat_summary", ticks=N)` once per hour instead.
**Warning signs:** `journalctl --disk-usage` grows by >50MB/week from one service.

### Pitfall 8: `MemoryDenyWriteExecute=true` breaking ML wheels
**What goes wrong:** Some numpy/scipy/xgboost wheels JIT a tiny shim at import. With this directive, import fails with `mmap: Permission denied`.
**Why it happens:** Generally rare in current wheels (2024+), but observable historically.
**How to avoid:** Smoke-test before flipping the directive on. If broken, drop this one line; the rest of the hardening still applies.
**Warning signs:** `journalctl -u bip` shows `OSError` on startup right after `Type=notify`.

## Code Examples

### Example 1: ClvTrendChecker with cooldown
```python
# Source: src/bip/clv/recorder.py:78-93 (existing compute_rolling_clv_average) [VERIFIED]
from datetime import UTC, datetime, timedelta
import structlog

from bip.clv.recorder import compute_rolling_clv_average
from bip.core.storage.repositories import ClvRecordRepository
from bip.core.telegram.sender import TelegramSender

logger = structlog.get_logger(__name__)


class ClvTrendChecker:
    """D-09 to D-12: hourly check, in-memory 12h cooldown.

    Concurrency note: cooldown_until is touched only from the asyncio event loop
    via async def check(); do not call from a sync context.
    """

    def __init__(
        self,
        clv_repo: ClvRecordRepository,
        ops_sender: TelegramSender,
        threshold_pct: float = 1.0,
        cooldown_hours: int = 12,
    ) -> None:
        self._repo = clv_repo
        self._sender = ops_sender
        self._threshold = threshold_pct
        self._cooldown = timedelta(hours=cooldown_hours)
        self._cooldown_until: dict[str, datetime] = {}

    async def check(self) -> None:
        await self._check_scope("global", market=None)
        # D-10 Phase 6 hook — iterate per-market when multiple markets exist
        for market in ("1X2",):  # extend in Phase 6
            await self._check_scope("market", market=market)

    async def _check_scope(self, scope: str, market: str | None) -> None:
        key = f"{scope}:{market or '*'}"
        now = datetime.now(UTC)
        if key in self._cooldown_until and now < self._cooldown_until[key]:
            return  # cooled down

        rows = self._repo.last_n_settled(n=50, market=market)  # NEW repo helper
        if len(rows) < 50:
            logger.info("clv_trend_skip_insufficient",
                        scope=scope, market=market, count=len(rows))
            return

        avg = compute_rolling_clv_average([r["clv_percentage"] for r in rows])
        if avg >= self._threshold:
            logger.info("clv_trend_ok", scope=scope, market=market, avg=avg)
            return

        msg = (
            f"⚠️ CLV +{avg:.1f}% < +{self._threshold:.0f}% threshold"
            + (f" [market: {market}]" if market else "")
        )
        await self._sender.send_html(msg)
        self._cooldown_until[key] = now + self._cooldown
        logger.info("clv_trend_alert_fired",
                    scope=scope, market=market, avg=avg)
```

### Example 2: PickEngine D-01 branch
```python
# Source: src/bip/core/picks/engine.py:115-116 (existing) [VERIFIED]
# Replace lines 115-116:
if verdict is None:
    if self._settings.claude_failure_mode == "filter":
        return self._persist_filtered(prediction, opening_odds, "claude_api_unavailable")
    # claude_failure_mode == "skip"
    pick = self._persist_pending_skipped(prediction, opening_odds, selection, idx,
                                         edge, kelly_fraction, stake)
    send_at = deterministic_send_at(datetime.now(UTC), fixture_id)
    self._schedule_send(pick, prediction, send_at)
    return pick

# New helper alongside _persist_pending:
def _persist_pending_skipped(self, prediction, opening_odds, selection, idx,
                             edge, kelly_fraction, stake) -> Pick:
    pick = self._build_pick_skeleton(
        prediction, opening_odds,
        selection=selection, idx=idx, edge=edge,
        kelly_fraction=kelly_fraction, stake=stake,
        status=PickStatus.pending,
    )
    pick.claude_validation = "SKIPPED"
    pick.claude_reasoning = "claude_api_unavailable"
    pick.claude_summary = "🤖❌ Claude validation unavailable; manual review recommended."
    self._pick_repo.insert(pick)
    logger.info("pick_persisted_skipped",
                fixture_id=prediction.fixture_id,
                market=prediction.market)
    return pick
```

### Example 3: ClvRecordRepository.last_n_settled (NEW helper)
```python
# Append to src/bip/core/storage/repositories.py [extends ClvRecordRepository]
def last_n_settled(self, n: int = 50, market: str | None = None) -> list[dict]:
    """Return the last n CLV records (settled picks only) for trend checking.

    D-09: feeds compute_rolling_clv_average. Joins picks for status filter.
    """
    try:
        query = (
            self.client.table("clv_records")
            .select("clv_percentage, market, created_at, picks!inner(status)")
            .neq("picks.status", "filtered")
            .neq("picks.status", "rejected")
            .neq("picks.status", "pending")
            .order("created_at", desc=True)
            .limit(n)
        )
        if market is not None:
            query = query.eq("market", market)
        return query.execute().data or []
    except Exception as e:
        raise StorageError(f"Failed to query last_n_settled clv_records: {e}") from e
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `signal.signal(SIGTERM, ...)` for asyncio shutdown | `loop.add_signal_handler(SIGTERM, ...)` | Python 3.5 (asyncio mature) | Mandatory for asyncio code; old form blocks event loop. |
| `Type=simple` + custom watchdog timer | `Type=notify` + `WatchdogSec=` + sd_notify | systemd 219+ (universal in 2025) | Native OS supervision; no need for Monit/supervisord/etc. |
| Multiple Postgres queries + Python rollup | Single SQL with `FILTER (WHERE ...)` aggregates | Postgres 9.4 (2014) | Fewer round trips, server-side computation. |
| Edge-triggered alert state machine | Fire-and-cooldown timer | Operational simplification | CONTEXT.md D-11; less code, accept duplicate-on-restart. |
| Per-feature settings classes | Flat `Settings` extension | PATTERNS.md drift risk #3 | Match Phase 3 convention. |

**Deprecated/outdated:**
- APScheduler 4.x `add_schedule(...)` — alpha; do not use.
- `signal.signal()` in async code — works but dangerous; superseded by `add_signal_handler`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Floor stdev at 1.0pp prevents soft-gate noise from steady prior windows | Drift Statistical Method | If too low, drift alerts spam ops. If too high, soft gate is dormant — the absolute threshold (2.0pp) still catches large drops. Tunable via `Settings.drift_stdev_floor_pp`. |
| A2 | `MemoryDenyWriteExecute=true` is safe for current numpy/xgboost/lightgbm/catboost wheels | systemd Unit Hardening | Smoke-test before going live; drop the line if any ML import fails. |
| A3 | Every Pinnacle CLV failure (D-02) results in a NULL row, not a crashing pick insert | Aggregator SQL | Verified — `_record_clv` swallows exceptions and returns; no DB write. Confirmed at orchestrator.py:443-448. |
| A4 | `coalesce=True` + `MemoryJobStore` does NOT replay missed daily crons after restart | APScheduler Operational Knobs | Verified by docs; "missed-day daily metric" is acceptable per CONTEXT.md (no backfill). |
| A5 | `sdnotify` 0.3.2 silently no-ops when `NOTIFY_SOCKET` is unset (dev machines, pytest) | Standard Stack | Verified by source inspection of bb4242/sdnotify; the library catches `OSError` on socket connect. |
| A6 | Daily-mean CLV has bounded variance even when per-pick CLV is heavy-tailed | Drift Statistical Method | True under standard CLT assumptions when daily pick count ≥ 1. Holds at 1+ picks/day in practice. |
| A7 | Phase 4 introduces ONE migration (005) for the `compute_performance_period` SQL function | Architecture | Acceptable — single migration for one repository method. |
| A8 | All four new cron jobs (heartbeat, clv_trend, metrics, drift) fit cleanly into `MemoryJobStore` without persistent backing | APScheduler Operational Knobs | Verified by Phase 1 D-03 contract; cron jobs are re-registered in `start()` on every process boot. |

## Open Questions

1. **Should the heartbeat tick log at every fire?**
   - What we know: structlog default level is INFO; 5-min ticks → 12 events/hour × 24 × 7 = 2016/week per service.
   - What's unclear: ops team preference. Some prefer "noisy but searchable", others "quiet by default".
   - Recommendation: Default to `logger.debug("heartbeat", ...)` and a once-per-hour `logger.info("heartbeat_summary", ticks=12)`. Tunable via existing `LOG_LEVEL` env var.

2. **Should the drift check write a `drift_events` table?**
   - What we know: D-14 says alert routes to ops channel. CONTEXT.md says schema migration is OPTIONAL ("if the planner adds one").
   - What's unclear: Is there ops-team appetite for a queryable drift history?
   - Recommendation: Skip in Phase 4. Drift events are rare (weekly cron, threshold-gated). Telegram channel history + journald is sufficient v1.

3. **Two `TelegramSender` instances vs one with channel param?**
   - What we know: D-03 says "implementation choice for planner". Existing `TelegramBot` takes `channel_id` in `__init__`.
   - What's unclear: Does `python-telegram-bot[rate-limiter]` rate-limit per-bot or per-chat?
   - Recommendation: Two separate `TelegramBot` instances (with the same token, different channel IDs). The rate limiter is bot-instance-scoped; two instances give two limiter buckets — desirable since picks vs ops have different cadence profiles. Cost: trivial (two ApplicationBuilder objects, ~500B RAM).

4. **Idempotency of `compute_performance_period` migration?**
   - What we know: `CREATE OR REPLACE FUNCTION` is idempotent in Postgres.
   - What's unclear: Does Supabase MCP allow re-running the same migration?
   - Recommendation: Use `CREATE OR REPLACE FUNCTION compute_performance_period(...)` in the migration. Survives re-apply.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | All Phase 4 code | ✓ (dev: 3.12.9; prod: install on Hetzner) | 3.12.9 | — |
| uv | venv build | ✓ (dev: 0.11.6; prod: install on Hetzner) | 0.11.6 | — |
| systemd | Production deployment | ✗ on dev (macOS); ✓ on Hetzner Ubuntu/Debian | varies | — (dev tests stub `sdnotify` no-op behavior) |
| `sdnotify` (PyPI) | D-07 heartbeat → systemd | ✗ until added | needs 0.3.2 | none — must be added via `uv add sdnotify==0.3.2` |
| Postgres `FILTER (WHERE ...)` | D-16 aggregator SQL | ✓ Supabase Postgres ≥9.4 | 15+ | none |
| Postgres functions / RPC | D-16 aggregator (via Supabase RPC) | ✓ Supabase RPC supported | — | none |
| Telegram bot tokens × 2 channels | D-03 ops channel | ✗ until ops channel created in Telegram | — | one channel possible (both ids equal) — silent loss of separation; reject |
| `/var/run/bip/` directory | D-07 heartbeat file | ✗ until install.sh runs | — | tmpfiles.d snippet survives reboots |
| `/etc/bip/.env` (mode 600) | D-06 secrets | ✗ until install.sh runs | — | none |

**Missing dependencies with no fallback:**
- `sdnotify` library (must be added — `uv add sdnotify==0.3.2`).
- Telegram ops channel (operator must create channel + bot to channel + record `-100<id>` in `.env`).
- Production VPS provisioning (out of phase scope; assumed done before deploy).

**Missing dependencies with fallback:**
- systemd on dev machine: `sdnotify.notify(...)` no-ops silently when `NOTIFY_SOCKET` unset; tests pass on macOS without modification.

## Validation Architecture

> Phase config: `workflow.nyquist_validation = true` (verified in `.planning/config.json`).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (asyncio_mode="auto") |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ --tb=short` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CLV-03 | Rolling 50-pick avg < threshold + cooldown not active → alert fires | unit | `pytest tests/alerts/test_clv_trend_checker.py::test_alert_fires_below_threshold -x` | ❌ Wave 0 |
| CLV-03 | Rolling 50-pick avg ≥ threshold → no alert | unit | `pytest tests/alerts/test_clv_trend_checker.py::test_no_alert_when_above -x` | ❌ Wave 0 |
| CLV-03 | <50 settled picks → skip (no alert) | unit | `pytest tests/alerts/test_clv_trend_checker.py::test_skip_insufficient_sample -x` | ❌ Wave 0 |
| CLV-03 | Cooldown active → suppress | unit | `pytest tests/alerts/test_clv_trend_checker.py::test_cooldown_suppresses -x` | ❌ Wave 0 |
| CLV-03 | Per-market dimension respects ≥50 guard | unit | `pytest tests/alerts/test_clv_trend_checker.py::test_per_market_skipped_below_50 -x` | ❌ Wave 0 |
| CLV-04 | `compute_period` produces correct ROI/yield/CLV with FILTER aggregates | integration (test DB or mocked SQL) | `pytest tests/metrics/test_aggregator.py::test_compute_period_math -x` | ❌ Wave 0 |
| CLV-04 | LEFT JOIN keeps picks with no clv_records row | unit | `pytest tests/metrics/test_aggregator.py::test_left_join_keeps_no_clv_picks -x` | ❌ Wave 0 |
| CLV-04 | Aggregator idempotent: same inputs → same upsert row | integration | `pytest tests/metrics/test_aggregator.py::test_idempotent_rerun -x` | ❌ Wave 0 |
| CLV-04 | All four periods (daily/weekly/monthly/all_time) compute in one job | unit | `pytest tests/metrics/test_aggregator.py::test_all_four_periods -x` | ❌ Wave 0 |
| DATA-04 | Heartbeat IntervalTrigger fires every 5min in scheduler tick simulation | integration | `pytest tests/scheduler/test_heartbeat.py::test_heartbeat_mtime_advances -x` | ❌ Wave 0 |
| DATA-04 | Heartbeat tick calls `sdnotify("WATCHDOG=1")` | unit (mock notifier) | `pytest tests/scheduler/test_heartbeat.py::test_heartbeat_calls_sdnotify -x` | ❌ Wave 0 |
| DATA-04 | `WatchdogSec` triggers restart on stale heartbeat | manual | (manual: stop heartbeat job, observe systemctl restart count) | N/A — documented |
| DATA-04 | Drift hard threshold (≥2pp drop) triggers | unit | `pytest tests/metrics/test_drift.py::test_hard_threshold_triggers -x` | ❌ Wave 0 |
| DATA-04 | Drift soft threshold (≥1.5×stdev drop) triggers | unit | `pytest tests/metrics/test_drift.py::test_soft_threshold_triggers -x` | ❌ Wave 0 |
| DATA-04 | Drift insufficient sample (<30 picks) → no alert | unit | `pytest tests/metrics/test_drift.py::test_insufficient_sample_no_alert -x` | ❌ Wave 0 |
| DATA-04 | Drift stdev floor prevents zero-stdev tight gate | unit | `pytest tests/metrics/test_drift.py::test_stdev_floor -x` | ❌ Wave 0 |
| DATA-04 | Two-channel routing: pick → picks bot, ops alert → ops bot | unit (mock senders) | `pytest tests/telegram/test_two_channel.py::test_routing -x` | ❌ Wave 0 |
| Graceful degradation D-01 | `claude_failure_mode='filter'` → status='filtered', reason_code='claude_api_unavailable' | unit | `pytest tests/picks/test_engine_d01.py::test_filter_mode -x` | ❌ Wave 0 |
| Graceful degradation D-01 | `claude_failure_mode='skip'` → status='pending', claude_validation='SKIPPED', schedule send | unit | `pytest tests/picks/test_engine_d01.py::test_skip_mode -x` | ❌ Wave 0 |
| Graceful degradation D-02 | Terminal Odds API failure → no `clv_records` row + structlog WARNING | unit + log assertion | `pytest tests/scheduler/test_clv_d02.py::test_silent_skip_warns -x` | ❌ Wave 0 |
| SIGTERM handling D-05 | SIGTERM → orchestrator.shutdown() called → telegram bots shut down | unit (signal mock) | `pytest tests/production/test_main_signals.py::test_sigterm_clean_shutdown -x` | ❌ Wave 0 |
| Settings D-03/D-05 | Phase 4 settings load from .env with validators | unit | `pytest tests/test_settings_phase4.py -x` | ❌ Wave 0 |
| `_auto_recover` D-08 | structlog event `auto_recover_complete` fires with re-queued counts | unit | `pytest tests/scheduler/test_orchestrator.py::test_auto_recover_complete_event -x` | ❌ Wave 0 |
| systemd unit | Unit file passes `systemd-analyze verify deploy/systemd/bip.service` | manual (Linux-only) | `systemd-analyze verify deploy/systemd/bip.service` | N/A — documented |

### Sampling Rate
- **Per task commit:** `pytest tests/<area>/ -x -q` (the just-touched test directory; <5s).
- **Per wave merge:** `pytest tests/ -x --tb=short` (full Phase 4 suite, ~30s).
- **Phase gate:** Full suite green before `/gsd-verify-work`. Manual systemd verification done in staging Hetzner VPS before milestone close.

### Wave 0 Gaps
- [ ] `tests/alerts/test_clv_trend_checker.py` — covers CLV-03 (5 cases above)
- [ ] `tests/alerts/__init__.py` — module init
- [ ] `tests/metrics/test_aggregator.py` — covers CLV-04 (4 cases)
- [ ] `tests/metrics/test_drift.py` — covers drift soft/hard/stdev-floor (4 cases)
- [ ] `tests/metrics/__init__.py` — module init
- [ ] `tests/scheduler/test_heartbeat.py` — covers heartbeat mtime + sdnotify (2 cases)
- [ ] `tests/scheduler/test_clv_d02.py` — covers Odds API silent skip (1 case)
- [ ] `tests/picks/test_engine_d01.py` — covers Claude failure mode branch (2 cases)
- [ ] `tests/picks/__init__.py` — module init
- [ ] `tests/production/test_main_signals.py` — covers SIGTERM handler (1 case)
- [ ] `tests/production/__init__.py` — module init
- [ ] `tests/telegram/test_two_channel.py` — covers two-channel routing (1 case)
- [ ] `tests/test_settings_phase4.py` — covers all new settings + validators
- [ ] `tests/conftest.py` — extend with `mock_sdnotifier`, `mock_ops_telegram_sender` fixtures
- [ ] **Migration 005:** `migrations/005_add_compute_performance_period.sql` (the SQL function — Wave 0 stub returns 0 rows; real impl in Wave 1)
- [ ] Framework install: none — pytest + pytest-asyncio already present per `pyproject.toml`.

## Security Domain

> `security_enforcement: true` (default). Phase 4 ADDS network-listening behavior (none — only egress) and OS-level isolation (systemd hardening). Auth/session/access-control mostly N/A; cryptography handled by underlying SDKs.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | partial | Anthropic + Telegram + Supabase + API-Football all use API keys read from `.env`. No new auth surface in Phase 4. |
| V3 Session Management | no | No web sessions; Telegram bot tokens are long-lived. |
| V4 Access Control | yes | systemd `User=bip` (non-root), `ProtectSystem=strict`, `ReadWritePaths=/var/run/bip` — least-privilege. `/etc/bip/.env` mode 600 owned by `bip:bip`. |
| V5 Input Validation | yes | `pydantic-settings` validators on `telegram_ops_channel_id` (mirrors D-13 pattern). Numeric Settings fields are float-typed. |
| V6 Cryptography | no | Never hand-rolled — TLS handled by `httpx`, Anthropic SDK, supabase-py. |
| V7 Error Handling | yes | structlog must NOT log API keys, channel IDs, or .env values. Verify by code review. |
| V8 Data Protection | yes | `.env` permissions 600 (root-owned dir, bip-owned file). `EnvironmentFile` injects to process env, never on disk image. |
| V9 Communication | yes | All outbound: HTTPS via `httpx`/SDKs. `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX` blocks raw sockets. |
| V12 File and Resources | yes | `ProtectSystem=strict`, `ReadWritePaths=/var/run/bip` only. No file uploads. |

### Known Threat Patterns for {APScheduler + Python service + Telegram bot + Postgres}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Secrets logged accidentally to journal | Information Disclosure | Code review checklist: structlog calls never include `*_key`, `*_token`, `.env` raw. |
| systemd watchdog DoS via blocking sync call in async loop | Denial of Service | Heartbeat is sync `Path.touch()` + sync `sdnotify.notify()` — both <1ms. AsyncIO loop never blocked. |
| Privilege escalation via setuid binary in `/opt/bip` | Elevation of Privilege | `NoNewPrivileges=true` blocks. |
| Telegram channel ID injection via env var | Spoofing | `_validate_ops_channel_id` requires `-100` prefix + min length. |
| Postgres SQL injection via `compute_period` parameters | Tampering | Supabase RPC parameters are bound, not interpolated. |
| Hung asyncio task → silent service unresponsiveness | DoS | `WatchdogSec=600` + `Restart=always` recovers within 10 min. |
| `/var/run/bip` mode-leak (other users read heartbeat) | Information Disclosure | `install -m 750`. Heartbeat file has no sensitive content; mode-750 is precaution. |
| API key leak via process list | Information Disclosure | Keys never on command line; `EnvironmentFile=` injects via env var only. |

## Sources

### Primary (HIGH confidence)
- [APScheduler 3.11.x AsyncIOScheduler docs](https://apscheduler.readthedocs.io/en/3.x/modules/schedulers/asyncio.html) — shutdown semantics, executor model
- [APScheduler 3.x User Guide](https://apscheduler.readthedocs.io/en/3.x/userguide.html) — coalesce, misfire_grace_time, MemoryJobStore behavior
- [APScheduler AsyncIOExecutor docs](https://apscheduler.readthedocs.io/en/3.x/modules/executors/asyncio.html) — async vs sync dispatch behavior
- [systemd sd_notify(3) man page](https://www.freedesktop.org/software/systemd/man/latest/sd_notify.html) — WATCHDOG=1 protocol
- [Python asyncio.loop.add_signal_handler docs](https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.add_signal_handler) — POSIX signal handling
- [PostgreSQL FILTER clause docs](https://www.postgresql.org/docs/current/sql-expressions.html#SYNTAX-AGGREGATES) — single-query aggregation
- [sdnotify on PyPI](https://pypi.org/project/sdnotify/) — version 0.3.2 verified
- [bb4242/sdnotify GitHub](https://github.com/bb4242/sdnotify) — API and source inspection

### Secondary (MEDIUM confidence — verified against authoritative source)
- [systemd Hardening (Arch Wiki)](https://wiki.archlinux.org/title/Systemd/Sandboxing) — directive safety
- [systemd Service Hardening (ageis gist)](https://gist.github.com/ageis/f5595e59b1cddb1513d1b425a323db04) — well-curated reference
- [Graceful Shutdowns with asyncio (Roguelynn)](https://roguelynn.com/words/asyncio-graceful-shutdowns/) — signal handler pattern
- [systemd Path Units (Putorius)](https://www.putorius.net/systemd-path-units.html) — path-based activation alternatives (rejected for this use case)
- [Pinnacle CLV variance discussion (sports-ai.dev)](https://www.sports-ai.dev/blog/closing-line-value-and-ai-model-performance) — variance characteristics of CLV
- [scipy.stats.ranksums docs](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ranksums.html) — v2 upgrade path

### Tertiary (LOW confidence — flagged for validation)
- [OneUptime systemd watchdog tutorial](https://oneuptime.com/blog/post/2026-03-04-set-up-systemd-watchdog-monitoring-for-critical-services/view) — secondary confirmation only

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified in `pyproject.toml`; sdnotify verified on PyPI.
- Architecture: HIGH — every integration point maps to existing code references.
- Heartbeat / WatchdogSec: HIGH — systemd man page is authoritative; the file-mtime design in CONTEXT.md is verifiably wrong.
- AsyncIOScheduler concurrency: HIGH — verified by docs.
- Drift method: MEDIUM — heavy-tail variance argument is sound but the 1.0pp floor and "daily means" choice are engineering judgments. Tunable.
- Postgres aggregation SQL: HIGH — `FILTER (WHERE ...)` since 9.4; LEFT JOIN behavior unambiguous.
- systemd hardening: HIGH on most directives; MEDIUM on `MemoryDenyWriteExecute=true` (smoke-test required).
- Pitfalls: HIGH — every pitfall traced to a documented source or codebase reference.

**Research date:** 2026-05-03
**Valid until:** 2026-06-02 (30 days; APScheduler 3.x is frozen, systemd is frozen, Postgres is stable — primary risk is `sdnotify` library if discontinued, but protocol is stable so even that's low risk)

---

## RESEARCH COMPLETE

**Phase:** 04 — production-orchestration
**Confidence:** HIGH overall.

### Key Findings
- The CONTEXT.md D-07 design ("WatchdogSec reads file mtime") is incorrect; `WatchdogSec=` requires `Type=notify` + `sd_notify("WATCHDOG=1")`. Recommendation: add `sdnotify==0.3.2` and three lines to the heartbeat tick. File-touch remains as a parallel signal for human ops.
- `AsyncIOScheduler.shutdown(wait=True)` waits for scheduler internals only, NOT for in-flight asyncio tasks — but the existing `_shutdown` flow is correct for this workload (no torn writes since DB calls are short).
- Drift D-14 soft gate (1.5 × stdev) is unstable at n=30 due to heavy-tailed CLV distribution. Recommendation: use stdev of daily-mean-CLV (n≈28) instead of per-pick CLV, and floor stdev at 1.0pp via new `Settings.drift_stdev_floor_pp`. v2 path: `scipy.stats.ranksums`.
- Postgres aggregation: `compute_period` requires a Supabase RPC function (Phase 4 migration 005) because PostgREST doesn't accept arbitrary SQL. LEFT JOIN on `clv_records` is mandatory (D-02 picks have no CLV row).
- `ClvTrendChecker.cooldown_until` dict is thread-safe under `AsyncIOScheduler` IF the check method is `async def` (single event loop thread). Document the constraint in code.
- All hardening directives in the recommended `bip.service` are safe for this workload, with one caveat: `MemoryDenyWriteExecute=true` should be smoke-tested in staging — drop only if any ML wheel import fails.

### File Created
`/Users/kevin_beltran/ProyectosPersonales/Sports_Betting/betting-intelligence-platform/.planning/phases/04-production-orchestration/04-RESEARCH.md`

### Confidence Assessment
| Area | Level | Reason |
|------|-------|--------|
| Standard Stack | HIGH | Every version verified in `pyproject.toml`; sdnotify verified on PyPI 2026-05. |
| Architecture | HIGH | Every integration point traces to a real file:line reference. |
| systemd / Watchdog integration | HIGH | Multiple authoritative sources confirm `WatchdogSec=` requires `sd_notify`. |
| Drift statistical method | MEDIUM | Engineering judgment on stdev floor; logically motivated but not benchmarked. |
| Postgres SQL shape | HIGH | `FILTER (WHERE ...)` is ANSI SQL since 9.4; behavior unambiguous. |
| Validation Architecture | HIGH | 24 distinct test cases mapped to phase requirements. |

### Open Questions
1. Two `TelegramSender` instances vs one with channel param (recommended: two — different rate-limiter buckets).
2. Whether to write a `drift_events` Supabase table (recommended: defer to v2 — Telegram + journald is sufficient).
3. Heartbeat log volume in journald (recommended: debug-level + once-per-hour summary).

### Ready for Planning
Research complete. Planner can now create PLAN.md files. Recommended plan structure (12-15 plans, 4-5 waves):

- Wave 0: stubs + migration 005 SQL function + new test files
- Wave 1: Settings extension + sdnotify dep + ops channel TelegramSender
- Wave 2: HeartbeatTicker + ClvTrendChecker + last_n_settled repo helper
- Wave 3: PerformanceMetricRepository.compute_period + MetricsAggregator + DriftChecker
- Wave 4: PickEngine D-01 branch + ClaudeValidator skip-mode + orchestrator job registration
- Wave 5: bip.production.__main__ + bip.production.builder + signal handlers
- Wave 6: deploy/systemd/bip.service + deploy/install.sh + deploy/tmpfiles.d/bip.conf + deploy README
- Wave 7: Phase 4 SC#1/SC#2 reconciliation in ROADMAP.md + manual smoke-test runbook
