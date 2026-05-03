"""APScheduler 3.x pipeline orchestrator.

CRITICAL: Uses APScheduler 3.x API (AsyncIOScheduler + add_job).
Do NOT use 4.x API (AsyncScheduler + add_schedule) — APScheduler 4.x is still alpha.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from bip.core.errors import SchedulerError
from bip.core.settings import Settings
from bip.core.storage.models import PickStatus
from bip.sports import SportPlugin

logger = structlog.get_logger(__name__)


class PipelineOrchestrator:
    """Orchestrates the full betting intelligence pipeline using APScheduler 3.x."""

    # D-16 status code groups (RESEARCH "API-Football Status Codes" + Risk 9)
    _STATUS_SETTLED_REGULATION = frozenset({"FT", "AWD", "WO"})
    _STATUS_SETTLED_REGULATION_PLUS_ET = frozenset({"AET"})
    _STATUS_SETTLED_PEN = frozenset({"PEN"})
    _STATUS_VOID = frozenset({"PST", "CANC", "ABD"})
    _STATUS_IN_PLAY = frozenset({"1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT"})
    _STATUS_NOT_STARTED = frozenset({"TBD", "NS"})
    _RECONCILE_MAX_RETRIES = 4

    def __init__(
        self,
        plugin: SportPlugin,
        settings: Settings | None = None,
        pick_engine: Any | None = None,
        pick_repo: Any | None = None,
        telegram_bot: Any | None = None,
        api_football_client: Any | None = None,
    ) -> None:
        self.plugin = plugin
        self.settings = settings
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self._today_jobs_registered = False
        self.pick_engine = pick_engine
        self.pick_repo = pick_repo
        self.telegram_bot = telegram_bot
        self._api_client = api_football_client

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

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._auto_recover())
        except RuntimeError:
            pass

    async def _auto_recover(self) -> None:
        """Auto-recovery on startup — re-register fixture jobs + re-queue lost send jobs (Pitfall 6)."""
        now = datetime.now(UTC)
        today_start = now.replace(hour=6, minute=0, second=0, microsecond=0)

        if now < today_start:
            logger.info("auto_recovery_skipped", reason="before_06:00_UTC")
        else:
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

        # Pitfall 6: re-queue lost send jobs
        if self.pick_repo is None or self.pick_engine is None:
            logger.info("auto_recovery_skipped_pending_sends", reason="pick_repo_or_engine_unwired")
            return

        try:
            pending = self.pick_repo.query_pending_sends(sport="football", max_age_minutes=30)
        except Exception as exc:
            logger.error("auto_recover_pending_sends_query_failed", error=str(exc))
            return

        requeued = 0
        existing_send_ids = {j.id for j in self.scheduler.get_jobs()
                             if j.id and j.id.startswith("send_pick_")}
        for row in pending:
            job_id = f"send_pick_{row['fixture_id']}_{row['market']}"
            if job_id in existing_send_ids:
                continue
            self.scheduler.add_job(
                self._send_recovered_pick,
                trigger=DateTrigger(run_date=datetime.now(UTC)),
                args=[row],
                id=job_id,
                replace_existing=True,
                misfire_grace_time=300,
            )
            requeued += 1
        logger.info("auto_recover_requeued", count=requeued, scanned=len(pending))

    async def _send_recovered_pick(self, row: dict) -> None:
        """Pitfall 6 recovery dispatch — re-build a Pick from the DB row and send."""
        if self.telegram_bot is None:
            logger.error("recovered_pick_send_failed", reason="telegram_bot_unwired")
            return
        from bip.core.storage.models import Pick
        from bip.core.telegram.sender import render_pick

        pick = Pick.model_validate(row)
        home = row.get("home_team", "Home")
        away = row.get("away_team", "Away")
        version = row.get("model_version", "unknown")
        text = render_pick(pick, home, away, version, reason_code=None)
        try:
            await self.telegram_bot.send_html(text)
            logger.info("recovered_pick_sent", fixture_id=pick.fixture_id, market=pick.market)
        except Exception as exc:
            logger.error("recovered_pick_send_failed", fixture_id=pick.fixture_id,
                         market=pick.market, error=str(exc))

    async def _daily_orchestrator(self) -> None:
        now = datetime.now(UTC)
        logger.info("daily_orchestrator_started", date=now.date().isoformat())

        try:
            fixtures = await self.plugin.get_fixtures(date=now)
        except Exception as exc:
            logger.error("get_fixtures_failed", error=str(exc))
            raise SchedulerError(f"Daily orchestrator failed: {exc}") from exc

        # Each fixture gets: T-2h, T-30min, T+105min (CLV snapshot), T+150min (reconcile) DateTrigger jobs
        for fixture in fixtures:
            self._register_fixture_jobs(fixture, now)

        logger.info("daily_orchestrator_completed", fixture_count=len(fixtures))

    def _register_fixture_jobs(self, fixture: object, now: datetime) -> None:
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

        # D-16: result reconciliation at kickoff + 150min
        t_plus_150 = kickoff + timedelta(minutes=150)
        if t_plus_150 > now:
            self.scheduler.add_job(
                self._reconcile_results,
                trigger=DateTrigger(run_date=t_plus_150),
                args=[fixture],
                id=f"reconcile_{fixture_id}",
                replace_existing=True,
                misfire_grace_time=600,
            )

    async def _run_pipeline(self, fixture: object, stage: str) -> None:
        """Run prediction pipeline for a fixture at the specified stage.

        Phase 3 hook: PickEngine.evaluate at t_minus_2h + t_minus_30m.
        D-01: T-30min skips evaluate when a (fixture_id, market='1X2') pick is already
        PickStatus.pending — without this guard, every successful T-2h pick fires a
        duplicate alert at T-30min.
        """
        fixture_id = fixture.fixture_id  # type: ignore[attr-defined]
        logger.info("pipeline_started", fixture_id=fixture_id, stage=stage)
        try:
            await self.plugin.build_features(fixture)  # type: ignore[arg-type]

            if self.pick_engine is not None and stage in ("t_minus_2h", "t_minus_30m"):
                if stage == "t_minus_30m":
                    # D-01 dup-alert guard (Blocker #1)
                    existing = await self.pick_repo.get_pending_for_fixture(fixture.fixture_id)  # type: ignore[attr-defined]
                    blocking = [p for p in existing
                                if getattr(p, "market", None) == "1X2"
                                and getattr(p, "status", None) == PickStatus.pending]
                    if blocking:
                        logger.info(
                            "t30_skipped_pending_already",
                            fixture_id=fixture.fixture_id,  # type: ignore[attr-defined]
                            t2h_pick_id=blocking[0].id,
                        )
                        return

                try:
                    prob_map = await self.plugin.predict(fixture, market="1X2")  # type: ignore[attr-defined]
                    if prob_map is None:
                        logger.info("pipeline_skip_evaluate_no_prediction",
                                    fixture_id=fixture_id, stage=stage)
                    else:
                        opening_odds = await self.plugin.get_opening_odds(  # type: ignore[attr-defined]
                            fixture.fixture_id  # type: ignore[attr-defined]
                        )
                        await self.pick_engine.evaluate(prob_map, opening_odds)
                except AttributeError:
                    logger.warning("pipeline_evaluate_unsupported", fixture_id=fixture_id, stage=stage)

            logger.info("pipeline_completed", fixture_id=fixture_id, stage=stage)
        except Exception as exc:
            logger.error("pipeline_failed", fixture_id=fixture_id, stage=stage, error=str(exc))

    async def _record_clv(self, fixture: object) -> None:
        fixture_id = fixture.fixture_id  # type: ignore[attr-defined]
        logger.info("clv_snapshot_triggered", fixture_id=fixture_id)

    async def _reconcile_clv(self) -> None:
        logger.info("clv_reconciliation_started")

    async def _reconcile_results(self, fixture: object, retries: int = 0) -> None:
        """D-16: settle pending picks based on API-Football status.

        All 16 status codes handled (Risk 9). Pitfall 7 reschedule on in-play, max 4 retries.
        Q3 RESOLVED: after 4 retries, log structlog.ERROR event=reconcile_abandoned.
        """
        fixture_id = fixture.fixture_id  # type: ignore[attr-defined]
        if self._api_client is None or self.pick_repo is None:
            logger.error("reconcile_unwired", fixture_id=fixture_id,
                         missing="api_client" if self._api_client is None else "pick_repo")
            return

        try:
            raw = await self._api_client.get_fixture(fixture_id)
        except Exception as exc:
            logger.error("reconcile_api_failed", fixture_id=fixture_id, error=str(exc))
            return

        item = raw["response"][0] if raw and raw.get("response") else None
        if item is None:
            logger.error("reconcile_no_response", fixture_id=fixture_id)
            return

        status = item["fixture"]["status"]["short"]
        logger.info("reconcile_started", fixture_id=fixture_id, status=status, retries=retries)

        if status in self._STATUS_VOID:
            n = self.pick_repo.update_status_by_fixture(fixture_id, "void")
            logger.info("reconcile_voided", fixture_id=fixture_id, status=status, count=n)
            return

        if status in self._STATUS_IN_PLAY or status in self._STATUS_NOT_STARTED:
            if retries >= self._RECONCILE_MAX_RETRIES:
                logger.error(
                    "reconcile_abandoned",
                    fixture_id=fixture_id,
                    status=status,
                    retries=retries,
                    note="max 4 reschedule attempts reached — leaving picks pending for manual review (Q3)",
                )
                return
            self.scheduler.add_job(
                self._reconcile_results,
                trigger=DateTrigger(run_date=datetime.now(UTC) + timedelta(minutes=30)),
                args=[fixture, retries + 1],
                id=f"reconcile_{fixture_id}",
                replace_existing=True,
                misfire_grace_time=600,
            )
            logger.info("reconcile_rescheduled", fixture_id=fixture_id, status=status,
                        retries=retries + 1)
            return

        home = item["goals"]["home"]
        away = item["goals"]["away"]

        if home is None or away is None:
            logger.error("reconcile_missing_goals", fixture_id=fixture_id, status=status,
                         home=home, away=away)
            return

        if status in self._STATUS_SETTLED_PEN:
            actual = "X"
            push_market = True
        elif status in (self._STATUS_SETTLED_REGULATION | self._STATUS_SETTLED_REGULATION_PLUS_ET):
            actual = "1" if home > away else ("2" if away > home else "X")
            push_market = False
        else:
            logger.error("reconcile_unknown_status", fixture_id=fixture_id, status=status,
                         note="leaving picks pending for manual review (Risk 9)")
            return

        pending = self.pick_repo.get_pending_for_fixture(fixture_id)
        settled = 0
        for pick in pending:
            if pick.get("market") != "1X2":
                continue
            if push_market:
                new_status = "push"
            else:
                new_status = "won" if pick["selection"] == actual else "lost"
            self.pick_repo.update_status(pick["id"], new_status)
            settled += 1
        logger.info("reconcile_settled", fixture_id=fixture_id, status=status, count=settled)

    def get_registered_jobs(self) -> list:
        return self.scheduler.get_jobs()

    def shutdown(self) -> None:
        self.scheduler.shutdown(wait=True)
        logger.info("scheduler_stopped")
