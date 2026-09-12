"""
Dynamic Train ETA model training.

This script generates a realistic DEMO training dataset, trains a RandomForestRegressor,
evaluates it with MAE/RMSE/R2, and saves:
  - historical_eta_demo.csv
  - eta_model.joblib
  - metadata.json

Important:
This is still synthetic/demo data. It is NOT a claim of real Indian Railways accuracy.
Replace the generated CSV with authorized historical railway data for production.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split


ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "historical_eta_demo.csv"
MODEL_PATH = ROOT / "eta_model.joblib"
METADATA_PATH = ROOT / "metadata.json"

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
MODEL_VERSION = "demo-rf-v2"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def generate_row(rng: random.Random) -> dict[str, float]:
    """
    Generate one synthetic but internally consistent railway ETA example.

    The target is based on a physics-inspired travel-time baseline plus:
    - current delay
    - historical/previous delay propagation
    - weather
    - congestion
    - signal halts
    - a small measurement/noise component
    """
    current_speed = rng.uniform(20, 115)
    section_average_speed = rng.uniform(40, 105)

    distance_remaining = rng.uniform(2, 180)

    current_delay = max(0.0, rng.gauss(8.0, 10.0))
    historical_delay = max(0.0, rng.gauss(7.0, 8.0))
    previous_station_delay = max(0.0, rng.gauss(5.0, 6.0))

    weather_factor = rng.choices(
        [1.0, 1.08, 1.18, 1.35, 1.55],
        weights=[62, 16, 10, 8, 4],
        k=1,
    )[0]

    congestion_factor = rng.choices(
        [0.85, 1.0, 1.08, 1.18, 1.35],
        weights=[10, 48, 18, 16, 8],
        k=1,
    )[0]

    signal_halt_minutes = clamp(
        rng.gauss(1.5 + congestion_factor * 1.0, 2.2),
        0,
        15,
    )

    # Effective speed becomes lower under poor conditions.
    effective_speed = max(
        18.0,
        min(current_speed, section_average_speed)
        / weather_factor
        / congestion_factor,
    )

    base_minutes = (distance_remaining / effective_speed) * 60.0

    delay_propagation = (
        0.68 * current_delay
        + 0.18 * historical_delay
        + 0.22 * previous_station_delay
    )

    operational_effect = (
        signal_halt_minutes
        + max(0.0, congestion_factor - 1.0) * 9.0
        + max(0.0, weather_factor - 1.0) * 7.0
    )

    noise = rng.gauss(0.0, 1.8)

    eta_minutes = max(
        1.0,
        base_minutes + delay_propagation + operational_effect + noise,
    )

    return {
        "current_speed": round(current_speed, 3),
        "current_delay": round(current_delay, 3),
        "distance_remaining": round(distance_remaining, 3),
        "historical_delay": round(historical_delay, 3),
        "previous_station_delay": round(previous_station_delay, 3),
        "section_average_speed": round(section_average_speed, 3),
        "weather_factor": round(float(weather_factor), 3),
        "congestion_factor": round(float(congestion_factor), 3),
        "signal_halt_minutes": round(signal_halt_minutes, 3),
        TARGET: round(eta_minutes, 3),
    }


def build_dataset(rows: int = 5000, seed: int = 42) -> pd.DataFrame:
    rng = random.Random(seed)
    data = [generate_row(rng) for _ in range(rows)]
    frame = pd.DataFrame(data, columns=FEATURES + [TARGET])
    frame.to_csv(DATA_PATH, index=False)
    return frame


def train(frame: pd.DataFrame) -> dict[str, float]:
    X = frame[FEATURES]
    y = frame[TARGET]

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.20,
        random_state=42,
    )

    model = RandomForestRegressor(
        n_estimators=300,
        max_depth=12,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=1,
    )
    model.fit(X_train, y_train)

    predictions = model.predict(X_test)

    mae = float(mean_absolute_error(y_test, predictions))
    rmse = float(math.sqrt(mean_squared_error(y_test, predictions)))
    r2 = float(r2_score(y_test, predictions))

    joblib.dump(model, MODEL_PATH)

    metadata = {
        "model_version": MODEL_VERSION,
        "target": TARGET,
        "features": FEATURES,
        "rows": int(len(frame)),
        "test_rows": int(len(X_test)),
        "metrics": {
            "mae_minutes": round(mae, 4),
            "rmse_minutes": round(rmse, 4),
            "r2": round(r2, 4),
        },
        "data_type": "synthetic_demo",
        "warning": (
            "Synthetic training data only. Do not present these metrics "
            "as real railway prediction accuracy."
        ),
    }

    METADATA_PATH.write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    print("\n=== Dynamic Train ETA Model ===")
    print(f"Dataset : {DATA_PATH}")
    print(f"Model   : {MODEL_PATH}")
    print(f"Metadata: {METADATA_PATH}")
    print(f"Rows    : {len(frame):,}")
    print(f"MAE     : {mae:.2f} min")
    print(f"RMSE    : {rmse:.2f} min")
    print(f"R2      : {r2:.4f}")
    print(f"Version : {MODEL_VERSION}")

    print("\nFeature importance:")
    importance = pd.Series(
        model.feature_importances_,
        index=FEATURES,
    ).sort_values(ascending=False)
    for name, value in importance.items():
        print(f"  {name:28s} {value:.4f}")

    return metadata["metrics"]


if __name__ == "__main__":
    dataset = build_dataset(rows=5000, seed=42)
    train(dataset)
