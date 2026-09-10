"""Live railway data provider backed by the configured RailRadar adapter."""

from collections.abc import Mapping, Sequence
from typing import Any

from ..config import Settings
from ..schemas import (
    Station,
    Train,
    TrainPosition,
    TrainTelemetry,
    WeatherData,
)
from .base import TrainDataProvider, ProviderConfigurationError
from .railradar import RailRadarProvider


class LiveRailwayDataProvider(TrainDataProvider):
    """Production live-provider boundary using RailRadar."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._provider = RailRadarProvider(settings)

    def _ensure_configured(self) -> None:
        if not self._settings.railway_api_base_url:
            raise ProviderConfigurationError(
                "RAILWAY_API_BASE_URL is required for DATA_PROVIDER=live"
            )

        if not self._settings.railway_api_key:
            raise ProviderConfigurationError(
                "RAILWAY_API_KEY is required for DATA_PROVIDER=live"
            )

    def list_trains(self) -> Sequence[Train]:
        self._ensure_configured()
        return []

    def get_train(self, train_id: str) -> Train | None:
        self._ensure_configured()

        telemetry = self._provider.fetch_live_status(train_id)

        route = telemetry.route or []

        # Get origin and destination from the RailRadar route.
        origin = "Unknown"
        destination = "Unknown"

        if route:
            first_station = route[0]
            last_station = route[-1]

            origin = str(
                first_station.get("name")
                or first_station.get("stationName")
                or first_station.get("code")
                or "Unknown"
            )

            destination = str(
                last_station.get("name")
                or last_station.get("stationName")
                or last_station.get("code")
                or "Unknown"
            )

        status = "RUNNING" if telemetry.is_live else "UNAVAILABLE"

        return Train(
            train_id=telemetry.train_id,
            name=telemetry.train_name or f"Train {telemetry.train_number}",
            number=telemetry.train_number,
            status=status,
            origin=origin,
            destination=destination,
            data_source=telemetry.data_source,
            source=telemetry.source or telemetry.data_source,
            is_live=telemetry.is_live,
            data_quality=telemetry.data_quality,
            last_updated=telemetry.last_updated,
            weather=WeatherData.unavailable(),
            eta=None,
            eta_confidence=None,
        )

    def get_route(self, train_id: str) -> Sequence[Station] | None:
        self._ensure_configured()

        telemetry = self._provider.fetch_live_status(train_id)
        return telemetry.route or []

    def get_telemetry(
        self, train_id: str
    ) -> TrainTelemetry | Mapping[str, Any] | None:
        self._ensure_configured()

        return self._provider.fetch_live_status(train_id)

    def get_live_position(self, train_id: str) -> TrainPosition | None:
        self._ensure_configured()

        telemetry = self._provider.fetch_live_status(train_id)

        return TrainPosition(
            train_id=telemetry.train_id,
            latitude=telemetry.latitude,
            longitude=telemetry.longitude,
            speed_kmph=telemetry.speed_kmph,
            current_delay=telemetry.current_delay,
            recorded_at=telemetry.recorded_at,
            source=telemetry.source or telemetry.data_source,
            data_source=telemetry.data_source,
            is_live=telemetry.is_live,
            data_quality=telemetry.data_quality,
            last_updated=telemetry.last_updated,
            next_station=telemetry.next_station,
            distance_to_next_station=telemetry.distance_to_next_station,
            weather=WeatherData.unavailable(),
            eta=None,
            eta_confidence=None,
        )