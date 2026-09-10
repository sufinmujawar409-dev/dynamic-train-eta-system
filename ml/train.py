"""Train and persist the DEMO ETA model.

The input CSV is intentionally synthetic and must not be treated as railway data.
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

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
TARGET = "eta_minutes"
ROOT = Path(__file__).resolve().parent
DATASET_PATH = ROOT / "historical_eta_demo.csv"
ARTIFACT_DIR = ROOT / "artifacts"
MODEL_PATH = ARTIFACT_DIR / "eta_model.joblib"
METADATA_PATH = ARTIFACT_DIR / "metadata.json"
MODEL_VERSION = "demo-rf-v1"


def train_model() -> dict[str, float | str]:
    frame = pd.read_csv(DATASET_PATH)
    if frame[FEATURES + [TARGET]].isnull().any().any():
        raise ValueError("DEMO training data contains missing feature or target values")
    x_train, x_test, y_train, y_test = train_test_split(
        frame[FEATURES], frame[TARGET], test_size=0.2, random_state=42
    )
    model = RandomForestRegressor(
        n_estimators=100, max_depth=8, random_state=42, n_jobs=1
    )
    model.fit(x_train, y_train)
    predictions = model.predict(x_test)
    metrics = {
        "mae": float(mean_absolute_error(y_test, predictions)),
        "rmse": float(mean_squared_error(y_test, predictions) ** 0.5),
        "r2": float(r2_score(y_test, predictions)),
    }
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    metadata = {
        "model_version": MODEL_VERSION,
        "model_type": "RandomForestRegressor",
        "features": FEATURES,
        "target": TARGET,
        "dataset": DATASET_PATH.name,
        "dataset_type": "DEMO synthetic historical data",
        "metrics": metrics,
    }
    METADATA_PATH.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


if __name__ == "__main__":
    print(json.dumps(train_model(), indent=2))
