from datetime import datetime, timezone

import httpx
import pytest

from backend.app.adapters.base import ProviderConfigurationError, ProviderUnavailable
from backend.app.adapters.railradar import RailRadarProvider
from backend.app.config import Settings


class FakeResponse:
    status_code = 200

    def __init__(self, payload: object, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("provider error", request=None, response=None)

    def json(self) -> object:
        return self._payload


def provider(client) -> RailRadarProvider:
    return RailRadarProvider(
        Settings(
            railway_api_key="mock-secret",
            railradar_api_base_url="https://railradar.example.test",
        ),
        client=client,
    )


def payload() -> dict[str, object]:
    return {
        "data": {
            "trainNumber": "101",
            "trainName": "RailRadar Express",
            "lastUpdatedAt": "2026-09-10T12:00:00Z",
            "delayMinutes": 4,
            "isLive": True,
            "currentLocation": {"stationCode": "CEN", "speedKmh": 72},
            "nextHalt": {"stationCode": "MID"},
            "route": [{"stationCode": "CEN", "stationName": "Central", "lat": 28.61, "lng": 77.21, "delayMinutes": 4, "status": "DEPARTED"}],
        },
        "geometry": {"type": "Point", "coordinates": [77.21, 28.61]},
    }


def test_railradar_normalizes_mocked_response_without_live_request() -> None:
    class Client:
        def get(self, url, *, params, headers, timeout):
            assert url == "https://railradar.example.test/v1/trains/101/live"
            assert params == {"authoritative": "true", "geometry": "true", "format": "geojson", "includeCoordinates": "true"}
            assert headers == {"Authorization": "Bearer mock-secret"}
            assert timeout > 0
            return FakeResponse(payload())

    telemetry = provider(Client()).fetch_live_status("101")
    assert telemetry.train_number == "101"
    assert telemetry.train_name == "RailRadar Express"
    assert telemetry.latitude == 28.61
    assert telemetry.longitude == 77.21
    assert telemetry.speed_kmph == 72
    assert telemetry.current_delay == 4
    assert telemetry.current_station == "CEN"
    assert telemetry.next_station == "MID"
    assert telemetry.source == "LIVE"
    assert telemetry.data_quality == "LIVE"


def test_railradar_missing_configuration_is_safe() -> None:
    with pytest.raises(ProviderConfigurationError):
        RailRadarProvider(Settings(railway_api_key="mock-secret", railradar_api_base_url="")).fetch_live_status("101")


def test_railradar_rate_limit_and_bad_payload_are_unavailable() -> None:
    class RateLimited:
        def get(self, *args, **kwargs):
            return FakeResponse({}, status_code=429)

    with pytest.raises(ProviderUnavailable, match="rate limit"):
        provider(RateLimited()).fetch_live_status("101")

    class BadJson:
        def get(self, *args, **kwargs):
            return FakeResponse({"unexpected": True})

    with pytest.raises(ProviderUnavailable, match="normalized"):
        provider(BadJson()).fetch_live_status("101")


def test_railradar_invalid_coordinates_are_rejected() -> None:
    invalid = payload()
    invalid["geometry"] = {"type": "Point", "coordinates": [77.21, 91]}

    class Client:
        def get(self, *args, **kwargs):
            return FakeResponse(invalid)

    with pytest.raises(ProviderUnavailable, match="normalized"):
        provider(Client()).fetch_live_status("101")


def test_railradar_timeout_is_unavailable() -> None:
    class Timeout:
        def get(self, *args, **kwargs):
            raise httpx.TimeoutException("timeout")

    with pytest.raises(ProviderUnavailable, match="timed out"):
        provider(Timeout()).fetch_live_status("101")
