"""Persistence boundary for normalized realtime train events."""

from collections.abc import Callable, Sequence

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..schemas import RealtimeTrainEvent, Station
from .database import SessionLocal
from .models import ETAPrediction, Station as DbStation, Train as DbTrain, TrainPosition


class TelemetryRepository:
    """Persist provider events when a corresponding database train exists."""

    def __init__(self, session_factory: Callable[[], Session] = SessionLocal) -> None:
        self._session_factory = session_factory

    def persist_event(self, event: RealtimeTrainEvent, route: Sequence[Station]) -> bool:
        try:
            with self._session_factory.begin() as session:
                train = session.scalar(select(DbTrain).where(DbTrain.train_number == event.train_number))
                if train is None:
                    return False

                session.add(
                    TrainPosition(
                        train_id=train.id,
                        latitude=event.latitude,
                        longitude=event.longitude,
                        speed=event.speed,
                        current_delay=event.current_delay,
                        recorded_at=event.timestamp,
                        data_source=event.source,
                        data_quality=event.data_quality,
                    )
                )
                station = session.scalar(
                    select(DbStation).where(DbStation.station_name == event.next_station)
                )
                if station is not None:
                    session.add(
                        ETAPrediction(
                            train_id=train.id,
                            station_id=station.id,
                            predicted_arrival=event.eta,
                            confidence=event.eta_confidence,
                            predicted_at=event.last_updated,
                            model_version="realtime-eta",
                            data_source=event.source,
                            data_quality=event.data_quality,
                        )
                    )
                return True
        except SQLAlchemyError:
            return False