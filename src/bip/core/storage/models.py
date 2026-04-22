"""Pydantic data models for Supabase entities.

These are the Python-side representations of the 6 Supabase tables.
Each model provides validation and a to_supabase_dict() method for inserts.
"""

from datetime import date, datetime

from pydantic import BaseModel, Field

from bip.core.types import AggregationPeriod, PickStatus


class Prediction(BaseModel):
    """Model output for a match/market combination."""

    fixture_id: int
    league: str
    sport: str = "football"
    market: str
    home_team: str
    away_team: str
    kickoff_utc: datetime
    probabilities: dict
    model_version: str
    is_lineup_adjusted: bool = False

    def to_supabase_dict(self) -> dict:
        """Convert to dict for Supabase insert."""
        data = self.model_dump()
        data["kickoff_utc"] = self.kickoff_utc.isoformat()
        return data


class Pick(BaseModel):
    """A prediction that met the edge threshold — a recommended bet."""

    prediction_id: int | None = None
    fixture_id: int
    league: str
    sport: str = "football"
    market: str
    selection: str
    model_probability: float
    implied_probability: float
    edge: float
    best_odds: float
    bookmaker: str
    kelly_fraction: float | None = None
    suggested_stake: float | None = None
    status: PickStatus = PickStatus.pending

    def to_supabase_dict(self) -> dict:
        """Convert to dict for Supabase insert."""
        data = self.model_dump()
        data["status"] = self.status.value
        return data


class OddsSnapshot(BaseModel):
    """Odds captured at a point in time for CLV tracking."""

    fixture_id: int
    sport: str = "football"
    market: str
    bookmaker: str
    odds: dict
    is_closing: bool = False
    captured_at: datetime | None = None

    def to_supabase_dict(self) -> dict:
        """Convert to dict for Supabase insert."""
        data = self.model_dump()
        if self.captured_at:
            data["captured_at"] = self.captured_at.isoformat()
        return data


class Result(BaseModel):
    """Match outcome."""

    fixture_id: int
    league: str
    sport: str = "football"
    home_team: str
    away_team: str
    home_goals: int | None = None
    away_goals: int | None = None
    home_corners: int | None = None
    away_corners: int | None = None
    match_stats: dict | None = None
    kickoff_utc: datetime
    finished_at: datetime | None = None

    def to_supabase_dict(self) -> dict:
        """Convert to dict for Supabase insert."""
        data = self.model_dump()
        data["kickoff_utc"] = self.kickoff_utc.isoformat()
        if self.finished_at:
            data["finished_at"] = self.finished_at.isoformat()
        return data


class ClvRecord(BaseModel):
    """Per-bet CLV (Closing Line Value) calculation."""

    pick_id: int
    fixture_id: int
    sport: str = "football"
    market: str
    odds_at_pick: float
    pinnacle_closing_odds: float | None = None
    implied_prob_at_pick: float
    implied_prob_closing: float | None = None
    clv_percentage: float | None = None
    odds_fetched_at: datetime | None = None

    def to_supabase_dict(self) -> dict:
        """Convert to dict for Supabase insert."""
        data = self.model_dump()
        if self.odds_fetched_at:
            data["odds_fetched_at"] = self.odds_fetched_at.isoformat()
        return data


class PerformanceMetric(BaseModel):
    """Aggregated performance metrics by league/market/period."""

    league: str
    sport: str = "football"
    market: str
    period: AggregationPeriod
    period_start: date
    period_end: date
    total_picks: int = Field(default=0)
    won: int = Field(default=0)
    lost: int = Field(default=0)
    void: int = Field(default=0)
    total_staked: float = Field(default=0.0)
    total_pnl: float = Field(default=0.0)
    roi: float | None = None
    yield_pct: float | None = None
    avg_clv: float | None = None
    avg_edge: float | None = None

    def to_supabase_dict(self) -> dict:
        """Convert to dict for Supabase insert."""
        data = self.model_dump()
        data["period"] = self.period.value
        data["period_start"] = self.period_start.isoformat()
        data["period_end"] = self.period_end.isoformat()
        return data
