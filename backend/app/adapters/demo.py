"""
Deterministic simulated railway provider for deployment/demo.

IMPORTANT:
- Train identities and published route stations are real.
- GPS position, speed, delay progression and telemetry are simulated.
- This provider NEVER claims to be live railway data.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from math import cos, radians, sin, sqrt
from time import monotonic

from ..schemas import (
    Station,
    Train,
    TrainPosition,
    TrainTelemetry,
    WeatherData,
)
from .base import ProviderUnavailable, TrainDataProvider


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _distance_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Lightweight approximate geographic distance.
    Good enough for the simulation engine.
    """
    r = 6371.0

    lat1 = radians(lat1)
    lat2 = radians(lat2)

    d_lat = lat2 - lat1
    d_lon = radians(lon2 - lon1)

    a = (
        sin(d_lat / 2) ** 2
        + cos(lat1)
        * cos(lat2)
        * sin(d_lon / 2) ** 2
    )

    return r * 2 * sqrt(
        max(
            0.0,
            min(
                1.0,
                a,
            ),
        )
    )


# ------------------------------------------------------------------
# REAL TRAIN IDENTITIES + REAL ROUTE CORRIDORS
#
# Coordinates are map/demo coordinates.
# Telemetry itself is simulated.
# ------------------------------------------------------------------

DEMO_TRAINS: dict[str, dict[str, object]] = {
    "12919": {
        "name": "MALWA EXPRESS",
        "origin": "Dr Ambedkar Ngr",
        "destination": "Shri Mata Vaishno Devi Katra",
        "base_delay": 86,
        "speed": 86.0,
        "phase_offset": 0.12,
        "route": [
            ("DADN", "Dr Ambedkar Ngr", 22.9425, 75.7837),
            ("INDB", "Indore Jn Bg", 22.7196, 75.8577),
            ("DWX", "Dewas", 22.9676, 76.0534),
            ("UJN", "Ujjain Jn", 23.1765, 75.7885),
            ("MKC", "Maksi", 23.2598, 76.1451),
            ("BPL", "Bhopal Jn", 23.2599, 77.4126),
            ("VGLJ", "Virangana Lakshmibai Jhansi", 25.4484, 78.5685),
            ("SVDK", "Shri Mata Vaishno Devi Katra", 32.9942, 74.9319),
        ],
    },
    "12952": {
        "name": "MMCT TEJAS RAJ",
        "origin": "New Delhi",
        "destination": "Mumbai Central",
        "base_delay": 46,
        "speed": 92.0,
        "phase_offset": 0.36,
        "route": [
            ("NDLS", "New Delhi", 28.6432, 77.2195),
            ("KOTA", "Kota Jn", 25.2138, 75.8648),
            ("NAD", "Nagda Jn", 23.4580, 75.4176),
            ("RTM", "Ratlam Jn", 23.3342, 75.0367),
            ("BRC", "Vadodara Jn", 22.3072, 73.1812),
            ("ST", "Surat", 21.2050, 72.8400),
            ("BVI", "Borivali", 19.2290, 72.8574),
            ("MMCT", "Mumbai Central", 18.9690, 72.8194),
        ],
    },
    "22436": {
        "name": "VANDE BHARAT EX",
        "origin": "New Delhi",
        "destination": "Varanasi Jn",
        "base_delay": 8,
        "speed": 96.0,
        "phase_offset": 0.58,
        "route": [
            ("NDLS", "New Delhi", 28.6432, 77.2195),
            ("CNB", "Kanpur Central", 26.4499, 80.3319),
            ("PRYJ", "Prayagraj Jn", 25.4358, 81.8463),
            ("BSB", "Varanasi Jn", 25.3176, 82.9739),
        ],
    },
    "16590": {
        "name": "RANI CHENNAMMA",
        "origin": "Sangli",
        "destination": "KSR Bengaluru",
        "base_delay": 28,
        "speed": 72.0,
        "phase_offset": 0.79,
        "route": [
            ("SLI", "Sangli", 16.8524, 74.5815),
            ("MRJ", "Miraj Jn", 16.8198, 74.6504),
            ("GKK", "Gokak Road", 16.1697, 74.8235),
            ("DWR", "Dharwad", 15.4589, 75.0078),
            ("UBL", "Hubballi Jn", 15.3500, 75.1386),
            ("DVG", "Davangere", 14.4644, 75.9218),
            ("MYS", "Mysuru Jn", 12.2958, 76.6394),
            ("SBC", "KSR Bengaluru", 12.9776, 77.5660),
        ],
    },
}


class DemoDataAdapter(TrainDataProvider):
    """
    Deployment-safe train simulation provider.

    The frontend sees:
        DEMO + SIMULATED

    It never pretends that GPS or railway telemetry is live.
    """

    # One complete simulated journey takes about 18 minutes.
    JOURNEY_SECONDS = 18 * 60

    def __init__(self) -> None:
        self._created_at = monotonic()

        print(
            "[DEMO] Simulated railway provider initialized."
        )

        print(
            "[DEMO] Trains:",
            list(DEMO_TRAINS.keys()),
        )

    # =========================================================
    # TRAIN NUMBERS
    # =========================================================

    @staticmethod
    def _train_config(
        train_id: str,
    ) -> dict[str, object]:

        key = str(train_id).strip()

        config = DEMO_TRAINS.get(key)

        if config is None:
            raise ProviderUnavailable(
                f"Demo train {key} is not configured."
            )

        return config

    # =========================================================
    # ROUTE
    # =========================================================

    def _route_stations(
        self,
        train_id: str,
    ) -> list[Station]:

        config = self._train_config(
            train_id
        )

        raw_route = config["route"]

        stations: list[Station] = []

        for index, item in enumerate(
            raw_route,
            start=1,
        ):
            code = str(item[0])
            name = str(item[1])

            latitude = float(item[2])
            longitude = float(item[3])

            stations.append(
                Station(
                    station_id=code,
                    name=name,
                    code=code,
                    sequence=index,
                    data_source="DEMO",
                    latitude=latitude,
                    longitude=longitude,
                )
            )

        return stations

    # =========================================================
    # SIMULATION STATE
    # =========================================================

    def _simulation_state(
        self,
        train_id: str,
    ) -> tuple[
        float,
        float,
        int,
        float,
        str,
        str,
        float,
        list[Station],
    ]:

        config = self._train_config(
            train_id
        )

        stations = self._route_stations(
            train_id
        )

        if len(stations) < 2:
            raise ProviderUnavailable(
                f"Demo route for {train_id} "
                "needs at least two stations."
            )

        phase_offset = float(
            config.get(
                "phase_offset",
                0.0,
            )
        )

        elapsed = (
            monotonic()
            - self._created_at
        )

        phase = (
            (
                elapsed
                / self.JOURNEY_SECONDS
            )
            + phase_offset
        ) % 1.0

        segment_count = (
            len(stations) - 1
        )

        scaled = (
            phase
            * segment_count
        )

        segment_index = min(
            segment_count - 1,
            int(scaled),
        )

        segment_progress = (
            scaled
            - segment_index
        )

        current_station = (
            stations[segment_index]
        )

        next_station = (
            stations[segment_index + 1]
        )

        current_lat = float(
            current_station.latitude
        )

        current_lon = float(
            current_station.longitude
        )

        next_lat = float(
            next_station.latitude
        )

        next_lon = float(
            next_station.longitude
        )

        latitude = (
            current_lat
            + (
                next_lat
                - current_lat
            )
            * segment_progress
        )

        longitude = (
            current_lon
            + (
                next_lon
                - current_lon
            )
            * segment_progress
        )

        segment_distance = (
            _distance_km(
                current_lat,
                current_lon,
                next_lat,
                next_lon,
            )
        )

        distance_remaining = max(
            0.0,
            segment_distance
            * (
                1.0
                - segment_progress
            ),
        )

        base_speed = float(
            config.get(
                "speed",
                70.0,
            )
        )

        # Smooth simulated speed variation.
        speed_wave = sin(
            elapsed / 25.0
        ) * 8.0

        speed = max(
            25.0,
            min(
                120.0,
                base_speed
                + speed_wave,
            ),
        )

        base_delay = int(
            config.get(
                "base_delay",
                10,
            )
        )

        # Delay changes slightly during the simulation
        # so the dashboard visibly updates.
        delay_wave = int(
            round(
                sin(
                    elapsed / 45.0
                )
                * 4
            )
        )

        current_delay = max(
            0,
            base_delay
            + delay_wave,
        )

        return (
            latitude,
            longitude,
            current_delay,
            speed,
            current_station.name,
            next_station.name,
            distance_remaining,
            stations,
        )

    # =========================================================
    # LIST TRAINS
    # =========================================================

    def list_trains(
        self,
    ) -> Sequence[Train]:

        trains: list[Train] = []

        now = _utc_now()

        for train_id, config in (
            DEMO_TRAINS.items()
        ):

            trains.append(
                Train(
                    train_id=train_id,
                    name=str(
                        config["name"]
                    ),
                    number=train_id,
                    status=(
                        "SIMULATED RUNNING"
                    ),
                    origin=str(
                        config["origin"]
                    ),
                    destination=str(
                        config["destination"]
                    ),
                    data_source="DEMO",
                    source="DEMO",
                    is_live=False,
                    data_quality="SIMULATED",
                    last_updated=now,
                    weather=(
                        WeatherData.unavailable()
                    ),
                    eta=None,
                    eta_confidence=0.82,
                )
            )

        return trains

    # =========================================================
    # GET TRAIN
    # =========================================================

    def get_train(
        self,
        train_id: str,
    ) -> Train | None:

        config = self._train_config(
            train_id
        )

        return Train(
            train_id=str(
                train_id
            ).strip(),
            name=str(
                config["name"]
            ),
            number=str(
                train_id
            ).strip(),
            status="SIMULATED RUNNING",
            origin=str(
                config["origin"]
            ),
            destination=str(
                config["destination"]
            ),
            data_source="DEMO",
            source="DEMO",
            is_live=False,
            data_quality="SIMULATED",
            last_updated=_utc_now(),
            weather=WeatherData.unavailable(),
            eta=None,
            eta_confidence=0.82,
        )

    # =========================================================
    # GET ROUTE
    # =========================================================

    def get_route(
        self,
        train_id: str,
    ) -> Sequence[Station] | None:

        return self._route_stations(
            train_id
        )

    # =========================================================
    # GET TELEMETRY
    # =========================================================

    def get_telemetry(
        self,
        train_id: str,
    ) -> TrainTelemetry | None:

        (
            latitude,
            longitude,
            current_delay,
            speed,
            current_station,
            next_station,
            distance_remaining,
            route,
        ) = self._simulation_state(
            train_id
        )

        config = self._train_config(
            train_id
        )

        now = _utc_now()

        return TrainTelemetry(
            train_id=str(
                train_id
            ).strip(),

            latitude=latitude,
            longitude=longitude,

            speed_kmph=round(
                speed,
                1,
            ),

            current_delay=current_delay,

            recorded_at=now,

            data_source="DEMO",
            data_quality="SIMULATED",

            train_number=str(
                train_id
            ).strip(),

            train_name=str(
                config["name"]
            ),

            next_station=next_station,
            current_station=current_station,

            distance_to_next_station=round(
                distance_remaining,
                2,
            ),

            timestamp=now,
            source="DEMO",

            is_live=False,

            last_updated=now,

            route=[
                {
                    "station_id": station.station_id,
                    "name": station.name,
                    "code": station.code,
                    "sequence": station.sequence,
                    "latitude": station.latitude,
                    "longitude": station.longitude,
                }
                for station in route
            ],
        )

    # =========================================================
    # GET LIVE POSITION
    # =========================================================

    def get_live_position(
        self,
        train_id: str,
    ) -> TrainPosition | None:

        telemetry = self.get_telemetry(
            train_id
        )

        if telemetry is None:
            return None

        return TrainPosition(
            train_id=telemetry.train_id,

            latitude=telemetry.latitude,
            longitude=telemetry.longitude,

            speed_kmph=telemetry.speed_kmph,

            current_delay=telemetry.current_delay,

            recorded_at=telemetry.recorded_at,

            data_source="DEMO",
            source="DEMO",

            is_live=False,
            data_quality="SIMULATED",

            last_updated=telemetry.last_updated,

            next_station=(
                telemetry.next_station
                or None
            ),

            distance_to_next_station=(
                telemetry.distance_to_next_station
            ),

            weather=WeatherData.unavailable(),

            eta=None,
            eta_confidence=0.82,
        )


__all__ = [
    "DemoDataAdapter",
]