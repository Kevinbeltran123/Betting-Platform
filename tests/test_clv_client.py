"""Odds API client tests — CLV-01."""

import pytest
from pytest_httpx import HTTPXMock


PINNACLE_RESPONSE = {
    "id": "event-uuid-123",
    "bookmakers": [
        {
            "key": "pinnacle",
            "title": "Pinnacle",
            "markets": [
                {
                    "key": "h2h",
                    "outcomes": [
                        {"name": "Arsenal", "price": 2.10},
                        {"name": "Draw", "price": 3.40},
                        {"name": "Chelsea", "price": 3.80},
                    ],
                }
            ],
        }
    ],
}


class TestOddsApiClient:
    """CLV-01: OddsApiClient fetches Pinnacle closing odds."""

    async def test_fetch_pinnacle_closing_odds_returns_bookmaker_dict(
        self, httpx_mock: HTTPXMock, settings
    ):
        """fetch_pinnacle_closing_odds() returns the Pinnacle bookmaker dict."""
        httpx_mock.add_response(status_code=200, json=PINNACLE_RESPONSE)
        from bip.clv.client import OddsApiClient
        async with OddsApiClient(api_key=settings.odds_api_key) as client:
            result = await client.fetch_pinnacle_closing_odds(
                sport_key="soccer_epl",
                event_id="event-uuid-123",
                market_key="h2h",
            )
        assert result is not None
        assert result["key"] == "pinnacle"

    async def test_returns_none_when_pinnacle_not_in_bookmakers(
        self, httpx_mock: HTTPXMock, settings
    ):
        """Returns None when Pinnacle is not in the bookmakers list."""
        httpx_mock.add_response(
            status_code=200,
            json={"id": "event-uuid-123", "bookmakers": []},
        )
        from bip.clv.client import OddsApiClient
        async with OddsApiClient(api_key=settings.odds_api_key) as client:
            result = await client.fetch_pinnacle_closing_odds(
                sport_key="soccer_epl",
                event_id="event-uuid-123",
                market_key="h2h",
            )
        assert result is None

    async def test_api_key_sent_as_query_param(
        self, httpx_mock: HTTPXMock, settings
    ):
        """apiKey query parameter must be present — Odds API v4 auth."""
        httpx_mock.add_response(status_code=200, json=PINNACLE_RESPONSE)
        from bip.clv.client import OddsApiClient
        async with OddsApiClient(api_key="test-odds-key-xyz") as client:
            await client.fetch_pinnacle_closing_odds(
                sport_key="soccer_epl",
                event_id="event-uuid-123",
                market_key="h2h",
            )
        request = httpx_mock.get_requests()[0]
        assert "apiKey=test-odds-key-xyz" in str(request.url)

    async def test_retries_on_429(self, httpx_mock: HTTPXMock, settings):
        """429 responses trigger retry with exponential backoff."""
        httpx_mock.add_response(status_code=429)
        httpx_mock.add_response(status_code=200, json=PINNACLE_RESPONSE)
        from bip.clv.client import OddsApiClient
        async with OddsApiClient(api_key=settings.odds_api_key) as client:
            result = await client.fetch_pinnacle_closing_odds(
                sport_key="soccer_epl",
                event_id="event-uuid-123",
                market_key="h2h",
            )
        assert result is not None
