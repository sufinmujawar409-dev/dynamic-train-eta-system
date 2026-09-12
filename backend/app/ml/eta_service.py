from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
from typing import Any

from ml.inference import load_metadata, load_model, predict_minutes


@dataclass(frozen=True)
class RealtimePrediction:
    eta_minutes: int
    predicted_arrival: datetime
    predicted_delay: int
    confidence_score: float
    confidence_level: str
    prediction_source: str


class ETAPredictionService:
    """
    Runtime service for Dynamic Train ETA prediction.

    Uses:
    - Trained ML ETA model
    - Physics-based distance/speed baseline
    - Confidence heuristic
    - DEMO/LIVE prediction source

    This service accepts both:
        distance_remaining
    and:
        distance_to_next_station

    so it remains compatible with the existing realtime service.
    """

    def __init__(self) -> None:
        self.model = load_model()
        self.metadata = load_metadata()

        self.model_version = str(
            self.metadata.get("model_version", "unknown")
        )

        metrics = self.metadata.get("metrics", {})

        self.mae_minutes = float(
            metrics.get("mae_minutes", 10.0)
        )

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    @staticmethod
    def _confidence_level(score: float) -> str:
        if score >= 0.85:
            return "HIGH"

        if score >= 0.65:
            return "MEDIUM"

        return "LOW"

    @staticmethod
    def _normalise_source(source: Any) -> str:
        value = str(source or "").upper()

        if value in {"LIVE", "DEMO"}:
            return value

        return "UNAVAILABLE"

    @staticmethod
    def _safe_float(
        value: Any,
        default: float = 0.0,
    ) -> float:
        try:
            result = float(value)

            if math.isfinite(result):
                return result

            return default

        except (TypeError, ValueError):
            return default

    # ---------------------------------------------------------
    # Basic ML prediction
    # ---------------------------------------------------------

    def predict_minutes(
        self,
        *,
        current_speed: float,
        current_delay: float,
        distance_remaining: float,
        historical_delay: float,
        previous_station_delay: float,
        section_average_speed: float,
        weather_factor: float,
        congestion_factor: float,
        signal_halt_minutes: float,
    ) -> float:

        values = {
            "current_speed": float(current_speed),
            "current_delay": float(current_delay),
            "distance_remaining": float(distance_remaining),
            "historical_delay": float(historical_delay),
            "previous_station_delay": float(previous_station_delay),
            "section_average_speed": float(section_average_speed),
            "weather_factor": float(weather_factor),
            "congestion_factor": float(congestion_factor),
            "signal_halt_minutes": float(signal_halt_minutes),
        }

        return self.predict(values)

    # ---------------------------------------------------------
    # ML model validation + prediction
    # ---------------------------------------------------------

    def predict(
        self,
        features: dict[str, float],
    ) -> float:

        required_features = {
            "current_speed",
            "current_delay",
            "distance_remaining",
            "historical_delay",
            "previous_station_delay",
            "section_average_speed",
            "weather_factor",
            "congestion_factor",
            "signal_halt_minutes",
        }

        missing = sorted(
            required_features - set(features.keys())
        )

        if missing:
            raise ValueError(
                f"Missing ETA model features: "
                f"{', '.join(missing)}"
            )

        numeric_values: dict[str, float] = {}

        for feature in required_features:
            value = float(features[feature])

            if not math.isfinite(value):
                raise ValueError(
                    f"Invalid numeric value for feature: {feature}"
                )

            numeric_values[feature] = value

        if numeric_values["current_speed"] < 0:
            raise ValueError(
                "current_speed cannot be negative"
            )

        if numeric_values["distance_remaining"] < 0:
            raise ValueError(
                "distance_remaining cannot be negative"
            )

        if numeric_values["current_delay"] < 0:
            raise ValueError(
                "current_delay cannot be negative"
            )

        if numeric_values["historical_delay"] < 0:
            raise ValueError(
                "historical_delay cannot be negative"
            )

        if numeric_values["previous_station_delay"] < 0:
            raise ValueError(
                "previous_station_delay cannot be negative"
            )

        if numeric_values["section_average_speed"] <= 0:
            raise ValueError(
                "section_average_speed must be greater than zero"
            )

        if numeric_values["weather_factor"] <= 0:
            raise ValueError(
                "weather_factor must be greater than zero"
            )

        if numeric_values["congestion_factor"] <= 0:
            raise ValueError(
                "congestion_factor must be greater than zero"
            )

        if numeric_values["signal_halt_minutes"] < 0:
            raise ValueError(
                "signal_halt_minutes cannot be negative"
            )

        prediction = predict_minutes(
            self.model,
            numeric_values,
        )

        if not math.isfinite(prediction):
            raise ValueError(
                "ML model returned an invalid ETA prediction"
            )

        return max(
            0.0,
            float(prediction),
        )

    # ---------------------------------------------------------
    # Realtime ETA
    # ---------------------------------------------------------

    def predict_realtime(
        self,
        *,
        distance_remaining: float | None = None,
        distance_to_next_station: float | None = None,

        current_speed: float | None = None,
        current_delay: float | None = None,

        historical_delay: float | None = None,
        previous_station_delay: float | None = None,

        section_average_speed: float | None = None,

        weather_factor: float | None = None,
        congestion_factor: float | None = None,
        signal_halt_minutes: float | None = None,

        prediction_source: str | None = None,

        observed_at: datetime | None = None,

        **kwargs: Any,
    ) -> RealtimePrediction:

        # -----------------------------------------------------
        # Accept both distance naming conventions
        # -----------------------------------------------------

        if distance_remaining is None:
            distance_remaining = distance_to_next_station

        if distance_remaining is None:
            distance_remaining = kwargs.get(
                "distance_to_station",
                kwargs.get("distance"),
            )

        distance = max(
            0.0,
            self._safe_float(distance_remaining),
        )

        # -----------------------------------------------------
        # Normalize all realtime inputs
        # -----------------------------------------------------

        speed = max(
            1.0,
            self._safe_float(
                current_speed,
                1.0,
            ),
        )

        current_delay_value = max(
            0.0,
            self._safe_float(
                current_delay,
            ),
        )

        historical_delay_value = max(
            0.0,
            self._safe_float(
                historical_delay,
            ),
        )

        previous_delay_value = max(
            0.0,
            self._safe_float(
                previous_station_delay,
            ),
        )

        section_speed = max(
            1.0,
            self._safe_float(
                section_average_speed,
                60.0,
            ),
        )

        weather_value = max(
            0.01,
            self._safe_float(
                weather_factor,
                1.0,
            ),
        )

        congestion_value = max(
            0.01,
            self._safe_float(
                congestion_factor,
                1.0,
            ),
        )

        signal_halt_value = max(
            0.0,
            self._safe_float(
                signal_halt_minutes,
            ),
        )

        # -----------------------------------------------------
        # Physics-based ETA baseline
        # -----------------------------------------------------

        effective_speed = max(
            12.0,
            min(
                speed,
                section_speed,
            ),
        )

        baseline_minutes = (
            distance / effective_speed
        ) * 60.0

        # -----------------------------------------------------
        # ML prediction
        # -----------------------------------------------------

        try:

            ml_minutes = self.predict_minutes(
                current_speed=speed,

                current_delay=current_delay_value,

                distance_remaining=distance,

                historical_delay=historical_delay_value,

                previous_station_delay=previous_delay_value,

                section_average_speed=section_speed,

                weather_factor=weather_value,

                congestion_factor=congestion_value,

                signal_halt_minutes=signal_halt_value,
            )

            # -------------------------------------------------
            # Final AI ETA
            #
            # 70% ML
            # 30% physics baseline
            # -------------------------------------------------

            eta_minutes = max(
                0,
                round(
                    (
                        0.70 * ml_minutes
                    )
                    +
                    (
                        0.30 * baseline_minutes
                    )
                ),
            )

            # -------------------------------------------------
            # Confidence score
            # -------------------------------------------------

            confidence_score = 0.90

            if speed < 25:
                confidence_score -= 0.12

            if weather_value >= 1.35:
                confidence_score -= 0.06

            if congestion_value >= 1.25:
                confidence_score -= 0.05

            confidence_score -= min(
                0.15,
                self.mae_minutes / 100.0,
            )

            confidence_score = max(
                0.45,
                min(
                    0.95,
                    confidence_score,
                ),
            )

            source = self._normalise_source(
                prediction_source
            )

        except (
            ValueError,
            TypeError,
            ArithmeticError,
            KeyError,
        ):

            # -------------------------------------------------
            # Safe fallback
            # -------------------------------------------------

            eta_minutes = max(
                0,
                round(
                    baseline_minutes
                ),
            )

            confidence_score = 0.45

            source = "UNAVAILABLE"

        # -----------------------------------------------------
        # Prediction timestamp
        # -----------------------------------------------------

        base_time = (
            observed_at
            if observed_at is not None
            else datetime.now(timezone.utc)
        )

        # Make timezone-aware
        if base_time.tzinfo is None:

            base_time = base_time.replace(
                tzinfo=timezone.utc
            )

        else:

            base_time = base_time.astimezone(
                timezone.utc
            )

        base_time = base_time.replace(
            microsecond=0
        )

        # -----------------------------------------------------
        # Predicted arrival
        # -----------------------------------------------------

        predicted_arrival = (
            base_time
            + timedelta(
                minutes=eta_minutes
            )
        )

        # -----------------------------------------------------
        # Current delay
        # -----------------------------------------------------

        predicted_delay = round(
            max(
                0.0,
                current_delay_value,
            )
        )

        # -----------------------------------------------------
        # Final response
        # -----------------------------------------------------

        return RealtimePrediction(

            eta_minutes=int(
                eta_minutes
            ),

            predicted_arrival=predicted_arrival,

            predicted_delay=int(
                predicted_delay
            ),

            confidence_score=round(
                float(
                    confidence_score
                ),
                3,
            ),

            confidence_level=self._confidence_level(
                confidence_score
            ),

            prediction_source=source,
        )