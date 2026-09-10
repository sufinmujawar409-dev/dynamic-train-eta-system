"""Train business operations independent of HTTP and data storage."""

from collections.abc import Sequence
from datetime import timedelta

from ..adapters.base import TrainDataProvider
from ..schemas import ETAPrediction, RealtimeTrainEvent, Station, Train, TrainPosition
from ..ml.eta_service import ETAPredictionService
from ..db.telemetry_repository import TelemetryRepository
from .realtime_service import RealtimeTrainTrackingService
from ..weather.base import WeatherProvider
from .alert_service import AlertService


class TrainNotFoundError(LookupError):
    """Raised when a requested train does not exist."""


class TrainService:
    def __init__(
        self,
        data_source: TrainDataProvider,
        predictor: ETAPredictionService | None = None,
        weather: WeatherProvider | None = None,
        stale_after_seconds: int = 30,
        persistence: TelemetryRepository | None = None,
        alerts: AlertService | None = None,
    ) -> None:
        self._data_source = data_source
        self._predictor = predictor or ETAPredictionService()
        self._realtime = RealtimeTrainTrackingService(
            self._data_source,
            self._predictor,
            weather=weather,
            stale_after_seconds=stale_after_seconds,
        )
        self._persistence = persistence
        self._alerts = alerts or AlertService()
        self._previous_events: dict[str, RealtimeTrainEvent] = {}

    def list_trains(self) -> Sequence[Train]:
        return [self._decorate_train(train) for train in self._data_source.list_trains()]

    def get_train(self, train_id: str) -> Train:
        train = self._data_source.get_train(train_id)
        if train is None:
            raise TrainNotFoundError(train_id)
        return self._decorate_train(train)

    def _decorate_train(self, train: Train) -> Train:
        event = self._realtime.get_event(train.train_id)
        return train.model_copy(
            update={
                "source": event.source,
                "data_source": event.data_source,
                "is_live": event.is_live,
                "data_quality": event.data_quality,
                "last_updated": event.last_updated,
                "weather": event.weather,
                "eta": event.eta,
                "eta_confidence": event.eta_confidence,
            }
        )

    def get_live_position(self, train_id: str) -> TrainPosition:
        position = self._data_source.get_live_position(train_id)
        if position is None:
            raise TrainNotFoundError(train_id)
        event = self.get_realtime_event(train_id)
        return position.model_copy(
            update={
                "source": event.source,
                "is_live": event.is_live,
                "data_quality": event.data_quality,
                "last_updated": event.last_updated,
                "next_station": event.next_station,
                "distance_to_next_station": event.distance_to_next_station,
                "weather": event.weather,
                "eta": event.eta,
                "eta_confidence": event.eta_confidence,
            }
        )

    def get_realtime_event(self, train_id: str) -> RealtimeTrainEvent:
        try:
            event = self._realtime.get_event(train_id)
            previous = self._previous_events.get(train_id)
            new_alerts = self._alerts.evaluate(event, previous)
            event = event.model_copy(update={"alerts": new_alerts})
            self._previous_events[train_id] = event
            if self._persistence is not None:
                route = self._data_source.get_route(train_id) or []
                self._persistence.persist_event(event, route)
            return event
        except LookupError:
            raise TrainNotFoundError(train_id) from None

    def list_alerts(self, **filters: str | bool | None):
        return self._alerts.list(**filters)

    def get_alert(self, alert_id: str):
        return self._alerts.get(alert_id)

    def acknowledge_alert(self, alert_id: str):
        return self._alerts.acknowledge(alert_id)

    def analytics(self) -> dict[str, object]:
        from .analytics_service import AnalyticsService

        events = list(self._previous_events.values())
        return AnalyticsService().summarize(events, self._alerts.list())

    def get_route(self, train_id: str) -> Sequence[Station]:
        route = self._data_source.get_route(train_id)
        if route is None:
            raise TrainNotFoundError(train_id)
        return route

    def get_eta(self, train_id: str) -> Sequence[ETAPrediction]:
        route = self._data_source.get_route(train_id)
        position = self._data_source.get_live_position(train_id)
        if route is None or position is None:
            raise TrainNotFoundError(train_id)
        event = self.get_realtime_event(train_id)
        now = position.recorded_at
        weather_factor = {"LOW": 1.0, "MEDIUM": 1.1, "HIGH": 1.25}.get(event.weather.weather_delay_risk, 1.0)
        predictions = []
        for station in route[1:]:
            minutes = self._predictor.predict_minutes(
                current_speed=position.speed_kmph,
                current_delay=position.current_delay,
                distance_remaining=station.sequence * 10,
                historical_delay=2,
                previous_station_delay=1,
                section_average_speed=60,
                weather_factor=weather_factor,
                congestion_factor=1,
                signal_halt_minutes=0,
            )
            predictions.append(
                ETAPrediction(
                    train_id=train_id,
                    station_id=station.station_id,
                    station_name=station.name,
                    next_station=event.next_station,
                    current_delay=position.current_delay,
                    estimated_arrival=now + timedelta(minutes=minutes),
                    minutes_remaining=minutes,
                    confidence=0.8,
                    model_version=self._predictor.metadata["model_version"],
                    source=event.source,
                    is_live=event.is_live,
                    data_quality=event.data_quality,
                    last_updated=event.last_updated,
                    weather=event.weather,
                    predicted_delay=event.predicted_delay,
                    confidence_score=event.eta_confidence,
                    confidence_level=event.confidence_level,
                    prediction_source=event.prediction_source,
                )
            )
        return predictions
