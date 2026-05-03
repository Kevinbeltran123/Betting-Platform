"""Shared enums and type aliases used across the system."""

from enum import StrEnum


class League(StrEnum):
    """Target leagues for prediction."""

    premier_league = "premier_league"
    la_liga = "la_liga"
    bundesliga = "bundesliga"
    serie_a = "serie_a"
    ligue_1 = "ligue_1"


class PickStatus(StrEnum):
    """Status of a betting pick."""

    pending = "pending"
    won = "won"
    lost = "lost"
    void = "void"
    push = "push"
    filtered = "filtered"   # D-03: did not clear edge / market_cap / claude_api_unavailable
    rejected = "rejected"   # D-03: Claude Role C returned REJECT (never sent)


class CalibrationMethod(StrEnum):
    """Probability calibration methods."""

    isotonic = "isotonic"
    platt = "platt"


class AggregationPeriod(StrEnum):
    """Time periods for performance aggregation."""

    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    season = "season"
    all_time = "all_time"
