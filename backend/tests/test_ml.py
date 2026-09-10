import pytest

from backend.app.ml.eta_service import ETAPredictionService, InvalidPredictionInput
from ml.inference import load_metadata, load_model


def test_model_and_metadata_load() -> None:
    model = load_model()
    metadata = load_metadata()
    assert model is not None
    assert metadata["model_version"] == "demo-rf-v1"
    assert metadata["model_type"] == "RandomForestRegressor"


def test_prediction_is_non_negative_integer() -> None:
    prediction = ETAPredictionService().predict_minutes(
        current_speed=60, current_delay=0, distance_remaining=10
    )
    assert isinstance(prediction, int)
    assert prediction >= 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"current_speed": 60, "current_delay": 0, "distance_remaining": -1},
        {"current_speed": 0, "current_delay": 0, "distance_remaining": 10},
        {"current_speed": 60, "current_delay": -1, "distance_remaining": 10},
    ],
)
def test_invalid_prediction_input(kwargs: dict[str, int]) -> None:
    with pytest.raises(InvalidPredictionInput):
        ETAPredictionService().predict_minutes(**kwargs)


def test_missing_prediction_input_is_rejected() -> None:
    with pytest.raises(InvalidPredictionInput, match="Missing model features"):
        ETAPredictionService().predict({})


def test_eta_endpoint_returns_ml_predictions_with_demo_contract() -> None:
    from fastapi.testclient import TestClient
    from backend.app.main import app

    response = TestClient(app).get("/api/trains/demo-express-101/eta")
    assert response.status_code == 200
    payload = response.json()
    assert payload
    assert all(item["data_source"] == "DEMO" for item in payload)
    assert all(isinstance(item["minutes_remaining"], int) for item in payload)
    assert all(item["model_version"] == "demo-rf-v1" for item in payload)
