"""CLV (Closing Line Value) recorder.

CLV formula (CLV-02): clv_percentage = (odds_at_pick / closing_odds - 1) * 100
Example: (2.10 / 2.00 - 1) * 100 = +5.0 (we got better odds than closing line)

Rolling average (CLV-03): tracks rolling 50-pick CLV for trend alerting.
If average drops below +1%, alert is triggered (Phase 4 sends Telegram warning).
"""

from datetime import UTC, datetime

import structlog

from bip.core.errors import ClvError
from bip.core.storage.models import ClvRecord
from bip.core.storage.repositories import ClvRecordRepository
from supabase import Client

logger = structlog.get_logger(__name__)


def calculate_clv_percentage(odds_at_pick: float, closing_odds: float) -> float:
    """Calculate CLV percentage.

    Formula: (odds_at_pick / closing_odds - 1) * 100

    Args:
        odds_at_pick: Decimal odds we recorded when placing the pick.
        closing_odds: Pinnacle decimal closing odds (at kickoff + 105min).

    Returns:
        CLV percentage. Positive = we beat the closing line.

    Raises:
        ClvError: If closing_odds is zero or negative.
    """
    if closing_odds <= 0:
        raise ClvError(f"Invalid closing_odds={closing_odds} — must be positive")
    return (odds_at_pick / closing_odds - 1) * 100


def compute_rolling_clv_average(clv_values: list[float]) -> float:
    """Compute rolling average using the last 50 values.

    CLV-03: If this average drops below +1.0, the caller should trigger
    a Telegram warning to pause betting and audit.

    Args:
        clv_values: All historical CLV percentages in chronological order.

    Returns:
        Mean of the last 50 values (or all values if fewer than 50).
    """
    window = clv_values[-50:] if len(clv_values) > 50 else clv_values
    if not window:
        return 0.0
    return sum(window) / len(window)


class ClvRecorder:
    """Records CLV measurements to Supabase.

    Uses ClvRecordRepository for all database interactions.
    Captures odds_fetched_at timestamp for data-freshness monitoring (D-04c).
    """

    def __init__(self, client: Client) -> None:
        self._repo = ClvRecordRepository(client=client)

    def record(
        self,
        pick_id: int,
        fixture_id: int,
        sport: str,
        market: str,
        odds_at_pick: float,
        pinnacle_closing_odds: float,
        odds_fetched_at: datetime | None = None,
    ) -> ClvRecord:
        """Calculate CLV and persist to Supabase clv_records table.

        Args:
            pick_id: FK to picks table.
            fixture_id: API-Football fixture ID.
            sport: Sport string (e.g., "football").
            market: Market key string (e.g., "btts").
            odds_at_pick: Decimal odds recorded at pick time.
            pinnacle_closing_odds: Pinnacle decimal closing odds.
            odds_fetched_at: When Pinnacle odds were fetched (D-04c).

        Returns:
            ClvRecord with clv_percentage populated.
        """
        if odds_fetched_at is None:
            odds_fetched_at = datetime.now(UTC)

        clv_pct = calculate_clv_percentage(odds_at_pick, pinnacle_closing_odds)

        clv_record = ClvRecord(
            pick_id=pick_id,
            fixture_id=fixture_id,
            sport=sport,
            market=market,
            odds_at_pick=odds_at_pick,
            pinnacle_closing_odds=pinnacle_closing_odds,
            implied_prob_at_pick=1.0 / odds_at_pick,
            implied_prob_closing=1.0 / pinnacle_closing_odds,
            clv_percentage=clv_pct,
            odds_fetched_at=odds_fetched_at,
        )

        try:
            self._repo.insert(clv_record)
        except Exception as exc:
            raise ClvError(
                f"Failed to record CLV for pick_id={pick_id}: {exc}"
            ) from exc

        logger.info(
            "clv_recorded",
            pick_id=pick_id,
            fixture_id=fixture_id,
            market=market,
            odds_at_pick=odds_at_pick,
            pinnacle_closing_odds=pinnacle_closing_odds,
            clv_percentage=clv_pct,
        )

        return clv_record
