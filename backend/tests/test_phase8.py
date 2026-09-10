from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient

from backend.app.adapters.base import ProviderConfigurationError
from backend.app.adapters.live import LiveRailwayDataProvider
from backend.app.config import Settings
from backend.app.main import app
from backend.app.ml.eta_service import ETAPredictionService
from backend.app.schemas import Station, Train, TrainTelemetry, WeatherData
from backend.app.services.realtime_service import RealtimeTrainTrackingService
from backend.app.weather.base import DemoWeatherProvider


class StaleProvider:
    def get_train(self, train_id: str) -> Train:
        return Train(train_id=train_id, name="Test", number="T-1", status="TEST", origin="A", destination="B")

    def get_route(self, train_id: str) -> list[Station]:
        return [
            Station(station_id="a", name="A", code="A", sequence=1),
            Station(station_id="b", name="B", code="B", sequence=2),
        ]

    def get_telemetry(self, train_id: str) -> TrainTelemetry:
        return TrainTelemetry(
            train_id=train_id,
            latitude=28.6,
            longitude=77.21,
            speed_kmph=60,
            current_delay=3,
            recorded_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            data_source="DEMO",
            data_quality="SIMULATED",
        )

    def get_live_position(self, train_id: str):
        return None

    def list_trains(self):
        return []


def test_demo_realtime_normalizes_standard_metadata() -> None:
    with TestClient(app).websocket_connect("/ws/trains/demo-express-101") as websocket:
        event = websocket.receive_json()

    assert {"source", "is_live", "data_quality", "last_updated", "weather", "eta_confidence"} <= event.keys()
    assert event["source"] == "DEMO"
    assert event["is_live"] is False


def test_stale_timestamp_is_marked_stale_and_eta_still_integrates() -> None:
    service = RealtimeTrainTrackingService(StaleProvider(), ETAPredictionService(), stale_after_seconds=30)
    event = service.get_event("test")
    assert event.data_quality == "STALE"
    assert event.current_delay == 3
    assert event.weather.available is False
    assert event.weather.message == "Weather data unavailable"
    assert event.eta_confidence >= 0


def test_invalid_train_id_speed_and_coordinates_are_rejected() -> None:
    base = {
        "train_id": "train-1",
        "latitude": 28.6,
        "longitude": 77.2,
        "speed_kmph": 60,
        "current_delay": 0,
        "recorded_at": datetime.now(timezone.utc),
        "data_source": "DEMO",
        "data_quality": "SIMULATED",
    }
    for field, value in (("train_id", ""), ("speed_kmph", -1), ("latitude", 91)):
        with pytest.raises(ValidationError):
            TrainTelemetry(**{**base, field: value})


def test_weather_unavailable_contract_contains_no_fake_values() -> None:
    weather = DemoWeatherProvider().get_weather(28.6, 77.2, datetime.now(timezone.utc))
    assert weather.available is False
    assert weather.message == "DEMO weather unavailable"
    assert weather.temperature is None
    assert weather.source == "DEMO"


def test_live_provider_requires_configuration_without_fabricating_data() -> None:
    provider = LiveRailwayDataProvider(Settings(data_provider="live"))
    with pytest.raises(ProviderConfigurationError, match="RAILWAY_API_BASE_URL"):
        provider.list_trains()


def test_metadata_endpoint_exposes_demo_source() -> None:
    response = TestClient(app).get("/api/trains/metadata")
    assert response.status_code == 200
    payload = response.json()
    assert payload["data_source"] == "DEMO"
    assert payload["is_live"] is False
    assert "weather_configured" in payload
