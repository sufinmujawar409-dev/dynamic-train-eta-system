"""Provider-independent realtime train tracking and ETA enrichment."""

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

from ..adapters.base import TrainDataAdapter
from ..ml.eta_service import ETAPredictionService
from ..schemas import RealtimeTrainEvent, TrainTelemetry
from ..weather.base import UnavailableWeatherProvider, WeatherProvider, WeatherUnavailable


class StaleTrainDataError(ValueError):
    """Raised when a provider snapshot is older than the configured threshold."""


class RealtimeTrainTrackingService:
    """Validate provider snapshots and turn them into dashboard events."""

    def __init__(
        self,
        provider: TrainDataAdapter,
        predictor: ETAPredictionService,
        weather: WeatherProvider | None = None,
        stale_after_seconds: int = 30,
    ) -> None:
        self._provider = provider
        self._predictor = predictor
        self._weather = weather or UnavailableWeatherProvider()
        self._stale_after_seconds = stale_after_seconds

    def get_event(self, train_id: str) -> RealtimeTrainEvent:
        train = self._provider.get_train(train_id)
        route = self._provider.get_route(train_id)
        telemetry_raw: TrainTelemetry | Mapping[str, Any] | None = self._provider.get_telemetry(train_id)
        if train is None or route is None or telemetry_raw is None or len(route) < 2:
            raise LookupError(train_id)

        telemetry = TrainTelemetry.model_validate(telemetry_raw)
        recorded_at = telemetry.timestamp or telemetry.recorded_at
        age_seconds = (datetime.now(timezone.utc) - recorded_at).total_seconds()
        is_stale = age_seconds > self._stale_after_seconds
        segment = min(max(0, round((telemetry.longitude - 77.2090) / 0.016)), len(route) - 2)
        next_station = route[segment + 1]
        try:
            weather = self._weather.get_weather(telemetry.latitude, telemetry.longitude, recorded_at)
        except WeatherUnavailable:
            weather = UnavailableWeatherProvider().get_weather(telemetry.latitude, telemetry.longitude, recorded_at)
        weather_factor = {"LOW": 1.0, "MEDIUM": 1.1, "HIGH": 1.25}.get(weather.weather_delay_risk, 1.0)
        prediction_source = (
            "LIVE"
            if telemetry.is_live and not is_stale
            else "DEMO"
            if telemetry.data_source == "DEMO"
            else "UNAVAILABLE"
        )
        prediction = self._predictor.predict_realtime(
            observed_at=recorded_at,
            current_speed=max(telemetry.speed_kmph, 1),
            current_delay=telemetry.current_delay,
            distance_to_next_station=max(0, telemetry.distance_to_next_station or (next_station.sequence - segment) * 10),
            historical_delay=2,
            previous_station_delay=telemetry.current_delay,
            average_sectional_speed=60,
            weather_factor=weather_factor,
            congestion_factor=1,
            prediction_source=prediction_source,
        )
        return RealtimeTrainEvent(
            train_id=train.train_id,
            train_number=train.number,
            latitude=telemetry.latitude,
            longitude=telemetry.longitude,
            speed=round(telemetry.speed_kmph, 1),
            current_delay=telemetry.current_delay,
            next_station=next_station.name,
            eta=prediction.predicted_arrival,
            timestamp=recorded_at,
            data_source=telemetry.data_source,
            data_quality="STALE" if is_stale else telemetry.data_quality,
            source=telemetry.source or telemetry.data_source,
            is_live=telemetry.is_live and not is_stale,
            last_updated=telemetry.last_updated or recorded_at,
            distance_to_next_station=telemetry.distance_to_next_station,
            weather=weather,
            eta_confidence=prediction.confidence_score,
            predicted_delay=prediction.predicted_delay,
            confidence_level=prediction.confidence_level,
            prediction_source=prediction.prediction_source,
        )


__all__ = ["RealtimeTrainTrackingService"]
