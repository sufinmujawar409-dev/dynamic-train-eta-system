"""SQLAlchemy persistence models for trains and ETA data."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Train(Base):
    __tablename__ = "trains"

    id: Mapped[int] = mapped_column(primary_key=True)
    train_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    train_name: Mapped[str] = mapped_column(String(120))
    source_station: Mapped[str] = mapped_column(String(120))
    destination_station: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    routes: Mapped[list["TrainRoute"]] = relationship(back_populates="train", cascade="all, delete-orphan")
    positions: Mapped[list["TrainPosition"]] = relationship(back_populates="train", cascade="all, delete-orphan")
    eta_predictions: Mapped[list["ETAPrediction"]] = relationship(
        back_populates="train", cascade="all, delete-orphan"
    )
    alerts: Mapped[list["Alert"]] = relationship(back_populates="train", cascade="all, delete-orphan")


class Station(Base):
    __tablename__ = "stations"

    id: Mapped[int] = mapped_column(primary_key=True)
    station_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    station_name: Mapped[str] = mapped_column(String(120))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)

    routes: Mapped[list["TrainRoute"]] = relationship(back_populates="station", cascade="all, delete-orphan")
    eta_predictions: Mapped[list["ETAPrediction"]] = relationship(
        back_populates="station", cascade="all, delete-orphan"
    )


class TrainRoute(Base):
    __tablename__ = "train_routes"
    __table_args__ = (Index("ix_train_routes_train_sequence", "train_id", "sequence_number", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    train_id: Mapped[int] = mapped_column(ForeignKey("trains.id", ondelete="CASCADE"), index=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id", ondelete="CASCADE"), index=True)
    sequence_number: Mapped[int] = mapped_column(Integer)
    scheduled_arrival: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_departure: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    train: Mapped[Train] = relationship(back_populates="routes")
    station: Mapped[Station] = relationship(back_populates="routes")


class TrainPosition(Base):
    __tablename__ = "train_positions"
    __table_args__ = (Index("ix_train_positions_train_recorded", "train_id", "recorded_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    train_id: Mapped[int] = mapped_column(ForeignKey("trains.id", ondelete="CASCADE"), index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    speed: Mapped[float] = mapped_column(Float)
    current_delay: Mapped[int] = mapped_column(Integer, default=0)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    data_source: Mapped[str] = mapped_column(String(16), default="DEMO")
    data_quality: Mapped[str] = mapped_column(String(16), default="SIMULATED")

    train: Mapped[Train] = relationship(back_populates="positions")


class ETAPrediction(Base):
    __tablename__ = "eta_predictions"
    __table_args__ = (Index("ix_eta_predictions_train_station_predicted", "train_id", "station_id", "predicted_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    train_id: Mapped[int] = mapped_column(ForeignKey("trains.id", ondelete="CASCADE"), index=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id", ondelete="CASCADE"), index=True)
    predicted_arrival: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float] = mapped_column(Float)
    predicted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    model_version: Mapped[str] = mapped_column(String(64))
    data_source: Mapped[str] = mapped_column(String(16), default="DEMO")
    data_quality: Mapped[str] = mapped_column(String(16), default="SIMULATED")

    train: Mapped[Train] = relationship(back_populates="eta_predictions")
    station: Mapped[Station] = relationship(back_populates="eta_predictions")


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_train_created", "train_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    train_id: Mapped[int] = mapped_column(ForeignKey("trains.id", ondelete="CASCADE"), index=True)
    alert_type: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(16), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    title: Mapped[str] = mapped_column(String(160), default="Operational alert")
    data_source: Mapped[str] = mapped_column(String(16), default="DEMO")
    data_quality: Mapped[str] = mapped_column(String(16), default="SIMULATED")
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)

    train: Mapped[Train] = relationship(back_populates="alerts")
class AppSetting(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    settings: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )