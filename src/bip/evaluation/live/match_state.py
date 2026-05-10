"""LiveMatchState — frozen snapshot of a fixture at one point in time.

Built from a Sportmonks ``Fixture`` populated with the standard live
includes (state, periods, scores, statistics, trends, pressure,
predictions, events, participants).

The state EXPOSES derived signals that the predictor consumes:
- Current score per side
- Elapsed minute (best-effort from periods)
- Per-team aggregate stats by name (`shots_on_target`, `dangerous_attacks`, etc.)
- Recent-window pressure averages (last 5/10 min)
- Goal-event timeline (for Dixon-Robinson scoring)
- Red card / yellow card / substitution event timelines
- Sportmonks predictions, indexed by type_id (for baseline lookup)
- Cached Sportmonks correct-score grid (for cross-market sanity)
- Informational-density score (gates live-adjusted picks)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np

from bip.sports.football.sportmonks.schemas import (
    Fixture,
    FixtureStatistic,
    Prediction,
    PressureMinute,
    Trend,
)
from bip.sports.football.sportmonks.types import (
    PERIOD_FIRST_HALF,
    PERIOD_SECOND_HALF,
    PredictionType,
    StatType,
)

# Forward reference: ``TeamForm`` is imported lazily inside the dataclass to
# avoid a circular import (team_form.py depends on this module's schemas).
if False:  # pragma: no cover - typing only
    from bip.evaluation.live.team_form import TeamForm


# Stat IDs used as live "shot quality" signal — the proxy for live xG when
# Sportmonks does not populate xGFixture for the league.
SHOT_QUALITY_STAT_IDS: tuple[int, ...] = (
    StatType.SHOTS_ON_TARGET,        # 86
    StatType.SHOTS_INSIDEBOX,        # 49
    StatType.BIG_CHANCES_CREATED,    # 580
    StatType.DANGEROUS_ATTACKS,      # 44 (denominator-ish)
)

# Empirical xG weights per shot/event type (literature consensus + sanity):
# Big chance ≈ 0.30 xG, Shot inside box ≈ 0.10, Shot on target ≈ 0.07,
# Dangerous attack ≈ 0.005. These are conservative — calibrated for
# proxy purposes, not used as primary xG when Sportmonks emits real xG.
XG_PROXY_WEIGHTS: dict[int, float] = {
    StatType.SHOTS_ON_TARGET: 0.07,
    StatType.SHOTS_INSIDEBOX: 0.05,  # incremental over shots_on_target
    StatType.BIG_CHANCES_CREATED: 0.20,  # incremental over inside-box
    StatType.DANGEROUS_ATTACKS: 0.005,
}


# Event type_ids (verified 2026-05-09 against /core/types).
EVENT_TYPE_GOAL = 14
EVENT_TYPE_OWNGOAL = 15
EVENT_TYPE_PENALTY_SCORED = 16
EVENT_TYPE_MISSED_PENALTY = 17
EVENT_TYPE_SUBSTITUTION = 18
EVENT_TYPE_YELLOWCARD = 19
EVENT_TYPE_REDCARD = 20
EVENT_TYPE_YELLOWREDCARD = 21


# Score-grid dimension for the cached Sportmonks correct-score table.
_SCORE_GRID_MAX_N = 8


@dataclass(frozen=True)
class LiveMatchState:
    """Immutable snapshot — one frame of one match."""

    fixture_id: int
    home_team_id: int
    away_team_id: int
    home_team_name: str
    away_team_name: str
    home_goals: int
    away_goals: int
    minute: int          # 0 if not yet started; clamps at 90/120
    period_id: int       # 0 if NS / FT, else 1 / 2 / 38 / 39
    is_live: bool
    is_half_time: bool
    is_finished: bool

    # Per-team aggregate stats (indexed by StatType enum value)
    home_stats: dict[int, float] = field(default_factory=dict)
    away_stats: dict[int, float] = field(default_factory=dict)

    # Pressure: per-minute samples, last N minutes window stored
    home_pressure_recent: list[float] = field(default_factory=list)
    away_pressure_recent: list[float] = field(default_factory=list)

    # Sportmonks pre-built predictions, indexed by type_id
    sportmonks_predictions: dict[int, dict[str, Any]] = field(default_factory=dict)

    # Goal-event timeline (minute, scoring_team_id) — sorted ascending
    goal_events: list[tuple[int, int]] = field(default_factory=list)

    # Red-card events (minute, team_affected_id)
    red_card_events: list[tuple[int, int]] = field(default_factory=list)

    # Yellow-card events (minute, team_id, player_id) — player_id is 0 when absent.
    # Used for booked-player tracking (yellow→red risk) and cards-market signal.
    yellow_card_events: list[tuple[int, int, int]] = field(default_factory=list)

    # Substitution events (minute, team_id, player_in_id-or-None).
    # Manager-intent signal: triple-sub by 70' = pushing for goal;
    # lone defensive sub at 80' = locking the result.
    substitution_events: list[tuple[int, int, int | None]] = field(default_factory=list)

    # Snapshot meta (best-effort; not always emitted by Sportmonks).
    snapshot_taken_at: datetime | None = None
    league_id: int | None = None
    season_id: int | None = None

    # Recent-form signals (resolved by the watcher via ``TeamFormCache``).
    # Either may be None when the team has too few completed fixtures or
    # when the fetch failed. The predictor reads these in the goal-timing
    # market emitters to tilt pre-match priors away from the league
    # baseline when a team's recent pattern is materially different.
    home_team_form: Any | None = None  # bip.evaluation.live.team_form.TeamForm
    away_team_form: Any | None = None

    # ── derived signals ─────────────────────────────────────────────────

    @property
    def score_diff_home(self) -> int:
        return self.home_goals - self.away_goals

    @property
    def remaining_minutes(self) -> int:
        """Conservative remaining-minutes estimate (caps at full match length).

        Treats halftime as paused — remaining = 90 - minute. Extra time and
        injury time are not modelled here.
        """
        if self.is_finished:
            return 0
        if self.minute >= 90:
            return 0
        return max(0, 90 - self.minute)

    @property
    def home_shot_quality_xg_proxy(self) -> float:
        """Sum of weighted shot-quality stats for home side."""
        return _xg_proxy(self.home_stats)

    @property
    def away_shot_quality_xg_proxy(self) -> float:
        return _xg_proxy(self.away_stats)

    @property
    def home_pressure_avg(self) -> float:
        return (
            sum(self.home_pressure_recent) / len(self.home_pressure_recent)
            if self.home_pressure_recent else 0.0
        )

    @property
    def away_pressure_avg(self) -> float:
        return (
            sum(self.away_pressure_recent) / len(self.away_pressure_recent)
            if self.away_pressure_recent else 0.0
        )

    @property
    def home_pressure_trend(self) -> float:
        """Difference between recent-half and earlier-half of pressure window.

        Positive = pressure rising; negative = falling. Zero when window
        too small to derive a trend. Used to distinguish a team that's
        BUILDING attack from one that's tired and DROPPING off.
        """
        return _trend_split(self.home_pressure_recent)

    @property
    def away_pressure_trend(self) -> float:
        return _trend_split(self.away_pressure_recent)

    @property
    def has_red_card_home(self) -> bool:
        return any(t == self.home_team_id for _, t in self.red_card_events)

    @property
    def has_red_card_away(self) -> bool:
        return any(t == self.away_team_id for _, t in self.red_card_events)

    @property
    def red_card_minute_home(self) -> int | None:
        """Earliest red-card minute for home team (or None if no red)."""
        homes = [m for m, t in self.red_card_events if t == self.home_team_id]
        return min(homes) if homes else None

    @property
    def red_card_minute_away(self) -> int | None:
        aways = [m for m, t in self.red_card_events if t == self.away_team_id]
        return min(aways) if aways else None

    # ── Stat-derived signals (B-1, B-2, B-3, B-5, B-6, B-7, B-9, B-11) ──

    @property
    def home_corners(self) -> int:
        return int(self.home_stats.get(StatType.CORNERS, 0))

    @property
    def away_corners(self) -> int:
        return int(self.away_stats.get(StatType.CORNERS, 0))

    @property
    def home_possession(self) -> float:
        """Possession % (0-100). Defaults to 50 when stat missing."""
        return float(self.home_stats.get(StatType.BALL_POSSESSION, 50.0))

    @property
    def away_possession(self) -> float:
        return float(self.away_stats.get(StatType.BALL_POSSESSION, 50.0))

    @property
    def home_shots_total(self) -> int:
        return int(self.home_stats.get(StatType.SHOTS_TOTAL, 0))

    @property
    def away_shots_total(self) -> int:
        return int(self.away_stats.get(StatType.SHOTS_TOTAL, 0))

    @property
    def home_key_passes(self) -> int:
        return int(self.home_stats.get(StatType.KEY_PASSES, 0))

    @property
    def away_key_passes(self) -> int:
        return int(self.away_stats.get(StatType.KEY_PASSES, 0))

    @property
    def home_saves(self) -> int:
        return int(self.home_stats.get(StatType.SAVES, 0))

    @property
    def away_saves(self) -> int:
        return int(self.away_stats.get(StatType.SAVES, 0))

    @property
    def home_big_chances_missed(self) -> int:
        return int(self.home_stats.get(StatType.BIG_CHANCES_MISSED, 0))

    @property
    def away_big_chances_missed(self) -> int:
        return int(self.away_stats.get(StatType.BIG_CHANCES_MISSED, 0))

    @property
    def home_big_chances_created(self) -> int:
        return int(self.home_stats.get(StatType.BIG_CHANCES_CREATED, 0))

    @property
    def away_big_chances_created(self) -> int:
        return int(self.away_stats.get(StatType.BIG_CHANCES_CREATED, 0))

    @property
    def home_injuries(self) -> int:
        return int(self.home_stats.get(StatType.INJURIES, 0))

    @property
    def away_injuries(self) -> int:
        return int(self.away_stats.get(StatType.INJURIES, 0))

    @property
    def home_engagement(self) -> int:
        """Tackles + interceptions + duels-won — defensive engagement.

        High engagement signals a scrappy game where the underlying goal
        rate compresses (defenders winning the ball before xG accumulates).
        """
        return (
            int(self.home_stats.get(StatType.TACKLES, 0))
            + int(self.home_stats.get(StatType.INTERCEPTIONS, 0))
            + int(self.home_stats.get(StatType.DUELS_WON, 0))
        )

    @property
    def away_engagement(self) -> int:
        return (
            int(self.away_stats.get(StatType.TACKLES, 0))
            + int(self.away_stats.get(StatType.INTERCEPTIONS, 0))
            + int(self.away_stats.get(StatType.DUELS_WON, 0))
        )

    # ── Yellow-card / booked-player signals (B-29) ─────────────────────

    @property
    def yellow_card_count_home(self) -> int:
        return sum(1 for _m, t, _p in self.yellow_card_events if t == self.home_team_id)

    @property
    def yellow_card_count_away(self) -> int:
        return sum(1 for _m, t, _p in self.yellow_card_events if t == self.away_team_id)

    @property
    def players_booked_home(self) -> set[int]:
        return {p for _m, t, p in self.yellow_card_events
                if t == self.home_team_id and p}

    @property
    def players_booked_away(self) -> set[int]:
        return {p for _m, t, p in self.yellow_card_events
                if t == self.away_team_id and p}

    # ── Substitution signals (B-30) ────────────────────────────────────

    @property
    def substitutions_home(self) -> int:
        return sum(1 for _m, t, _p in self.substitution_events if t == self.home_team_id)

    @property
    def substitutions_away(self) -> int:
        return sum(1 for _m, t, _p in self.substitution_events if t == self.away_team_id)

    # ── Killing-the-clock detector (B-3) ───────────────────────────────

    def is_killing_clock(self, side: str) -> bool:
        """Detect "high possession but no penetration" pattern.

        Triggers when a team has ≥65% possession from min ≥60, but their
        attacking productivity per minute of ball is suspiciously low. In
        that pattern they are protecting a result, NOT going for a goal,
        so over-goals + draw-pushing nudges should be suppressed.

        Productivity = (shots_total + key_passes) / minutes_of_possession,
        where minutes_of_possession ≈ minute × possession_pct/100. League
        average for attacking teams is ~0.40-0.70 actions per poss-minute;
        clock-killing sits significantly below that band.
        """
        if self.minute < 60:
            return False
        if side == "home":
            poss, st, kp = self.home_possession, self.home_shots_total, self.home_key_passes
        else:
            poss, st, kp = self.away_possession, self.away_shots_total, self.away_key_passes
        if poss < 65.0:
            return False
        poss_minutes = self.minute * (poss / 100.0)
        if poss_minutes < 5.0:
            return False  # too small a sample for a stable rate
        productivity = (st + kp) / poss_minutes
        return productivity < 0.20

    # ── Information-content gate (B-7 / B-G3) ──────────────────────────

    @property
    def informational_density(self) -> float:
        """Score in [0, 1] — how much real live signal has accumulated.

        Used by the predictor to decide whether to live-adjust at all.
        At low density we return Sportmonks pre-match priors verbatim
        rather than rebuild from per-team OU + pressure.

        Formula::

            minute_term = min(1, minute / 25)
            data_term   = max(pressure_term, stat_term, event_term)
            density     = minute_term × (0.4 + 0.6 × data_term)

        Match events (goals, red cards) feed ``event_term`` — a strong
        signal that accelerates density to full credit ON THE DATA AXIS.
        But they DO NOT bypass the minute floor: a red card at minute 5
        still leaves minute_term=0.20, so density caps at 0.20 — below
        the gate floor — until enough match time has elapsed for stats
        and pressure to complement the event.

        The previous override to 1.0 on any event was a bug: it allowed
        live-adjusted picks to emit at minute 5-15 with no statistical
        accumulation, recreating the cluster-C "min-8 burst" via early
        events.
        """
        minute_term = min(1.0, max(0, self.minute) / 25.0)
        n_pressure = len(self.home_pressure_recent) + len(self.away_pressure_recent)
        pressure_term = min(1.0, n_pressure / 8.0)  # 4 samples per side = full
        stat_events = sum(
            self.home_stats.get(t, 0) + self.away_stats.get(t, 0)
            for t in (
                StatType.SHOTS_TOTAL, StatType.KEY_PASSES,
                StatType.CORNERS, StatType.SHOTS_ON_TARGET,
            )
        )
        stat_term = min(1.0, stat_events / 12.0)
        event_term = 1.0 if (
            self.red_card_events
            or (self.home_goals + self.away_goals) >= 1
        ) else 0.0
        data_term = max(pressure_term, stat_term, event_term)
        return minute_term * (0.4 + 0.6 * data_term)

    # ── Sportmonks correct-score grid (B-16) ───────────────────────────

    @property
    def sportmonks_score_grid(self) -> np.ndarray | None:
        """Build a (max_n+1, max_n+1) probability grid from Sportmonks
        ``CORRECT_SCORE_PROBABILITY`` (type_id 240).

        Body shape (verified): ``{scores: {"0-0": 8.4, "1-0": 11.2, ..., "other": 4.1}}``.
        Values are percentages 0-100. The "other" bucket is ignored for
        marginal calculations — its mass is redistributed via final
        normalisation. None when Sportmonks didn't emit the prediction.
        """
        sm = self.sportmonks_predictions.get(PredictionType.CORRECT_SCORE_PROBABILITY)
        if not sm:
            return None
        scores = sm.get("scores") if isinstance(sm, dict) else None
        if not isinstance(scores, dict):
            return None
        n = _SCORE_GRID_MAX_N + 1
        grid = np.zeros((n, n))
        for k, v in scores.items():
            if not isinstance(k, str) or k == "other":
                continue
            try:
                h_str, a_str = k.split("-")
                h, a = int(h_str), int(a_str)
            except (ValueError, IndexError):
                continue
            if 0 <= h < n and 0 <= a < n:
                try:
                    grid[h, a] = float(v) / 100.0
                except (TypeError, ValueError):
                    continue
        total = grid.sum()
        if total <= 0:
            return None
        return grid / total

    # ── Live xG signal (computed vs expected) ───────────────────────────

    def home_live_xg_signal(self) -> float:
        """Live xG performance vs minute-prorated expectation.

        Positive value means home team has out-performed their
        pre-match expected goal-creation rate up to current minute;
        negative means they've under-performed. Range typically
        ±1.5 in active matches.

        Uses the operator-tuned XG_PROXY_WEIGHTS to estimate live
        creation, and compares against (Sportmonks pre-match λ_home) ×
        (minute / 90) as the expected level for this point in time.
        """
        return self._live_xg_signal(self.home_stats, self.home_team_id)

    def away_live_xg_signal(self) -> float:
        return self._live_xg_signal(self.away_stats, self.away_team_id)

    def _live_xg_signal(self, stats: dict[int, float], team_id: int) -> float:
        live_proxy = _xg_proxy(stats)
        # We can't compute the expected here without external context;
        # the predictor has access to Sportmonks predictions and will
        # subtract the expected level itself. This method exposes raw
        # live proxy.
        return live_proxy

    def sportmonks_prediction(self, type_id: int) -> dict[str, Any] | None:
        return self.sportmonks_predictions.get(type_id)

    # ── construction from a Sportmonks Fixture ──────────────────────────

    @classmethod
    def from_fixture(
        cls,
        fixture: Fixture,
        *,
        pressure_window_minutes: int = 10,
        snapshot_taken_at: datetime | None = None,
    ) -> LiveMatchState:
        """Build a state from an enriched Fixture.

        Required includes on the fixture:
        - participants, state, periods, scores, statistics, predictions
        Optional:
        - trends, pressure, events
        """
        if not fixture.participants or len(fixture.participants) < 2:
            raise ValueError("Fixture missing participants")
        home, away = _identify_home_away(fixture)

        # Score (latest current score per side)
        home_goals, away_goals = _extract_current_score(fixture, home.id, away.id)

        # Minute + period
        minute, period_id = _extract_minute_and_period(fixture)
        is_live = fixture.is_live()
        state_dev = fixture.state.developer_name if fixture.state else ""
        is_half_time = state_dev == "HT"
        is_finished = state_dev in ("FT", "AET", "FT_PEN", "FINISHED")

        # Aggregate statistics by type_id × team
        home_stats, away_stats = _aggregate_statistics(
            fixture.statistics or [], home.id, away.id
        )

        # Pressure window (last N minutes)
        home_pressure, away_pressure = _pressure_window(
            fixture.pressure or [], home.id, away.id, minute, pressure_window_minutes
        )

        # Sportmonks predictions indexed by type_id
        predictions_by_type = _index_predictions(fixture.predictions or [])

        # Events: extract goals + red cards + yellow cards + subs
        goal_events, red_card_events, yellow_events, sub_events = _extract_events(
            fixture.events or [], home.id, away.id
        )

        return cls(
            fixture_id=fixture.id,
            home_team_id=home.id,
            away_team_id=away.id,
            home_team_name=home.name,
            away_team_name=away.name,
            home_goals=home_goals,
            away_goals=away_goals,
            minute=minute,
            period_id=period_id,
            is_live=is_live,
            is_half_time=is_half_time,
            is_finished=is_finished,
            home_stats=home_stats,
            away_stats=away_stats,
            home_pressure_recent=home_pressure,
            away_pressure_recent=away_pressure,
            sportmonks_predictions=predictions_by_type,
            goal_events=goal_events,
            red_card_events=red_card_events,
            yellow_card_events=yellow_events,
            substitution_events=sub_events,
            snapshot_taken_at=snapshot_taken_at,
            league_id=fixture.league_id,
            season_id=fixture.season_id,
        )


# ── helpers ─────────────────────────────────────────────────────────────────


def _trend_split(samples: list[float]) -> float:
    """Compare recent-half vs earlier-half of a sample window.

    Positive return = trend is rising. Zero when fewer than 4 samples.
    """
    if len(samples) < 4:
        return 0.0
    half = len(samples) // 2
    earlier = samples[:half]
    later = samples[half:]
    return (sum(later) / len(later)) - (sum(earlier) / len(earlier))


def _xg_proxy(stats: dict[int, float]) -> float:
    """Compute a weighted xG proxy from shot-quality stats.

    NOTE: this is a backstop when Sportmonks does not emit real xG. The
    weights are tuned for monotonicity (more shots → higher xG) but are
    NOT calibrated against ground truth. Use Sportmonks predictions
    directly when available.
    """
    return sum(
        XG_PROXY_WEIGHTS[tid] * stats.get(tid, 0.0)
        for tid in XG_PROXY_WEIGHTS
        if tid in stats
    )


def _identify_home_away(fixture: Fixture):
    """Sportmonks puts location info on participants[i].meta.location.

    Our schema doesn't model meta yet; fall back to participants[0]=home,
    [1]=away which matches API convention.
    """
    if not fixture.participants or len(fixture.participants) < 2:
        raise ValueError("need 2 participants")
    return fixture.participants[0], fixture.participants[1]


def _extract_current_score(
    fixture: Fixture, home_id: int, away_id: int,
) -> tuple[int, int]:
    """Pull the most recent CURRENT score per team from scores list.

    Sportmonks emits scores entries with type_id corresponding to:
    - 1H_SCORE, 2H_SCORE, CURRENT, FT_SCORE, ET_SCORE, etc.
    We look at score.score['participant'] = 'home'|'away'.
    """
    home_goals, away_goals = 0, 0
    if not fixture.scores:
        return home_goals, away_goals
    # Prefer the latest score entries (Sportmonks lists chronologically)
    # by walking and overwriting — final values win.
    for s in fixture.scores:
        body = s.score or {}
        loc = body.get("participant")
        goals = body.get("goals")
        if not isinstance(goals, (int, float)):
            continue
        if loc == "home":
            home_goals = int(goals)
        elif loc == "away":
            away_goals = int(goals)
    return home_goals, away_goals


def _extract_minute_and_period(fixture: Fixture) -> tuple[int, int]:
    """Return (minute, period_id) for the active period.

    Falls back to 0 when periods are absent, FT, or NS.
    """
    if not fixture.periods:
        return 0, 0
    # Active period: ticking, or the latest started one
    active = [p for p in fixture.periods if p.ticking]
    if active:
        p = active[0]
        return (p.minutes or 0, p.type_id)
    # Finished match: pick the period with the largest minutes
    finished = sorted(
        (p for p in fixture.periods if p.minutes is not None),
        key=lambda p: p.minutes or 0,
        reverse=True,
    )
    if finished:
        return finished[0].minutes or 0, finished[0].type_id
    return 0, 0


def _aggregate_statistics(
    stats: list[FixtureStatistic], home_id: int, away_id: int,
) -> tuple[dict[int, float], dict[int, float]]:
    home: dict[int, float] = {}
    away: dict[int, float] = {}
    for s in stats:
        v = s.value
        if v is None:
            continue
        if s.participant_id == home_id:
            home[s.type_id] = v
        elif s.participant_id == away_id:
            away[s.type_id] = v
    return home, away


def _pressure_window(
    pressure: list[PressureMinute],
    home_id: int,
    away_id: int,
    current_minute: int,
    window: int,
) -> tuple[list[float], list[float]]:
    """Return last ``window`` minutes of pressure values per side."""
    if not pressure:
        return [], []
    threshold = max(0, current_minute - window)
    home: list[float] = []
    away: list[float] = []
    for p in pressure:
        if p.minute < threshold:
            continue
        if p.minute > current_minute:
            continue
        if p.participant_id == home_id:
            home.append(p.pressure)
        elif p.participant_id == away_id:
            away.append(p.pressure)
    return home, away


def _index_predictions(preds: list[Prediction]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for p in preds:
        if p.predictions:
            out[p.type_id] = p.predictions
    return out


def _extract_events(
    events, home_id: int, away_id: int,
) -> tuple[
    list[tuple[int, int]],
    list[tuple[int, int]],
    list[tuple[int, int, int]],
    list[tuple[int, int, int | None]],
]:
    """Pull goals + red cards + yellow cards + substitutions from event list.

    Sportmonks v3 event type_ids (verified 2026-05-09 against /core/types):
    - 14 = GOAL
    - 15 = OWNGOAL (we record minute regardless of attribution side)
    - 16 = PENALTY (scored from the spot)
    - 17 = MISSED_PENALTY (NOT a goal)
    - 18 = SUBSTITUTION
    - 19 = YELLOWCARD
    - 20 = REDCARD (straight red)
    - 21 = YELLOWREDCARD (second yellow → red, treated as red card)

    Returns
    -------
    goal_events
        ``[(minute, scoring_team_id), ...]`` sorted by minute.
    red_card_events
        ``[(minute, team_affected_id), ...]`` sorted by minute. Combines
        straight-red and yellow→red into one stream.
    yellow_card_events
        ``[(minute, team_id, player_id_or_0), ...]`` sorted. Used for
        booked-player tracking and cards-market signal.
    substitution_events
        ``[(minute, team_id, related_player_id_or_None), ...]`` sorted.
    """
    goal_events: list[tuple[int, int]] = []
    red_card_events: list[tuple[int, int]] = []
    yellow_card_events: list[tuple[int, int, int]] = []
    substitution_events: list[tuple[int, int, int | None]] = []
    GOAL_TYPE_IDS = {EVENT_TYPE_GOAL, EVENT_TYPE_OWNGOAL, EVENT_TYPE_PENALTY_SCORED}
    RED_CARD_TYPE_IDS = {EVENT_TYPE_REDCARD, EVENT_TYPE_YELLOWREDCARD}
    for e in events:
        minute = e.minute
        team = e.participant_id
        if minute is None or team is None:
            continue
        if team not in (home_id, away_id):
            continue
        if e.type_id in GOAL_TYPE_IDS:
            goal_events.append((minute, team))
        elif e.type_id in RED_CARD_TYPE_IDS:
            red_card_events.append((minute, team))
        elif e.type_id == EVENT_TYPE_YELLOWCARD:
            yellow_card_events.append((minute, team, e.player_id or 0))
        elif e.type_id == EVENT_TYPE_SUBSTITUTION:
            substitution_events.append((minute, team, e.related_player_id))
    goal_events.sort()
    red_card_events.sort()
    yellow_card_events.sort()
    substitution_events.sort()
    return goal_events, red_card_events, yellow_card_events, substitution_events
