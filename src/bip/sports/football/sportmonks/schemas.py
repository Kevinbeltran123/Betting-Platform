"""Pydantic v2 models for Sportmonks v3 Football API responses.

Schemas are minimal and FORGIVING by default (extra='ignore') because
Sportmonks adds fields without notice. We pin only the fields our
predictor reads; the raw payload is also persisted to disk.

All models are frozen for safety — Sportmonks data is read-only here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


_MODEL_CONFIG = ConfigDict(frozen=True, extra="ignore")


# ── Core fixture ─────────────────────────────────────────────────────────────


class Participant(BaseModel):
    """One team in a fixture."""

    model_config = _MODEL_CONFIG

    id: int
    name: str
    short_code: str | None = None
    image_path: str | None = None


class FixtureState(BaseModel):
    """Current lifecycle state — INPLAY_*, FINISHED, NS, HT, etc."""

    model_config = _MODEL_CONFIG

    id: int
    state: str
    name: str
    short_name: str | None = None
    developer_name: str


class League(BaseModel):
    model_config = _MODEL_CONFIG

    id: int
    name: str
    country_id: int | None = None
    short_code: str | None = None


class Period(BaseModel):
    """Match period (1H / 2H / ET / Pen). Used to derive elapsed minute."""

    model_config = _MODEL_CONFIG

    id: int
    fixture_id: int
    type_id: int
    started: datetime | int | None = None  # epoch seconds when an int
    ended: datetime | int | None = None
    counts_from: int | None = None
    minutes: int | None = None
    seconds: int | None = None
    has_timer: bool | None = None
    ticking: bool | None = None
    description: str | None = None


class Score(BaseModel):
    """Per-period score per participant. Multiple types: 1H_SCORE, 2H_SCORE,
    CURRENT, FT_SCORE, etc."""

    model_config = _MODEL_CONFIG

    id: int
    fixture_id: int
    type_id: int
    participant_id: int | None = None
    score: dict[str, Any]  # {goals: int, participant: 'home'|'away'}
    description: str | None = None


# ── Statistics + trends ──────────────────────────────────────────────────────


class FixtureStatistic(BaseModel):
    """Aggregate stat for one team in one fixture (e.g. shots_total = 14)."""

    model_config = _MODEL_CONFIG

    id: int
    fixture_id: int
    type_id: int
    participant_id: int
    data: dict[str, Any]  # {value: number}
    location: str | None = None  # 'home' | 'away'

    @property
    def value(self) -> float | None:
        v = self.data.get("value") if self.data else None
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None


class Trend(BaseModel):
    """Minute-by-minute statistic value. Same type_ids as FixtureStatistic
    but emitted per minute → time series."""

    model_config = _MODEL_CONFIG

    id: int
    fixture_id: int
    type_id: int
    participant_id: int
    period_id: int
    minute: int
    value: float | int | None = None


class PressureMinute(BaseModel):
    """Per-minute attack pressure index (Sportmonks proprietary, 0-100)."""

    model_config = _MODEL_CONFIG

    id: int
    fixture_id: int
    participant_id: int
    minute: int
    pressure: float


# ── Predictions + odds ───────────────────────────────────────────────────────


class Prediction(BaseModel):
    """One pre-built ML prediction for a market.

    The ``predictions`` body shape varies by ``type_id``:
    - 231 BTTS  → {yes, no}
    - 232 HT/FT → {home_home, home_draw, ..., away_away, draw_draw}
    - 233 First Half Winner → {home, draw, away}
    - 234 OU 1.5 → {yes, no}
    - 235 OU 2.5 → {yes, no}
    - 237 Fulltime Result → {home, draw, away}
    - 239 Double Chance → {draw_home, draw_away, home_away}
    - 240 Correct Score → {scores: {0-0, 0-1, ..., 5-5, other}}
    - 33 Value Bet → {bet, bookmaker, fair_odd, odd, stake, is_value}
    """

    model_config = _MODEL_CONFIG

    id: int
    fixture_id: int
    type_id: int
    predictions: dict[str, Any] = Field(default_factory=dict)


class Odd(BaseModel):
    """One bookmaker quote for one market selection."""

    model_config = _MODEL_CONFIG

    id: int
    fixture_id: int
    market_id: int
    bookmaker_id: int
    label: str
    value: str | None = None  # decimal odd string
    name: str | None = None
    sort_order: int | None = None
    market_description: str | None = None
    probability: str | None = None  # "12.5%" string
    handicap: str | None = None
    total: str | None = None
    participants: str | None = None
    suspended: bool = False
    stopped: bool = False
    winning: bool | None = None
    latest_bookmaker_update: datetime | None = None

    @property
    def decimal_odd(self) -> float | None:
        if self.value is None:
            return None
        try:
            return float(self.value)
        except ValueError:
            return None

    @property
    def implied_prob(self) -> float | None:
        d = self.decimal_odd
        if d is None or d <= 1.0:
            return None
        return 1.0 / d


# ── Fixture (top-level) + LiveScore ──────────────────────────────────────────


class Event(BaseModel):
    """Match event (goal, yellow card, substitution, etc.)."""

    model_config = _MODEL_CONFIG

    id: int
    fixture_id: int
    period_id: int
    participant_id: int | None = None
    type_id: int
    minute: int | None = None
    extra_minute: int | None = None
    player_id: int | None = None
    related_player_id: int | None = None
    player_name: str | None = None


class Lineup(BaseModel):
    """Team lineup entry (player + position)."""

    model_config = _MODEL_CONFIG

    id: int
    fixture_id: int
    player_id: int | None = None
    team_id: int
    type_id: int  # starting / bench / unavailable
    position_id: int | None = None
    jersey_number: int | None = None
    formation_position: int | None = None
    player_name: str | None = None


class Fixture(BaseModel):
    """A single fixture with optional includes attached.

    Includes that may be present (per request): participants, state,
    league, season, periods, scores, statistics, trends, pressure,
    predictions, odds, events, lineups, comments.
    """

    model_config = _MODEL_CONFIG

    id: int
    sport_id: int
    league_id: int
    season_id: int
    starting_at: datetime | None = None
    name: str | None = None
    state_id: int | None = None
    venue_id: int | None = None
    result_info: str | None = None
    leg: str | None = None
    has_odds: bool | None = None
    has_premium_odds: bool | None = None

    # Includes (None when not requested)
    participants: list[Participant] | None = None
    state: FixtureState | None = None
    league: League | None = None
    periods: list[Period] | None = None
    scores: list[Score] | None = None
    events: list[Event] | None = None
    lineups: list[Lineup] | None = None
    statistics: list[FixtureStatistic] | None = None
    trends: list[Trend] | None = None
    pressure: list[PressureMinute] | None = None
    predictions: list[Prediction] | None = None
    odds: list[Odd] | None = None

    # Convenience accessors

    def home_team(self) -> Participant | None:
        if not self.participants:
            return None
        for p in self.participants:
            # Sportmonks uses 'meta.location' on participants — not in our schema
            # yet; for now return first as home (matches API ordering convention).
            return p
        return None

    def away_team(self) -> Participant | None:
        if not self.participants or len(self.participants) < 2:
            return None
        return self.participants[1]

    def is_live(self) -> bool:
        if self.state is None:
            return False
        return self.state.developer_name.startswith("INPLAY")

    def current_minute(self) -> int | None:
        """Best-effort current minute: max minute across active periods."""
        if not self.periods:
            return None
        active = [p for p in self.periods if p.ticking or (p.minutes and not p.ended)]
        if not active:
            # FT or HT — return the last started minute
            ms = [p.minutes for p in self.periods if p.minutes is not None]
            return max(ms) if ms else None
        return max((p.minutes or 0) for p in active)


class LiveScore(BaseModel):
    """A livescore is structurally a Fixture (with state/scores). We keep
    the alias for clarity in callers."""

    model_config = _MODEL_CONFIG

    id: int
    league_id: int
    starting_at: datetime | None = None
    state_id: int | None = None


# ── API envelope ─────────────────────────────────────────────────────────────


class Pagination(BaseModel):
    model_config = ConfigDict(extra="ignore")

    count: int | None = None
    per_page: int | None = None
    current_page: int | None = None
    next_page: str | None = None
    has_more: bool | None = None


class RateLimitInfo(BaseModel):
    """Sportmonks per-entity rate limit reporting (per response meta)."""

    model_config = ConfigDict(extra="ignore")

    resets_in_seconds: int | None = None
    remaining: int | None = None
    requested_entity: str | None = None
