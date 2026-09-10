"""API schemas for the Dynamic Train ETA service."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


DataSource = Literal["DEMO", "LIVE"]
DataQuality = Literal["SIMULATED", "LIVE", "STALE", "UNAVAILABLE"]
WeatherRisk = Literal["LOW", "MEDIUM", "HIGH", "UNAVAILABLE"]
WeatherQuality = Literal["LIVE", "DEMO", "UNAVAILABLE", "STALE"]
AlertSeverity = Literal["INFO", "WARNING", "CRITICAL"]
AlertType = Literal[
    "DELAY_INCREASED", "MAJOR_DELAY", "APPROACHING_STATION", "STATION_DEPARTURE",
    "UNUSUAL_STOPPAGE", "ETA_CHANGED", "SPEED_ANOMALY", "ROUTE_DISRUPTION",
    "DATA_STALE", "DATA_SOURCE_UNAVAILABLE", "WEATHER_IMPACT",
]


class WeatherData(BaseModel):
    temperature: float | None = None
    feels_like: float | None = None
    humidity: float | None = Field(default=None, ge=0, le=100)
    weather_condition: str | None = None
    precipitation: float | None = Field(default=None, ge=0)
    wind_speed: float | None = Field(default=None, ge=0)
    visibility: float | None = Field(default=None, ge=0)
    weather_delay_risk: WeatherRisk = "UNAVAILABLE"
    weather_last_updated: datetime | None = None
    source: str = "UNAVAILABLE"
    data_quality: WeatherQuality = "UNAVAILABLE"
    observation_timestamp: datetime | None = None
    available: bool = False
    message: str = "Weather data unavailable"

    @classmethod
    def unavailable(cls) -> "WeatherData":
        return cls()


class Station(BaseModel):
    station_id: str
    name: str
    code: str
    sequence: int = Field(ge=1)
    data_source: DataSource = "DEMO"
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class Train(BaseModel):
    train_id: str
    name: str
    number: str
    status: str
    origin: str
    destination: str
    data_source: DataSource = "DEMO"
    source: DataSource = "DEMO"
    is_live: bool = False
    data_quality: DataQuality = "SIMULATED"
    last_updated: datetime | None = None
    weather: WeatherData = Field(default_factory=WeatherData.unavailable)
    eta: datetime | None = None
    eta_confidence: float | None = Field(default=None, ge=0, le=1)


class TrainPosition(BaseModel):
    train_id: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    speed_kmph: float = Field(ge=0)
    recorded_at: datetime
    data_source: DataSource = "DEMO"
    current_delay: int = Field(default=0, ge=0)
    source: DataSource = "DEMO"
    is_live: bool = False
    data_quality: DataQuality = "SIMULATED"
    last_updated: datetime | None = None
    next_station: str | None = None
    distance_to_next_station: float | None = Field(default=None, ge=0)
    weather: WeatherData = Field(default_factory=WeatherData.unavailable)
    eta: datetime | None = None
    eta_confidence: float | None = Field(default=None, ge=0, le=1)


class TrainTelemetry(BaseModel):
    """Validated source snapshot before ETA enrichment and transport."""

    train_id: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    speed_kmph: float = Field(ge=0)
    current_delay: int = Field(ge=0)
    recorded_at: datetime
    data_source: DataSource
    data_quality: DataQuality
    train_number: str = ""
    train_name: str = ""
    next_station: str = ""
    current_station: str = ""
    distance_to_next_station: float = Field(default=0, ge=0)
    timestamp: datetime | None = None
    source: DataSource | None = None
    is_live: bool = False
    last_updated: datetime | None = None
    route: list[dict[str, object]] = Field(default_factory=list)

    @field_validator("train_id")
    @classmethod
    def train_id_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("train_id cannot be empty")
        return value

    @field_validator("recorded_at")
    @classmethod
    def timestamp_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return value.astimezone(timezone.utc)


class RealtimeTrainEvent(BaseModel):
    """Stable WebSocket contract consumed by the dashboard."""

    train_id: str
    train_number: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    speed: float = Field(ge=0)
    current_delay: int = Field(ge=0)
    next_station: str
    eta: datetime
    timestamp: datetime
    data_source: DataSource
    data_quality: DataQuality
    source: DataSource = "DEMO"
    is_live: bool = False
    last_updated: datetime
    distance_to_next_station: float = Field(default=0, ge=0)
    weather: WeatherData = Field(default_factory=WeatherData.unavailable)
    eta_confidence: float = Field(default=0.8, ge=0, le=1)
    predicted_delay: int = Field(default=0, ge=0)
    confidence_level: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"
    prediction_source: Literal["LIVE", "DEMO", "UNAVAILABLE"] = "DEMO"
    alerts: list["AlertRecord"] = Field(default_factory=list)


class AlertRecord(BaseModel):
    id: str
    train_id: str
    type: AlertType
    severity: AlertSeverity
    title: str
    message: str
    created_at: datetime
    acknowledged: bool = False
    source: DataSource
    data_quality: DataQuality
    metadata: dict[str, object] = Field(default_factory=dict)


class ETAPrediction(BaseModel):
    train_id: str
    station_id: str
    station_name: str
    next_station: str = ""
    current_delay: int = Field(default=0, ge=0)
    estimated_arrival: datetime
    minutes_remaining: int = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    model_version: str = "demo-rf-v1"
    data_source: DataSource = "DEMO"
    source: DataSource = "DEMO"
    is_live: bool = False
    data_quality: DataQuality = "SIMULATED"
    last_updated: datetime | None = None
    weather: WeatherData = Field(default_factory=WeatherData.unavailable)
    predicted_delay: int = Field(default=0, ge=0)
    confidence_score: float = Field(default=0.8, ge=0, le=1)
    confidence_level: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"
    prediction_source: Literal["LIVE", "DEMO", "UNAVAILABLE"] = "DEMO"
