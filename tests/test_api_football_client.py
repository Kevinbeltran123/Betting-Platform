"""API-Football client tests — DATA-01 (retry/rate-limit)."""

import pytest
from pytest_httpx import HTTPXMock


class TestApiFootballClient:
    """DATA-01: ApiFootballClient retries on 429 with exponential backoff."""

    async def test_get_fixtures_returns_response_dict(self, httpx_mock: HTTPXMock, settings):
        """Successful GET /fixtures returns parsed JSON dict."""
        httpx_mock.add_response(
            status_code=200,
            json={"response": [{"fixture": {"id": 12345}}]},
        )
        from bip.sports.football.client import ApiFootballClient
        async with ApiFootballClient(api_key=settings.api_football_key) as client:
            result = await client.get_fixtures(league_id=39, date="2026-04-22")
        assert "response" in result

    async def test_get_fixtures_retries_on_429(self, httpx_mock: HTTPXMock, settings):
        """On 429, client must retry and succeed on subsequent attempt."""
        # First call: rate limited; second call: success
        httpx_mock.add_response(status_code=429)
        httpx_mock.add_response(
            status_code=200,
            json={"response": []},
        )
        from bip.sports.football.client import ApiFootballClient
        # tenacity will retry — test must not raise
        async with ApiFootballClient(api_key=settings.api_football_key) as client:
            result = await client.get_fixtures(league_id=39, date="2026-04-22")
        assert result == {"response": []}

    async def test_api_key_in_request_header(self, httpx_mock: HTTPXMock, settings):
        """x-apisports-key header must be present on every request."""
        httpx_mock.add_response(status_code=200, json={"response": []})
        from bip.sports.football.client import ApiFootballClient
        async with ApiFootballClient(api_key="test-key-xyz") as client:
            await client.get_fixtures(league_id=39, date="2026-04-22")
        request = httpx_mock.get_requests()[0]
        assert request.headers.get("x-apisports-key") == "test-key-xyz"

    async def test_get_lineups_retries_on_500(self, httpx_mock: HTTPXMock, settings):
        """Server error 500 is retryable — client retries and succeeds."""
        httpx_mock.add_response(status_code=500)
        httpx_mock.add_response(status_code=200, json={"response": []})
        from bip.sports.football.client import ApiFootballClient
        async with ApiFootballClient(api_key=settings.api_football_key) as client:
            result = await client.get_lineups(fixture_id=12345)
        assert "response" in result
