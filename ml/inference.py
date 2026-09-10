"""Safe loading and prediction helpers for the bundled model artifact."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from .train import ARTIFACT_DIR, FEATURES, METADATA_PATH, MODEL_PATH


def load_model(model_path: Path = MODEL_PATH) -> Any:
    """Load only the trusted, bundled model path."""
    resolved = model_path.resolve()
    if ARTIFACT_DIR.resolve() not in resolved.parents:
        raise ValueError("Model path must be inside the application artifact directory")
    if not resolved.is_file():
        raise FileNotFoundError(f"Model artifact not found: {resolved}")
    return joblib.load(resolved)


def load_metadata(metadata_path: Path = METADATA_PATH) -> dict[str, Any]:
    if metadata_path.resolve().parent != ARTIFACT_DIR.resolve():
        raise ValueError("Metadata path must be inside the application artifact directory")
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def predict_minutes(model: Any, values: dict[str, float]) -> float:
    missing = [feature for feature in FEATURES if feature not in values]
    if missing:
        raise ValueError(f"Missing model features: {', '.join(missing)}")
    frame = pd.DataFrame([[values[feature] for feature in FEATURES]], columns=FEATURES)
    return float(model.predict(frame)[0])
