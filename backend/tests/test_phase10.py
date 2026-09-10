from datetime import datetime, timezone

from backend.app.ml.eta_service import ETAPredictionService


def test_realtime_prediction_is_non_negative_at_zero_speed() -> None:
    prediction = ETAPredictionService().predict_realtime(
        observed_at=datetime.now(timezone.utc),
        current_speed=0,
        current_delay=0,
        distance_to_next_station=10,
        average_sectional_speed=60,
    )
    assert prediction.eta_minutes >= 0
    assert prediction.predicted_arrival.tzinfo is not None


def test_realtime_prediction_carries_delay_and_confidence() -> None:
    prediction = ETAPredictionService().predict_realtime(
        observed_at=datetime.now(timezone.utc),
        current_speed=65,
        current_delay=7,
        distance_to_next_station=8,
        historical_delay=4,
        previous_station_delay=5,
        average_sectional_speed=60,
        weather_factor=1.1,
        congestion_factor=1.1,
        prediction_source="LIVE",
    )
    assert prediction.predicted_delay == 7
    assert prediction.prediction_source == "LIVE"
    assert 0 <= prediction.confidence_score <= 1
    assert prediction.confidence_level in {"HIGH", "MEDIUM", "LOW"}


def test_realtime_prediction_falls_back_to_baseline_when_model_unavailable() -> None:
    service = ETAPredictionService()
    service.model = None
    prediction = service.predict_realtime(
        observed_at=datetime.now(timezone.utc),
        current_speed=40,
        current_delay=2,
        distance_to_next_station=5,
    )
    assert prediction.eta_minutes >= 0
    assert prediction.prediction_source == "UNAVAILABLE"