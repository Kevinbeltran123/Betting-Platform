"""Dual-write runtime — v3 shadow co-execution alongside v2.

T1.3 of v3 phase-4 readiness mission. v3 runs concurrently with v2 in
watch.py's scan loop but is **structurally isolated** so a v3 hang,
crash, or slow-path cannot affect v2's path to the Telegram operator.

# Isolation choice

Of the four alternatives in the mission spec:

- **(a) inline sync try/except** — too coupled: a 5-second hang in v3
  stalls the entire per-fixture pipeline of v2.
- **(b) asyncio.to_thread + timeout** — CHOSEN. watch.py is already
  asyncio-native; the pattern is one ``await`` line. The v3 pipeline
  is synchronous CPU work so ``to_thread`` is the correct primitive
  (event-loop never blocks). A wall-clock timeout aborts hangs without
  needing process boundaries.
- **(c) thread pool + queue** — over-engineered: the v3 work per
  fixture is bounded, no batching needed, no need for a dedicated
  worker pool.
- **(d) multiprocessing.Queue** — IPC overhead + deployment complexity
  for marginal extra isolation. The thread already prevents v3
  exceptions from raising into v2.

Net effect of (b):

  - v3 exceptions: caught, counted in ``error_count``, never propagated.
  - v3 hang > ``timeout_sec``: cancelled (the thread is left to finish
    in the background but the await returns; the next call gets a
    fresh attempt). Counted as an error.
  - v3 success: ShadowLogger writes its own buffers. Zero contact with
    PickTracker, TelegramSender, or any v2 sink.
  - v3 disabled (``V3_SHADOW_ENABLED=false`` or kill-switch file
    present): the dual-write call returns ``False`` cheaply.

# Kill switch

The kill switch is a filesystem flag at
``data/cache/v3_shadow/v3_kill_switch.flag``. Either:

- ``kill_criteria.evaluate_cohort`` returns a hard-stop verdict and
  the operator writes the flag, OR
- ``shadow_metrics_report.py`` runs (weekly cron) and decides the
  cohort verdict + writes the flag.

The runtime checks the flag on every ``run_shadow`` call; presence
short-circuits without calling V3Pipeline. Removing the flag re-enables
v3 immediately on the next iteration.

# Disabling without redeploy

The env var ``V3_SHADOW_ENABLED`` (default ``true``) is checked on
every call. Setting it to ``false`` (or ``0``, ``no``, ``off``) skips
v3 work entirely. This is the operator's manual override; the kill
switch is the automated equivalent.

# Monitoring v3 errors

``DualWriteRuntime.error_count`` is exposed as a property. watch.py
should log it once per iteration when nonzero. Searching production
logs for ``event="v3_shadow_error"`` returns each individual failure
with reason.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from bip.evaluation.live.engine_v3 import (
    ConditionalPredictor,
    MarketLine,
    MarketSnapshot,
    OODDetector,
    PatternLayer,
    PipelineOutput,
    PreMatchPriors,
    ShadowLogger,
    V3Pipeline,
)
from bip.evaluation.live.engine_v3.runtime.live_observer import (
    LivePickObserver,
    NullObserver,
)
from bip.evaluation.live.engine_v3.runtime.telegram_adapter import (
    shadow_pick_to_live_pick,
)
from bip.evaluation.live.engine_v3.shadow_logger import DEFAULT_SHADOW_ROOT
from bip.evaluation.live.match_state import LiveMatchState

log = logging.getLogger("v3.dual_write")

DEFAULT_KILL_SWITCH_PATH = DEFAULT_SHADOW_ROOT / "v3_kill_switch.flag"
DEFAULT_V3_TIMEOUT_SEC = 0.8  # 800ms — matches mission spec ceiling
def _pick_ood_default() -> Path:
    """Prefer the v2 detector (fitted on 1642 real Day-3 GSVs, 1% skip
    rate) over the v1 synthetic-fit detector (99% skip rate). If neither
    exists, return the v2 path so the absent-pkl warning fires on the
    "correct" default."""
    v2 = Path("data/cache/ood_detector_v2_real.pkl")
    v1 = Path("data/cache/ood_detector_v1.pkl")
    return v2 if v2.exists() else (v1 if v1.exists() else v2)


DEFAULT_OOD_PKL = _pick_ood_default()
DEFAULT_PATTERN_PKL = Path("data/cache/pattern_layer_v1.pkl")
DEFAULT_CALIBRATOR_PKL = Path("data/cache/isotonic_calibrator_v1.pkl")
DEFAULT_V2_PICKS_PARQUET = Path(
    "reports/sportmonks_live/exports/picks_graded.parquet"
)

_TRUE_STRINGS = {"1", "true", "yes", "on", "y", "t"}
_FALSE_STRINGS = {"0", "false", "no", "off", "n", "f"}


def is_v3_shadow_enabled(env_var: str = "V3_SHADOW_ENABLED") -> bool:
    """Read the env-var override. Default is ``True`` when unset.

    Accepts case-insensitive ``true/false/1/0/yes/no/on/off``. Anything
    else falls back to ``True`` (fail-open for typos so the operator
    notices via logs rather than silent dis-shadow).
    """
    raw = os.environ.get(env_var, "true").strip().lower()
    if raw in _FALSE_STRINGS:
        return False
    if raw in _TRUE_STRINGS:
        return True
    log.warning(
        "v3_shadow_enabled_unparseable env=%s value=%r — defaulting to true",
        env_var,
        raw,
    )
    return True


def is_v3_kill_switch_engaged(path: Path = DEFAULT_KILL_SWITCH_PATH) -> bool:
    """Returns ``True`` if the kill-switch flag file exists.

    Cheap stat() call — safe to invoke on every fixture in watch.py.
    """
    try:
        return path.exists()
    except OSError:
        # Defensive: if the FS is in a weird state, treat as engaged
        # (fail-closed) so we don't accidentally keep emitting picks.
        return True


# ──────────────────────────────────────────────────────────────────────
# Adapters: watch.py inputs → v3 inputs
# ──────────────────────────────────────────────────────────────────────


def derive_priors_from_fixture(fixture) -> PreMatchPriors:
    """Best-effort priors from Sportmonks predictions, mirror of
    ``replay_shadow.derive_priors_from_predictions`` for parity.

    Returns neutral defaults if predictions are absent or malformed —
    v3 doesn't crash, it just makes weaker thesis claims.
    """
    lam_h = 1.35
    lam_a = 1.15
    for p in getattr(fixture, "predictions", None) or []:
        if p.type_id != 240 or not p.predictions:
            continue
        scores = p.predictions.get("scores") if isinstance(p.predictions, dict) else None
        if not isinstance(scores, dict):
            continue
        e_h = e_a = 0.0
        total = 0.0
        for k, v in scores.items():
            if not isinstance(k, str) or k == "other":
                continue
            try:
                h_str, a_str = k.split("-")
                h, a = int(h_str), int(a_str)
                w = float(v) / 100.0
            except (TypeError, ValueError):
                continue
            e_h += h * w
            e_a += a * w
            total += w
        if total > 0:
            lam_h = e_h / total
            lam_a = e_a / total
        break
    return PreMatchPriors(
        lambda_home_prematch=lam_h,
        lambda_away_prematch=lam_a,
    )


def market_snapshot_from_odds(odds, captured_at: datetime) -> MarketSnapshot:
    """Convert a Sportmonks ``list[Odd]`` to a v3 ``MarketSnapshot``.

    Same heuristic mapping as ``replay_shadow._build_market_id``: we
    concatenate ``description`` + ``label`` + ``total`` into a
    namespace-style id (``match_corners_over_10.5``,
    ``both_teams_to_score_yes``). The downstream
    ``family_for_market_id`` is the canonical resolver.

    For Phase-1 we cap ``max_stake_cap`` at 1.0 — replay_shadow
    convention. Phase 2 will wire real caps from Sportmonks when emitted.
    """
    lines: dict[str, MarketLine] = {}
    for o in odds or []:
        desc = (getattr(o, "market_description", None) or "").strip().lower()
        label = (getattr(o, "label", None) or "").strip().lower()
        value = getattr(o, "value", None) or getattr(o, "decimal", None)
        if not desc or value is None:
            continue
        try:
            decimal = float(value)
        except (TypeError, ValueError):
            continue
        if decimal <= 1.0:
            continue
        total = getattr(o, "total", None)
        total_val = _parse_total(total)
        market_id = _build_market_id(desc, label, total_val)
        if market_id in lines:
            continue
        last_update = getattr(o, "latest_bookmaker_update", None) or captured_at
        lines[market_id] = MarketLine(
            market_id=market_id,
            side_a_decimal=decimal,
            side_b_decimal=None,
            line_value=total_val,
            max_stake_cap=1.0,
            last_update_utc=last_update,
        )
    return MarketSnapshot(lines=lines)


def _parse_total(raw) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _build_market_id(description: str, label: str, total: float | None) -> str:
    desc_norm = description.replace(" ", "_").replace("/", "_")
    bits = [desc_norm]
    if label:
        bits.append(label.replace(" ", "_"))
    if total is not None:
        bits.append(str(total))
    return "_".join(bits)


# ──────────────────────────────────────────────────────────────────────
# Runtime
# ──────────────────────────────────────────────────────────────────────


@dataclass
class DualWriteRuntime:
    """Stateful holder for the v3 shadow co-execution path.

    Constructed once at watch.py startup. ``run_shadow`` is called
    per-fixture in the scan loop and returns a bool indicating whether
    v3 actually ran (False when disabled, kill-switched, or after a
    catastrophic failure that already incremented the counter).

    Thread safety: the V3Pipeline + ShadowLogger are not thread-safe by
    design (they assume single-writer per-fixture). ``run_shadow``
    serializes via ``self._lock`` so concurrent fixtures in watch.py
    don't trample the buffers. The lock is held only across the
    pipeline call + buffer append, which is sub-second.

    Telegram promotion: when ``telegram_sender`` is wired AND the env
    var ``V3_TELEGRAM_ENABLED`` is truthy, every allowed v3 pick is
    adapted to a ``LivePick`` and pushed through the existing
    ``LiveAlertSender`` pipeline (tier classification, throttling,
    keyboards, message-id tracking — all reused). v3-as-shadow is the
    default; promotion is opt-in per process.
    """

    pipeline: V3Pipeline
    logger: ShadowLogger
    timeout_sec: float = DEFAULT_V3_TIMEOUT_SEC
    kill_switch_path: Path = DEFAULT_KILL_SWITCH_PATH
    env_var: str = "V3_SHADOW_ENABLED"
    observer: LivePickObserver = field(default_factory=NullObserver)
    telegram_sender: object | None = None  # LiveAlertSender, optional
    telegram_env_var: str = "V3_TELEGRAM_ENABLED"
    error_count: int = 0
    success_count: int = 0
    skip_count: int = 0
    alerts_sent: int = 0
    alerts_skipped: int = 0
    alerts_failed: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @classmethod
    def from_paths(
        cls,
        ood_pkl: Path | None = DEFAULT_OOD_PKL,
        pattern_pkl: Path | None = DEFAULT_PATTERN_PKL,
        calibrator_pkl: Path | None = DEFAULT_CALIBRATOR_PKL,
        v2_picks_parquet: Path | None = DEFAULT_V2_PICKS_PARQUET,
        shadow_root: Path = DEFAULT_SHADOW_ROOT,
        kill_switch_path: Path | None = None,
        timeout_sec: float = DEFAULT_V3_TIMEOUT_SEC,
        env_var: str = "V3_SHADOW_ENABLED",
        observer: LivePickObserver | None = None,
        telegram_sender: object | None = None,
        telegram_env_var: str = "V3_TELEGRAM_ENABLED",
    ) -> DualWriteRuntime:
        """Build a runtime with detectors loaded from disk.

        Missing pkls → that layer = None (matches replay_shadow.load_detectors
        contract). v3 still runs, just without rule #9 or pattern layer.
        ``calibrator_pkl`` is the Phase-2 isotonic calibrator; when absent,
        the predictor returns raw probabilities (no calibration).
        """
        ood = None
        if ood_pkl is not None and ood_pkl.exists():
            try:
                ood = OODDetector.load(ood_pkl)
                log.info("v3_runtime_loaded_ood path=%s", ood_pkl)
            except Exception as exc:  # noqa: BLE001
                log.warning("v3_runtime_ood_load_failed path=%s err=%s", ood_pkl, exc)
        else:
            log.warning("v3_runtime_ood_pkl_absent path=%s", ood_pkl)

        pattern = None
        if pattern_pkl is not None and pattern_pkl.exists():
            try:
                pattern = PatternLayer.load(pattern_pkl)
                log.info("v3_runtime_loaded_pattern path=%s", pattern_pkl)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "v3_runtime_pattern_load_failed path=%s err=%s",
                    pattern_pkl,
                    exc,
                )
        else:
            log.warning("v3_runtime_pattern_pkl_absent path=%s", pattern_pkl)

        calibrator = None
        if calibrator_pkl is not None and calibrator_pkl.exists():
            try:
                from bip.evaluation.live.engine_v3.calibrator import (
                    IsotonicCalibrator,
                )
                calibrator = IsotonicCalibrator.load(calibrator_pkl)
                log.info(
                    "v3_runtime_loaded_calibrator path=%s coverage=%d_cells",
                    calibrator_pkl,
                    len(calibrator.per_cell),
                )
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "v3_runtime_calibrator_load_failed path=%s err=%s",
                    calibrator_pkl,
                    exc,
                )
        else:
            log.info("v3_runtime_calibrator_pkl_absent path=%s", calibrator_pkl)

        drift_monitor = None
        if v2_picks_parquet is not None and v2_picks_parquet.exists():
            try:
                from bip.evaluation.live.engine_v3.drift_monitor import (
                    CalibrationDriftMonitor,
                )
                drift_monitor = CalibrationDriftMonitor()
                n_seeded = drift_monitor.warm_up_from_v2_history(
                    v2_picks_parquet
                )
                log.info(
                    "v3_runtime_drift_monitor_warmed picks=%d coverage=%s",
                    n_seeded,
                    {
                        f: sum(buckets.values())
                        for f, buckets in drift_monitor.coverage().items()
                    },
                )
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "v3_runtime_drift_monitor_warmup_failed path=%s err=%s",
                    v2_picks_parquet,
                    exc,
                )
        else:
            log.info(
                "v3_runtime_drift_monitor_history_absent path=%s",
                v2_picks_parquet,
            )

        predictor = ConditionalPredictor.default(calibrator=calibrator)
        pipeline = V3Pipeline(
            ood_detector=ood,
            pattern_layer=pattern,
            conditional_predictor=predictor,
            drift_monitor=drift_monitor,
        )
        logger = ShadowLogger(output_root=shadow_root)
        return cls(
            pipeline=pipeline,
            logger=logger,
            timeout_sec=timeout_sec,
            kill_switch_path=kill_switch_path or (shadow_root / "v3_kill_switch.flag"),
            env_var=env_var,
            observer=observer or NullObserver(),
            telegram_sender=telegram_sender,
            telegram_env_var=telegram_env_var,
        )

    async def run_shadow(
        self,
        state: LiveMatchState,
        fixture,
        odds,
        now_utc: datetime,
    ) -> bool:
        """Execute v3 in shadow mode for one fixture frame.

        Returns ``True`` when v3 ran to completion (success or recorded
        denials). Returns ``False`` when skipped or errored.

        Never raises — every exception path is captured into
        ``error_count`` and logged. v2's path through watch.py is
        protected by construction.

        When ``telegram_sender`` is wired AND ``V3_TELEGRAM_ENABLED`` is
        truthy, allowed picks are adapted and pushed through the
        existing alert pipeline AFTER the sync pipeline returns. The
        alert send is awaited in the caller's event loop (not in the
        thread that ran V3Pipeline) so the LiveAlertSender's async
        primitives (throttle, bot.send_html) execute correctly.
        """
        if not is_v3_shadow_enabled(self.env_var):
            self.skip_count += 1
            return False
        if is_v3_kill_switch_engaged(self.kill_switch_path):
            self.skip_count += 1
            return False

        out: PipelineOutput | None = None
        try:
            out = await asyncio.wait_for(
                asyncio.to_thread(
                    self._run_pipeline_sync, state, fixture, odds, now_utc,
                ),
                timeout=self.timeout_sec,
            )
            self.success_count += 1
        except TimeoutError:
            self.error_count += 1
            log.warning(
                "v3_shadow_error fixture=%s reason=timeout timeout_sec=%.2f",
                getattr(fixture, "id", "?"),
                self.timeout_sec,
            )
            return False
        except Exception as exc:  # noqa: BLE001
            self.error_count += 1
            log.warning(
                "v3_shadow_error fixture=%s reason=%s",
                getattr(fixture, "id", "?"),
                type(exc).__name__,
            )
            return False

        # Telegram promotion — opt-in via env var. Async send happens
        # in the caller's event loop, not the worker thread.
        if (
            out is not None
            and out.allowed_picks
            and self.telegram_sender is not None
            and is_v3_shadow_enabled(self.telegram_env_var)
        ):
            await self._send_alerts_for(out)
        return True

    async def _send_alerts_for(self, out: PipelineOutput) -> None:
        """Adapt v3 picks → LivePick and push through the v2 alert sender.

        Failures are caught individually so a bad single pick doesn't
        block the others. The send method itself is already failure-
        safe (``send_pick_safe`` never raises).
        """
        for pick in out.allowed_picks:
            try:
                live_pick = shadow_pick_to_live_pick(pick, out.gsv)
            except Exception as exc:  # noqa: BLE001
                self.alerts_failed += 1
                log.warning(
                    "v3_alert_adapter_error fixture=%s reason=%s",
                    out.gsv.fixture_id, type(exc).__name__,
                )
                continue
            if live_pick is None:
                self.alerts_skipped += 1
                continue
            try:
                sent = await self.telegram_sender.send_pick_safe(
                    live_pick,
                    home_score=out.gsv.score.home_goals,
                    away_score=out.gsv.score.away_goals,
                )
                if sent:
                    self.alerts_sent += 1
                else:
                    self.alerts_skipped += 1
            except Exception as exc:  # noqa: BLE001
                self.alerts_failed += 1
                log.warning(
                    "v3_alert_send_error fixture=%s reason=%s",
                    out.gsv.fixture_id, type(exc).__name__,
                )

    def _run_pipeline_sync(
        self,
        state: LiveMatchState,
        fixture,
        odds,
        now_utc: datetime,
    ) -> PipelineOutput:
        """The actual sync work that runs inside ``asyncio.to_thread``."""
        priors = derive_priors_from_fixture(fixture)
        markets = market_snapshot_from_odds(odds, captured_at=now_utc)
        if not markets.lines:
            # No markets to evaluate — fast return, not an error
            return None  # type: ignore[return-value]
        with self._lock:
            out = self.pipeline.run(
                state,
                priors=priors,
                markets=markets,
                now_utc=now_utc,
            )
            self.logger.record(out)
            # Live observer: surface allowed picks to the operator's
            # terminal/log in real time. Observers are side-effect-only
            # and MUST NOT raise — we catch defensively so a formatter
            # bug never propagates into the v3 critical path.
            if out is not None and out.allowed_picks:
                for pick in out.allowed_picks:
                    try:
                        self.observer.on_pick(pick, out.gsv, out.mispricing_window)
                    except Exception as exc:  # noqa: BLE001
                        log.warning(
                            "v3_observer_error reason=%s",
                            type(exc).__name__,
                        )
            return out

    def flush(self) -> dict[str, Path]:
        """Forwarding helper — flush the underlying ShadowLogger buffers."""
        with self._lock:
            return self.logger.flush()

    @property
    def stats(self) -> dict[str, int]:
        return {
            "v3_success": self.success_count,
            "v3_error": self.error_count,
            "v3_skip": self.skip_count,
        }
