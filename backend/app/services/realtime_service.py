"""Provider-independent realtime train tracking and ETA enrichment."""

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from ..adapters.base import TrainDataAdapter
from ..ml.eta_service import ETAPredictionService
from ..schemas import RealtimeTrainEvent, TrainTelemetry
from ..weather.base import (
    UnavailableWeatherProvider,
    WeatherProvider,
    WeatherUnavailable,
)


class StaleTrainDataError(ValueError):
    """Raised when a provider snapshot is older than the configured threshold."""


class RealtimeTrainTrackingService:
    """Validate provider snapshots and turn them into dashboard events."""

    DEFAULT_STALE_AFTER_SECONDS = 180

    # Maximum allowed fallback speed.
    MAX_ESTIMATED_SPEED_KMPH = 180.0

    # Ignore very small GPS movement caused by coordinate noise.
    MIN_MOVEMENT_KM = 0.03

    # Valid time window for GPS/distance speed estimation.
    MIN_SPEED_SAMPLE_SECONDS = 5.0
    MAX_SPEED_SAMPLE_SECONDS = 600.0

    # Minimum distance change used for distance-based estimation.
    MIN_DISTANCE_CHANGE_KM = 0.02

    def __init__(
        self,
        provider: TrainDataAdapter,
        predictor: ETAPredictionService,
        weather: WeatherProvider | None = None,
        stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
    ) -> None:
        self._provider = provider
        self._predictor = predictor

        self._weather = (
            weather
            or UnavailableWeatherProvider()
        )

        self._stale_after_seconds = max(
            60,
            stale_after_seconds,
        )

        # -----------------------------------------------------
        # Previous GPS observations
        #
        # train_id ->
        # (latitude, longitude, recorded_at)
        # -----------------------------------------------------
        self._previous_positions: dict[
            str,
            tuple[
                float,
                float,
                datetime,
            ],
        ] = {}

        # -----------------------------------------------------
        # Previous distance observations
        #
        # train_id ->
        # (
        #     next_station_identifier,
        #     distance_km,
        #     recorded_at,
        # )
        #
        # Used when provider speed = 0 and GPS coordinates
        # are unchanged.
        # -----------------------------------------------------
        self._previous_distances: dict[
            str,
            tuple[
                str,
                float,
                datetime,
            ],
        ] = {}

    # =========================================================
    # TIMESTAMP HELPERS
    # =========================================================

    @staticmethod
    def _normalize_timestamp(
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None:
            return value.replace(
                tzinfo=timezone.utc
            )

        return value.astimezone(
            timezone.utc
        )

    @staticmethod
    def _age_seconds(
        timestamp: datetime,
    ) -> float:
        timestamp = (
            RealtimeTrainTrackingService
            ._normalize_timestamp(
                timestamp
            )
        )

        age = (
            datetime.now(timezone.utc)
            - timestamp
        ).total_seconds()

        return max(
            0.0,
            age,
        )

    # =========================================================
    # GEO HELPERS
    # =========================================================

    @staticmethod
    def _haversine_km(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> float:
        """Calculate distance between two GPS points in km."""

        from math import (
            atan2,
            cos,
            radians,
            sin,
            sqrt,
        )

        earth_radius_km = 6371.0

        d_lat = radians(
            lat2 - lat1
        )

        d_lon = radians(
            lon2 - lon1
        )

        a = (
            sin(d_lat / 2) ** 2
            + cos(radians(lat1))
            * cos(radians(lat2))
            * sin(d_lon / 2) ** 2
        )

        # Protect against tiny floating-point overflow.
        a = min(
            1.0,
            max(
                0.0,
                a,
            ),
        )

        return (
            earth_radius_km
            * 2
            * atan2(
                sqrt(a),
                sqrt(
                    max(
                        0.0,
                        1.0 - a,
                    )
                ),
            )
        )

    @staticmethod
    def _station_coordinates(
        station: Any,
    ) -> tuple[float, float] | None:
        latitude = getattr(
            station,
            "latitude",
            None,
        )

        longitude = getattr(
            station,
            "longitude",
            None,
        )

        if (
            latitude is None
            or longitude is None
        ):
            return None

        try:
            latitude = float(
                latitude
            )

            longitude = float(
                longitude
            )
        except (
            TypeError,
            ValueError,
        ):
            return None

        if (
            not -90 <= latitude <= 90
            or not -180 <= longitude <= 180
        ):
            return None

        return (
            latitude,
            longitude,
        )

    # =========================================================
    # STATION IDENTIFIER
    # =========================================================

    @staticmethod
    def _station_identifier(
        station: Any,
    ) -> str:
        """
        Build a stable identifier for the next station.

        Code is preferred because it is stable. Name is used
        as fallback.
        """

        if station is None:
            return ""

        code = getattr(
            station,
            "code",
            None,
        )

        if code:
            return str(
                code
            ).strip().upper()

        name = getattr(
            station,
            "name",
            None,
        )

        if name:
            return str(
                name
            ).strip().lower()

        return ""

    # =========================================================
    # GPS SPEED FALLBACK
    # =========================================================

    def _estimate_speed_from_gps(
        self,
        train_id: str,
        latitude: float,
        longitude: float,
        recorded_at: datetime,
    ) -> float:
        """
        Estimate train speed from two consecutive GPS observations.

        Provider-reported speed is preferred. This method is only
        used when provider speed is zero or unavailable.
        """

        previous = (
            self._previous_positions.get(
                train_id
            )
        )

        current_position = (
            latitude,
            longitude,
            recorded_at,
        )

        # Always store the latest sample.
        self._previous_positions[
            train_id
        ] = current_position

        if previous is None:
            return 0.0

        (
            previous_latitude,
            previous_longitude,
            previous_timestamp,
        ) = previous

        elapsed_seconds = (
            recorded_at
            - previous_timestamp
        ).total_seconds()

        if (
            elapsed_seconds
            < self.MIN_SPEED_SAMPLE_SECONDS
            or elapsed_seconds
            > self.MAX_SPEED_SAMPLE_SECONDS
        ):
            return 0.0

        distance_km = (
            self._haversine_km(
                previous_latitude,
                previous_longitude,
                latitude,
                longitude,
            )
        )

        # GPS jitter.
        if (
            distance_km
            < self.MIN_MOVEMENT_KM
        ):
            return 0.0

        speed_kmph = (
            distance_km
            / elapsed_seconds
            * 3600.0
        )

        if (
            speed_kmph <= 0
            or speed_kmph
            > self.MAX_ESTIMATED_SPEED_KMPH
        ):
            return 0.0

        return round(
            speed_kmph,
            1,
        )

    # =========================================================
    # DISTANCE CHANGE SPEED FALLBACK
    # =========================================================

    def _estimate_speed_from_distance(
        self,
        train_id: str,
        distance_to_next_station: float,
        next_station: Any,
        recorded_at: datetime,
    ) -> float:
        """
        Estimate train speed from decreasing distance to the
        same next station.

        Example:

            previous = 2.63 km
            current  = 1.13 km
            elapsed  = 402 sec

        Speed ~= 13.4 km/h

        This is an inferred speed, not provider-reported speed.
        """

        current_distance = max(
            0.0,
            float(
                distance_to_next_station
            ),
        )

        station_id = (
            self._station_identifier(
                next_station
            )
        )

        previous = (
            self._previous_distances.get(
                train_id
            )
        )

        current_sample = (
            station_id,
            current_distance,
            recorded_at,
        )

        # Always update the stored sample.
        self._previous_distances[
            train_id
        ] = current_sample

        if previous is None:
            return 0.0

        (
            previous_station_id,
            previous_distance,
            previous_timestamp,
        ) = previous

        # Do not compare distances belonging to different
        # next stations.
        if (
            previous_station_id
            != station_id
        ):
            return 0.0

        elapsed_seconds = (
            recorded_at
            - previous_timestamp
        ).total_seconds()

        if (
            elapsed_seconds
            < self.MIN_SPEED_SAMPLE_SECONDS
            or elapsed_seconds
            > self.MAX_SPEED_SAMPLE_SECONDS
        ):
            return 0.0

        distance_reduced_km = (
            previous_distance
            - current_distance
        )

        # Distance must actually decrease.
        if (
            distance_reduced_km
            < self.MIN_DISTANCE_CHANGE_KM
        ):
            return 0.0

        speed_kmph = (
            distance_reduced_km
            / elapsed_seconds
            * 3600.0
        )

        if (
            speed_kmph <= 0
            or speed_kmph
            > self.MAX_ESTIMATED_SPEED_KMPH
        ):
            return 0.0

        return round(
            speed_kmph,
            1,
        )

    # =========================================================
    # SPEED RESOLUTION
    # =========================================================

    def _resolve_speed(
        self,
        train_id: str,
        telemetry: TrainTelemetry,
        recorded_at: datetime,
        next_station: Any,
        distance_to_next_station: float,
    ) -> float:
        """
        Resolve the speed used by the rest of the system.

        Priority:

        1. Provider-reported speed
        2. GPS movement speed
        3. Distance-to-next-station speed
        4. Zero
        """

        try:
            provider_speed = float(
                telemetry.speed_kmph
            )
        except (
            TypeError,
            ValueError,
        ):
            provider_speed = 0.0

        # -----------------------------------------------------
        # 1. Provider speed
        # -----------------------------------------------------

        if (
            provider_speed > 0
            and provider_speed
            <= self.MAX_ESTIMATED_SPEED_KMPH
        ):
            # Keep GPS history updated.
            self._previous_positions[
                train_id
            ] = (
                float(
                    telemetry.latitude
                ),
                float(
                    telemetry.longitude
                ),
                recorded_at,
            )

            # Keep distance history updated too.
            self._estimate_speed_from_distance(
                train_id=train_id,
                distance_to_next_station=(
                    distance_to_next_station
                ),
                next_station=next_station,
                recorded_at=recorded_at,
            )

            return round(
                provider_speed,
                1,
            )

        # -----------------------------------------------------
        # 2. GPS movement fallback
        # -----------------------------------------------------

        gps_speed = (
            self._estimate_speed_from_gps(
                train_id=train_id,
                latitude=float(
                    telemetry.latitude
                ),
                longitude=float(
                    telemetry.longitude
                ),
                recorded_at=recorded_at,
            )
        )

        # Distance history must still be updated even when
        # GPS fallback succeeds.
        distance_speed = (
            self._estimate_speed_from_distance(
                train_id=train_id,
                distance_to_next_station=(
                    distance_to_next_station
                ),
                next_station=next_station,
                recorded_at=recorded_at,
            )
        )

        if gps_speed > 0:
            return round(
                gps_speed,
                1,
            )

        # -----------------------------------------------------
        # 3. Distance fallback
        # -----------------------------------------------------

        if distance_speed > 0:
            return round(
                distance_speed,
                1,
            )

        # -----------------------------------------------------
        # 4. Genuine stop / insufficient data
        # -----------------------------------------------------

        return 0.0

    # =========================================================
    # ROUTE HELPERS
    # =========================================================

    @staticmethod
    def _find_station_index(
        route: list[Any],
        station_value: str | None,
    ) -> int | None:
        if not station_value:
            return None

        target = (
            str(station_value)
            .strip()
            .lower()
        )

        if not target:
            return None

        for index, station in enumerate(
            route
        ):
            station_code = getattr(
                station,
                "code",
                None,
            )

            station_name = getattr(
                station,
                "name",
                None,
            )

            station_id = getattr(
                station,
                "station_id",
                None,
            )

            values = [
                station_code,
                station_name,
                station_id,
            ]

            for value in values:
                if value is None:
                    continue

                if (
                    str(value)
                    .strip()
                    .lower()
                    == target
                ):
                    return index

        return None

    def _find_nearest_station_index(
        self,
        route: list[Any],
        latitude: float,
        longitude: float,
    ) -> int | None:
        """Find nearest route station to current GPS."""

        closest_index: int | None = None

        closest_distance = float(
            "inf"
        )

        for index, station in enumerate(
            route
        ):
            coordinates = (
                self._station_coordinates(
                    station
                )
            )

            if coordinates is None:
                continue

            (
                station_latitude,
                station_longitude,
            ) = coordinates

            distance = (
                self._haversine_km(
                    latitude,
                    longitude,
                    station_latitude,
                    station_longitude,
                )
            )

            if (
                distance
                < closest_distance
            ):
                closest_distance = distance
                closest_index = index

        return closest_index

    def _find_next_station(
        self,
        route: list[Any],
        telemetry: TrainTelemetry,
    ) -> Any | None:
        """
        Select next station using provider station data
        first, then GPS proximity, then route fallback.
        """

        # -----------------------------------------------------
        # 1. Provider next station
        # -----------------------------------------------------

        next_index = (
            self._find_station_index(
                route,
                telemetry.next_station,
            )
        )

        if next_index is not None:
            return route[next_index]

        # -----------------------------------------------------
        # 2. Current station -> next station
        # -----------------------------------------------------

        current_index = (
            self._find_station_index(
                route,
                telemetry.current_station,
            )
        )

        if (
            current_index is not None
            and current_index + 1
            < len(route)
        ):
            return route[
                current_index + 1
            ]

        # -----------------------------------------------------
        # 3. GPS nearest station -> next
        # -----------------------------------------------------

        nearest_index = (
            self._find_nearest_station_index(
                route=route,
                latitude=float(
                    telemetry.latitude
                ),
                longitude=float(
                    telemetry.longitude
                ),
            )
        )

        if (
            nearest_index is not None
            and nearest_index + 1
            < len(route)
        ):
            return route[
                nearest_index + 1
            ]

        # -----------------------------------------------------
        # 4. Safe fallback
        # -----------------------------------------------------

        return (
            route[1]
            if len(route) > 1
            else None
        )

    # =========================================================
    # DISTANCE TO NEXT STATION
    # =========================================================

    def _distance_to_station(
        self,
        telemetry: TrainTelemetry,
        station: Any,
    ) -> float | None:
        """
        Use provider distance when valid.

        Otherwise calculate GPS -> station distance.
        """

        provider_distance = (
            telemetry.distance_to_next_station
        )

        if (
            provider_distance is not None
        ):
            try:
                value = float(
                    provider_distance
                )

                if (
                    value >= 0
                    and value < 1000
                ):
                    return value

            except (
                TypeError,
                ValueError,
            ):
                pass

        station_coordinates = (
            self._station_coordinates(
                station
            )
        )

        if station_coordinates is None:
            return 0.0

        (
            station_latitude,
            station_longitude,
        ) = station_coordinates

        return max(
            0.0,
            self._haversine_km(
                float(
                    telemetry.latitude
                ),
                float(
                    telemetry.longitude
                ),
                station_latitude,
                station_longitude,
            ),
        )

    # =========================================================
    # DATA QUALITY
    # =========================================================

    def _is_snapshot_stale(
        self,
        recorded_at: datetime,
    ) -> bool:
        age_seconds = (
            self._age_seconds(
                recorded_at
            )
        )

        return (
            age_seconds
            > self._stale_after_seconds
        )

    # =========================================================
    # MAIN EVENT
    # =========================================================

    def get_event(
        self,
        train_id: str,
    ) -> RealtimeTrainEvent:

        train = self._provider.get_train(
            train_id
        )

        route_raw = self._provider.get_route(
            train_id
        )

        telemetry_raw: (
            TrainTelemetry
            | Mapping[str, Any]
            | None
        ) = self._provider.get_telemetry(
            train_id
        )

        if (
            train is None
            or route_raw is None
            or telemetry_raw is None
            or len(route_raw) < 2
        ):
            raise LookupError(
                train_id
            )

        route = list(route_raw)

        telemetry = (
            TrainTelemetry.model_validate(
                telemetry_raw
            )
        )

        recorded_at = (
            telemetry.timestamp
            or telemetry.recorded_at
        )

        recorded_at = (
            self._normalize_timestamp(
                recorded_at
            )
        )

        # -----------------------------------------------------
        # Freshness
        # -----------------------------------------------------

        age_seconds = (
            self._age_seconds(
                recorded_at
            )
        )

        is_stale = (
            age_seconds
            > self._stale_after_seconds
        )

        # -----------------------------------------------------
        # Next station
        # -----------------------------------------------------

        next_station = (
            self._find_next_station(
                route,
                telemetry,
            )
        )

        if next_station is None:
            raise LookupError(
                train_id
            )

        # -----------------------------------------------------
        # Distance to next station
        # -----------------------------------------------------

        distance_to_next_station = (
            self._distance_to_station(
                telemetry,
                next_station,
            )
        )

        if (
            distance_to_next_station
            is None
        ):
            distance_to_next_station = 0.0

        distance_to_next_station = max(
            0.0,
            float(
                distance_to_next_station
            ),
        )

        # -----------------------------------------------------
        # Resolve actual speed
        #
        # IMPORTANT:
        # Next station + distance are calculated BEFORE speed
        # because the distance fallback needs them.
        # -----------------------------------------------------

        resolved_speed = (
            self._resolve_speed(
                train_id=train_id,
                telemetry=telemetry,
                recorded_at=recorded_at,
                next_station=next_station,
                distance_to_next_station=(
                    distance_to_next_station
                ),
            )
        )

        # -----------------------------------------------------
        # Weather
        # -----------------------------------------------------

        try:
            weather = (
                self._weather.get_weather(
                    float(
                        telemetry.latitude
                    ),
                    float(
                        telemetry.longitude
                    ),
                    recorded_at,
                )
            )

        except WeatherUnavailable:
            weather = (
                UnavailableWeatherProvider()
                .get_weather(
                    float(
                        telemetry.latitude
                    ),
                    float(
                        telemetry.longitude
                    ),
                    recorded_at,
                )
            )

        weather_factor = {
            "LOW": 1.0,
            "MEDIUM": 1.10,
            "HIGH": 1.25,
        }.get(
            weather.weather_delay_risk,
            1.0,
        )

        # -----------------------------------------------------
        # Prediction source
        # -----------------------------------------------------

        if (
            telemetry.data_source
            == "DEMO"
        ):
            prediction_source = "DEMO"

        elif is_stale:
            prediction_source = "STALE"

        else:
            prediction_source = "LIVE"

        # -----------------------------------------------------
        # AI ETA
        # -----------------------------------------------------

        prediction = (
            self._predictor.predict_realtime(
                observed_at=recorded_at,

                current_speed=max(
                    resolved_speed,
                    1.0,
                ),

                current_delay=max(
                    float(
                        telemetry.current_delay
                    ),
                    0.0,
                ),

                distance_to_next_station=(
                    distance_to_next_station
                ),

                historical_delay=2.0,

                previous_station_delay=max(
                    float(
                        telemetry.current_delay
                    ),
                    0.0,
                ),

                section_average_speed=60.0,

                weather_factor=(
                    weather_factor
                ),

                congestion_factor=1.0,

                signal_halt_minutes=0.0,

                prediction_source=(
                    prediction_source
                ),
            )
        )

        # -----------------------------------------------------
        # Final data quality
        # -----------------------------------------------------

        if is_stale:
            final_data_quality = "STALE"

        elif (
            telemetry.data_source
            == "DEMO"
        ):
            final_data_quality = "DEMO"

        else:
            final_data_quality = "LIVE"

        # -----------------------------------------------------
        # Final source
        # -----------------------------------------------------

        if telemetry.data_source:
            final_source = (
                telemetry.source
                or telemetry.data_source
            )
        else:
            final_source = "UNKNOWN"

        # -----------------------------------------------------
        # Final live flag
        # -----------------------------------------------------

        final_is_live = (
            not is_stale
            and telemetry.data_source
            != "DEMO"
        )

        # -----------------------------------------------------
        # Build realtime event
        # -----------------------------------------------------

        return RealtimeTrainEvent(
            train_id=train.train_id,

            train_number=train.number,

            latitude=float(
                telemetry.latitude
            ),

            longitude=float(
                telemetry.longitude
            ),

            speed=round(
                resolved_speed,
                1,
            ),

            current_delay=max(
                0,
                int(
                    round(
                        float(
                            telemetry.current_delay
                        )
                    )
                ),
            ),

            next_station=(
                next_station.name
            ),

            eta=(
                prediction.predicted_arrival
            ),

            timestamp=(
                recorded_at
            ),

            data_source=(
                telemetry.data_source
            ),

            data_quality=(
                final_data_quality
            ),

            source=(
                final_source
            ),

            is_live=(
                final_is_live
            ),

            last_updated=(
                telemetry.last_updated
                or recorded_at
            ),

            distance_to_next_station=(
                distance_to_next_station
            ),

            weather=(
                weather
            ),

            eta_confidence=(
                prediction.confidence_score
            ),

            predicted_delay=(
                prediction.predicted_delay
            ),

            confidence_level=(
                prediction.confidence_level
            ),

            prediction_source=(
                prediction.prediction_source
            ),
        )


__all__ = [
    "RealtimeTrainTrackingService",
]