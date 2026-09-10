"""Deterministic operational alert generation and acknowledgement store."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from ..schemas import AlertRecord, RealtimeTrainEvent


class AlertService:
    def __init__(self, cooldown_seconds: int = 120) -> None:
        self._cooldown = timedelta(seconds=cooldown_seconds)
        self._alerts: dict[str, AlertRecord] = {}
        self._last_created: dict[tuple[str, str], datetime] = {}

    def evaluate(self, event: RealtimeTrainEvent, previous: RealtimeTrainEvent | None = None) -> list[AlertRecord]:
        candidates: list[tuple[str, str, str, dict[str, object]]] = []
        if previous and event.current_delay - previous.current_delay >= 3:
            candidates.append(("DELAY_INCREASED", "WARNING", "Delay increased", {"previous_delay": previous.current_delay}))
        if event.current_delay >= 10:
            candidates.append(("MAJOR_DELAY", "CRITICAL", "Major delay detected", {}))
        if event.distance_to_next_station <= 1:
            candidates.append(("APPROACHING_STATION", "INFO", "Approaching next station", {}))
        if event.speed <= 5 and event.distance_to_next_station > 1:
            candidates.append(("UNUSUAL_STOPPAGE", "WARNING", "Unusual stoppage detected", {"speed": event.speed}))
        if previous and abs((event.eta - previous.eta).total_seconds()) >= 300:
            candidates.append(("ETA_CHANGED", "INFO", "ETA changed", {"previous_eta": previous.eta.isoformat()}))
        if event.data_quality == "STALE":
            candidates.append(("DATA_STALE", "WARNING", "Train telemetry is stale", {}))
        if event.data_quality == "UNAVAILABLE" or event.prediction_source == "UNAVAILABLE":
            candidates.append(("DATA_SOURCE_UNAVAILABLE", "CRITICAL", "Train data source unavailable", {}))
        if event.weather.weather_delay_risk == "HIGH":
            candidates.append(("WEATHER_IMPACT", "WARNING", "Weather may affect operations", {"source": event.weather.source}))

        created: list[AlertRecord] = []
        now = datetime.now(timezone.utc)
        for alert_type, severity, title, metadata in candidates:
            key = (event.train_id, alert_type)
            last = self._last_created.get(key)
            if last and now - last < self._cooldown:
                continue
            alert = AlertRecord(
                id=str(uuid4()),
                train_id=event.train_id,
                type=alert_type,
                severity=severity,
                title=title,
                message=self._message(alert_type, event),
                created_at=now,
                source=event.source,
                data_quality=event.data_quality,
                metadata=metadata,
            )
            self._alerts[alert.id] = alert
            self._last_created[key] = now
            created.append(alert)
        return created

    def _message(self, alert_type: str, event: RealtimeTrainEvent) -> str:
        messages = {
            "DELAY_INCREASED": f"{event.train_number} is now {event.current_delay} minutes delayed.",
            "MAJOR_DELAY": f"{event.train_number} has a major delay of {event.current_delay} minutes.",
            "APPROACHING_STATION": f"{event.train_number} is approaching {event.next_station}.",
            "UNUSUAL_STOPPAGE": f"{event.train_number} is moving at {event.speed:.0f} km/h before {event.next_station}.",
            "ETA_CHANGED": f"The predicted arrival for {event.next_station} has changed.",
            "DATA_STALE": "The last known telemetry update is older than the freshness threshold.",
            "DATA_SOURCE_UNAVAILABLE": "A reliable train data source is unavailable.",
            "WEATHER_IMPACT": "Weather conditions may affect the predicted arrival.",
        }
        return messages.get(alert_type, "Operational condition detected.")

    def list(self, train_id: str | None = None, severity: str | None = None, alert_type: str | None = None, acknowledged: bool | None = None) -> list[AlertRecord]:
        alerts = list(self._alerts.values())
        return [a for a in alerts if (train_id is None or a.train_id == train_id) and (severity is None or a.severity == severity) and (alert_type is None or a.type == alert_type) and (acknowledged is None or a.acknowledged == acknowledged)]

    def get(self, alert_id: str) -> AlertRecord | None:
        return self._alerts.get(alert_id)

    def acknowledge(self, alert_id: str) -> AlertRecord | None:
        alert = self._alerts.get(alert_id)
        if alert is None:
            return None
        updated = alert.model_copy(update={"acknowledged": True})
        self._alerts[alert_id] = updated
        return updated


__all__ = ["AlertService"]