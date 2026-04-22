"""The Odds API v4 async client for Pinnacle closing odds.

Used at kickoff + 105 minutes for CLV snapshot (D-04a).
Rookie tier: 500 requests/month — use sparingly.
"""


import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from bip.core.errors import ApiError

logger = structlog.get_logger(__name__)

# Market key mapping: internal key -> The Odds API market key (RESEARCH.md Pattern 5)
MARKET_KEY_MAP: dict[str, str] = {
    "onextwo": "h2h",
    "btts": "btts",
    "ou": "totals",
    "ah": "alternate_spreads",
}


def _is_retryable_http_error(exc: BaseException) -> bool:
    """Retry on 429 (rate limit), 500, 502, 503, 504."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {429, 500, 502, 503, 504}
    return isinstance(exc, (httpx.ConnectError, httpx.TimeoutException))


class OddsApiClient:
    """Async Odds API v4 client for Pinnacle closing odds."""

    BASE_URL = "https://api.the-odds-api.com"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=httpx.Timeout(30.0),
        )

    async def __aenter__(self) -> "OddsApiClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    @retry(
        retry=retry_if_exception(_is_retryable_http_error),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def fetch_pinnacle_closing_odds(
        self,
        sport_key: str,
        event_id: str,
        market_key: str,
    ) -> dict | None:
        """Fetch Pinnacle closing odds for a specific event.

        Returns:
            Pinnacle bookmaker dict or None if Pinnacle not available.

        Raises:
            ApiError: After 3 retries if The Odds API is unreachable.
        """
        logger.info(
            "fetch_pinnacle_odds",
            sport_key=sport_key,
            event_id=event_id,
            market_key=market_key,
        )
        try:
            response = await self._client.get(
                f"/v4/sports/{sport_key}/events/{event_id}/odds",
                params={
                    "apiKey": self._api_key,
                    "bookmakers": "pinnacle",
                    "markets": market_key,
                    "oddsFormat": "decimal",
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {429, 500, 502, 503, 504}:
                raise
            raise ApiError(
                f"Odds API returned {exc.response.status_code} for event {event_id}"
            ) from exc

        data = response.json()
        for bookmaker in data.get("bookmakers", []):
            if bookmaker["key"] == "pinnacle":
                return bookmaker
        return None

    def map_market_key(self, internal_key: str) -> str | None:
        """Convert internal market key to Odds API market key.

        Returns None for markets not supported by The Odds API (e.g., corners).
        """
        return MARKET_KEY_MAP.get(internal_key)
