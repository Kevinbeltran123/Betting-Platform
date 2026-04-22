"""Async API-Football v3 client with tenacity retry.

All methods use @retry with exponential backoff covering 429, 500, 502, 503, 504.
Authentication: x-apisports-key header set at client construction (not per-request).

DATA-01: Retry/rate-limit handling via tenacity.
T-05-04: API key loaded from settings env var — never logged.
"""

from __future__ import annotations

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger(__name__)

BASE_URL = "https://v3.football.api-sports.io"


def is_retryable_http_error(exc: BaseException) -> bool:
    """Predicate: retry on rate-limit, server errors, and network failures."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {429, 500, 502, 503, 504}
    return isinstance(exc, (httpx.ConnectError, httpx.TimeoutException))


class ApiFootballClient:
    """Async API-Football v3 client.

    Usage::

        async with ApiFootballClient(api_key=settings.api_football_key) as client:
            raw = await client.get_fixtures(league_id=39, date="2026-04-22")

    All 5 endpoint methods are decorated with @retry (tenacity) covering:
    - HTTP 429 (rate limit)
    - HTTP 500/502/503/504 (server errors)
    - httpx.ConnectError / httpx.TimeoutException (network failures)

    Retry strategy: exponential backoff, min=2s, max=60s, up to 5 attempts.
    On exhaustion, re-raises the original exception.
    """

    def __init__(self, api_key: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"x-apisports-key": api_key},
            timeout=httpx.Timeout(30.0),
        )

    async def __aenter__(self) -> ApiFootballClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying httpx client."""
        await self._client.aclose()

    @retry(
        retry=retry_if_exception(is_retryable_http_error),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def get_fixtures(self, league_id: int, date: str) -> dict:
        """GET /fixtures?league={id}&date={YYYY-MM-DD}.

        Args:
            league_id: API-Football league ID (e.g., 39 for Premier League).
            date: Date string in YYYY-MM-DD format.

        Returns:
            Parsed JSON response dict from API-Football.
        """
        params = {"league": league_id, "date": date}
        logger.info("api_football_request", endpoint="/fixtures", params=params)
        response = await self._client.get("/fixtures", params=params)
        response.raise_for_status()
        return response.json()

    @retry(
        retry=retry_if_exception(is_retryable_http_error),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def get_lineups(self, fixture_id: int) -> dict:
        """GET /fixtures/lineups?fixture={id}.

        Args:
            fixture_id: API-Football fixture ID.

        Returns:
            Parsed JSON response dict from API-Football.
        """
        params = {"fixture": fixture_id}
        logger.info("api_football_request", endpoint="/fixtures/lineups", params=params)
        response = await self._client.get("/fixtures/lineups", params=params)
        response.raise_for_status()
        return response.json()

    @retry(
        retry=retry_if_exception(is_retryable_http_error),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def get_statistics(self, fixture_id: int) -> dict:
        """GET /fixtures/statistics?fixture={id}.

        Args:
            fixture_id: API-Football fixture ID.

        Returns:
            Parsed JSON response dict from API-Football.
        """
        params = {"fixture": fixture_id}
        logger.info("api_football_request", endpoint="/fixtures/statistics", params=params)
        response = await self._client.get("/fixtures/statistics", params=params)
        response.raise_for_status()
        return response.json()

    @retry(
        retry=retry_if_exception(is_retryable_http_error),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def get_injuries(self, league_id: int, season: int) -> dict:
        """GET /injuries?league={id}&season={season}.

        Args:
            league_id: API-Football league ID.
            season: Season year (e.g., 2025 for 2025/26 season).

        Returns:
            Parsed JSON response dict from API-Football.
        """
        params = {"league": league_id, "season": season}
        logger.info("api_football_request", endpoint="/injuries", params=params)
        response = await self._client.get("/injuries", params=params)
        response.raise_for_status()
        return response.json()

    @retry(
        retry=retry_if_exception(is_retryable_http_error),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def get_h2h(self, team1_id: int, team2_id: int) -> dict:
        """GET /fixtures/headtohead?h2h={team1_id}-{team2_id}.

        Args:
            team1_id: Home team ID.
            team2_id: Away team ID.

        Returns:
            Parsed JSON response dict from API-Football.
        """
        params = {"h2h": f"{team1_id}-{team2_id}"}
        logger.info("api_football_request", endpoint="/fixtures/headtohead", params=params)
        response = await self._client.get("/fixtures/headtohead", params=params)
        response.raise_for_status()
        return response.json()
