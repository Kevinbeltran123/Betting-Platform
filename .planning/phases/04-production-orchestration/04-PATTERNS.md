# Phase 4: Production Orchestration — Pattern Map

**Mapped:** 2026-05-03
**Files analyzed:** 21 (12 NEW, 9 MODIFIED)
**Analogs found:** 19 / 21
**No-analog files:** 2 (`deploy/systemd/bip.service`, `deploy/tmpfiles.d/bip.conf` — first systemd assets in the repo; follow RESEARCH.md template).

## File Classification

### NEW Files

| New File | Role | Data Flow | Closest Analog | Match |
|----------|------|-----------|----------------|-------|
| `src/bip/production/__init__.py` | builder/factory | wiring | `src/bip/core/scheduler/orchestrator.py:41-63` (`__init__`) | role-match |
| `src/bip/production/__main__.py` | entrypoint | event-driven (asyncio) | `src/bip/train/__main__.py` (shape only) + `src/bip/core/telegram/bot.py` (asyncio app lifecycle) | partial |
| `src/bip/production/heartbeat.py` | service (sync tick) | event-driven (timer) | `src/bip/core/telegram/bot.py:20-58` (small class, structlog, init+method) | role-match |
| `src/bip/core/metrics/__init__.py` | barrel/public-api | n/a | `src/bip/core/storage/__init__.py` (if present) — fallback: empty re-exports per pattern | partial |
| `src/bip/core/metrics/aggregator.py` | service | CRUD + transform | `src/bip/clv/recorder.py:96-189` (`ClvRecorder`: dataclass-style class, repo-backed, structlog) | role-match |
| `src/bip/clv/trend_checker.py` | service | request-response (query + alert) | `src/bip/clv/recorder.py:96-189` (class wrapping a free function + repo) | exact |
| `supabase/migrations/005_compute_period_rpc.sql` | sql migration | DDL | `supabase/migrations/20260502000000_add_claude_validation_to_picks.sql` (BEGIN/COMMIT, IF NOT EXISTS, idempotent comments) | role-match |
| `deploy/systemd/bip.service` | systemd unit | OS supervision | none in repo | NO ANALOG (use RESEARCH.md §systemd Unit Hardening template) |
| `deploy/tmpfiles.d/bip.conf` | systemd config | OS bootstrap | none in repo | NO ANALOG (use RESEARCH.md §Deployment Runbook step 3) |
| `deploy/install.sh` | shell script | imperative install | none in repo | NO ANALOG (use RESEARCH.md §Deployment Runbook outline) |
| `tests/unit/production/test_heartbeat.py` | test (sync) | unit | `tests/telegram/test_bot.py` (small class init + mocks) | exact |
| `tests/unit/production/test_builder.py` | test | unit | `tests/scheduler/test_orchestrator.py:16-42` (`_make_orchestrator` with MagicMock wiring) | exact |
| `tests/unit/production/test_main.py` | test (async) | unit | `tests/claude/test_validator.py:52-100` (async test + monkeypatch) | exact |
| `tests/unit/clv/test_trend_checker.py` | test | unit | `tests/test_clv_recorder.py:69-78` (rolling-avg test) + `tests/picks/test_engine.py` (async + mocks) | exact |
| `tests/unit/metrics/test_aggregator.py` | test | unit | `tests/test_repositories.py` (PerformanceMetric + setup_mock_chain) | exact |
| `tests/unit/metrics/test_drift.py` | test | unit | `tests/test_clv_recorder.py:69-100` (numeric helper functions) | exact |
| `tests/unit/picks/test_engine_claude_failure.py` | test (async) | unit | `tests/picks/test_engine.py:104-120` (`_make_engine` factory) | exact |
| `tests/unit/telegram/test_routing.py` | test | unit | `tests/telegram/test_bot.py` | exact |
| `tests/integration/test_metrics_aggregator_idempotent.py` | test | integration | `tests/test_repositories.py` (Supabase mock fluent chain via `setup_mock_chain`) | partial |
| `tests/integration/test_compute_period_rpc.py` | test | integration | `tests/test_repositories.py` + `setup_mock_chain` for `.rpc()` (no existing `.rpc` test — extend pattern) | partial |

### MODIFIED Files

| Modified File | Role | Data Flow | What Changes | Pattern Source |
|---------------|------|-----------|--------------|----------------|
| `src/bip/core/settings.py` | settings | config | +8 fields, +1 validator | `src/bip/core/settings.py:29-58` (existing `_validate_channel_id`) |
| `src/bip/core/storage/repositories.py` | repository | CRUD | +`PerformanceMetricRepository.compute_period()` | `repositories.py:376-389` (`upsert`) + RPC client call |
| `src/bip/core/scheduler/orchestrator.py` | scheduler | event-driven | +4 cron-job registrations in `start()`, +structlog event in `_auto_recover` | `orchestrator.py:65-81` (existing `start()`) |
| `src/bip/core/claude/validator.py` | service | request-response | +`mode` parameter / SKIPPED return path | `validator.py:91-137` (existing retry) |
| `src/bip/core/picks/engine.py` | service | request-response | branch on `settings.claude_failure_mode` at line 115-116 | `engine.py:115-116` (existing filter) |
| `src/bip/clv/recorder.py` | service | CRUD | (optional) re-export `compute_rolling_clv_average` | `recorder.py:78-93` (already public) |
| `src/bip/core/telegram/bot.py` (or sender.py) | service | one-way push | accept `channel_id` param OR allow second instance | `bot.py:23-35` (existing single-channel init) |
| `pyproject.toml` | config | dependency | +`sdnotify==0.3.2` | `pyproject.toml:10-34` (existing pinned dep list) |
| `tests/conftest.py` | test fixtures | fixture | +`mock_sd_notify`, +`mock_ops_telegram_sender`, +`tmp_heartbeat_path` | `conftest.py:171-182` (existing `mock_telegram_bot`) |

---

## Pattern Assignments — NEW Files

### `src/bip/production/__init__.py` (builder/factory)

**Analog:** `src/bip/core/scheduler/orchestrator.py` (`__init__` wiring shape) + `src/bip/clv/recorder.py:103-104` (small public class).

**Why this analog:** `PipelineOrchestrator.__init__` already does *exactly* the wiring this builder must do — gather optional dependencies and assign them to fields. The builder is the inverse: gather settings, *construct* the dependencies, hand back the orchestrator.

**Imports pattern** (mirror `orchestrator.py:1-22`):
```python
from __future__ import annotations

import structlog
from supabase import create_client

from bip.clv.client import OddsApiClient
from bip.clv.recorder import ClvRecorder
from bip.clv.trend_checker import ClvTrendChecker
from bip.core.claude.validator import ClaudeValidator
from bip.core.metrics.aggregator import MetricsAggregator
from bip.core.picks.engine import PickEngine
from bip.core.scheduler.orchestrator import PipelineOrchestrator
from bip.core.settings import Settings
from bip.core.storage.repositories import PerformanceMetricRepository, PickRepository
from bip.core.telegram.bot import TelegramBot
from bip.core.telegram.sender import TelegramSender

logger = structlog.get_logger(__name__)
```

**Construction pattern** (mirror the `__init__` field-assignment shape from `orchestrator.py:41-63` but flipped — return a tuple of constructed deps):
```python
def build_orchestrator(settings: Settings) -> tuple[PipelineOrchestrator, TelegramBot, TelegramBot, "sdnotify.SystemdNotifier"]:
    """Build a fully-wired orchestrator + the two TelegramBots + the sd_notifier.

    Returned tuple is consumed by __main__.main() which owns the asyncio lifecycle.
    Tests call this with a hand-built Settings(_env_file=None, ...) and assert on
    the wiring (not behavior).
    """
    import sdnotify  # local import keeps unit tests under macOS clean

    client = create_client(settings.supabase_url, settings.supabase_key)
    pick_repo = PickRepository(client=client)
    perf_repo = PerformanceMetricRepository(client=client)

    picks_bot = TelegramBot(token=settings.telegram_bot_token,
                            channel_id=settings.telegram_channel_id)
    ops_bot = TelegramBot(token=settings.telegram_bot_token,
                          channel_id=settings.telegram_ops_channel_id)
    picks_sender = TelegramSender(bot=picks_bot)
    ops_sender = TelegramSender(bot=ops_bot)

    odds_client = OddsApiClient(api_key=settings.odds_api_key)
    clv_recorder = ClvRecorder(client=client)
    # ... validator + pick engine + plugin (omitted — same shape) ...

    metrics_aggregator = MetricsAggregator(perf_repo=perf_repo, pick_repo=pick_repo)
    clv_trend_checker = ClvTrendChecker(
        client=client,
        ops_sender=ops_sender,
        threshold=settings.clv_trend_alert_threshold,
        cooldown_hours=settings.clv_trend_cooldown_hours,
    )

    sd_notifier = sdnotify.SystemdNotifier()

    orchestrator = PipelineOrchestrator(
        plugin=plugin,
        settings=settings,
        pick_engine=pick_engine,
        pick_repo=pick_repo,
        telegram_bot=picks_bot,
        odds_api_client=odds_client,
        clv_recorder=clv_recorder,
        # NEW Phase 4 wiring (planner adds these kwargs to __init__):
        metrics_aggregator=metrics_aggregator,
        clv_trend_checker=clv_trend_checker,
        ops_sender=ops_sender,
        heartbeat_path=settings.heartbeat_file_path,
        sd_notifier=sd_notifier,
    )
    logger.info("build_orchestrator_complete",
                heartbeat_path=settings.heartbeat_file_path,
                ops_channel_set=bool(settings.telegram_ops_channel_id))
    return orchestrator, picks_bot, ops_bot, sd_notifier
```

---

### `src/bip/production/__main__.py` (entrypoint)

**Analogs:**
- `src/bip/train/__main__.py` (entrypoint shape — only 6 lines, just delegates)
- `src/bip/core/telegram/bot.py:37-45` (asyncio app `start()`/`shutdown()` pattern)
- RESEARCH.md Pattern 1 (verbatim — copy this)

**Why these analogs:** `bip/train/__main__.py` is the *only* existing `__main__.py` in the repo, and it deliberately keeps logic in a CLI module (`bip.train.cli`). For Phase 4 the logic must live here per D-05; the asyncio lifecycle pattern comes from RESEARCH §Pattern 1, lifted into the production-shape.

**Existing analog code** (`src/bip/train/__main__.py`, full file):
```python
"""Entry point for `python -m bip.train`."""

from bip.train.cli import app

if __name__ == "__main__":
    app()
```

**Imports + main pattern to copy** (RESEARCH.md §Pattern 1 — already verified against `docs.python.org` + `roguelynn.com`):
```python
"""Entry point for `python -m bip.production` (D-05).

systemd unit ExecStart points here. SIGTERM handled via asyncio signal handler
fanning out to scheduler.shutdown(wait=True) + telegram_bot.shutdown() per
RESEARCH §Pitfall 2 (in-flight async tasks must drain).
"""
from __future__ import annotations

import asyncio
import signal

import structlog

from bip.core.settings import Settings
from bip.production import build_orchestrator

logger = structlog.get_logger(__name__)


async def main() -> None:
    settings = Settings()  # raises ValidationError on missing required env

    orchestrator, picks_bot, ops_bot, sd_notifier = build_orchestrator(settings)

    await picks_bot.start()
    await ops_bot.start()
    orchestrator.start()  # registers all scheduled jobs

    sd_notifier.notify("READY=1")  # critical for Type=notify
    logger.info("production_started")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig,
            lambda s=sig: asyncio.create_task(
                _shutdown(s, stop_event, orchestrator, picks_bot, ops_bot)
            ),
        )
    await stop_event.wait()


async def _shutdown(sig, stop_event, orch, picks_bot, ops_bot) -> None:
    logger.info("shutdown_started", signal=sig.name)
    orch.shutdown()  # sync — calls scheduler.shutdown(wait=True) at orchestrator.py:572-574
    await picks_bot.shutdown()
    await ops_bot.shutdown()
    stop_event.set()
    logger.info("shutdown_complete")


if __name__ == "__main__":
    asyncio.run(main())
```

**Critical details (verbatim from RESEARCH §Pattern 1):**
- `loop.add_signal_handler` (NOT `signal.signal` — sync handler can't await).
- `orchestrator.shutdown()` is sync and stays that way. Don't `await` it.
- `sdnotify.SystemdNotifier().notify("READY=1")` after scheduler is up — this is what tells systemd `Type=notify` startup is complete.

---

### `src/bip/production/heartbeat.py` (service)

**Analog:** `src/bip/core/telegram/bot.py:20-58` (small dataclass-style class with init + one-method API + structlog event).

**Why:** `TelegramBot` is the closest existing class shape — minimal init, single behavior method, structlog at the boundary. `HeartbeatTicker` follows the exact same shape.

**Existing analog code** (`src/bip/core/telegram/bot.py:20-35`):
```python
class TelegramBot:
    """Outbound-only Telegram bot owned by PipelineOrchestrator for the process lifetime."""

    def __init__(self, token: str, channel_id: str) -> None:
        if not token:
            raise TelegramError("telegram_bot_token is empty — set TELEGRAM_BOT_TOKEN in .env")
        if not channel_id:
            raise TelegramError("telegram_channel_id is empty — set TELEGRAM_CHANNEL_ID in .env")
        self._channel_id = channel_id
        self._app: Application = (
            ApplicationBuilder().token(token).rate_limiter(AIORateLimiter(max_retries=3)).build()
        )
```

**Pattern to mimic** (lifted verbatim from RESEARCH §Pattern 2 — `sdnotify` + `Path.touch`):
```python
"""HeartbeatTicker (D-07).

Touches Settings.heartbeat_file_path every 5 min AND sends WATCHDOG=1 on the
systemd notify socket (D-06 with Type=notify + WatchdogSec=600).

The file mtime is for human/external observers (`stat -c %Y heartbeat`); the
sdnotify call is what systemd's WatchdogSec= actually consumes (RESEARCH
§Heartbeat & Watchdog Integration).
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

import structlog

logger = structlog.get_logger(__name__)


class _Notifier(Protocol):
    def notify(self, msg: str) -> bool: ...  # sdnotify.SystemdNotifier shape


class HeartbeatTicker:
    """File-touch + systemd watchdog notification for a process supervised by systemd."""

    def __init__(self, path: str | Path, notifier: _Notifier) -> None:
        self._path = Path(path)
        self._notifier = notifier  # sdnotify.SystemdNotifier — silently no-ops on macOS

    def tick(self) -> None:
        """Run on APScheduler IntervalTrigger(minutes=5). Sync — fine in AsyncIOExecutor."""
        self._path.touch()
        self._notifier.notify("WATCHDOG=1")
        logger.debug("heartbeat", path=str(self._path))
```

**Drift risk:** Test must inject the `_Notifier` (use the `mock_sd_notify` fixture) — never instantiate `sdnotify.SystemdNotifier()` directly inside `HeartbeatTicker` (CLAUDE.md mock-data convention).

---

### `src/bip/clv/trend_checker.py` (service)

**Analog:** `src/bip/clv/recorder.py:96-189` (`ClvRecorder` — class wrapping a free function + repo + structlog).

**Why:** Identical shape: a stateful class that holds a Supabase client, calls a pure helper (`compute_rolling_clv_average` already at `recorder.py:78-93`), formats a structlog event. Add a cooldown dict and an ops-sender call; that's the only delta.

**Existing analog code** (`src/bip/clv/recorder.py:103-189`):
```python
class ClvRecorder:
    def __init__(self, client: Client) -> None:
        self._repo = ClvRecordRepository(client=client)

    def record(self, pick_id: int, fixture_id: int, ..., selection: str, ...) -> ClvRecord:
        ...
        try:
            self._repo.insert(clv_record)
        except Exception as exc:
            raise ClvError(f"Failed to record CLV for pick_id={pick_id}: {exc}") from exc

        logger.info("clv_recorded", pick_id=pick_id, fixture_id=fixture_id, ...)
        return clv_record
```

**Pattern to mimic** (apply same shape; cooldown is the only new state):
```python
"""ClvTrendChecker (CLV-03 — D-09 through D-12).

Hourly cron wrapper around bip.clv.recorder.compute_rolling_clv_average.
Queries last 50 settled CLV values, alerts ops channel when rolling avg <
Settings.clv_trend_alert_threshold. 12h in-memory cooldown per scope.

Cooldown dict is touched only from the asyncio event loop (declare check()
async to make this guarantee explicit — RESEARCH §CLV Trend Cooldown).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from supabase import Client

from bip.clv.recorder import compute_rolling_clv_average

logger = structlog.get_logger(__name__)


class ClvTrendChecker:
    def __init__(
        self,
        client: Client,
        ops_sender: Any,
        threshold: float = 1.0,
        cooldown_hours: int = 12,
    ) -> None:
        self._client = client
        self._ops_sender = ops_sender
        self._threshold = threshold
        self._cooldown = timedelta(hours=cooldown_hours)
        self._last_alert: dict[str, datetime] = {}  # key: f"{scope}:{market}"

    async def check(self) -> None:
        """Run hourly. Global rolling-50 + per-market rolling-50 (when ≥50 picks).
        D-10: per-market only when sample is large enough — no false-alarm noise.
        """
        try:
            global_vals = self._fetch_recent_clv(market=None)
        except Exception as exc:
            logger.error("clv_trend_query_failed", error=str(exc))
            return

        if global_vals:
            await self._maybe_alert(scope="global", market=None, values=global_vals)
        # ... per-market loop omitted ...

    async def _maybe_alert(self, scope: str, market: str | None, values: list[float]) -> None:
        avg = compute_rolling_clv_average(values)
        key = f"{scope}:{market or '*'}"
        now = datetime.now(UTC)
        last = self._last_alert.get(key)
        if last is not None and now - last < self._cooldown:
            logger.info("clv_trend_in_cooldown", scope=scope, market=market, avg=avg)
            return
        if avg < self._threshold:
            suffix = f" [market: {market}]" if market else ""
            text = f"⚠️ CLV +{avg:.1f}% < +{self._threshold:.0f}% threshold{suffix}"
            await self._ops_sender.send_html(text)  # mirrors TelegramBot.send_html
            self._last_alert[key] = now
            logger.info("clv_trend_alert_fired", scope=scope, market=market, avg=avg)

    def _fetch_recent_clv(self, market: str | None) -> list[float]:
        # SELECT clv_percentage FROM clv_records WHERE pinnacle_closing_odds IS NOT NULL
        # ORDER BY created_at DESC LIMIT 50; project to list[float] (oldest-first
        # is irrelevant for rolling average).
        ...
```

**Drift risk:** Cooldown key must include `*` for the global scope (otherwise the `:None` stringification leaks Python repr into the dict key — this matches D-11 which says `f"{scope}:{market}"`).

---

### `src/bip/core/metrics/__init__.py` (barrel)

**Analog:** existing `bip.core.types` style — just re-export.

**Pattern to copy:**
```python
"""Phase 4 metrics public API (D-15).

Sport-agnostic per CORE-02. Functions take `sport` as a parameter; never branch on it.
"""
from bip.core.metrics.aggregator import (
    DriftResult,
    MetricsAggregator,
    compute_daily_metrics,
    compute_weekly_drift,
)

__all__ = [
    "DriftResult",
    "MetricsAggregator",
    "compute_daily_metrics",
    "compute_weekly_drift",
]
```

---

### `src/bip/core/metrics/aggregator.py` (service)

**Analog:** `src/bip/clv/recorder.py:78-189` (`compute_rolling_clv_average` free function + `ClvRecorder` class — same dual shape this file needs: pure functions PLUS a class that holds repos).

**Why:** D-15 says "pure functions", and there's a Phase-4 class wrapper too. `recorder.py` is the closest precedent: a free `compute_rolling_clv_average` + a `ClvRecorder` class with `client`-typed init.

**Pattern to mimic** (combining `recorder.py` shape with RESEARCH §Drift Statistical Method):

```python
"""MetricsAggregator + drift compute (D-13/D-14/D-15/D-16).

D-13: daily cron computes/upserts metrics for all four periods in one pass.
D-14: weekly drift compares 4-week rolling-mean CLV vs prior 4-week mean.
D-16: aggregator pushes math to Postgres via PerformanceMetricRepository.compute_period;
      drift check uses Polars over rows fetched via PickRepository + ClvRecordRepository.

Sport-agnostic per CORE-02 — every public function takes `sport` as a parameter.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import polars as pl
import structlog

from bip.core.storage.models import PerformanceMetric
from bip.core.storage.repositories import (
    ClvRecordRepository,
    PerformanceMetricRepository,
    PickRepository,
)
from bip.core.types import AggregationPeriod

logger = structlog.get_logger(__name__)


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
    delta_pp: float
    stdev_pp: float
    triggered_hard: bool
    triggered_soft: bool

    @property
    def triggered(self) -> bool:
        return self.triggered_hard or self.triggered_soft


def compute_daily_metrics(
    perf_repo: PerformanceMetricRepository,
    sport: str,
    league: str,
    market: str,
    today: date,
) -> list[PerformanceMetric]:
    """Compute and return PerformanceMetric for daily/weekly/monthly/all_time.

    Caller is responsible for upserting (this stays pure for testability — D-15).
    """
    out: list[PerformanceMetric] = []
    for period, start, end in _period_ranges(today):
        m = perf_repo.compute_period(sport=sport, league=league, market=market,
                                     period=period, period_start=start, period_end=end)
        out.append(m)
    return out


class MetricsAggregator:
    """Orchestrator-facing class. Iterates over (sport, league, market) and upserts."""

    def __init__(self, perf_repo: PerformanceMetricRepository,
                 pick_repo: PickRepository) -> None:
        self._perf_repo = perf_repo
        self._pick_repo = pick_repo

    async def run(self, today: date | None = None) -> int:
        today = today or datetime.now(UTC).date()
        # ... discover (sport, league, market) tuples from picks; for v1 = football/<league>/onextwo ...
        upserted = 0
        for sport, league, market in self._discover_tuples():
            metrics = compute_daily_metrics(self._perf_repo, sport, league, market, today)
            for m in metrics:
                self._perf_repo.upsert(m)  # idempotent on (sport,league,market,period,period_start)
                upserted += 1
        logger.info("metrics_aggregation_complete", upserted=upserted, date=today.isoformat())
        return upserted
```

**`compute_weekly_drift` shape:** lifted verbatim from RESEARCH §Drift Statistical Method (already validated). Apply daily-mean-CLV stdev with `drift_stdev_floor_pp = 1.0` floor.

---

### `supabase/migrations/005_compute_period_rpc.sql` (sql migration)

**Analog:** `supabase/migrations/20260502000000_add_claude_validation_to_picks.sql` (verified header style + BEGIN/COMMIT atomic-wrap).

**Why:** It's the most recent migration and uses the exact patterns required: `IF NOT EXISTS`, BEGIN/COMMIT, idempotency comments, references to D-numbers and PITFALLS.md. Phase 4's RPC migration must keep the same shape.

**Imports/preamble pattern** (mirror `migration 004` lines 1-22):
```sql
-- Migration 005: compute_performance_period(...) RPC for D-16 single-round-trip aggregation.
--
-- Implements D-16 (Phase 4): one Supabase round trip per (sport, league, market) period
-- replaces N application-level queries. Required because the supabase-py SDK does NOT
-- expose arbitrary SELECT — only .table().select() (PostgREST) or .rpc(name, params).
-- A Postgres function is the supported path for SELECT count(*) FILTER (WHERE ...) with
-- LEFT JOIN on clv_records.
--
-- INNER JOIN on clv_records is INCORRECT — picks where Odds API failed (D-02 path) have
-- NO clv_records row; INNER JOIN silently drops them and ROI under-reports
-- (RESEARCH §Pitfall 3). LEFT JOIN keeps them; AVG(c.clv_percentage) ignores NULLs natively.
--
-- Idempotent: CREATE OR REPLACE FUNCTION. Atomic: BEGIN/COMMIT.

BEGIN;
```

**Body pattern** (use the SQL from RESEARCH §Pattern 4 verbatim — already verified — wrapped as a `LANGUAGE sql` function):

```sql
CREATE OR REPLACE FUNCTION compute_performance_period(
    p_sport  text,
    p_league text,
    p_market text,
    p_start  timestamptz,
    p_end    timestamptz
)
RETURNS TABLE (
    total_picks  bigint,
    won          bigint,
    lost         bigint,
    void         bigint,
    total_staked double precision,
    total_pnl    double precision,
    roi          double precision,
    avg_clv      double precision,
    avg_edge     double precision
)
LANGUAGE sql STABLE AS $$
    SELECT
        COUNT(*)                                          AS total_picks,
        COUNT(*) FILTER (WHERE p.status = 'won')          AS won,
        COUNT(*) FILTER (WHERE p.status = 'lost')         AS lost,
        COUNT(*) FILTER (WHERE p.status IN ('void','push')) AS void,
        COALESCE(SUM(p.suggested_stake), 0)               AS total_staked,
        COALESCE(SUM(
            CASE p.status
                WHEN 'won'  THEN p.suggested_stake * (p.best_odds - 1)
                WHEN 'lost' THEN -p.suggested_stake
                ELSE 0
            END
        ), 0)                                             AS total_pnl,
        SUM(
            CASE p.status
                WHEN 'won'  THEN p.suggested_stake * (p.best_odds - 1)
                WHEN 'lost' THEN -p.suggested_stake
                ELSE 0
            END
        ) / NULLIF(SUM(p.suggested_stake), 0)             AS roi,
        AVG(c.clv_percentage)                             AS avg_clv,
        AVG(p.edge)                                       AS avg_edge
    FROM picks p
    LEFT JOIN clv_records c ON c.pick_id = p.id
    WHERE p.sport     = p_sport
      AND p.league    = p_league
      AND p.market    = p_market
      AND p.created_at >= p_start
      AND p.created_at <  p_end
      AND p.status NOT IN ('filtered', 'rejected', 'pending');
$$;

COMMIT;
```

**Filename convention** — existing migrations use `YYYYMMDDhhmmss_<name>.sql`. The CONTEXT lists this as `005_compute_period_rpc.sql`; planner should rename to match the timestamp pattern actually used (`2026MMDDhhmmss_compute_period_rpc.sql`) for consistency.

---

### `deploy/systemd/bip.service` — NO ANALOG

No systemd unit exists in the repo. **Use RESEARCH.md §systemd Unit Hardening verbatim** — that template is already verified against `archlinux.org/wiki/systemd/Sandboxing` and `freedesktop.org/software/systemd/man`. Critical lines:

```ini
[Service]
Type=notify              # NOT simple — required for WatchdogSec
NotifyAccess=main        # required so sdnotify from main process is accepted
WatchdogSec=600          # 10 min — gives 2x margin on 5-min heartbeat
EnvironmentFile=/etc/bip/.env
ExecStart=/opt/bip/.venv/bin/python -m bip.production
Restart=always
RestartSec=10
ReadWritePaths=/var/run/bip
```

**Drift risk:** `Type=simple` + `WatchdogSec=` is silently broken (RESEARCH §Pitfall 1).

---

### `deploy/tmpfiles.d/bip.conf` — NO ANALOG

```
d /var/run/bip 0750 bip bip - -
```

Single line; no analog needed. Loaded by `systemd-tmpfiles --create` at boot so `/var/run/bip/` survives reboots (it's tmpfs).

---

### `deploy/install.sh` — NO ANALOG

No shell scripts in the repo. **Use RESEARCH.md §Deployment Runbook outline verbatim** (7 sequential steps; each step is `[ … ] || …` style idempotent; never overwrite `/etc/bip/.env`). Pattern is shellcheck-clean — quoted vars, `set -euo pipefail` at the top.

---

### Test files (NEW)

| Test | Analog | Lines/symbols to copy |
|------|--------|------------------------|
| `tests/unit/production/test_heartbeat.py` | `tests/telegram/test_bot.py:9-44` | `class TestBotInit` shape, init-validation, mock-injection |
| `tests/unit/production/test_builder.py` | `tests/scheduler/test_orchestrator.py:16-42` (`_make_orchestrator`) | factory + MagicMock wiring + assertion that all dependencies are constructed |
| `tests/unit/production/test_main.py` | `tests/claude/test_validator.py:53-100` (`@pytest.mark.asyncio` + `monkeypatch.setattr`) | async test that monkey-patches `signal.SIGTERM` handler |
| `tests/unit/clv/test_trend_checker.py` | `tests/test_clv_recorder.py:69-100` (rolling avg) + `tests/picks/test_engine.py` (async + mocks) | numeric assertion + cooldown-state assertion |
| `tests/unit/metrics/test_aggregator.py` | `tests/test_repositories.py` (`TestPerformanceMetricRepository`) + `setup_mock_chain` | `setup_mock_chain` for repo, `MetricsAggregator.run()` happy path |
| `tests/unit/metrics/test_drift.py` | `tests/test_clv_recorder.py:69-100` (numeric helpers) | `pl.DataFrame` fixtures, hard/soft trigger boundary cases, stdev floor case |
| `tests/unit/picks/test_engine_claude_failure.py` | `tests/picks/test_engine.py:104-125` (`_make_engine`) | invoke `evaluate(...)` with `claude_verdict=None` under both `claude_failure_mode='filter'` and `'skip'` settings |
| `tests/unit/telegram/test_routing.py` | `tests/telegram/test_bot.py` | two-channel sender wiring + which channel each message routes to |
| `tests/integration/test_metrics_aggregator_idempotent.py` | `tests/test_repositories.py` | call `aggregator.run()` twice, assert second call upserts (not inserts) |
| `tests/integration/test_compute_period_rpc.py` | `tests/test_repositories.py` (extend with `.rpc()`) | `mock_client.rpc().execute()` chain — mirror `setup_mock_chain` shape |

**Common test pattern** (mirrors `tests/picks/test_engine.py:104-125`):

```python
def _make_<thing>(...):
    repo = MagicMock()
    repo.insert = MagicMock(return_value={"id": 999})

    sender = MagicMock()
    sender.send_html = AsyncMock()

    return SubjectUnderTest(repo=repo, sender=sender, ...)


@pytest.mark.asyncio
async def test_happy_path(...):
    s = _make_<thing>()
    await s.method()
    sender.send_html.assert_awaited_once()
```

---

## Pattern Assignments — MODIFIED Files

### `src/bip/core/settings.py` (settings)

**Analog:** itself — `Settings._validate_channel_id` at lines 39-58 + the `Phase 3 additions` block at lines 25-37.

**Existing pattern to copy** (lines 29-58):
```python
# ─────────────────────────────────────────────────────
# Phase 3 additions (D-13, RESEARCH §Standard Stack)
# PATTERNS.md drift risk #3: append flat fields to existing class — NO per-feature settings classes.
# ─────────────────────────────────────────────────────
telegram_channel_id: str = ""              # D-13: -100<id> format; validated below
anthropic_api_key: str = ""
claude_model: str = "claude-sonnet-4-6"
max_kelly_fraction: float = 0.25

@field_validator("telegram_channel_id")
@classmethod
def _validate_channel_id(cls, v: str) -> str:
    if v == "":
        return v
    if not v.startswith("-100"):
        raise ValueError(...)
    if len(v) < 8:
        raise ValueError(...)
    return v
```

**Phase 4 extension** (mirror exact shape — append a Phase 4 block, validator named `_validate_ops_channel_id`):
```python
# ─────────────────────────────────────────────────────
# Phase 4 additions (D-01, D-03, D-07, D-09–D-12, D-14)
# PATTERNS.md drift risk #3: flat fields, NO per-feature settings classes.
# ─────────────────────────────────────────────────────
claude_failure_mode: Literal["filter", "skip"] = "filter"  # D-01
telegram_ops_channel_id: str = ""                          # D-03
heartbeat_file_path: str = "/var/run/bip/heartbeat"        # D-07
clv_trend_alert_threshold: float = 1.0                     # D-09
clv_trend_cooldown_hours: int = 12                         # D-11
drift_check_min_picks_per_window: int = 30                 # D-14
drift_absolute_threshold_pp: float = 2.0                   # D-14
drift_stdev_multiplier: float = 1.5                        # D-14
drift_stdev_floor_pp: float = 1.0                          # RESEARCH §Drift Statistical Method

@field_validator("telegram_ops_channel_id")
@classmethod
def _validate_ops_channel_id(cls, v: str) -> str:
    # Mirror _validate_channel_id (Pitfall 8). Empty default allowed.
    if v == "":
        return v
    if not v.startswith("-100"):
        raise ValueError(
            f"telegram_ops_channel_id must start with '-100' (got {v!r})."
        )
    if len(v) < 8:
        raise ValueError(
            f"telegram_ops_channel_id appears truncated (got {v!r})."
        )
    return v
```

**Required new import:** add `from typing import Literal` to the top.

**Drift risk:** Don't introduce a `Phase4Settings` subclass — D-15/CONTEXT explicitly forbids per-feature settings classes ("PATTERNS.md drift risk #3: append flat fields").

---

### `src/bip/core/storage/repositories.py` (repository)

**Analog:** `PerformanceMetricRepository.upsert` at lines 376-389 (existing repo method).

**Existing analog code** (lines 370-389):
```python
@dataclass
class PerformanceMetricRepository:
    client: Client

    def upsert(self, metric: PerformanceMetric) -> dict:
        try:
            response = (
                self.client.table("performance_metrics")
                .upsert(metric.to_supabase_dict(), on_conflict="league,market,period,period_start")
                .execute()
            )
            return response.data[0]
        except Exception as e:
            raise StorageError(f"Failed to upsert into performance_metrics: {e}") from e
```

**New `compute_period` method to add** (mirrors error-handling shape exactly; uses `.rpc()` per RESEARCH §Pattern 4 / Pitfall 5):
```python
def compute_period(
    self,
    sport: str,
    league: str,
    market: str,
    period: AggregationPeriod,   # already imported via models
    period_start: date,
    period_end: date,
) -> PerformanceMetric:
    """D-16: single Supabase round trip for one (sport,league,market) over a window.

    Calls Postgres function compute_performance_period(p_sport,p_league,p_market,p_start,p_end)
    added by migration 005. LEFT JOIN on clv_records — picks with no CLV row (D-02 Odds API
    failure path) are still counted; AVG ignores NULL clv_percentage (Pitfall 3).
    """
    try:
        response = self.client.rpc(
            "compute_performance_period",
            {
                "p_sport":  sport,
                "p_league": league,
                "p_market": market,
                "p_start":  datetime.combine(period_start, time.min, tzinfo=UTC).isoformat(),
                "p_end":    datetime.combine(period_end,   time.min, tzinfo=UTC).isoformat(),
            },
        ).execute()
    except Exception as e:
        raise StorageError(
            f"Failed compute_performance_period(sport={sport},league={league},market={market}): {e}"
        ) from e

    row = response.data[0] if response.data else {}
    return PerformanceMetric(
        sport=sport, league=league, market=market,
        period=period, period_start=period_start, period_end=period_end,
        total_picks=int(row.get("total_picks") or 0),
        won=int(row.get("won") or 0),
        lost=int(row.get("lost") or 0),
        void=int(row.get("void") or 0),
        total_staked=float(row.get("total_staked") or 0.0),
        total_pnl=float(row.get("total_pnl") or 0.0),
        roi=float(row["roi"]) if row.get("roi") is not None else None,
        yield_pct=(float(row["roi"]) * 100.0) if row.get("roi") is not None else None,
        avg_clv=float(row["avg_clv"]) if row.get("avg_clv") is not None else None,
        avg_edge=float(row["avg_edge"]) if row.get("avg_edge") is not None else None,
    )
```

**Required new imports** (top of file): `from datetime import UTC, date, datetime, time` + ensure `AggregationPeriod` is in scope.

---

### `src/bip/core/scheduler/orchestrator.py` (scheduler — extend `start()`)

**Analog:** lines 65-81 (existing two `add_job` calls + `scheduler.start()` + structlog event).

**Existing analog code** (lines 65-81):
```python
def start(self) -> None:
    self.scheduler.add_job(
        self._daily_orchestrator,
        trigger=CronTrigger(hour=6, minute=0, timezone="UTC"),
        id="daily_orchestrator",
        replace_existing=True,
    )

    self.scheduler.add_job(
        self._reconcile_clv,
        trigger=CronTrigger(hour=3, minute=0, timezone="UTC"),
        id="nightly_clv_reconciliation",
        replace_existing=True,
    )

    self.scheduler.start()
    logger.info("scheduler_started", jobs=len(self.scheduler.get_jobs()))
```

**Phase 4 extension — append four `add_job` calls before `scheduler.start()`** (each with `coalesce=True` + `misfire_grace_time` per RESEARCH §APScheduler 3.x Operational Knobs):
```python
# Phase 4 — heartbeat (D-07)
self.scheduler.add_job(
    self._heartbeat_ticker.tick,
    trigger=IntervalTrigger(minutes=5),  # add IntervalTrigger import
    id="heartbeat",
    replace_existing=True,
    coalesce=True,
    misfire_grace_time=60,
)

# Phase 4 — CLV trend (D-09)
self.scheduler.add_job(
    self._check_clv_trend,
    trigger=CronTrigger(minute=0, timezone="UTC"),
    id="clv_trend",
    replace_existing=True,
    coalesce=True,
    misfire_grace_time=600,
)

# Phase 4 — metrics aggregator (D-13)
self.scheduler.add_job(
    self._aggregate_metrics,
    trigger=CronTrigger(hour=23, minute=0, timezone="UTC"),
    id="metrics_aggregator",
    replace_existing=True,
    coalesce=True,
    misfire_grace_time=600,
)

# Phase 4 — weekly drift (D-14)
self.scheduler.add_job(
    self._check_drift,
    trigger=CronTrigger(day_of_week='mon', hour=6, minute=0, timezone="UTC"),
    id="weekly_drift",
    replace_existing=True,
    coalesce=True,
    misfire_grace_time=600,
)
```

**Required new imports:** `from apscheduler.triggers.interval import IntervalTrigger`.

**Required new `__init__` kwargs:** `metrics_aggregator: Any | None = None`, `clv_trend_checker: Any | None = None`, `ops_sender: Any | None = None`, `heartbeat_path: str | None = None`, `sd_notifier: Any | None = None` (mirror the existing `Any | None = None` shape from lines 41-52).

**Required new methods on the orchestrator** (`_check_clv_trend`, `_aggregate_metrics`, `_check_drift`) — each is a thin async wrapper that delegates to the injected service and `logger.info("<event_name>_complete", ...)` per repo convention. Pattern from `_record_clv` at lines 306-455 (long body) but each is much shorter.

**`_auto_recover` augmentation (D-08)** — append `logger.info("auto_recover_complete", jobs_re_queued=requeued)` after the existing `logger.info("auto_recover_requeued", count=requeued, scanned=len(pending))` at line 138.

---

### `src/bip/core/claude/validator.py` (service — `mode='skip'` branch)

**Analog:** itself — lines 91-137 (existing `validate` retry loop).

**Existing analog code** (lines 91-137):
```python
async def validate(self, pick_summary: str, curated_signals: str) -> ClaudeVerdict | None:
    for attempt in range(2):
        try:
            msg = await self._client.messages.create(...)
            tool_block = next(c for c in msg.content if c.type == "tool_use")
            return ClaudeVerdict(**tool_block.input)
        except (RateLimitError, APIError) as exc:
            logger.warning("claude_validator_failed", attempt=attempt, ...)
            if attempt == 0:
                await asyncio.sleep(60)
    logger.error("claude_validator_unavailable", attempts=2, ...)
    return None
```

**Modification (D-01):** keep the existing return-`None`-after-2-attempts behavior — the engine's branch at `engine.py:115-116` is the *single* place that decides between filter and skip based on `settings.claude_failure_mode`. The validator itself does NOT need a new code path; the contract stays "returns `None` on terminal failure".

**Alternative if the planner prefers a marker return value:** add a `SKIPPED` sentinel `ClaudeVerdict(verdict="SKIPPED", reason_code="claude_api_unavailable", reasoning="", summary="")`. This keeps verdict-typing tighter but requires `ClaudeVerdict.verdict` enum to admit `"SKIPPED"` (already permitted in DB CHECK constraint per migration 004 line 51) and the Pydantic regex pattern in `validator.py:28` to broaden. **Recommendation:** stay with `None` return; branch in engine.

---

### `src/bip/core/picks/engine.py` (engine — branch on `claude_failure_mode`)

**Analog:** itself — lines 113-116 (existing filter call).

**Existing analog code** (lines 113-128):
```python
verdict = await self._validator.validate(pick_summary, curated_signals)

if verdict is None:
    return self._persist_filtered(prediction, opening_odds, "claude_api_unavailable")

if verdict.verdict == "REJECT":
    return self._persist_rejected(...)

pick = self._persist_pending(...)
send_at = deterministic_send_at(datetime.now(UTC), fixture_id)
self._schedule_send(pick, prediction, send_at)
return pick
```

**Modification (D-01):**
```python
verdict = await self._validator.validate(pick_summary, curated_signals)

if verdict is None:
    if self._settings.claude_failure_mode == "filter":
        return self._persist_filtered(prediction, opening_odds, "claude_api_unavailable")
    # claude_failure_mode == "skip": persist pending + send with SKIPPED marker.
    skipped = ClaudeVerdict(
        verdict="SKIPPED",
        reason_code="claude_api_unavailable",
        reasoning="",
        summary="",  # template renders 🤖❌ marker when claude_validation == 'SKIPPED'
    )
    pick = self._persist_pending(prediction, opening_odds, selection, idx, edge,
                                 kelly_fraction, stake, skipped)
    send_at = deterministic_send_at(datetime.now(UTC), fixture_id)
    self._schedule_send(pick, prediction, send_at)
    return pick
```

**Required new import:** `from bip.core.claude.validator import ClaudeVerdict` (already imported at line 29).

**Required template change:** the Telegram pick template (`bip/core/telegram/templates/pick.html`) must render the `🤖❌` marker when `claude_validation == 'SKIPPED'` (D-01). Mirror the existing FLAG branch (D-14, sender.py).

**Drift risk:** `_persist_pending` currently asserts a non-`SKIPPED` verdict implicitly via the unconditional `claude_validation = verdict.verdict` assignment at engine.py:173 — no change required, but the test must construct a `ClaudeVerdict(verdict="SKIPPED", ...)` and confirm it round-trips into `pick.claude_validation`.

---

### `src/bip/clv/recorder.py` (re-export only)

**Analog:** itself.

**Modification:** the `compute_rolling_clv_average` free function at lines 78-93 is already module-level and importable as `from bip.clv.recorder import compute_rolling_clv_average`. **No changes needed** — `ClvTrendChecker` imports it directly. The CONTEXT line "expose `compute_rolling_clv_average` for the trend checker (or keep import as-is)" resolves as **keep import as-is**.

---

### `src/bip/core/telegram/bot.py` + `src/bip/core/telegram/sender.py` (two-channel)

**Analog:** existing `TelegramBot.__init__` at `bot.py:23-35` + `TelegramSender.__init__` at `sender.py:61-62`.

**Existing analog code** (`bot.py:23-35`):
```python
def __init__(self, token: str, channel_id: str) -> None:
    if not token:
        raise TelegramError("telegram_bot_token is empty — set TELEGRAM_BOT_TOKEN in .env")
    if not channel_id:
        raise TelegramError("telegram_channel_id is empty — set TELEGRAM_CHANNEL_ID in .env")
    self._channel_id = channel_id
    ...
```

**D-03 Implementation choice (planner picks):**

**Option A (recommended — two instances):** instantiate `TelegramBot(token, settings.telegram_channel_id)` AND `TelegramBot(token, settings.telegram_ops_channel_id)` in `build_orchestrator`. Wrap each in a `TelegramSender`. Pass `picks_sender` to `PickEngine`, pass `ops_sender` to `ClvTrendChecker` + drift check + (future) ops alerts. **No code changes to `bot.py` or `sender.py` required.**

**Option B (one instance with channel param):** widen `TelegramBot.send_html(text)` → `TelegramBot.send_html(text, channel_id=None)` defaulting to the configured channel. **Adds branching that Option A avoids.**

**Recommendation: Option A.** It mirrors the existing `TelegramBot` shape exactly — one bot per channel — and lets the validator at `settings.py:39-58` enforce both channel IDs uniformly.

---

### `pyproject.toml` (config)

**Analog:** itself — line 28 (`"python-telegram-bot[rate-limiter]==22.7"`).

**Modification:** append `"sdnotify==0.3.2"` to the `dependencies` list at lines 10-34 (alphabetical-ish; group with other infra: between `python-telegram-bot` and `jinja2` is fine, or end-of-list). RESEARCH already verified version 0.3.2 against PyPI.

---

### `tests/conftest.py` (fixtures)

**Analog:** existing fixtures `mock_telegram_bot` (lines 171-182) and `settings` (lines 35-47).

**Existing analog code** (lines 171-182):
```python
@pytest.fixture
def mock_telegram_bot():
    """Returns a MagicMock with .send_html as AsyncMock that records calls."""
    from unittest.mock import AsyncMock, MagicMock
    bot = MagicMock()
    bot.send_html = AsyncMock()
    return bot
```

**Phase 4 fixtures to add:**
```python
@pytest.fixture
def mock_sd_notify():
    """Returns a MagicMock matching sdnotify.SystemdNotifier (.notify(msg) -> bool)."""
    from unittest.mock import MagicMock
    n = MagicMock()
    n.notify = MagicMock(return_value=True)
    return n


@pytest.fixture
def mock_ops_telegram_sender():
    """Returns a MagicMock with .send_html as AsyncMock — the ops-channel sender."""
    from unittest.mock import AsyncMock, MagicMock
    s = MagicMock()
    s.send_html = AsyncMock()
    return s


@pytest.fixture
def tmp_heartbeat_path(tmp_path):
    """Returns Path under tmp_path for HeartbeatTicker tests; the file does not pre-exist."""
    return tmp_path / "heartbeat"
```

**Settings fixture extension** (mirror `settings` fixture at lines 35-47):
```python
# Add to existing fixture:
monkeypatch.setenv("TELEGRAM_OPS_CHANNEL_ID", "-1009876543210")
# Phase 4 fields all have sensible defaults per Settings — no other env mods needed.
```

---

## Shared Patterns

### Authentication / API-key handling

**Source:** `src/bip/core/settings.py` (pydantic-settings + `.env`).
**Apply to:** All Phase 4 modules. NEVER read `os.environ` directly — pull from `settings: Settings` parameter.

### Error handling

**Source:** `src/bip/core/storage/repositories.py:33-43` (every repo method's try/except → wrap-and-raise pattern).
**Apply to:** `PerformanceMetricRepository.compute_period`, any new RPC calls.
```python
try:
    response = self.client.<call>(...).execute()
    return response.data[0]
except Exception as e:
    raise StorageError(f"Failed <op> on <table>: {e}") from e
```

### Structlog event naming

**Source:** every `logger.info(...)` call across the codebase (e.g., `orchestrator.py:81 "scheduler_started"`, `recorder.py:177 "clv_recorded"`, `engine.py:138 "pick_filtered"`, `validator.py:114 "claude_validator_success"`).

**Convention (CONTEXT.md §code_context line 202):** snake_case, past tense for completed work, present tense for in-flight. **All Phase 4 events use `logger.info("event_name", **kwargs)` with keyword args.**

**Phase 4 event names to use (CONTEXT.md §code_context line 199):**
- `heartbeat` (debug level — see D-discretion bullet)
- `clv_trend_check`, `clv_trend_alert_fired`, `clv_trend_in_cooldown`
- `metrics_aggregation_complete`
- `drift_check_complete`, `drift_alert_fired`
- `auto_recover_complete` (D-08)
- `production_started`, `shutdown_started`, `shutdown_complete`
- `build_orchestrator_complete`

### APScheduler 3.x knob set

**Source:** `orchestrator.py:204-222` (existing CLV + reconcile job registrations) + RESEARCH §APScheduler 3.x Operational Knobs.
**Apply to:** All four new `add_job` calls in `start()`.
```python
self.scheduler.add_job(
    callback,
    trigger=<Cron|Interval>Trigger(...),
    id="<unique_id>",
    replace_existing=True,    # idempotent re-registration
    coalesce=True,            # collapse missed runs
    misfire_grace_time=600,   # 60 for IntervalTrigger heartbeat; 600 for daily/weekly
)
```

### Repository constructor shape

**Source:** `src/bip/core/storage/repositories.py:27-31` (`@dataclass` with `client: Client`).
**Apply to:** Any new repo, but Phase 4 reuses `PerformanceMetricRepository` only.

### Pydantic Settings extension

**Source:** `src/bip/core/settings.py:39-58` (single `@field_validator` decorator, `@classmethod`, `if v == "": return v` empty-default short-circuit).
**Apply to:** New `_validate_ops_channel_id`. Mirror the exact early-return-on-empty pattern.

### Test factory function

**Source:** `tests/picks/test_engine.py:104-125` (`_make_engine`) + `tests/scheduler/test_orchestrator.py:16-42` (`_make_orchestrator`).
**Apply to:** All Phase 4 tests. Each test module exposes a `_make_<subject>(...)` factory that wires MagicMocks and returns the SUT. The test then tweaks one mock and asserts.

### Async test pattern

**Source:** `tests/claude/test_validator.py:53-100` (`@pytest.mark.asyncio` + `monkeypatch.setattr` + `AsyncMock`).
**Apply to:** Tests for `ClvTrendChecker.check`, `MetricsAggregator.run`, `bip.production.__main__.main`, the engine's claude-failure path.

---

## No Analog Found

| File | Role | Why no analog | Source to use |
|------|------|---------------|---------------|
| `deploy/systemd/bip.service` | systemd unit | First systemd asset in this repo | RESEARCH.md §systemd Unit Hardening (verified template) |
| `deploy/tmpfiles.d/bip.conf` | tmpfiles spec | First tmpfiles spec in this repo | RESEARCH.md §Deployment Runbook step 3 |
| `deploy/install.sh` | shell installer | First shell script in this repo | RESEARCH.md §Deployment Runbook (7-step outline) |

For these three, planner uses the RESEARCH-provided patterns instead of in-repo analogs. All three are validated against external sources (`freedesktop.org`, `archlinux.org/wiki/systemd/Sandboxing`).

---

## Metadata

**Analog search scope:** `src/bip/`, `tests/`, `supabase/migrations/`, `pyproject.toml` (full repo, depth 4).
**Files scanned:** ~25 source files; 8 test files; 4 SQL migrations; 1 pyproject.
**Pattern extraction date:** 2026-05-03.

## PATTERN MAPPING COMPLETE
