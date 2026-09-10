"""Control-room analytics derived from normalized realtime state."""

from statistics import mean
from typing import Iterable

from ..schemas import AlertRecord, RealtimeTrainEvent


class AnalyticsService:
    def summarize(self, events: Iterable[RealtimeTrainEvent], alerts: Iterable[AlertRecord]) -> dict[str, object]:
        snapshots = list(events)
        alert_list = list(alerts)
        delays = [event.current_delay for event in snapshots]
        speeds = [event.speed for event in snapshots]
        confidence = [event.eta_confidence for event in snapshots]
        return {
            "active_trains": len({event.train_id for event in snapshots}),
            "on_time_trains": sum(event.current_delay == 0 for event in snapshots),
            "delayed_trains": sum(event.current_delay > 0 for event in snapshots),
            "major_delay_trains": sum(event.current_delay >= 10 for event in snapshots),
            "average_delay": round(mean(delays), 2) if delays else 0,
            "average_speed": round(mean(speeds), 2) if speeds else 0,
            "eta_confidence": round(mean(confidence), 3) if confidence else 0,
            "active_alerts": sum(not alert.acknowledged for alert in alert_list),
            "critical_alerts": sum(alert.severity == "CRITICAL" and not alert.acknowledged for alert in alert_list),
            "data_quality": snapshots[-1].data_quality if snapshots else "UNAVAILABLE",
            "data_source": snapshots[-1].source if snapshots else "DEMO",
        }
