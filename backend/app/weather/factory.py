"""Configuration-driven weather provider construction."""

from ..config import Settings
from .base import DemoWeatherProvider, WeatherProvider
from .provider import LiveWeatherProvider


def build_weather_provider(settings: Settings) -> WeatherProvider:
    if settings.openweather_api_key or settings.weather_api_base_url or settings.weather_api_key:
        return LiveWeatherProvider(settings)
    return DemoWeatherProvider()
