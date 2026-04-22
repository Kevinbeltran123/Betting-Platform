"""APScheduler 3.x pipeline orchestrator.

CRITICAL: Uses APScheduler 3.x API (AsyncIOScheduler + add_job).
Do NOT use 4.x API (AsyncScheduler + add_schedule) — APScheduler 4.x is still alpha.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from bip.core.errors import SchedulerError
from bip.core.settings import Settings
from bip.sports import SportPlugin

logger = structlog.get_logger(__name__)


class PipelineOrchestrator:
    """Orchestrates the full betting intelligence pipeline using APScheduler 3.x.

    Job schedule:
    - 06:00 UTC daily: Fetch fixtures + register per-fixture jobs (D-03a)
    - 03:00 UTC daily: Reconcile missing CLV records (D-04b)
    - T-2h per fixture: Data refresh + prediction
    - T-30min per fixture: Lineup-adjusted re-prediction
    - T+105min per fixture: CLV snapshot (D-04a)
    """

    def __init__(self, plugin: SportPlugin, settings: Settings | None = None) -> None:
        self.plugin = plugin
        self.settings = settings
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self._today_jobs_registered = False

    def start(self) -> None:
        """Start the scheduler with daily + nightly jobs.

        Triggers auto-recovery on startup (D-03b).
        """
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

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._auto_recover())
        except RuntimeError:
            pass  # No running event loop (e.g., during unit tests)

    async def _auto_recover(self) -> None:
        """Auto-recovery on startup — re-register today's fixture jobs if missing.

        D-03b: On VPS restart between 06:00 UTC and last kickoff of the day,
        immediately re-run the daily orchestrator to register jobs for
        fixtures that haven't yet kicked off.
        """
        now = datetime.now(UTC)
        today_start = now.replace(hour=6, minute=0, second=0, microsecond=0)

        if now < today_start:
            logger.info("auto_recovery_skipped", reason="before_06:00_UTC")
            return

        existing_fixture_jobs = [
            j for j in self.scheduler.get_jobs()
            if j.id not in {"daily_orchestrator", "nightly_clv_reconciliation"}
        ]

        if not existing_fixture_jobs:
            logger.info("auto_recovery_triggered", reason="no_fixture_jobs_found")
            await self._daily_orchestrator()
        else:
            logger.info(
                "auto_recovery_skipped",
                reason="jobs_already_registered",
                count=len(existing_fixture_jobs),
            )

    async def _daily_orchestrator(self) -> None:
        """Fetch today's fixtures and register per-fixture DateTrigger jobs.

        Called at 06:00 UTC (CronTrigger) and during auto-recovery.
        """
        now = datetime.now(UTC)
        logger.info("daily_orchestrator_started", date=now.date().isoformat())

        try:
            fixtures = await self.plugin.get_fixtures(date=now)
        except Exception as exc:
            logger.error("get_fixtures_failed", error=str(exc))
            raise SchedulerError(f"Daily orchestrator failed: {exc}") from exc

        # Each fixture gets: T-2h, T-30min, T+105min (CLV snapshot) DateTrigger jobs
        for fixture in fixtures:
            self._register_fixture_jobs(fixture, now)

        logger.info("daily_orchestrator_completed", fixture_count=len(fixtures))

    def _register_fixture_jobs(self, fixture: object, now: datetime) -> None:
        """Register 3 DateTrigger jobs for a single fixture.

        Jobs:
        - T-2h: data refresh + prediction
        - T-30min: lineup-adjusted re-prediction
        - T+105min: CLV snapshot
        """
        kickoff = fixture.kickoff_utc  # type: ignore[attr-defined]
        fixture_id = fixture.fixture_id  # type: ignore[attr-defined]

        t_minus_2h = kickoff - timedelta(hours=2)
        if t_minus_2h > now:
            self.scheduler.add_job(
                self._run_pipeline,
                trigger=DateTrigger(run_date=t_minus_2h),
                args=[fixture, "t_minus_2h"],
                id=f"pipeline_{fixture_id}_t_minus_2h",
                replace_existing=True,
            )

        t_minus_30m = kickoff - timedelta(minutes=30)
        if t_minus_30m > now:
            self.scheduler.add_job(
                self._run_pipeline,
                trigger=DateTrigger(run_date=t_minus_30m),
                args=[fixture, "t_minus_30m"],
                id=f"pipeline_{fixture_id}_t_minus_30m",
                replace_existing=True,
            )

        t_plus_105m = kickoff + timedelta(minutes=105)
        if t_plus_105m > now:
            self.scheduler.add_job(
                self._record_clv,
                trigger=DateTrigger(run_date=t_plus_105m),
                args=[fixture],
                id=f"clv_{fixture_id}_t_plus_105m",
                replace_existing=True,
            )

    async def _run_pipeline(self, fixture: object, stage: str) -> None:
        """Run prediction pipeline for a fixture at the specified stage.

        Phase 1: builds features only.
        Phase 2 (ML Core) adds real prediction.
        Phase 3 (Pick Engine) adds EV filter + Telegram.
        """
        fixture_id = fixture.fixture_id  # type: ignore[attr-defined]
        logger.info("pipeline_started", fixture_id=fixture_id, stage=stage)
        try:
            await self.plugin.build_features(fixture)  # type: ignore[arg-type]
            logger.info("pipeline_completed", fixture_id=fixture_id, stage=stage)
        except Exception as exc:
            logger.error("pipeline_failed", fixture_id=fixture_id, stage=stage, error=str(exc))

    async def _record_clv(self, fixture: object) -> None:
        """CLV snapshot job — runs at kickoff + 105 minutes.

        Phase 1: Stub. Full implementation in Phase 3 (needs pick_id from picks table).
        Logs that CLV recording was triggered.
        """
        fixture_id = fixture.fixture_id  # type: ignore[attr-defined]
        logger.info("clv_snapshot_triggered", fixture_id=fixture_id)

    async def _reconcile_clv(self) -> None:
        """Nightly CLV reconciliation — refetch missing Pinnacle closing odds.

        D-04b: At 03:00 UTC, queries clv_records WHERE pinnacle_closing_odds IS NULL
        and re-fetches via OddsApiClient. Covers extra-time edge cases.
        """
        logger.info("clv_reconciliation_started")

    def get_registered_jobs(self) -> list:
        """Return all currently registered APScheduler jobs (D-03b auto-recovery check)."""
        return self.scheduler.get_jobs()

    def shutdown(self) -> None:
        """Graceful scheduler shutdown."""
        self.scheduler.shutdown(wait=True)
        logger.info("scheduler_stopped")
