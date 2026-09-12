"""Development-only simulated train data adapter.

This adapter intentionally does not represent live railway data.
All train positions and operational values are simulated.
"""

import math
import time
from datetime import datetime, timedelta, timezone

from ..schemas import ETAPrediction, Station, Train, TrainPosition, TrainTelemetry


class DemoDataAdapter:
    """Simulate multiple trains moving across fixed demo routes."""

    _station_coordinates = {
        # Route A
        "central": (28.6139, 77.2090),
        "midtown": (28.6280, 77.2250),
        "north-junction": (28.6460, 77.2410),
        "north-terminal": (28.6650, 77.2550),

        # Route B
        "east-central": (28.6200, 77.2350),
        "east-market": (28.6350, 77.2550),
        "east-junction": (28.6500, 77.2750),
        "east-terminal": (28.6680, 77.2920),

        # Route C
        "south-central": (28.6000, 77.2050),
        "south-market": (28.5820, 77.2150),
        "south-junction": (28.5650, 77.2300),
        "south-terminal": (28.5450, 77.2450),

        # Route D
        "west-central": (28.6150, 77.1850),
        "west-market": (28.6300, 77.1650),
        "west-junction": (28.6450, 77.1450),
        "west-terminal": (28.6600, 77.1250),

        # Route E
        "central-hub": (28.6100, 77.2200),
        "university": (28.6250, 77.2100),
        "airport-junction": (28.6400, 77.1950),
        "airport-terminal": (28.6550, 77.1800),
    }

    _segment_duration_seconds = 45.0

    _trains = [
        Train(
            train_id="demo-express-101",
            name="DEMO Express",
            number="DEMO-101",
            status="DEMO - on time",
            origin="Central Station",
            destination="North Terminal",
        ),
        Train(
            train_id="demo-intercity-202",
            name="DEMO InterCity",
            number="DEMO-202",
            status="DEMO - delayed",
            origin="East Central",
            destination="East Terminal",
        ),
        Train(
            train_id="demo-superfast-303",
            name="DEMO Superfast",
            number="DEMO-303",
            status="DEMO - on time",
            origin="South Central",
            destination="South Terminal",
        ),
        Train(
            train_id="demo-rapid-404",
            name="DEMO Rapid",
            number="DEMO-404",
            status="DEMO - delayed",
            origin="West Central",
            destination="West Terminal",
        ),
        Train(
            train_id="demo-city-505",
            name="DEMO City Express",
            number="DEMO-505",
            status="DEMO - on time",
            origin="Central Hub",
            destination="Airport Terminal",
        ),
    ]

    _routes = {
        "demo-express-101": [
            Station(
                station_id="central",
                name="Central Station",
                code="CEN",
                sequence=1,
            ),
            Station(
                station_id="midtown",
                name="Midtown",
                code="MID",
                sequence=2,
            ),
            Station(
                station_id="north-junction",
                name="North Junction",
                code="NJN",
                sequence=3,
            ),
            Station(
                station_id="north-terminal",
                name="North Terminal",
                code="NTR",
                sequence=4,
            ),
        ],
        "demo-intercity-202": [
            Station(
                station_id="east-central",
                name="East Central",
                code="ECN",
                sequence=1,
            ),
            Station(
                station_id="east-market",
                name="East Market",
                code="EMK",
                sequence=2,
            ),
            Station(
                station_id="east-junction",
                name="East Junction",
                code="EJN",
                sequence=3,
            ),
            Station(
                station_id="east-terminal",
                name="East Terminal",
                code="ETR",
                sequence=4,
            ),
        ],
        "demo-superfast-303": [
            Station(
                station_id="south-central",
                name="South Central",
                code="SCN",
                sequence=1,
            ),
            Station(
                station_id="south-market",
                name="South Market",
                code="SMK",
                sequence=2,
            ),
            Station(
                station_id="south-junction",
                name="South Junction",
                code="SJN",
                sequence=3,
            ),
            Station(
                station_id="south-terminal",
                name="South Terminal",
                code="STR",
                sequence=4,
            ),
        ],
        "demo-rapid-404": [
            Station(
                station_id="west-central",
                name="West Central",
                code="WCN",
                sequence=1,
            ),
            Station(
                station_id="west-market",
                name="West Market",
                code="WMK",
                sequence=2,
            ),
            Station(
                station_id="west-junction",
                name="West Junction",
                code="WJN",
                sequence=3,
            ),
            Station(
                station_id="west-terminal",
                name="West Terminal",
                code="WTR",
                sequence=4,
            ),
        ],
        "demo-city-505": [
            Station(
                station_id="central-hub",
                name="Central Hub",
                code="CHB",
                sequence=1,
            ),
            Station(
                station_id="university",
                name="University",
                code="UNI",
                sequence=2,
            ),
            Station(
                station_id="airport-junction",
                name="Airport Junction",
                code="AJN",
                sequence=3,
            ),
            Station(
                station_id="airport-terminal",
                name="Airport Terminal",
                code="ATR",
                sequence=4,
            ),
        ],
    }

    # Different movement characteristics for each demo train.
    _train_profiles = {
        "demo-express-101": {
            "speed": 72,
            "delay": 1,
            "phase": 0,
        },
        "demo-intercity-202": {
            "speed": 62,
            "delay": 7,
            "phase": 12,
        },
        "demo-superfast-303": {
            "speed": 88,
            "delay": 0,
            "phase": 25,
        },
        "demo-rapid-404": {
            "speed": 55,
            "delay": 5,
            "phase": 37,
        },
        "demo-city-505": {
            "speed": 68,
            "delay": 2,
            "phase": 50,
        },
    }

    def list_trains(self) -> list[Train]:
        return list(self._trains)

    def get_train(self, train_id: str) -> Train | None:
        return next(
            (train for train in self._trains if train.train_id == train_id),
            None,
        )

    def get_live_position(self, train_id: str) -> TrainPosition | None:
        telemetry = self.get_telemetry(train_id)

        if telemetry is None:
            return None

        return TrainPosition(
            train_id=telemetry.train_id,
            latitude=telemetry.latitude,
            longitude=telemetry.longitude,
            speed_kmph=telemetry.speed_kmph,
            recorded_at=telemetry.recorded_at,
            data_source=telemetry.data_source,
            current_delay=telemetry.current_delay,
            source=telemetry.source,
            is_live=False,
            data_quality=telemetry.data_quality,
            last_updated=telemetry.last_updated,
            next_station=telemetry.next_station,
            distance_to_next_station=telemetry.distance_to_next_station,
        )

    def get_telemetry(self, train_id: str) -> TrainTelemetry | None:
        train = self.get_train(train_id)

        if train is None:
            return None

        route = self.get_route(train_id)

        if route is None or len(route) < 2:
            return None

        profile = self._train_profiles.get(
            train_id,
            {
                "speed": 65,
                "delay": 2,
                "phase": 0,
            },
        )

        # Each train gets its own movement phase so they don't move together.
        now_monotonic = time.monotonic() + profile["phase"]

        cycle_duration = self._segment_duration_seconds * (len(route) - 1)

        elapsed = now_monotonic % cycle_duration

        segment = min(
            int(elapsed // self._segment_duration_seconds),
            len(route) - 2,
        )

        fraction = (
            elapsed % self._segment_duration_seconds
        ) / self._segment_duration_seconds

        start_station = route[segment]
        next_station = route[segment + 1]

        start = self._station_coordinates[start_station.station_id]
        end = self._station_coordinates[next_station.station_id]

        # Smooth movement between two stations.
        latitude = start[0] + (end[0] - start[0]) * fraction
        longitude = start[1] + (end[1] - start[1]) * fraction

        # Slight speed variation so the dashboard looks alive.
        speed = (
            profile["speed"]
            + math.sin(time.monotonic() / 8 + profile["phase"]) * 8
        )

        speed = max(20, round(speed, 1))

        # Slight delay variation.
        delay = max(
            0,
            round(
                profile["delay"]
                + math.sin(time.monotonic() / 18 + profile["phase"]) * 1
            ),
        )

        # Approximate demo distance remaining in km.
        distance_to_next_station = round(
            max(0, 10 * (1 - fraction)),
            2,
        )

        recorded_at = datetime.now(timezone.utc)

        return TrainTelemetry(
            train_id=train_id,
            latitude=latitude,
            longitude=longitude,
            speed_kmph=speed,
            current_delay=delay,
            recorded_at=recorded_at,
            data_source="DEMO",
            data_quality="SIMULATED",
            train_number=train.number,
            train_name=train.name,
            next_station=next_station.name,
            current_station=start_station.name,
            distance_to_next_station=distance_to_next_station,
            timestamp=recorded_at,
            source="DEMO",
            is_live=False,
            last_updated=recorded_at,
            route=[
                {
                    "station_code": station.code,
                    "station_name": station.name,
                    "latitude": station.latitude,
                    "longitude": station.longitude,
                    "sequence": station.sequence,
                }
                for station in route
            ],
        )

    def get_route(self, train_id: str) -> list[Station] | None:
        if train_id not in self._routes:
            return None

        return list(self._routes[train_id])

    def get_eta(self, train_id: str) -> list[ETAPrediction] | None:
        route = self.get_route(train_id)

        if route is None:
            return None

        now = datetime.now(timezone.utc)

        return [
            ETAPrediction(
                train_id=train_id,
                station_id=station.station_id,
                station_name=station.name,
                estimated_arrival=now + timedelta(
                    minutes=15 * station.sequence
                ),
                minutes_remaining=15 * station.sequence,
                confidence=0.8,
            )
            for station in route[1:]
        ]