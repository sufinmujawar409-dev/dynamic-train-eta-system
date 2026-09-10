from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.schemas import RealtimeTrainEvent, WeatherData
from backend.app.services.alert_service import AlertService
from backend.app.services.analytics_service import AnalyticsService


def event(**updates: object) -> RealtimeTrainEvent:
    timestamp = datetime.now(timezone.utc)
    values = {
        "train_id": "demo-express-101",
        "train_number": "DEMO-101",
        "latitude": 28.6,
        "longitude": 77.2,
        "speed": 60,
        "current_delay": 0,
        "next_station": "Midtown",
        "eta": timestamp + timedelta(minutes=10),
        "timestamp": timestamp,
        "data_source": "DEMO",
        "data_quality": "SIMULATED",
        "source": "DEMO",
        "last_updated": timestamp,
        "weather": WeatherData.unavailable(),
        "distance_to_next_station": 5,
        "prediction_source": "DEMO",
    }
    values.update(updates)
    return RealtimeTrainEvent(**values)


def test_alert_service_generates_severity_and_deduplicates() -> None:
    service = AlertService(cooldown_seconds=300)
    first = service.evaluate(event(current_delay=3), event())
    second = service.evaluate(event(current_delay=6), event(current_delay=3))

    assert any(alert.type == "DELAY_INCREASED" and alert.severity == "WARNING" for alert in first)
    assert any(alert.type == "DELAY_INCREASED" for alert in second) is False


def test_alert_service_generates_major_stale_and_stoppage_alerts() -> None:
    service = AlertService()
    alerts = service.evaluate(event(current_delay=12, speed=0, distance_to_next_station=4, data_quality="STALE"))
    types = {alert.type for alert in alerts}
    assert {"MAJOR_DELAY", "UNUSUAL_STOPPAGE", "DATA_STALE"} <= types
    assert any(alert.severity == "CRITICAL" for alert in alerts)


def test_alert_acknowledgement_and_filtering() -> None:
    service = AlertService()
    alerts = service.evaluate(event(current_delay=12))
    alert = alerts[0]
    assert service.get(alert.id) is not None
    acknowledged = service.acknowledge(alert.id)
    assert acknowledged is not None and acknowledged.acknowledged is True
    assert service.list(acknowledged=True)[0].id == alert.id


def test_alert_api_returns_not_found_for_unknown_alert() -> None:
    response = TestClient(app).get("/api/alerts/unknown-alert")
    assert response.status_code == 404


def test_realtime_websocket_event_contains_alerts_field() -> None:
    with TestClient(app).websocket_connect("/ws/trains/demo-express-101") as websocket:
        payload = websocket.receive_json()
    assert "alerts" in payload
    assert all("severity" in alert for alert in payload["alerts"])


def test_analytics_service_preserves_data_quality_and_counts() -> None:
    first = event(current_delay=0, speed=70)
    second = event(current_delay=12, speed=30, data_quality="STALE")
    summary = AnalyticsService().summarize([first, second], [])
    assert summary["active_trains"] == 1
    assert summary["on_time_trains"] == 1
    assert summary["major_delay_trains"] == 1
    assert summary["data_quality"] == "STALE"
