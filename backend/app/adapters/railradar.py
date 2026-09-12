"""RailRadar connectivity adapter for authorized live railway data."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from threading import Lock
from time import monotonic
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from ..config import Settings
from ..schemas import (
    Station,
    Train,
    TrainPosition,
    TrainTelemetry,
)
from .base import (
    ProviderConfigurationError,
    ProviderUnavailable,
)


class RailRadarProvider:
    """
    Adapter for authorized RailRadar live train status data.

    Protection layers:

    1. Per-train cache
    2. Per-train request locking
    3. Provider rate-limit cooldown
    4. Retry-After support
    5. Stale-data fallback
    6. Last-known telemetry retention
    7. Robust speed normalization
    8. Rate-limit diagnostics
    """

    DEFAULT_CACHE_TTL_SECONDS = 30.0
    DEFAULT_STALE_CACHE_TTL_SECONDS = 300.0
    DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS = 60.0

    MAX_REASONABLE_TRAIN_SPEED_KMPH = 220.0

    def __init__(
        self,
        settings: Settings,
        client: Any = httpx,
    ) -> None:
        self._settings = settings
        self._client = client

        # train_number -> (monotonic_time, telemetry)
        self._cache: dict[
            str,
            tuple[float, TrainTelemetry],
        ] = {}

        # train_number -> provider cooldown timestamp
        self._rate_limited_until: dict[
            str,
            float,
        ] = {}

        # train_number -> Lock
        self._locks: dict[str, Lock] = {}

        self._cache_lock = Lock()

    # =========================================================
    # CACHE CONFIGURATION
    # =========================================================

    def _cache_ttl(self) -> float:
        import os

        try:
            value = float(
                os.getenv(
                    "RAILRADAR_CACHE_TTL_SECONDS",
                    str(
                        self.DEFAULT_CACHE_TTL_SECONDS
                    ),
                )
            )

            return max(
                5.0,
                value,
            )

        except (
            TypeError,
            ValueError,
        ):
            return self.DEFAULT_CACHE_TTL_SECONDS

    def _stale_cache_ttl(self) -> float:
        import os

        try:
            value = float(
                os.getenv(
                    "RAILRADAR_STALE_CACHE_TTL_SECONDS",
                    str(
                        self.DEFAULT_STALE_CACHE_TTL_SECONDS
                    ),
                )
            )

            return max(
                30.0,
                value,
            )

        except (
            TypeError,
            ValueError,
        ):
            return self.DEFAULT_STALE_CACHE_TTL_SECONDS

    def _rate_limit_cooldown(self) -> float:
        import os

        try:
            value = float(
                os.getenv(
                    "RAILRADAR_RATE_LIMIT_COOLDOWN_SECONDS",
                    str(
                        self.DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS
                    ),
                )
            )

            return max(
                10.0,
                value,
            )

        except (
            TypeError,
            ValueError,
        ):
            return self.DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS

    # =========================================================
    # LOCK
    # =========================================================

    def _get_train_lock(
        self,
        train_number: str,
    ) -> Lock:
        with self._cache_lock:
            lock = self._locks.get(
                train_number
            )

            if lock is None:
                lock = Lock()

                self._locks[
                    train_number
                ] = lock

            return lock

    # =========================================================
    # CACHE
    # =========================================================

    def _get_cached(
        self,
        train_number: str,
        *,
        allow_stale: bool = False,
    ) -> TrainTelemetry | None:
        with self._cache_lock:
            cached = self._cache.get(
                train_number
            )

        if cached is None:
            return None

        cached_at, telemetry = cached

        age = (
            monotonic()
            - cached_at
        )

        ttl = (
            self._stale_cache_ttl()
            if allow_stale
            else self._cache_ttl()
        )

        if age > ttl:
            return None

        return telemetry

    def _store_cached(
        self,
        train_number: str,
        telemetry: TrainTelemetry,
    ) -> None:
        with self._cache_lock:
            self._cache[
                train_number
            ] = (
                monotonic(),
                telemetry,
            )

    # =========================================================
    # RATE LIMIT STATE
    # =========================================================

    def _set_rate_limit(
        self,
        train_number: str,
        cooldown_seconds: float | None = None,
    ) -> None:
        cooldown = (
            cooldown_seconds
            if cooldown_seconds is not None
            else self._rate_limit_cooldown()
        )

        cooldown = max(
            10.0,
            cooldown,
        )

        cooldown_until = (
            monotonic()
            + cooldown
        )

        with self._cache_lock:
            self._rate_limited_until[
                train_number
            ] = cooldown_until

    def _is_rate_limited(
        self,
        train_number: str,
    ) -> bool:
        with self._cache_lock:
            until = (
                self._rate_limited_until.get(
                    train_number
                )
            )

        if until is None:
            return False

        if monotonic() >= until:
            with self._cache_lock:
                self._rate_limited_until.pop(
                    train_number,
                    None,
                )

            return False

        return True

    def _remaining_rate_limit_seconds(
        self,
        train_number: str,
    ) -> float:
        with self._cache_lock:
            until = (
                self._rate_limited_until.get(
                    train_number
                )
            )

        if until is None:
            return 0.0

        return max(
            0.0,
            until - monotonic(),
        )

    def clear_cache(
        self,
        train_number: str | None = None,
    ) -> None:
        with self._cache_lock:
            if train_number is None:
                self._cache.clear()
                self._rate_limited_until.clear()
            else:
                key = str(
                    train_number
                ).strip()

                self._cache.pop(
                    key,
                    None,
                )

                self._rate_limited_until.pop(
                    key,
                    None,
                )

    # =========================================================
    # CONFIGURATION
    # =========================================================

    def _configuration(self) -> None:
        missing: list[str] = []

        if not self._settings.railradar_api_base_url:
            missing.append(
                "RAILRADAR_API_BASE_URL"
            )

        if not self._settings.railway_api_key:
            missing.append(
                "RAILWAY_API_KEY"
            )

        if missing:
            raise ProviderConfigurationError(
                "RailRadar configuration missing: "
                + ", ".join(missing)
            )

    # =========================================================
    # SAFE FLOAT
    # =========================================================

    @staticmethod
    def _safe_float(
        value: Any,
    ) -> float | None:
        """
        Convert provider values such as:
            45
            45.2
            "45"
            "45.2"
            "45 km/h"
        into a safe float.
        """

        if value is None:
            return None

        if isinstance(
            value,
            bool,
        ):
            return None

        if isinstance(
            value,
            (int, float),
        ):
            numeric = float(value)

            if numeric == numeric:
                return numeric

            return None

        if isinstance(
            value,
            str,
        ):
            cleaned = (
                value.strip()
                .lower()
                .replace(
                    "km/h",
                    "",
                )
                .replace(
                    "kmph",
                    "",
                )
                .replace(
                    "kph",
                    "",
                )
                .strip()
            )

            try:
                numeric = float(
                    cleaned
                )

                if numeric == numeric:
                    return numeric

            except ValueError:
                return None

        return None

    # =========================================================
    # RATE-LIMIT DIAGNOSTICS
    # =========================================================

    @staticmethod
    def _retry_after_seconds(
        response: Any,
    ) -> float | None:
        """
        Read Retry-After when the provider supplies it.

        Supports:
            Retry-After: 60
        """

        try:
            raw = response.headers.get(
                "Retry-After"
            )
        except Exception:
            return None

        if raw is None:
            return None

        try:
            value = float(
                str(raw).strip()
            )

            if value >= 0:
                return value

        except (
            TypeError,
            ValueError,
        ):
            pass

        return None

    @staticmethod
    def _print_rate_limit_debug(
        response: Any,
        train_number: str,
    ) -> None:
        """
        Print provider rate-limit diagnostics.

        Secrets such as Authorization headers are NOT printed.
        """

        try:
            headers = dict(
                response.headers
            )
        except Exception:
            headers = {}

        safe_headers = {}

        for key, value in headers.items():
            key_lower = str(
                key
            ).lower()

            if (
                "authorization"
                in key_lower
                or "api-key"
                in key_lower
                or "apikey"
                in key_lower
                or "token"
                in key_lower
            ):
                continue

            if (
                "rate"
                in key_lower
                or "retry"
                in key_lower
                or key_lower
                in {
                    "date",
                    "server",
                    "content-type",
                    "content-length",
                }
            ):
                safe_headers[
                    str(key)
                ] = str(value)

        try:
            body = response.text[:1000]
        except Exception:
            body = "<unable to read response body>"

        print(
            "\n"
            "====================================================\n"
            "RAILRADAR RATE-LIMIT DEBUG\n"
            "===================================================="
        )

        print(
            f"Train Number : {train_number}"
        )

        print(
            f"HTTP Status  : {response.status_code}"
        )

        print(
            f"Headers      : {safe_headers}"
        )

        print(
            f"Body         : {body}"
        )

        print(
            "====================================================\n"
        )

    # =========================================================
    # SPEED EXTRACTION
    # =========================================================

    @classmethod
    def _extract_speed_from_mapping(
        cls,
        payload: Mapping[str, Any],
    ) -> float:
        """
        Find train speed from several common provider
        response shapes.
        """

        speed_keys = (
            "speedKmh",
            "speedKmph",
            "speedKmH",
            "speed_kmph",
            "speed_kmh",
            "speed",
            "currentSpeed",
            "currentSpeedKmh",
            "currentSpeedKmph",
            "current_speed",
            "current_speed_kmph",
            "current_speed_kmh",
            "velocity",
            "velocityKmh",
            "velocityKmph",
            "avgSpeed",
            "averageSpeed",
            "averageSpeedKmh",
            "averageSpeedKmph",
        )

        for key in speed_keys:
            if key not in payload:
                continue

            numeric = cls._safe_float(
                payload.get(key)
            )

            if numeric is None:
                continue

            if (
                0.0
                <= numeric
                <= cls.MAX_REASONABLE_TRAIN_SPEED_KMPH
            ):
                return round(
                    numeric,
                    1,
                )

        nested_keys = (
            "currentLocation",
            "location",
            "position",
            "trainLocation",
            "gps",
            "telemetry",
            "live",
            "movement",
            "trainStatus",
        )

        for key in nested_keys:
            value = payload.get(
                key
            )

            if not isinstance(
                value,
                Mapping,
            ):
                continue

            nested_speed = (
                cls._extract_speed_from_mapping(
                    value
                )
            )

            if nested_speed > 0:
                return nested_speed

        for key, value in payload.items():
            if not isinstance(
                value,
                Mapping,
            ):
                continue

            key_lower = str(
                key
            ).lower()

            if any(
                token in key_lower
                for token in (
                    "location",
                    "position",
                    "telemetry",
                    "movement",
                    "status",
                )
            ):
                nested_speed = (
                    cls._extract_speed_from_mapping(
                        value
                    )
                )

                if nested_speed > 0:
                    return nested_speed

        return 0.0

    @classmethod
    def _extract_speed(
        cls,
        payload: Mapping[str, Any],
        data: Mapping[str, Any],
        location: Mapping[str, Any],
    ) -> float:
        """
        Speed extraction priority:

        1. currentLocation
        2. data
        3. complete payload
        """

        speed = (
            cls._extract_speed_from_mapping(
                location
            )
        )

        if speed > 0:
            return speed

        speed = (
            cls._extract_speed_from_mapping(
                data
            )
        )

        if speed > 0:
            return speed

        speed = (
            cls._extract_speed_from_mapping(
                payload
            )
        )

        if speed > 0:
            return speed

        return 0.0

    # =========================================================
    # COORDINATES
    # =========================================================

    @staticmethod
    def _coordinates(
        payload: Mapping[str, Any],
        data: Mapping[str, Any],
    ) -> tuple[float, float]:

        geometry = payload.get(
            "geometry"
        )

        if isinstance(
            geometry,
            Mapping,
        ):
            coordinates = geometry.get(
                "coordinates"
            )

            if (
                isinstance(
                    coordinates,
                    (list, tuple),
                )
                and len(coordinates) >= 2
            ):
                return (
                    float(
                        coordinates[1]
                    ),
                    float(
                        coordinates[0]
                    ),
                )

        geometry = data.get(
            "geometry"
        )

        if isinstance(
            geometry,
            Mapping,
        ):
            coordinates = geometry.get(
                "coordinates"
            )

            if (
                isinstance(
                    coordinates,
                    (list, tuple),
                )
                and len(coordinates) >= 2
            ):
                return (
                    float(
                        coordinates[1]
                    ),
                    float(
                        coordinates[0]
                    ),
                )

        location = data.get(
            "currentLocation"
        )

        if isinstance(
            location,
            Mapping,
        ):
            coordinates = location.get(
                "coordinates"
            )

            if (
                isinstance(
                    coordinates,
                    (list, tuple),
                )
                and len(coordinates) >= 2
            ):
                return (
                    float(
                        coordinates[1]
                    ),
                    float(
                        coordinates[0]
                    ),
                )

            latitude = (
                location.get(
                    "latitude"
                )
                or location.get(
                    "lat"
                )
            )

            longitude = (
                location.get(
                    "longitude"
                )
                or location.get(
                    "lng"
                )
                or location.get(
                    "lon"
                )
            )

            if (
                latitude is not None
                and longitude is not None
            ):
                return (
                    float(
                        latitude
                    ),
                    float(
                        longitude
                    ),
                )

        route = (
            data.get(
                "route"
            )
            or []
        )

        station_code = (
            location.get(
                "stationCode"
            )
            if isinstance(
                location,
                Mapping,
            )
            else None
        )

        if (
            isinstance(
                route,
                list,
            )
            and station_code
        ):
            for station in route:
                if not isinstance(
                    station,
                    Mapping,
                ):
                    continue

                if (
                    str(
                        station.get(
                            "stationCode"
                        )
                    )
                    == str(
                        station_code
                    )
                ):
                    lat = (
                        station.get(
                            "lat"
                        )
                        or station.get(
                            "latitude"
                        )
                    )

                    lng = (
                        station.get(
                            "lng"
                        )
                        or station.get(
                            "longitude"
                        )
                    )

                    if (
                        lat is not None
                        and lng is not None
                    ):
                        return (
                            float(lat),
                            float(lng),
                        )

        raise KeyError(
            "No usable train coordinates found"
        )

    # =========================================================
    # DISTANCE TO NEXT STATION
    # =========================================================

    @staticmethod
    def _calculate_distance_to_next_station(
        route: list[dict[str, object]],
        current_station_code: str,
        next_station_code: str,
        segment_progress: float = 0.0,
    ) -> float:

        current_station = None
        next_station = None

        for station in route:
            station_code = str(
                station.get(
                    "station_code",
                    "",
                )
            )

            if (
                station_code
                == str(
                    current_station_code
                )
            ):
                current_station = station

            if (
                station_code
                == str(
                    next_station_code
                )
            ):
                next_station = station

        if (
            current_station is None
            or next_station is None
        ):
            return 0.0

        current_distance = (
            current_station.get(
                "distance"
            )
        )

        next_distance = (
            next_station.get(
                "distance"
            )
        )

        if (
            current_distance is None
            or next_distance is None
        ):
            return 0.0

        try:
            current_distance_value = float(
                current_distance
            )

            next_distance_value = float(
                next_distance
            )

            segment_distance = max(
                0.0,
                next_distance_value
                - current_distance_value,
            )

            progress = min(
                1.0,
                max(
                    0.0,
                    float(
                        segment_progress
                    ),
                ),
            )

            remaining_distance = (
                segment_distance
                * (
                    1.0
                    - progress
                )
            )

            return round(
                max(
                    0.0,
                    remaining_distance,
                ),
                2,
            )

        except (
            TypeError,
            ValueError,
        ):
            return 0.0

    # =========================================================
    # LIVE STATUS
    # =========================================================

    def fetch_live_status(
        self,
        train_number: str,
    ) -> TrainTelemetry:

        self._configuration()

        clean_train_number = str(
            train_number
        ).strip()

        if not clean_train_number:
            raise ProviderUnavailable(
                "Train number is required"
            )

        # -----------------------------------------------------
        # NORMAL CACHE
        # -----------------------------------------------------

        cached = self._get_cached(
            clean_train_number
        )

        if cached is not None:
            return cached

        # -----------------------------------------------------
        # RATE LIMIT COOLDOWN
        # -----------------------------------------------------

        if self._is_rate_limited(
            clean_train_number
        ):
            stale = self._get_cached(
                clean_train_number,
                allow_stale=True,
            )

            if stale is not None:
                return stale

            remaining = (
                self._remaining_rate_limit_seconds(
                    clean_train_number
                )
            )

            raise ProviderUnavailable(
                "RailRadar rate limit active; "
                f"backend cooldown remaining "
                f"{remaining:.0f}s"
            )

        # -----------------------------------------------------
        # REQUEST LOCK
        # -----------------------------------------------------

        train_lock = self._get_train_lock(
            clean_train_number
        )

        with train_lock:

            cached = self._get_cached(
                clean_train_number
            )

            if cached is not None:
                return cached

            if self._is_rate_limited(
                clean_train_number
            ):
                stale = self._get_cached(
                    clean_train_number,
                    allow_stale=True,
                )

                if stale is not None:
                    return stale

                remaining = (
                    self._remaining_rate_limit_seconds(
                        clean_train_number
                    )
                )

                raise ProviderUnavailable(
                    "RailRadar rate limit active; "
                    f"backend cooldown remaining "
                    f"{remaining:.0f}s"
                )

            # -------------------------------------------------
            # REQUEST
            # -------------------------------------------------

            url = (
                f"{self._settings.railradar_api_base_url.rstrip('/')}"
                f"/v1/trains/"
                f"{quote(clean_train_number, safe='')}"
                f"/live"
            )

            try:
                response = self._client.get(
                    url,
                    params={
                        "authoritative": "true",
                        "geometry": "true",
                        "format": "geojson",
                        "includeCoordinates": "true",
                    },
                    headers={
                        "Authorization": (
                            "Bearer "
                            f"{self._settings.railway_api_key}"
                        )
                    },
                    timeout=(
                        self._settings
                        .weather_timeout_seconds
                    ),
                )

                # -------------------------------------------------
                # DEBUG EVERY RESPONSE
                #
                # Authorization header is NOT printed.
                # -------------------------------------------------

                print(
                    "\n"
                    "[RailRadar]"
                    f" train={clean_train_number}"
                    f" status={response.status_code}"
                )

                if response.status_code in (
                    429,
                    500,
                    502,
                    503,
                    504,
                ):
                    self._print_rate_limit_debug(
                        response,
                        clean_train_number,
                    )

                # ---------------------------------------------
                # RATE LIMIT
                # ---------------------------------------------

                if response.status_code == 429:

                    retry_after = (
                        self._retry_after_seconds(
                            response
                        )
                    )

                    cooldown = (
                        retry_after
                        if retry_after is not None
                        else self._rate_limit_cooldown()
                    )

                    self._set_rate_limit(
                        clean_train_number,
                        cooldown_seconds=cooldown,
                    )

                    stale = self._get_cached(
                        clean_train_number,
                        allow_stale=True,
                    )

                    if stale is not None:
                        return stale

                    raise ProviderUnavailable(
                        "RailRadar rate limit reached; "
                        f"provider requested retry after "
                        f"{cooldown:.0f}s"
                    )

                # ---------------------------------------------
                # AUTH
                # ---------------------------------------------

                if response.status_code == 401:
                    raise ProviderUnavailable(
                        "RailRadar authentication failed"
                    )

                # ---------------------------------------------
                # FORBIDDEN
                # ---------------------------------------------

                if response.status_code == 403:
                    raise ProviderUnavailable(
                        "RailRadar access forbidden"
                    )

                # ---------------------------------------------
                # NOT FOUND
                # ---------------------------------------------

                if response.status_code == 404:
                    raise ProviderUnavailable(
                        f"Train '{clean_train_number}' "
                        "was not found by RailRadar"
                    )

                # ---------------------------------------------
                # SERVER / UPSTREAM ERROR
                # ---------------------------------------------

                if response.status_code in (
                    500,
                    502,
                    503,
                    504,
                ):
                    stale = self._get_cached(
                        clean_train_number,
                        allow_stale=True,
                    )

                    if stale is not None:
                        return stale

                    raise ProviderUnavailable(
                        "RailRadar upstream/service "
                        f"error ({response.status_code})"
                    )

                response.raise_for_status()

                # ---------------------------------------------
                # JSON
                # ---------------------------------------------

                payload = response.json()

                if (
                    not isinstance(
                        payload,
                        Mapping,
                    )
                    or not isinstance(
                        payload.get(
                            "data"
                        ),
                        Mapping,
                    )
                ):
                    raise ProviderUnavailable(
                        "RailRadar response could not "
                        "be normalized"
                    )

                data = payload["data"]

                # ---------------------------------------------
                # CURRENT LOCATION
                # ---------------------------------------------

                location = data.get(
                    "currentLocation"
                )

                if not isinstance(
                    location,
                    Mapping,
                ):
                    location = {}

                # ---------------------------------------------
                # NEXT HALT
                # ---------------------------------------------

                next_halt = (
                    data.get(
                        "nextHalt"
                    )
                    or data.get(
                        "nextHaltStation"
                    )
                    or {}
                )

                if not isinstance(
                    next_halt,
                    Mapping,
                ):
                    next_halt = {}

                # ---------------------------------------------
                # COORDINATES
                # ---------------------------------------------

                latitude, longitude = (
                    self._coordinates(
                        payload,
                        data,
                    )
                )

                # ---------------------------------------------
                # SPEED
                # ---------------------------------------------

                speed_kmph = (
                    self._extract_speed(
                        payload=payload,
                        data=data,
                        location=location,
                    )
                )

                # ---------------------------------------------
                # ROUTE
                # ---------------------------------------------

                raw_route = (
                    data.get(
                        "route"
                    )
                    or []
                )

                if not isinstance(
                    raw_route,
                    list,
                ):
                    raise ProviderUnavailable(
                        "RailRadar station route "
                        "has invalid shape"
                    )

                normalized_route = [
                    self._normalize_route_item(
                        item
                    )
                    for item in raw_route
                    if isinstance(
                        item,
                        Mapping,
                    )
                ]

                # ---------------------------------------------
                # TIMESTAMP
                # ---------------------------------------------

                last_updated_raw = (
                    data.get(
                        "lastUpdatedAt"
                    )
                    or data.get(
                        "updatedAt"
                    )
                    or data.get(
                        "timestamp"
                    )
                    or location.get(
                        "lastUpdatedAt"
                    )
                )

                if not last_updated_raw:
                    raise ProviderUnavailable(
                        "RailRadar update timestamp "
                        "is unavailable"
                    )

                recorded_at = (
                    datetime.fromisoformat(
                        str(
                            last_updated_raw
                        ).replace(
                            "Z",
                            "+00:00",
                        )
                    )
                )

                # ---------------------------------------------
                # TRAIN DETAILS
                # ---------------------------------------------

                actual_train_number = str(
                    data.get(
                        "trainNumber",
                        clean_train_number,
                    )
                )

                train_name = str(
                    data.get(
                        "trainName",
                        f"Train {actual_train_number}",
                    )
                )

                # ---------------------------------------------
                # DELAY
                # ---------------------------------------------

                raw_delay = (
                    data.get(
                        "delayMinutes"
                    )
                    or data.get(
                        "currentDelay"
                    )
                    or data.get(
                        "delay"
                    )
                    or 0
                )

                parsed_delay = (
                    self._safe_float(
                        raw_delay
                    )
                    or 0.0
                )

                delay_minutes = max(
                    0,
                    int(
                        round(
                            parsed_delay
                        )
                    ),
                )

                # ---------------------------------------------
                # CURRENT / NEXT STATION
                # ---------------------------------------------

                current_station_code = str(
                    location.get(
                        "stationCode",
                        data.get(
                            "currentStationCode",
                            "",
                        ),
                    )
                )

                next_station_code = str(
                    next_halt.get(
                        "stationCode",
                        next_halt.get(
                            "code",
                            "",
                        ),
                    )
                )

                # ---------------------------------------------
                # SEGMENT PROGRESS
                # ---------------------------------------------

                segment_progress_raw = (
                    location.get(
                        "segmentProgress"
                    )
                    or location.get(
                        "segmentProgressPercent"
                    )
                    or data.get(
                        "segmentProgress"
                    )
                    or 0
                )

                segment_progress = (
                    self._safe_float(
                        segment_progress_raw
                    )
                    or 0.0
                )

                if segment_progress > 1:
                    segment_progress /= 100

                segment_progress = min(
                    1.0,
                    max(
                        0.0,
                        segment_progress,
                    ),
                )

                # ---------------------------------------------
                # DISTANCE TO NEXT
                # ---------------------------------------------

                distance_to_next_station = (
                    self._calculate_distance_to_next_station(
                        normalized_route,
                        current_station_code,
                        next_station_code,
                        segment_progress,
                    )
                )

                # Provider may directly expose distance.
                if (
                    distance_to_next_station
                    <= 0
                ):
                    direct_distance = (
                        location.get(
                            "distanceToNextStation"
                        )
                        or location.get(
                            "distanceToNext"
                        )
                        or data.get(
                            "distanceToNextStation"
                        )
                    )

                    parsed_distance = (
                        self._safe_float(
                            direct_distance
                        )
                    )

                    if (
                        parsed_distance is not None
                        and 0
                        <= parsed_distance
                        < 1000
                    ):
                        distance_to_next_station = round(
                            parsed_distance,
                            2,
                        )

                # ---------------------------------------------
                # LIVE STATUS
                # ---------------------------------------------

                is_live = bool(
                    data.get(
                        "isLive",
                        True,
                    )
                )

                # ---------------------------------------------
                # BUILD TELEMETRY
                # ---------------------------------------------

                telemetry = TrainTelemetry(
                    train_id=actual_train_number,
                    train_number=actual_train_number,
                    train_name=train_name,

                    latitude=latitude,
                    longitude=longitude,

                    speed_kmph=max(
                        0.0,
                        min(
                            speed_kmph,
                            self.MAX_REASONABLE_TRAIN_SPEED_KMPH,
                        ),
                    ),

                    current_delay=delay_minutes,

                    current_station=(
                        current_station_code
                        or None
                    ),

                    next_station=(
                        next_station_code
                        or None
                    ),

                    recorded_at=recorded_at,

                    timestamp=recorded_at,

                    data_source="LIVE",
                    data_quality="LIVE",
                    source="LIVE",

                    is_live=is_live,

                    last_updated=recorded_at,

                    distance_to_next_station=max(
                        0.0,
                        distance_to_next_station,
                    ),

                    route=normalized_route,
                )

                # ---------------------------------------------
                # SUCCESS
                # ---------------------------------------------

                self._store_cached(
                    clean_train_number,
                    telemetry,
                )

                with self._cache_lock:
                    self._rate_limited_until.pop(
                        clean_train_number,
                        None,
                    )

                return telemetry

            except ProviderUnavailable:
                raise

            except (
                httpx.TimeoutException,
                httpx.ConnectError,
            ) as error:

                stale = self._get_cached(
                    clean_train_number,
                    allow_stale=True,
                )

                if stale is not None:
                    return stale

                raise ProviderUnavailable(
                    "RailRadar request timed out "
                    "or could not connect"
                ) from error

            except httpx.HTTPError as error:

                stale = self._get_cached(
                    clean_train_number,
                    allow_stale=True,
                )

                if stale is not None:
                    return stale

                raise ProviderUnavailable(
                    "RailRadar returned an HTTP error"
                ) from error

            except (
                KeyError,
                TypeError,
                ValueError,
                ValidationError,
            ) as error:

                stale = self._get_cached(
                    clean_train_number,
                    allow_stale=True,
                )

                if stale is not None:
                    return stale

                raise ProviderUnavailable(
                    "RailRadar response could not "
                    "be normalized"
                ) from error

    # =========================================================
    # ROUTE NORMALIZATION
    # =========================================================

    @staticmethod
    def _normalize_route_item(
        item: Mapping[str, Any],
    ) -> dict[str, object]:

        return {
            "station_code": item.get(
                "stationCode",
                item.get(
                    "code",
                    "",
                ),
            ),
            "station_name": item.get(
                "stationName",
                item.get(
                    "name",
                    "",
                ),
            ),
            "latitude": item.get(
                "lat",
                item.get(
                    "latitude"
                ),
            ),
            "longitude": item.get(
                "lng",
                item.get(
                    "longitude"
                ),
            ),
            "sequence": item.get(
                "sequence"
            ),
            "distance": item.get(
                "distance"
            ),
            "speed_to_next_station_kmph": (
                item.get(
                    "speedToNextStationKmph"
                )
            ),
            "scheduled_arrival": (
                item.get(
                    "scheduledArrival"
                )
            ),
            "actual_arrival": (
                item.get(
                    "actualArrival"
                )
            ),
            "delay_minutes": item.get(
                "delayMinutes",
                0,
            ),
            "status": item.get(
                "status"
            ),
            "platform": item.get(
                "platform"
            ),
        }

    # =========================================================
    # STATION NORMALIZATION
    # =========================================================

    def normalize_stations(
        self,
        items: Sequence[
            Mapping[str, Any]
        ],
    ) -> Sequence[Station]:

        stations: list[Station] = []

        for index, item in enumerate(
            items,
            start=1,
        ):
            stations.append(
                Station(
                    station_id=str(
                        item.get(
                            "station_id",
                            item.get(
                                "id",
                                index,
                            ),
                        )
                    ),
                    name=str(
                        item.get(
                            "name",
                            item.get(
                                "station_name",
                                "",
                            ),
                        )
                    ),
                    code=str(
                        item.get(
                            "code",
                            item.get(
                                "station_code",
                                "",
                            ),
                        )
                    ),
                    sequence=int(
                        item.get(
                            "sequence",
                            index,
                        )
                    ),
                    data_source="LIVE",
                    latitude=item.get(
                        "latitude"
                    ),
                    longitude=item.get(
                        "longitude"
                    ),
                )
            )

        return stations

    # =========================================================
    # PROVIDER INTERFACE
    # =========================================================

    def list_trains(
        self,
    ) -> Sequence[Train]:
        raise ProviderUnavailable(
            "RailRadar train listing is not configured"
        )

    def get_train(
        self,
        train_id: str,
    ) -> Train | None:
        raise ProviderUnavailable(
            "RailRadar direct train lookup "
            "uses fetch_live_status()"
        )

    def get_route(
        self,
        train_id: str,
    ) -> Sequence[Station] | None:
        raise ProviderUnavailable(
            "RailRadar route lookup "
            "uses fetch_live_status()"
        )

    def get_telemetry(
        self,
        train_id: str,
    ) -> TrainTelemetry | None:
        raise ProviderUnavailable(
            "Use fetch_live_status() "
            "with an official train number"
        )

    def get_live_position(
        self,
        train_id: str,
    ) -> TrainPosition | None:
        raise ProviderUnavailable(
            "RailRadar live position lookup "
            "uses fetch_live_status()"
        )


__all__ = [
    "RailRadarProvider",
]