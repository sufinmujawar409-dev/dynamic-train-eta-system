from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import pandas as pd


ROOT_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = ROOT_DIR / "artifacts"

MODEL_PATH = ARTIFACT_DIR / "eta_model.joblib"
METADATA_PATH = ARTIFACT_DIR / "metadata.json"

FEATURES = [
    "current_speed",
    "current_delay",
    "distance_remaining",
    "historical_delay",
    "previous_station_delay",
    "section_average_speed",
    "weather_factor",
    "congestion_factor",
    "signal_halt_minutes",
]


def load_model() -> Any:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"ETA model not found: {MODEL_PATH}"
        )

    return joblib.load(MODEL_PATH)


def load_metadata() -> dict[str, Any]:
    if not METADATA_PATH.exists():
        raise FileNotFoundError(
            f"ETA metadata not found: {METADATA_PATH}"
        )

    with METADATA_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def predict_minutes(
    model: Any,
    values: dict[str, float],
) -> float:
    missing = [feature for feature in FEATURES if feature not in values]

    if missing:
        raise ValueError(
            f"Missing ETA model features: {', '.join(missing)}"
        )

    row = {
        feature: float(values[feature])
        for feature in FEATURES
    }

    dataframe = pd.DataFrame([row], columns=FEATURES)

    prediction = model.predict(dataframe)

    return float(prediction[0])