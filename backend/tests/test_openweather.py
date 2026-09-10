from datetime import datetime, timezone

import httpx

from backend.app.config import Settings
from backend.app.schemas import WeatherData
from backend.app.weather.provider import LiveWeatherProvider


class FakeResponse:
    def __init__(self, payload: dict[str, object], error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error

    def raise_for_status(self) -> None:
        if self.error:
            raise self.error

    def json(self) -> dict[str, object]:
        return self.payload


def settings_with_key() -> Settings:
    return Settings(openweather_api_key="test-key", weather_timeout_seconds=1)


def test_openweather_success_is_live_and_normalized() -> None:
    payload = {
        "dt": 1789050000,
        "main": {"temp": 26.5, "feels_like": 27.2, "humidity": 71},
        "wind": {"speed": 4.5},
        "visibility": 9000,
        "weather": [{"description": "light rain"}],
        "rain": {"1h": 1.2},
    }
    provider = LiveWeatherProvider(settings_with_key(), client=type("Client", (), {"get": lambda *args, **kwargs: FakeResponse(payload)})())

    weather = provider.get_weather(28.6, 77.2, datetime.now(timezone.utc))

    assert weather.available is True
    assert weather.source == "OPENWEATHER"
    assert weather.data_quality == "LIVE"
    assert weather.temperature == 26.5
    assert weather.feels_like == 27.2
    assert weather.humidity == 71
    assert weather.precipitation == 1.2
    assert weather.observation_timestamp is not None


def test_openweather_missing_key_is_unavailable() -> None:
    provider = LiveWeatherProvider(Settings(openweather_api_key=""), client=None)
    weather = provider.get_weather(28.6, 77.2, datetime.now(timezone.utc))
    assert weather == WeatherData.unavailable()


def test_openweather_timeout_is_unavailable() -> None:
    class TimeoutClient:
        def get(self, *args, **kwargs):
            raise httpx.TimeoutException("timed out")

    provider = LiveWeatherProvider(settings_with_key(), client=TimeoutClient())
    weather = provider.get_weather(28.6, 77.2, datetime.now(timezone.utc))
    assert weather.available is False
    assert weather.data_quality == "UNAVAILABLE"
    assert weather.source == "UNAVAILABLE"


def test_openweather_malformed_payload_is_unavailable() -> None:
    class MalformedClient:
        def get(self, *args, **kwargs):
            return FakeResponse({"main": {"humidity": "not-a-number"}})

    provider = LiveWeatherProvider(settings_with_key(), client=MalformedClient())
    weather = provider.get_weather(28.6, 77.2, datetime.now(timezone.utc))
    assert weather.available is False
    assert weather.data_quality == "UNAVAILABLE"
