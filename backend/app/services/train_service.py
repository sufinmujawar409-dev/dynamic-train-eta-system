"""Train business operations independent of HTTP and data storage."""

from collections.abc import Sequence
from datetime import timedelta
from math import asin, cos, radians, sin, sqrt
from time import monotonic

from ..adapters.base import TrainDataProvider
from ..db.telemetry_repository import TelemetryRepository
from ..ml.eta_service import ETAPredictionService
from ..schemas import (
    ETAPrediction,
    RealtimeTrainEvent,
    Station,
    Train,
    TrainPosition,
)
from ..weather.base import WeatherProvider
from .alert_service import AlertService
from .realtime_service import RealtimeTrainTrackingService


class TrainNotFoundError(LookupError):
    """Raised when a requested train does not exist."""


class TrainService:
    """
    Central business layer for train data.

    Provider
        ↓
    RealtimeTrainTrackingService
        ↓
    Cached RealtimeTrainEvent
        ↓
    live / position / ETA / websocket

    This prevents every endpoint from independently
    requesting the NTES provider.
    """

    # =========================================================
    # CACHE SETTINGS
    # =========================================================

    REALTIME_CACHE_TTL_SECONDS = 20.0

    REALTIME_STALE_CACHE_TTL_SECONDS = 300.0

    ROUTE_CACHE_TTL_SECONDS = 300.0

    # =========================================================
    # INIT
    # =========================================================

    def __init__(
        self,
        data_source: TrainDataProvider,
        predictor: ETAPredictionService | None = None,
        weather: WeatherProvider | None = None,
        stale_after_seconds: int = 300,
        persistence: TelemetryRepository | None = None,
        alerts: AlertService | None = None,
    ) -> None:

        self._data_source = data_source

        self._predictor = (
            predictor
            or ETAPredictionService()
        )

        self._realtime = RealtimeTrainTrackingService(
            provider=self._data_source,
            predictor=self._predictor,
            weather=weather,
            stale_after_seconds=stale_after_seconds,
        )

        self._persistence = persistence

        self._alerts = (
            alerts
            or AlertService()
        )

        # -----------------------------------------------------
        # Previous events for alert detection.
        # -----------------------------------------------------

        self._previous_events: dict[
            str,
            RealtimeTrainEvent,
        ] = {}

        # -----------------------------------------------------
        # Fresh event cache.
        #
        # train_id ->
        # (monotonic_time, event)
        # -----------------------------------------------------

        self._event_cache: dict[
            str,
            tuple[
                float,
                RealtimeTrainEvent,
            ],
        ] = {}

        # -----------------------------------------------------
        # Last successful event cache.
        # -----------------------------------------------------

        self._stale_event_cache: dict[
            str,
            tuple[
                float,
                RealtimeTrainEvent,
            ],
        ] = {}

        # -----------------------------------------------------
        # Route cache.
        # -----------------------------------------------------

        self._route_cache: dict[
            str,
            tuple[
                float,
                Sequence[Station],
            ],
        ] = {}

    # =========================================================
    # BASIC HELPERS
    # =========================================================

    @staticmethod
    def _clean_train_id(
        train_id: str,
    ) -> str:
        return str(train_id).strip()

    # =========================================================
    # FRESH EVENT CACHE
    # =========================================================

    def _fresh_event(
        self,
        train_id: str,
    ) -> RealtimeTrainEvent | None:

        key = self._clean_train_id(
            train_id
        )

        cached = self._event_cache.get(
            key
        )

        if cached is None:
            return None

        cached_at, event = cached

        age = (
            monotonic()
            - cached_at
        )

        if (
            age
            > self.REALTIME_CACHE_TTL_SECONDS
        ):
            return None

        return event

    # =========================================================
    # STALE EVENT CACHE
    # =========================================================

    def _stale_event(
        self,
        train_id: str,
    ) -> RealtimeTrainEvent | None:

        key = self._clean_train_id(
            train_id
        )

        cached = (
            self._stale_event_cache.get(
                key
            )
        )

        if cached is None:
            return None

        cached_at, event = cached

        age = (
            monotonic()
            - cached_at
        )

        if (
            age
            > self.REALTIME_STALE_CACHE_TTL_SECONDS
        ):
            return None

        return event

    # =========================================================
    # STORE EVENT
    # =========================================================

    def _store_event(
        self,
        train_id: str,
        event: RealtimeTrainEvent,
    ) -> None:

        key = self._clean_train_id(
            train_id
        )

        now = monotonic()

        self._event_cache[key] = (
            now,
            event,
        )

        self._stale_event_cache[key] = (
            now,
            event,
        )

    # =========================================================
    # ROUTE CACHE
    # =========================================================

    def _cached_route(
        self,
        train_id: str,
    ) -> Sequence[Station] | None:

        key = self._clean_train_id(
            train_id
        )

        cached = self._route_cache.get(
            key
        )

        if cached is None:
            return None

        cached_at, route = cached

        age = (
            monotonic()
            - cached_at
        )

        if (
            age
            > self.ROUTE_CACHE_TTL_SECONDS
        ):
            return None

        return route

    def _store_route(
        self,
        train_id: str,
        route: Sequence[Station],
    ) -> None:

        key = self._clean_train_id(
            train_id
        )

        self._route_cache[key] = (
            monotonic(),
            list(route),
        )

    def clear_cache(
        self,
        train_id: str | None = None,
    ) -> None:
        """
        Clear service-level caches.

        clear_cache()
            clears all trains

        clear_cache("12919")
            clears one train
        """

        if train_id is None:

            self._event_cache.clear()
            self._stale_event_cache.clear()
            self._route_cache.clear()

            return

        key = self._clean_train_id(
            train_id
        )

        self._event_cache.pop(
            key,
            None,
        )

        self._stale_event_cache.pop(
            key,
            None,
        )

        self._route_cache.pop(
            key,
            None,
        )

    # =========================================================
    # GEO
    # =========================================================

    @staticmethod
    def _haversine_km(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:

        earth_radius_km = 6371.0088

        lat1_rad = radians(lat1)
        lat2_rad = radians(lat2)

        delta_lat = radians(
            lat2 - lat1
        )

        delta_lon = radians(
            lon2 - lon1
        )

        a = (
            sin(delta_lat / 2) ** 2
            + cos(lat1_rad)
            * cos(lat2_rad)
            * sin(delta_lon / 2) ** 2
        )

        a = max(
            0.0,
            min(
                1.0,
                a,
            ),
        )

        return (
            2
            * earth_radius_km
            * asin(
                sqrt(a)
            )
        )

    @staticmethod
    def _station_has_coordinates(
        station: Station,
    ) -> bool:

        if (
            station.latitude is None
            or station.longitude is None
        ):
            return False

        try:
            latitude = float(
                station.latitude
            )

            longitude = float(
                station.longitude
            )

        except (
            TypeError,
            ValueError,
        ):
            return False

        return (
            -90 <= latitude <= 90
            and -180 <= longitude <= 180
            and not (
                latitude == 0
                and longitude == 0
            )
        )

    def _distance_between_stations(
        self,
        first: Station,
        second: Station,
    ) -> float:

        if not self._station_has_coordinates(
            first
        ):
            return 0.0

        if not self._station_has_coordinates(
            second
        ):
            return 0.0

        return self._haversine_km(
            float(first.latitude),
            float(first.longitude),
            float(second.latitude),
            float(second.longitude),
        )

    # =========================================================
    # NEXT STATION
    # =========================================================

    def _find_next_station_index(
        self,
        route: Sequence[Station],
        event: RealtimeTrainEvent,
    ) -> int:

        target = (
            event.next_station
            or ""
        ).strip().lower()

        if not target:
            return 0

        for index, station in enumerate(
            route
        ):

            name = (
                station.name
                .strip()
                .lower()
            )

            code = (
                station.code
                .strip()
                .lower()
            )

            station_id = (
                station.station_id
                .strip()
                .lower()
            )

            if (
                name == target
                or code == target
                or station_id == target
                or name in target
                or target in name
            ):
                return index

        return 0

    # =========================================================
    # ROUTE CACHE ACCESS
    # =========================================================

    def _get_route_cached(
        self,
        train_id: str,
    ) -> Sequence[Station]:

        clean_train_id = (
            self._clean_train_id(
                train_id
            )
        )

        cached = self._cached_route(
            clean_train_id
        )

        if cached is not None:
            return cached

        route = (
            self._data_source.get_route(
                clean_train_id
            )
        )

        if route is None:
            raise TrainNotFoundError(
                clean_train_id
            )

        route = list(route)

        self._store_route(
            clean_train_id,
            route,
        )

        return route

    # =========================================================
    # TRAIN LIST
    # =========================================================

    def list_trains(
        self,
    ) -> Sequence[Train]:

        trains = (
            self._data_source.list_trains()
        )

        return [
            self._decorate_train(
                train
            )
            for train in trains
        ]

    # =========================================================
    # GET TRAIN
    # =========================================================

    def get_train(
        self,
        train_id: str,
    ) -> Train:

        clean_train_id = (
            self._clean_train_id(
                train_id
            )
        )

        train = (
            self._data_source.get_train(
                clean_train_id
            )
        )

        if train is None:
            raise TrainNotFoundError(
                clean_train_id
            )

        return self._decorate_train(
            train
        )

    # =========================================================
    # DECORATE TRAIN
    # =========================================================

    def _decorate_train(
        self,
        train: Train,
    ) -> Train:

        event = (
            self.get_realtime_event(
                train.train_id
            )
        )

        return train.model_copy(
            update={
                "source": event.source,
                "data_source": event.data_source,
                "is_live": event.is_live,
                "data_quality": event.data_quality,
                "last_updated": event.last_updated,
                "weather": event.weather,
                "eta": event.eta,
                "eta_confidence": (
                    event.eta_confidence
                ),
            }
        )

    # =========================================================
    # LIVE POSITION
    # =========================================================

    def get_live_position(
        self,
        train_id: str,
    ) -> TrainPosition:

        clean_train_id = (
            self._clean_train_id(
                train_id
            )
        )

        event = (
            self.get_realtime_event(
                clean_train_id
            )
        )

        return TrainPosition(
            train_id=event.train_id,

            latitude=event.latitude,
            longitude=event.longitude,

            speed_kmph=event.speed,

            current_delay=event.current_delay,

            recorded_at=event.timestamp,

            data_source=event.data_source,

            source=event.source,

            is_live=event.is_live,

            data_quality=event.data_quality,

            last_updated=event.last_updated,

            next_station=event.next_station,

            distance_to_next_station=(
                event.distance_to_next_station
            ),

            weather=event.weather,

            eta=event.eta,

            eta_confidence=(
                event.eta_confidence
            ),
        )

    # =========================================================
    # REALTIME EVENT
    # =========================================================

    def get_realtime_event(
        self,
        train_id: str,
    ) -> RealtimeTrainEvent:

        clean_train_id = (
            self._clean_train_id(
                train_id
            )
        )

        if not clean_train_id:
            raise TrainNotFoundError(
                train_id
            )

        # -----------------------------------------------------
        # FRESH CACHE
        # -----------------------------------------------------

        fresh = self._fresh_event(
            clean_train_id
        )

        if fresh is not None:
            return fresh

        # -----------------------------------------------------
        # PROVIDER / REALTIME SERVICE
        # -----------------------------------------------------

        try:

            event = (
                self._realtime.get_event(
                    clean_train_id
                )
            )

            # -------------------------------------------------
            # ALERTS
            # -------------------------------------------------

            previous = (
                self._previous_events.get(
                    clean_train_id
                )
            )

            alerts = (
                self._alerts.evaluate(
                    event,
                    previous,
                )
            )

            event = event.model_copy(
                update={
                    "alerts": alerts
                }
            )

            self._previous_events[
                clean_train_id
            ] = event

            # -------------------------------------------------
            # DATABASE PERSISTENCE
            # -------------------------------------------------

            if self._persistence is not None:

                try:

                    route = (
                        self._get_route_cached(
                            clean_train_id
                        )
                    )

                    self._persistence.persist_event(
                        event,
                        route,
                    )

                except Exception:
                    # Database failure should never
                    # break live dashboard.
                    pass

            # -------------------------------------------------
            # STORE CACHE
            # -------------------------------------------------

            self._store_event(
                clean_train_id,
                event,
            )

            return event

        except LookupError:

            raise TrainNotFoundError(
                clean_train_id
            ) from None

        except Exception:

            # -------------------------------------------------
            # LAST KNOWN EVENT
            # -------------------------------------------------

            stale = self._stale_event(
                clean_train_id
            )

            if stale is not None:
                return stale

            raise

    # =========================================================
    # ALERTS
    # =========================================================

    def list_alerts(
        self,
        **filters: str | bool | None,
    ):
        return self._alerts.list(
            **filters
        )

    def get_alert(
        self,
        alert_id: str,
    ):
        return self._alerts.get(
            alert_id
        )

    def acknowledge_alert(
        self,
        alert_id: str,
    ):
        return self._alerts.acknowledge(
            alert_id
        )

    # =========================================================
    # ANALYTICS
    # =========================================================

    def analytics(
        self,
    ) -> dict[str, object]:

        from .analytics_service import (
            AnalyticsService
        )

        events = list(
            self._previous_events.values()
        )

        return AnalyticsService().summarize(
            events,
            self._alerts.list(),
        )

    # =========================================================
    # ROUTE
    # =========================================================

    def get_route(
        self,
        train_id: str,
    ) -> Sequence[Station]:

        return self._get_route_cached(
            train_id
        )

    # =========================================================
    # ETA
    # =========================================================

    def get_eta(
        self,
        train_id: str,
    ) -> Sequence[ETAPrediction]:

        clean_train_id = (
            self._clean_train_id(
                train_id
            )
        )

        # -----------------------------------------------------
        # ONE realtime event
        # -----------------------------------------------------

        event = (
            self.get_realtime_event(
                clean_train_id
            )
        )

        # -----------------------------------------------------
        # CACHED ROUTE
        # -----------------------------------------------------

        route = (
            self._get_route_cached(
                clean_train_id
            )
        )

        if not route:
            return []

        # -----------------------------------------------------
        # Observation timestamp
        # -----------------------------------------------------

        now = event.timestamp

        # -----------------------------------------------------
        # Weather factor
        # -----------------------------------------------------

        weather_factor = {
            "LOW": 1.0,
            "MEDIUM": 1.10,
            "HIGH": 1.25,
        }.get(
            event.weather.weather_delay_risk,
            1.0,
        )

        # -----------------------------------------------------
        # NEXT STATION INDEX
        # -----------------------------------------------------

        next_index = (
            self._find_next_station_index(
                route,
                event,
            )
        )

        upcoming_route = route[
            next_index:
        ]

        if not upcoming_route:
            upcoming_route = route[-1:]

        # -----------------------------------------------------
        # DISTANCE FROM LIVE EVENT
        # -----------------------------------------------------

        live_distance = 0.0

        try:
            live_distance = max(
                0.0,
                float(
                    event.distance_to_next_station
                ),
            )
        except (
            TypeError,
            ValueError,
        ):
            live_distance = 0.0

        # -----------------------------------------------------
        # CUMULATIVE DISTANCE
        # -----------------------------------------------------

        cumulative_distance = (
            live_distance
        )

        previous_station = (
            upcoming_route[0]
        )

        predictions: list[
            ETAPrediction
        ] = []

        # =====================================================
        # EACH UPCOMING STATION
        # =====================================================

        for station_index, station in enumerate(
            upcoming_route
        ):

            if station_index == 0:

                distance_remaining = max(
                    0.0,
                    cumulative_distance,
                )

            else:

                segment_distance = (
                    self._distance_between_stations(
                        previous_station,
                        station,
                    )
                )

                cumulative_distance += max(
                    0.0,
                    segment_distance,
                )

                distance_remaining = max(
                    0.0,
                    cumulative_distance,
                )

            previous_station = station

            # -------------------------------------------------
            # Current speed
            #
            # Can be:
            # - provider speed
            # - GPS-derived speed
            # - distance-derived speed
            # - 0 if insufficient samples
            # -------------------------------------------------

            current_speed = max(
                float(
                    event.speed
                ),
                1.0,
            )

            # -------------------------------------------------
            # MODEL
            # -------------------------------------------------

            predicted_minutes = (
                self._predictor.predict_minutes(
                    current_speed=current_speed,

                    current_delay=max(
                        float(
                            event.current_delay
                        ),
                        0.0,
                    ),

                    distance_remaining=(
                        distance_remaining
                    ),

                    historical_delay=2.0,

                    previous_station_delay=max(
                        float(
                            event.current_delay
                        ),
                        0.0,
                    ),

                    section_average_speed=60.0,

                    weather_factor=(
                        weather_factor
                    ),

                    congestion_factor=1.0,

                    signal_halt_minutes=0.0,
                )
            )

            minutes_remaining = max(
                0,
                int(
                    round(
                        float(
                            predicted_minutes
                        )
                    )
                ),
            )

            estimated_arrival = (
                now
                + timedelta(
                    minutes=minutes_remaining
                )
            )

            # -------------------------------------------------
            # CONFIDENCE
            # -------------------------------------------------

            confidence_score = float(
                event.eta_confidence
                or 0.80
            )

            confidence_score = max(
                0.0,
                min(
                    1.0,
                    confidence_score,
                ),
            )

            # -------------------------------------------------
            # DATA QUALITY
            # -------------------------------------------------

            data_quality = (
                event.data_quality
            )

            # -------------------------------------------------
            # PREDICTION SOURCE
            # -------------------------------------------------

            prediction_source = (
                event.prediction_source
            )

            # -------------------------------------------------
            # BUILD PREDICTION
            # -------------------------------------------------

            prediction = ETAPrediction(
                train_id=clean_train_id,

                station_id=(
                    station.station_id
                ),

                station_name=(
                    station.name
                ),

                next_station=(
                    event.next_station
                ),

                current_delay=max(
                    0,
                    int(
                        round(
                            float(
                                event.current_delay
                            )
                        )
                    ),
                ),

                estimated_arrival=(
                    estimated_arrival
                ),

                minutes_remaining=(
                    minutes_remaining
                ),

                confidence=(
                    confidence_score
                ),

                model_version=str(
                    self._predictor.metadata.get(
                        "model_version",
                        "unknown",
                    )
                ),

                data_source=(
                    event.data_source
                ),

                source=(
                    event.source
                ),

                is_live=(
                    event.is_live
                ),

                data_quality=(
                    data_quality
                ),

                last_updated=(
                    event.last_updated
                ),

                weather=(
                    event.weather
                ),

                predicted_delay=max(
                    0,
                    int(
                        round(
                            float(
                                event.predicted_delay
                            )
                        )
                    ),
                ),

                confidence_score=(
                    confidence_score
                ),

                confidence_level=(
                    event.confidence_level
                ),

                prediction_source=(
                    prediction_source
                ),
            )

            predictions.append(
                prediction
            )

        return predictions


__all__ = [
    "TrainService",
    "TrainNotFoundError",
]