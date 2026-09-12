"""
NTES live railway data provider for Dynamic Train ETA.

Uses the unofficial ntes-client package.

Features:
- Reads LIVE_TRAIN_NUMBERS from project-root .env
- Reads NTES_CACHE_TTL_SECONDS from project-root .env
- Fetches live NTES running status
- Maps NTES station codes to local station coordinates
- Returns current application Pydantic schemas
- Supports /api/trains
- Supports /api/trains/{train_id}/live
- Supports route and telemetry
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
import time
from typing import Any

from ntes import NTESClient

from ..schemas import (
    Station,
    Train,
    TrainPosition,
    TrainTelemetry,
    WeatherData,
)
from .base import ProviderUnavailable, TrainDataProvider


# ================================================================
# PROJECT ROOT .ENV
# ================================================================

def _load_root_env() -> dict[str, str]:
    """
    Load the project root .env file.

    Project structure:

        Dyanamic Eta project/
        ├── .env
        ├── backend/
        │   └── app/
        │       └── adapters/
        │           └── ntes.py
        └── frontend/
    """

    env_path = (
        Path(__file__).resolve().parents[3]
        / ".env"
    )

    if not env_path.exists():
        return {}

    values: dict[str, str] = {}

    try:
        for line in env_path.read_text(
            encoding="utf-8"
        ).splitlines():

            line = line.strip()

            if not line:
                continue

            if line.startswith("#"):
                continue

            if "=" not in line:
                continue

            key, value = line.split(
                "=",
                1,
            )

            key = key.strip()
            value = value.strip()

            if (
                len(value) >= 2
                and value.startswith('"')
                and value.endswith('"')
            ):
                value = value[1:-1]

            elif (
                len(value) >= 2
                and value.startswith("'")
                and value.endswith("'")
            ):
                value = value[1:-1]

            values[key] = value

    except OSError:
        return {}

    return values


_ROOT_ENV = _load_root_env()


def _env(
    name: str,
    default: str = "",
) -> str:
    """
    Priority:
    1. OS environment
    2. project .env
    3. default
    """

    value = os.getenv(name)

    if value is not None:
        return value.strip()

    return _ROOT_ENV.get(
        name,
        default,
    ).strip()


# ================================================================
# NTES PROVIDER
# ================================================================

class NTESProvider(TrainDataProvider):
    """Live railway provider backed by NTES."""

    def __init__(self) -> None:

        self._client = NTESClient(
            timeout=15,
            retries=1,
        )

        # train_id -> (monotonic_timestamp, response)
        self._cache: dict[
            str,
            tuple[
                float,
                dict[str, Any],
            ],
        ] = {}

        self._cache_lock = threading.Lock()

        self._cache_ttl_seconds = float(
            _env(
                "NTES_CACHE_TTL_SECONDS",
                "10",
            )
        )

        self._station_coordinates = (
            self._load_station_coordinates()
        )

        configured = self._configured_train_numbers()

        print(
            "[NTES] Provider initialized."
        )

        print(
            f"[NTES] Configured trains: {configured}"
        )

        print(
            "[NTES] Station coordinates loaded: "
            f"{len(self._station_coordinates)}"
        )

    # ============================================================
    # STATION COORDINATE FILE
    # ============================================================

    @staticmethod
    def _load_station_coordinates() -> dict[
        str,
        dict[str, Any],
    ]:
        """
        Load:

        backend/data/station_coordinates.json
        """

        path = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "station_coordinates.json"
        )

        if not path.exists():

            print(
                "[NTES] station_coordinates.json "
                "not found."
            )

            print(
                f"[NTES] Expected path: {path}"
            )

            return {}

        try:

            content = path.read_text(
                encoding="utf-8"
            )

            data = json.loads(content)

            if not isinstance(
                data,
                dict,
            ):
                print(
                    "[NTES] station_coordinates.json "
                    "must contain a JSON object."
                )
                return {}

            normalized: dict[
                str,
                dict[str, Any],
            ] = {}

            for key, value in data.items():

                if not isinstance(
                    value,
                    dict,
                ):
                    continue

                normalized[
                    str(key).strip().upper()
                ] = value

            return normalized

        except Exception as exc:

            print(
                "[NTES] Failed to load station "
                f"coordinates: {exc}"
            )

            return {}

    # ============================================================
    # TIME
    # ============================================================

    @staticmethod
    def _journey_date() -> str:
        """
        NTES format:
        DD-MMM-YYYY
        """

        return datetime.now().strftime(
            "%d-%b-%Y"
        )

    @staticmethod
    def _now_utc() -> datetime:
        return datetime.now(
            timezone.utc
        )

    # ============================================================
    # SAFE HELPERS
    # ============================================================

    @staticmethod
    def _clean_train_id(
        train_id: str,
    ) -> str:

        return str(train_id).strip()

    @staticmethod
    def _safe_string(
        value: Any,
        default: str = "",
    ) -> str:

        if value is None:
            return default

        text = str(value).strip()

        if text.lower() in {
            "",
            "none",
            "null",
        }:
            return default

        return text

    @staticmethod
    def _safe_float(
        value: Any,
        default: float = 0.0,
    ) -> float:

        try:

            if value is None:
                return default

            if isinstance(
                value,
                str,
            ):
                value = value.replace(
                    ",",
                    "",
                ).strip()

            return float(value)

        except (
            TypeError,
            ValueError,
        ):
            return default

    @staticmethod
    def _parse_delay(
        value: Any,
    ) -> int:
        """
        Parse:
        86
        "86"
        "86 min"
        """

        if value is None:
            return 0

        if isinstance(
            value,
            (
                int,
                float,
            ),
        ):
            return max(
                0,
                int(value),
            )

        text = str(value).strip()

        if not text:
            return 0

        digits = ""

        for char in text:

            if char.isdigit():
                digits += char

            elif digits:
                break

        if not digits:
            return 0

        return max(
            0,
            int(digits),
        )

    # ============================================================
    # CONFIGURED TRAIN NUMBERS
    # ============================================================

    @staticmethod
    def _configured_train_numbers() -> list[str]:

        raw = _env(
            "LIVE_TRAIN_NUMBERS",
            "",
        )

        if not raw:
            return []

        numbers: list[str] = []

        for item in raw.split(","):

            number = item.strip()

            if (
                number
                and number not in numbers
            ):
                numbers.append(number)

        return numbers

    # ============================================================
    # FETCH LIVE NTES DATA
    # ============================================================

    def _fetch_status(
        self,
        train_id: str,
        force_refresh: bool = False,
    ) -> dict[str, Any]:

        clean_id = self._clean_train_id(
            train_id
        )

        if not clean_id:
            raise ProviderUnavailable(
                "Train number is required."
            )

        now = time.monotonic()

        # --------------------------------------------------------
        # CACHE
        # --------------------------------------------------------

        if not force_refresh:

            with self._cache_lock:
                cached = self._cache.get(
                    clean_id
                )

            if cached is not None:

                cached_at, cached_data = cached

                if (
                    now - cached_at
                    < self._cache_ttl_seconds
                ):
                    return cached_data

        # --------------------------------------------------------
        # NTES REQUEST
        # --------------------------------------------------------

        try:

            response = self._client.live_status(
                clean_id,
                self._journey_date(),
            )

        except Exception as exc:

            # Use previous cache if available.
            with self._cache_lock:
                cached = self._cache.get(
                    clean_id
                )

            if cached is not None:
                return cached[1]

            raise ProviderUnavailable(
                f"NTES live status unavailable "
                f"for train {clean_id}: {exc}"
            ) from exc

        if response is None:

            raise ProviderUnavailable(
                f"NTES returned no data "
                f"for train {clean_id}."
            )

        if not isinstance(
            response,
            dict,
        ):

            raise ProviderUnavailable(
                f"Unexpected NTES response "
                f"for train {clean_id}."
            )

        # --------------------------------------------------------
        # SAVE CACHE
        # --------------------------------------------------------

        with self._cache_lock:

            self._cache[clean_id] = (
                now,
                response,
            )

        return response

    # ============================================================
    # TRAIN FIELDS
    # ============================================================

    def _train_number(
        self,
        data: dict[str, Any],
        requested_id: str,
    ) -> str:

        return (
            self._safe_string(
                data.get("TN")
            )
            or requested_id
        )

    def _train_name(
        self,
        data: dict[str, Any],
        train_number: str,
    ) -> str:

        return (
            self._safe_string(
                data.get("TNM")
            )
            or f"Train {train_number}"
        )

    def _origin(
        self,
        data: dict[str, Any],
    ) -> str:

        return (
            self._safe_string(
                data.get("SRCN")
            )
            or self._safe_string(
                data.get("SRC")
            )
            or "Unknown"
        )

    def _destination(
        self,
        data: dict[str, Any],
    ) -> str:

        return (
            self._safe_string(
                data.get("DSTNHN")
            )
            or self._safe_string(
                data.get("DSTNN")
            )
            or self._safe_string(
                data.get("DSTN")
            )
            or "Unknown"
        )

    # ============================================================
    # CURRENT / NEXT STATION
    # ============================================================

    def _current_station_code(
        self,
        data: dict[str, Any],
    ) -> str:

        return (
            self._safe_string(
                data.get("LSTN")
            )
            or self._safe_string(
                data.get("lastStation")
            )
        )

    def _current_station_name(
        self,
        data: dict[str, Any],
    ) -> str:

        return (
            self._safe_string(
                data.get("LSTNN")
            )
            or self._safe_string(
                data.get("lastStationName")
            )
            or self._current_station_code(data)
        )

    def _next_station_code(
        self,
        data: dict[str, Any],
    ) -> str:

        return (
            self._safe_string(
                data.get("NPSTN")
            )
            or self._safe_string(
                data.get("nextStation")
            )
        )

    def _next_station_name(
        self,
        data: dict[str, Any],
    ) -> str:

        return (
            self._safe_string(
                data.get("NPSTNN")
            )
            or self._safe_string(
                data.get("nextStationName")
            )
            or self._next_station_code(data)
        )

    # ============================================================
    # STATION CODE / NAME
    # ============================================================

    @staticmethod
    def _station_code(
        station: dict[str, Any],
    ) -> str:

        return (
            NTESProvider._safe_string(
                station.get("SC")
            )
            or NTESProvider._safe_string(
                station.get("code")
            )
            or NTESProvider._safe_string(
                station.get("STN")
            )
        )

    @staticmethod
    def _station_name(
        station: dict[str, Any],
    ) -> str:

        return (
            NTESProvider._safe_string(
                station.get("SN")
            )
            or NTESProvider._safe_string(
                station.get("name")
            )
            or NTESProvider._safe_string(
                station.get("SHN")
            )
            or NTESProvider._station_code(
                station
            )
        )

    # ============================================================
    # ROUTE
    # ============================================================

    def _raw_route(
        self,
        data: dict[str, Any],
    ) -> list[dict[str, object]]:

        raw_stations = data.get("STNS")

        if not isinstance(
            raw_stations,
            list,
        ):
            return []

        route: list[
            dict[str, object]
        ] = []

        sequence = 0

        for item in raw_stations:

            if not isinstance(
                item,
                dict,
            ):
                continue

            code = self._station_code(item)
            name = self._station_name(item)

            if not code:
                continue

            sequence += 1

            coordinate_data = (
                self._station_coordinates.get(
                    code.upper(),
                    {},
                )
            )

            latitude = coordinate_data.get(
                "latitude"
            )

            longitude = coordinate_data.get(
                "longitude"
            )

            route.append(
                {
                    "sequence": sequence,
                    "code": code,
                    "name": name or code,

                    "distance_km":
                        self._safe_float(
                            item.get("DIST"),
                            0.0,
                        ),

                    "latitude": latitude,
                    "longitude": longitude,

                    "scheduled_arrival":
                        self._safe_string(
                            item.get("STA")
                        ),

                    "scheduled_departure":
                        self._safe_string(
                            item.get("STD")
                        ),

                    "expected_arrival":
                        self._safe_string(
                            item.get("ETA")
                        ),

                    "expected_departure":
                        self._safe_string(
                            item.get("ETD")
                        ),

                    "actual_arrival":
                        self._safe_string(
                            item.get("DARR")
                        ),

                    "actual_departure":
                        self._safe_string(
                            item.get("DDEP")
                        ),

                    "platform":
                        self._safe_string(
                            item.get("PF")
                        ),
                }
            )

        return route

    # ============================================================
    # DISTANCE TO NEXT
    # ============================================================

    def _distance_to_next_station(
        self,
        data: dict[str, Any],
    ) -> float:

        route = self._raw_route(
            data
        )

        current_code = (
            self._current_station_code(data)
        )

        next_code = (
            self._next_station_code(data)
        )

        current_distance: (
            float | None
        ) = None

        next_distance: (
            float | None
        ) = None

        for station in route:

            code = str(
                station.get(
                    "code",
                    "",
                )
            )

            distance = self._safe_float(
                station.get(
                    "distance_km",
                    0.0,
                )
            )

            if code == current_code:
                current_distance = distance

            if code == next_code:
                next_distance = distance

        if (
            current_distance is not None
            and next_distance is not None
        ):

            return max(
                0.0,
                next_distance - current_distance,
            )

        return 0.0

    # ============================================================
    # GET TRAIN
    # ============================================================

    def get_train(
        self,
        train_id: str,
    ) -> Train | None:

        clean_id = self._clean_train_id(
            train_id
        )

        data = self._fetch_status(
            clean_id
        )

        number = self._train_number(
            data,
            clean_id,
        )

        name = self._train_name(
            data,
            number,
        )

        origin = self._origin(
            data
        )

        destination = self._destination(
            data
        )

        current_station = (
            self._current_station_name(data)
        )

        next_station = (
            self._next_station_name(data)
        )

        delay = self._parse_delay(
            data.get("LDEL")
        )

        # --------------------------------------------------------
        # STATUS
        # --------------------------------------------------------

        if delay > 0:

            status = (
                f"Delayed by "
                f"{delay} minutes"
            )

        elif (
            current_station
            and next_station
        ):

            status = (
                f"Running - "
                f"{current_station} → "
                f"{next_station}"
            )

        elif current_station:

            status = (
                f"Running - "
                f"{current_station}"
            )

        else:

            status = "Running"

        now = self._now_utc()

        return Train(
            train_id=clean_id,
            name=name,
            number=number,
            status=status,
            origin=origin,
            destination=destination,

            data_source="LIVE",
            source="LIVE",
            is_live=True,
            data_quality="LIVE",

            last_updated=now,
            weather=WeatherData.unavailable(),
        )

    # ============================================================
    # GET ROUTE
    # ============================================================

    def get_route(
        self,
        train_id: str,
    ) -> Sequence[Station] | None:

        data = self._fetch_status(
            train_id
        )

        raw_stations = data.get(
            "STNS"
        )

        if not isinstance(
            raw_stations,
            list,
        ):
            return []

        stations: list[Station] = []

        sequence = 0

        for item in raw_stations:

            if not isinstance(
                item,
                dict,
            ):
                continue

            code = self._station_code(
                item
            )

            name = self._station_name(
                item
            )

            if not code:
                continue

            sequence += 1

            coordinate_data = (
                self._station_coordinates.get(
                    code.upper(),
                    {},
                )
            )

            latitude = coordinate_data.get(
                "latitude"
            )

            longitude = coordinate_data.get(
                "longitude"
            )

            stations.append(
                Station(
                    station_id=code,
                    name=name or code,
                    code=code,
                    sequence=sequence,

                    data_source="LIVE",

                    latitude=(
                        self._safe_float(
                            latitude,
                        )
                        if latitude is not None
                        else None
                    ),

                    longitude=(
                        self._safe_float(
                            longitude,
                        )
                        if longitude is not None
                        else None
                    ),
                )
            )

        return stations

    # ============================================================
    # GET TELEMETRY
    # ============================================================

    def get_telemetry(
        self,
        train_id: str,
    ) -> TrainTelemetry | None:

        clean_id = self._clean_train_id(
            train_id
        )

        data = self._fetch_status(
            clean_id
        )

        train_number = (
            self._train_number(
                data,
                clean_id,
            )
        )

        train_name = (
            self._train_name(
                data,
                train_number,
            )
        )

        current_station = (
            self._current_station_name(
                data
            )
        )

        next_station = (
            self._next_station_name(
                data
            )
        )

        delay = self._parse_delay(
            data.get("LDEL")
        )

        distance = (
            self._distance_to_next_station(
                data
            )
        )

        now = self._now_utc()

        return TrainTelemetry(
            train_id=clean_id,

            # NTES doesn't provide reliable
            # GPS coordinates here.
            latitude=0.0,
            longitude=0.0,

            speed_kmph=0.0,

            current_delay=delay,
            recorded_at=now,

            data_source="LIVE",
            data_quality="LIVE",

            train_number=train_number,
            train_name=train_name,

            next_station=next_station,
            current_station=current_station,

            distance_to_next_station=distance,

            timestamp=now,
            source="LIVE",

            is_live=True,
            last_updated=now,

            route=self._raw_route(data),
        )

    # ============================================================
    # GET LIVE POSITION
    # ============================================================

    def get_live_position(
        self,
        train_id: str,
    ) -> TrainPosition | None:

        clean_id = self._clean_train_id(
            train_id
        )

        data = self._fetch_status(
            clean_id
        )

        now = self._now_utc()

        return TrainPosition(
            train_id=clean_id,

            # GPS unavailable directly from NTES.
            latitude=0.0,
            longitude=0.0,

            speed_kmph=0.0,

            recorded_at=now,

            data_source="LIVE",

            current_delay=self._parse_delay(
                data.get("LDEL")
            ),

            source="LIVE",

            is_live=True,
            data_quality="LIVE",

            last_updated=now,

            next_station=(
                self._next_station_name(
                    data
                )
            ),

            distance_to_next_station=(
                self._distance_to_next_station(
                    data
                )
            ),

            weather=WeatherData.unavailable(),
        )

    # ============================================================
    # LIST TRAINS
    # ============================================================

    def list_trains(
        self,
    ) -> Sequence[Train]:

        train_numbers = (
            self._configured_train_numbers()
        )

        if not train_numbers:

            raise ProviderUnavailable(
                "LIVE_TRAIN_NUMBERS is not "
                "configured in .env"
            )

        trains: list[Train] = []

        for train_number in train_numbers:

            try:

                train = self.get_train(
                    train_number
                )

                if train is not None:
                    trains.append(train)

            except Exception as exc:

                print(
                    f"[NTES] Failed train "
                    f"{train_number}: {exc}"
                )

                continue

        if trains:
            return trains

        raise ProviderUnavailable(
            "No configured NTES train "
            "could be loaded."
        )

    # ============================================================
    # FORCE REFRESH
    # ============================================================

    def refresh(
        self,
        train_id: str,
    ) -> dict[str, Any]:

        return self._fetch_status(
            train_id,
            force_refresh=True,
        )

    # ============================================================
    # CLEAR CACHE
    # ============================================================

    def clear_cache(
        self,
        train_id: str | None = None,
    ) -> None:

        with self._cache_lock:

            if train_id is None:

                self._cache.clear()

                return

            self._cache.pop(
                self._clean_train_id(
                    train_id
                ),
                None,
            )


__all__ = [
    "NTESProvider",
]