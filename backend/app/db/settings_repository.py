"""Persistence helpers for application settings."""

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import AppSetting


DEFAULT_SETTINGS: dict[str, object] = {
    "notifications": True,
    "delayAlerts": True,
    "etaAlerts": True,
    "criticalAlerts": True,
    "liveTracking": True,
    "autoRefresh": True,
    "autoEta": True,
    "refreshInterval": 10,
    "showStations": True,
    "showTrainRoute": True,
    "showTrainPosition": True,
    "aiPrediction": True,
    "predictionConfidence": True,
}


class SettingsRepository:
    """Read and update application settings."""

    def __init__(
        self,
        session_factory: Callable[[], Session] = SessionLocal,
    ) -> None:
        self._session_factory = session_factory

    def get_settings(self) -> dict[str, object]:
        with self._session_factory() as session:
            record = session.scalar(
                select(AppSetting).where(AppSetting.id == 1)
            )

            if record is None:
                return DEFAULT_SETTINGS.copy()

            saved = dict(record.settings or {})
            return {
                **DEFAULT_SETTINGS,
                **saved,
            }

    def save_settings(
        self,
        settings: dict[str, object],
    ) -> dict[str, object]:
        with self._session_factory.begin() as session:
            record = session.scalar(
                select(AppSetting).where(AppSetting.id == 1)
            )

            if record is None:
                record = AppSetting(
                    id=1,
                    settings={
                        **DEFAULT_SETTINGS,
                        **settings,
                    },
                )
                session.add(record)
            else:
                record.settings = {
                    **DEFAULT_SETTINGS,
                    **dict(settings),
                }

            session.flush()

            return {
                **DEFAULT_SETTINGS,
                **dict(record.settings),
            }