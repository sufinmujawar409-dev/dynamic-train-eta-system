from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from backend.app.main import app
from backend.app.schemas import TrainTelemetry

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "dynamic-train-eta",
        "environment": "development",
    }


def test_train_endpoints_return_demo_data() -> None:
    train_response = client.get("/api/trains")
    assert train_response.status_code == 200
    train = train_response.json()[0]
    train_id = train["train_id"]
    assert train["data_source"] == "DEMO"

    for suffix in ("", "/live", "/route", "/eta"):
        response = client.get(f"/api/trains/{train_id}{suffix}")
        assert response.status_code == 200
        payload = response.json()
        records = payload if isinstance(payload, list) else [payload]
        assert all(record["data_source"] == "DEMO" for record in records)


def test_unknown_train_returns_not_found() -> None:
    response = client.get("/api/trains/unknown-train")
    assert response.status_code == 404
    assert response.json()["detail"] == "Train 'unknown-train' was not found"


def test_train_websocket_stream_returns_validated_demo_event() -> None:
    with client.websocket_connect("/ws/trains/demo-express-101") as websocket:
        event = websocket.receive_json()

    assert event["train_id"] == "demo-express-101"
    assert event["train_number"] == "DEMO-101"
    assert event["data_source"] == "DEMO"
    assert event["data_quality"] == "SIMULATED"
    assert {"latitude", "longitude", "speed", "current_delay", "next_station", "eta", "timestamp"} <= event.keys()


def test_train_websocket_stream_sends_successive_updates() -> None:
    with client.websocket_connect("/ws/trains/demo-express-101") as websocket:
        first = websocket.receive_json()
        second = websocket.receive_json()

    assert first["timestamp"] != second["timestamp"]
    assert first["data_quality"] == second["data_quality"] == "SIMULATED"


def test_train_websocket_can_reconnect_after_disconnect() -> None:
    with client.websocket_connect("/ws/trains/demo-express-101") as websocket:
        websocket.receive_json()

    with client.websocket_connect("/ws/trains/demo-express-101") as websocket:
        event = websocket.receive_json()

    assert event["train_id"] == "demo-express-101"


def test_provider_position_validation_rejects_invalid_coordinates() -> None:
    with pytest.raises(ValidationError):
        TrainTelemetry(
            train_id="demo-express-101",
            latitude=91,
            longitude=77.2,
            speed_kmph=60,
            current_delay=0,
            recorded_at="2026-09-10T00:00:00Z",
            data_source="DEMO",
            data_quality="SIMULATED",
        )
