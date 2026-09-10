"""Weather provider contracts."""

from datetime import datetime
from typing import Protocol

from ..schemas import WeatherData


class WeatherProvider(Protocol):
    def get_weather(self, latitude: float, longitude: float, observed_at: datetime) -> WeatherData: ...


class WeatherUnavailable(Exception):
    """Raised when no authorized weather source can provide data."""


class UnavailableWeatherProvider:
    """Explicit no-data fallback; it never invents weather values."""

    def get_weather(self, latitude: float, longitude: float, observed_at: datetime) -> WeatherData:
        return WeatherData.unavailable()


class DemoWeatherProvider(UnavailableWeatherProvider):
    """DEMO weather adapter that deliberately exposes no synthetic conditions."""

    def get_weather(self, latitude: float, longitude: float, observed_at: datetime) -> WeatherData:
        return WeatherData(
            source="DEMO",
            data_quality="DEMO",
            message="DEMO weather unavailable",
        )
