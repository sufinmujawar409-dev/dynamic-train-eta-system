"""Smart deterministic operational alert generation and acknowledgement store."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from ..schemas import AlertRecord, RealtimeTrainEvent


class AlertService:
    """
    Generates deterministic operational railway alerts.

    Uses only alert types supported by AlertRecord.
    """

    def __init__(
        self,
        cooldown_seconds: int = 120,
    ) -> None:

        self._cooldown = timedelta(
            seconds=max(
                30,
                cooldown_seconds,
            )
        )

        self._alerts: dict[
            str,
            AlertRecord,
        ] = {}

        self._last_created: dict[
            tuple[str, str],
            datetime,
        ] = {}

    # =========================================================
    # EVALUATE
    # =========================================================

    def evaluate(
        self,
        event: RealtimeTrainEvent,
        previous: RealtimeTrainEvent | None = None,
    ) -> list[AlertRecord]:

        candidates: list[
            tuple[
                str,
                str,
                str,
                dict[str, object],
            ]
        ] = []

        # -----------------------------------------------------
        # DELAY INCREASED
        # -----------------------------------------------------

        if (
            previous is not None
            and event.current_delay
            - previous.current_delay
            >= 3
        ):

            delay_change = (
                event.current_delay
                - previous.current_delay
            )

            severity = (
                "CRITICAL"
                if delay_change >= 30
                else "WARNING"
            )

            candidates.append(
                (
                    "DELAY_INCREASED",
                    severity,
                    (
                        "Delay increased sharply"
                        if delay_change >= 15
                        else "Delay increased"
                    ),
                    {
                        "previous_delay": (
                            previous.current_delay
                        ),
                        "current_delay": (
                            event.current_delay
                        ),
                        "increase_minutes": (
                            delay_change
                        ),
                    },
                )
            )

        # -----------------------------------------------------
        # MAJOR DELAY
        # -----------------------------------------------------

        if event.current_delay >= 10:

            severity = (
                "CRITICAL"
                if event.current_delay >= 60
                else "WARNING"
            )

            candidates.append(
                (
                    "MAJOR_DELAY",
                    severity,
                    (
                        "Severe delay detected"
                        if event.current_delay >= 60
                        else "Major delay detected"
                    ),
                    {
                        "delay_minutes": (
                            event.current_delay
                        )
                    },
                )
            )

        # -----------------------------------------------------
        # APPROACHING STATION
        # -----------------------------------------------------

        if (
            event.distance_to_next_station
            <= 3
        ):

            candidates.append(
                (
                    "APPROACHING_STATION",
                    "INFO",
                    "Train is approaching the next station",
                    {
                        "distance_km": (
                            event.distance_to_next_station
                        ),
                        "next_station": (
                            event.next_station
                        ),
                    },
                )
            )

        # -----------------------------------------------------
        # UNUSUAL STOPPAGE
        # -----------------------------------------------------

        if (
            event.speed <= 5
            and event.distance_to_next_station > 1
            and event.data_quality != "STALE"
        ):

            candidates.append(
                (
                    "UNUSUAL_STOPPAGE",
                    "WARNING",
                    "Unusual stoppage detected",
                    {
                        "speed": (
                            event.speed
                        ),
                        "distance_to_next_station": (
                            event.distance_to_next_station
                        ),
                    },
                )
            )

        # -----------------------------------------------------
        # ETA CHANGED
        # -----------------------------------------------------

        if previous is not None:

            eta_change_minutes = abs(
                (
                    event.eta
                    - previous.eta
                ).total_seconds()
                / 60
            )

            if eta_change_minutes >= 5:

                candidates.append(
                    (
                        "ETA_CHANGED",
                        "INFO",
                        "Predicted arrival time changed",
                        {
                            "previous_eta": (
                                previous.eta.isoformat()
                            ),
                            "current_eta": (
                                event.eta.isoformat()
                            ),
                            "change_minutes": (
                                round(
                                    eta_change_minutes,
                                    1,
                                )
                            ),
                            "direction": (
                                "EARLIER"
                                if event.eta
                                < previous.eta
                                else "LATER"
                            ),
                        },
                    )
                )

        # -----------------------------------------------------
        # SPEED ANOMALY
        #
        # Covers abnormal movement changes.
        # -----------------------------------------------------

        if previous is not None:

            speed_change = (
                event.speed
                - previous.speed
            )

            if (
                abs(speed_change) >= 30
                and event.data_quality != "STALE"
            ):

                candidates.append(
                    (
                        "SPEED_ANOMALY",
                        "INFO",
                        "Significant speed change detected",
                        {
                            "previous_speed": (
                                previous.speed
                            ),
                            "current_speed": (
                                event.speed
                            ),
                            "speed_change": (
                                round(
                                    speed_change,
                                    1,
                                )
                            ),
                        },
                    )
                )

        # -----------------------------------------------------
        # STALE DATA
        # -----------------------------------------------------

        if (
            event.data_quality
            == "STALE"
        ):

            candidates.append(
                (
                    "DATA_STALE",
                    "WARNING",
                    "Train telemetry is stale",
                    {},
                )
            )

        # -----------------------------------------------------
        # DATA SOURCE UNAVAILABLE
        # -----------------------------------------------------

        if (
            event.data_quality
            == "UNAVAILABLE"
            or event.prediction_source
            == "UNAVAILABLE"
        ):

            candidates.append(
                (
                    "DATA_SOURCE_UNAVAILABLE",
                    "CRITICAL",
                    "Train data source unavailable",
                    {},
                )
            )

        # -----------------------------------------------------
        # WEATHER IMPACT
        # -----------------------------------------------------

        if (
            event.weather.weather_delay_risk
            == "HIGH"
        ):

            candidates.append(
                (
                    "WEATHER_IMPACT",
                    "WARNING",
                    "Weather may affect operations",
                    {
                        "source": (
                            event.weather.source
                        ),
                        "weather_risk": (
                            event.weather.weather_delay_risk
                        ),
                    },
                )
            )

        # -----------------------------------------------------
        # CREATE ALERTS
        # -----------------------------------------------------

        created: list[AlertRecord] = []

        now = datetime.now(
            timezone.utc
        )

        for (
            alert_type,
            severity,
            title,
            metadata,
        ) in candidates:

            key = (
                event.train_id,
                alert_type,
            )

            last_created = (
                self._last_created.get(
                    key
                )
            )

            if (
                last_created is not None
                and now - last_created
                < self._cooldown
            ):
                continue

            alert = AlertRecord(
                id=str(uuid4()),

                train_id=event.train_id,

                type=alert_type,

                severity=severity,

                title=title,

                message=self._message(
                    alert_type,
                    event,
                ),

                created_at=now,

                source=event.source,

                data_quality=(
                    event.data_quality
                ),

                metadata=metadata,
            )

            self._alerts[
                alert.id
            ] = alert

            self._last_created[
                key
            ] = now

            created.append(alert)

        return created

    # =========================================================
    # MESSAGES
    # =========================================================

    def _message(
        self,
        alert_type: str,
        event: RealtimeTrainEvent,
    ) -> str:

        messages = {
            "DELAY_INCREASED": (
                f"{event.train_number} is now "
                f"{event.current_delay} minutes delayed."
            ),

            "MAJOR_DELAY": (
                f"{event.train_number} has a major "
                f"delay of {event.current_delay} minutes."
            ),

            "APPROACHING_STATION": (
                f"{event.train_number} is approaching "
                f"{event.next_station}; approximately "
                f"{event.distance_to_next_station:.1f} km remaining."
            ),

            "UNUSUAL_STOPPAGE": (
                f"{event.train_number} is moving at "
                f"{event.speed:.0f} km/h with "
                f"{event.distance_to_next_station:.1f} km "
                f"remaining to {event.next_station}."
            ),

            "ETA_CHANGED": (
                f"The predicted arrival for "
                f"{event.next_station} has changed."
            ),

            "SPEED_ANOMALY": (
                f"{event.train_number} experienced "
                f"a significant speed change; current "
                f"speed is {event.speed:.0f} km/h."
            ),

            "DATA_STALE": (
                "The last known telemetry update "
                "is older than the configured "
                "freshness threshold."
            ),

            "DATA_SOURCE_UNAVAILABLE": (
                "A reliable train data source "
                "is currently unavailable."
            ),

            "WEATHER_IMPACT": (
                "Current weather conditions may "
                "affect the predicted arrival."
            ),
        }

        return messages.get(
            alert_type,
            "Operational condition detected.",
        )

    # =========================================================
    # LIST
    # =========================================================

    def list(
        self,
        train_id: str | None = None,
        severity: str | None = None,
        alert_type: str | None = None,
        acknowledged: bool | None = None,
    ) -> list[AlertRecord]:

        alerts = list(
            self._alerts.values()
        )

        return [
            alert
            for alert in alerts
            if (
                train_id is None
                or alert.train_id
                == train_id
            )
            and (
                severity is None
                or alert.severity
                == severity
            )
            and (
                alert_type is None
                or alert.type
                == alert_type
            )
            and (
                acknowledged is None
                or alert.acknowledged
                == acknowledged
            )
        ]

    # =========================================================
    # GET
    # =========================================================

    def get(
        self,
        alert_id: str,
    ) -> AlertRecord | None:

        return self._alerts.get(
            alert_id
        )

    # =========================================================
    # ACKNOWLEDGE
    # =========================================================

    def acknowledge(
        self,
        alert_id: str,
    ) -> AlertRecord | None:

        alert = self._alerts.get(
            alert_id
        )

        if alert is None:
            return None

        updated = alert.model_copy(
            update={
                "acknowledged": True
            }
        )

        self._alerts[
            alert_id
        ] = updated

        return updated


__all__ = [
    "AlertService",
]