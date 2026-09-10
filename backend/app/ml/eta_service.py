"""Validated, reusable ETA prediction service."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from numbers import Real

from ml.inference import load_metadata, load_model, predict_minutes


class InvalidPredictionInput(ValueError):
    """Raised when an ETA feature is missing or outside its valid range."""


@dataclass(frozen=True)
class RealtimePrediction:
    eta_minutes: int
    predicted_arrival: datetime
    predicted_delay: int
    confidence_score: float
    confidence_level: str
    prediction_source: str


def _confidence_level(score: float) -> str:
    if score >= 0.8:
        return "HIGH"
    if score >= 0.6:
        return "MEDIUM"
    return "LOW"


class ETAPredictionService:
    def __init__(self) -> None:
        self.model = load_model()
        self.metadata = load_metadata()

    def predict_minutes(
        self,
        *,
        current_speed: Real,
        current_delay: Real,
        distance_remaining: Real,
        historical_delay: Real = 0,
        previous_station_delay: Real = 0,
        section_average_speed: Real = 50,
        weather_factor: Real = 1,
        congestion_factor: Real = 1,
        signal_halt_minutes: Real = 0,
    ) -> int:
        values = {
            "current_speed": current_speed,
            "current_delay": current_delay,
            "distance_remaining": distance_remaining,
            "historical_delay": historical_delay,
            "previous_station_delay": previous_station_delay,
            "section_average_speed": section_average_speed,
            "weather_factor": weather_factor,
            "congestion_factor": congestion_factor,
            "signal_halt_minutes": signal_halt_minutes,
        }
        return self.predict(values)

    def predict_realtime(
        self,
        *,
        observed_at: datetime,
        current_speed: Real,
        current_delay: Real,
        distance_to_next_station: Real,
        historical_delay: Real = 2,
        previous_station_delay: Real = 1,
        average_sectional_speed: Real = 60,
        congestion_factor: Real = 1,
        weather_factor: Real = 1,
        prediction_source: str = "DEMO",
    ) -> RealtimePrediction:
        distance = max(0.0, float(distance_to_next_station))
        sectional_speed = max(1.0, float(average_sectional_speed))
        safe_speed = max(1.0, float(current_speed))
        baseline_speed = max(safe_speed, sectional_speed * 0.25)
        baseline_minutes = max(0, round((distance / baseline_speed) * 60))
        try:
            ml_minutes = self.predict_minutes(
                current_speed=safe_speed,
                current_delay=current_delay,
                distance_remaining=distance,
                historical_delay=historical_delay,
                previous_station_delay=previous_station_delay,
                section_average_speed=sectional_speed,
                weather_factor=weather_factor,
                congestion_factor=congestion_factor,
                signal_halt_minutes=0,
            )
            eta_minutes = max(0, round((ml_minutes + baseline_minutes) / 2))
            confidence_score = 0.85 if float(current_speed) > 1 else 0.65
            source = prediction_source
        except (AttributeError, InvalidPredictionInput, OSError, RuntimeError, TypeError, ValueError):
            eta_minutes = baseline_minutes
            confidence_score = 0.45
            source = "UNAVAILABLE"
        return RealtimePrediction(
            eta_minutes=max(0, eta_minutes),
            predicted_arrival=observed_at + timedelta(minutes=max(0, eta_minutes)),
            predicted_delay=max(0, round(float(current_delay))),
            confidence_score=confidence_score,
            confidence_level=_confidence_level(confidence_score),
            prediction_source=source if source in {"LIVE", "DEMO"} else "UNAVAILABLE",
        )

    def predict(self, features: Mapping[str, Real]) -> int:
        """Validate a feature mapping and return the predicted ETA in minutes."""
        required = (
            "current_speed",
            "current_delay",
            "distance_remaining",
            "historical_delay",
            "previous_station_delay",
            "section_average_speed",
            "weather_factor",
            "congestion_factor",
            "signal_halt_minutes",
        )
        missing = [name for name in required if name not in features]
        if missing:
            raise InvalidPredictionInput(f"Missing model features: {', '.join(missing)}")
        values = {name: features[name] for name in required}
        for name, value in values.items():
            if not isinstance(value, Real) or not math.isfinite(float(value)):
                raise InvalidPredictionInput(f"{name} must be a finite number")
        if values["distance_remaining"] < 0:
            raise InvalidPredictionInput("distance_remaining must be non-negative")
        if values["current_speed"] <= 0:
            raise InvalidPredictionInput("current_speed must be greater than zero")
        for name in (
            "current_delay",
            "historical_delay",
            "previous_station_delay",
            "signal_halt_minutes",
        ):
            if values[name] < 0 or values[name] > 24 * 60:
                raise InvalidPredictionInput(f"{name} must be between 0 and 1440 minutes")
        if values["section_average_speed"] <= 0:
            raise InvalidPredictionInput("section_average_speed must be greater than zero")
        if values["weather_factor"] <= 0 or values["congestion_factor"] <= 0:
            raise InvalidPredictionInput("factors must be greater than zero")
        return max(0, round(predict_minutes(self.model, values)))
