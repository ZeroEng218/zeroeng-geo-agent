"""
Unit tests for the deterministic lookup logic in geo_agent.py, using real
fixture responses captured from the live FCC Census Area API (this sandbox's
network policy blocks outbound calls to geo.fcc.gov, so these tests mock the
HTTP layer with actual recorded responses instead of hitting the network).

Run:
    python test_geo_lookup.py
"""

import asyncio
from unittest.mock import AsyncMock, patch

from geo_agent import _lookup_state

# Captured verbatim from:
# https://geo.fcc.gov/api/census/area?lat=30.2672&lon=-97.7431&format=json
AUSTIN_TX_RESPONSE = {
    "input": {"lat": 30.2672, "lon": -97.7431, "censusYear": "2020"},
    "results": [
        {
            "block_fips": "484530011032007",
            "county_fips": "48453",
            "county_name": "Travis County",
            "state_fips": "48",
            "state_code": "TX",
            "state_name": "Texas",
            "block_pop_2020": 10,
        }
    ],
}

# Captured verbatim from:
# https://geo.fcc.gov/api/census/area?lat=25.0&lon=-70.0&format=json
OCEAN_RESPONSE = {
    "input": {"lat": 25, "lon": -70, "censusYear": "2020"},
    "results": [],
}


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


async def test_found_state():
    with patch("geo_agent.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = FakeResponse(200, AUSTIN_TX_RESPONSE)
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await _lookup_state(30.2672, -97.7431)

    assert result == {
        "status": "found",
        "state_name": "Texas",
        "state_code": "TX",
        "county_name": "Travis County",
        "state_fips": "48",
    }, result
    print("test_found_state: PASS ->", result)


async def test_outside_us():
    with patch("geo_agent.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = FakeResponse(200, OCEAN_RESPONSE)
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await _lookup_state(25.0, -70.0)

    assert result == {"status": "outside_us"}, result
    print("test_outside_us: PASS ->", result)


async def test_http_error():
    with patch("geo_agent.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = FakeResponse(500, {})
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await _lookup_state(30.2672, -97.7431)

    assert result["status"] == "error", result
    assert "500" in result["message"], result
    print("test_http_error: PASS ->", result)


async def main():
    await test_found_state()
    await test_outside_us()
    await test_http_error()
    print("\nAll tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
