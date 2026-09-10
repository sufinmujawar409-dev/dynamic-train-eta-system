"""OpenWeather Current Weather API adapter."""

from datetime import datetime
from typing import Any

import httpx
from pydantic import ValidationError

from ..config import Settings
from ..schemas import WeatherData
from .base import WeatherUnavailable


class LiveWeatherProvider:
    """Fetch authorized OpenWeather observations for a train coordinate."""

    def __init__(self, settings: Settings, client: Any = httpx) -> None:
        self._settings = settings
        self._client = client

    def get_weather(self, latitude: float, longitude: float, observed_at: datetime) -> WeatherData:
        if not self._settings.openweather_api_key:
            return WeatherData.unavailable()
        try:
            response = self._client.get(
                self._settings.openweather_api_base_url,
                params={
                    "lat": latitude,
                    "lon": longitude,
                    "appid": self._settings.openweather_api_key,
                    "units": "metric",
                },
                timeout=self._settings.weather_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise TypeError("response payload is not an object")
            weather = payload.get("weather", [{}])[0]
            main = payload.get("main", {})
            wind = payload.get("wind", {})
            rain = payload.get("rain", {})
            observation_timestamp = datetime.fromtimestamp(payload["dt"], tz=observed_at.tzinfo)
            return WeatherData(
                temperature=main.get("temp"),
                feels_like=main.get("feels_like"),
                humidity=main.get("humidity"),
                wind_speed=wind.get("speed"),
                visibility=payload.get("visibility"),
                precipitation=rain.get("1h", rain.get("3h")),
                weather_condition=weather.get("description"),
                weather_delay_risk="LOW",
                weather_last_updated=observation_timestamp,
                observation_timestamp=observation_timestamp,
                source="OPENWEATHER",
                data_quality="LIVE",
                available=True,
                message="",
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError, ValidationError):
            return WeatherData.unavailable()
