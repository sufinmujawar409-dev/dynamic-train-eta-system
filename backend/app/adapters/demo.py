"""Development-only simulated train data adapter.

This adapter intentionally does not represent live railway data.
"""

import math
import time
from datetime import datetime, timedelta, timezone

from ..schemas import ETAPrediction, Station, Train, TrainPosition, TrainTelemetry


class DemoDataAdapter:
    """Simulate movement between fixed demo stations; never live telemetry."""

    _station_coordinates = {
        "central": (28.6139, 77.2090),
        "midtown": (28.6280, 77.2250),
        "north-junction": (28.6460, 77.2410),
    }
    _segment_duration_seconds = 45.0

    _trains = [
        Train(
            train_id="demo-express-101",
            name="DEMO Express",
            number="DEMO-101",
            status="DEMO - on time",
            origin="Central Station",
            destination="North Junction",
        )
    ]
    _routes = {
        "demo-express-101": [
            Station(station_id="central", name="Central Station", code="CEN", sequence=1),
            Station(station_id="midtown", name="Midtown", code="MID", sequence=2),
            Station(station_id="north-junction", name="North Junction", code="NJN", sequence=3),
        ]
    }

    def list_trains(self) -> list[Train]:
        return list(self._trains)

    def get_train(self, train_id: str) -> Train | None:
        return next((train for train in self._trains if train.train_id == train_id), None)

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
        )

    def get_telemetry(self, train_id: str) -> TrainTelemetry | None:
        if self.get_train(train_id) is None:
            return None
        route = self.get_route(train_id)
        assert route is not None
        elapsed = time.monotonic() % (self._segment_duration_seconds * (len(route) - 1))
        segment = min(int(elapsed // self._segment_duration_seconds), len(route) - 2)
        fraction = (elapsed % self._segment_duration_seconds) / self._segment_duration_seconds
        start = self._station_coordinates[route[segment].station_id]
        end = self._station_coordinates[route[segment + 1].station_id]
        latitude = start[0] + (end[0] - start[0]) * fraction
        longitude = start[1] + (end[1] - start[1]) * fraction
        speed = 68 + math.sin(time.monotonic() / 8) * 10
        delay = max(0, round(2 + math.sin(time.monotonic() / 18)))
        recorded_at = datetime.now(timezone.utc)
        train = self.get_train(train_id)
        assert train is not None
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
            next_station=route[segment + 1].name,
            distance_to_next_station=round(max(0, 10 * (1 - fraction)), 2),
            timestamp=recorded_at,
            source="DEMO",
            is_live=False,
            last_updated=recorded_at,
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
                estimated_arrival=now + timedelta(minutes=15 * station.sequence),
                minutes_remaining=15 * station.sequence,
                confidence=0.8,
            )
            for station in route[1:]
        ]
