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
- Sportmonks predictions, indexed by type_id (for baseline lookup)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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

        # Events: extract goals + red cards
        goal_events, red_card_events = _extract_events(
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


def _extract_events(events, home_id: int, away_id: int):
    """Pull goals + red cards from event list. Sportmonks event type_ids:
    14 = goal, 16 = penalty goal (variants), 19 = red card.
    The exact type_ids vary slightly; we match by minute presence and
    participant_id, ignoring unknown types.
    """
    goal_events: list[tuple[int, int]] = []
    red_card_events: list[tuple[int, int]] = []
    GOAL_TYPE_IDS = {14, 15, 16, 17, 18}  # goal variants
    RED_CARD_TYPE_IDS = {19, 20, 21}      # red / yellow-red variants
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
    goal_events.sort()
    red_card_events.sort()
    return goal_events, red_card_events
