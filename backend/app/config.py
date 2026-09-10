"""Application configuration loaded from environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


def _load_root_env() -> dict[str, str]:
	"""Load simple KEY=VALUE pairs without logging or exposing secret values."""
	env_path = Path(__file__).resolve().parents[2] / ".env"
	if not env_path.exists():
		return {}
	values: dict[str, str] = {}
	for line in env_path.read_text(encoding="utf-8").splitlines():
		line = line.strip()
		if line and not line.startswith("#") and "=" in line:
			key, value = line.split("=", 1)
			values[key.strip()] = value.strip().strip('"').strip("'")
	return values


_ROOT_ENV = _load_root_env()


def _env(name: str, default: str = "") -> str:
	return os.getenv(name, _ROOT_ENV.get(name, default))


DATABASE_URL = _env("DATABASE_URL", "sqlite:///./dynamic_eta_dev.db")
ENVIRONMENT = _env("ENVIRONMENT", "development")


@dataclass(frozen=True)
class Settings:
	environment: str = ENVIRONMENT
	data_provider: Literal["demo", "live"] = _env("DATA_PROVIDER", "demo").lower()  # type: ignore[assignment]
	railway_api_base_url: str = _env("RAILWAY_API_BASE_URL")
	railway_api_key: str = _env("RAILWAY_API_KEY")
	weather_api_base_url: str = _env("WEATHER_API_BASE_URL")
	weather_api_key: str = _env("WEATHER_API_KEY")
	openweather_api_key: str = _env("OPENWEATHER_API_KEY")
	openweather_api_base_url: str = _env(
		"OPENWEATHER_API_BASE_URL", "https://api.openweathermap.org/data/2.5/weather"
	)
	railradar_api_base_url: str = _env("RAILRADAR_API_BASE_URL", "https://api.railradar.in")
	weather_timeout_seconds: float = float(_env("WEATHER_TIMEOUT_SECONDS", "5"))
	stale_after_seconds: int = int(_env("STALE_AFTER_SECONDS", "30"))
	realtime_interval_seconds: float = float(_env("REALTIME_INTERVAL_SECONDS", "2"))

	def validate(self) -> "Settings":
		if self.data_provider not in {"demo", "live"}:
			raise ValueError("DATA_PROVIDER must be 'demo' or 'live'")
		if self.stale_after_seconds <= 0:
			raise ValueError("STALE_AFTER_SECONDS must be positive")
		if self.realtime_interval_seconds <= 0:
			raise ValueError("REALTIME_INTERVAL_SECONDS must be positive")
		return self


settings = Settings().validate()
