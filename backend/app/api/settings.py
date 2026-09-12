"""Application settings API."""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..db.settings_repository import SettingsRepository


router = APIRouter(
    prefix="/api/settings",
    tags=["settings"],
)

repository = SettingsRepository()


class SettingsPayload(BaseModel):
    notifications: bool = True
    delayAlerts: bool = True
    etaAlerts: bool = True
    criticalAlerts: bool = True

    liveTracking: bool = True
    autoRefresh: bool = True
    autoEta: bool = True
    refreshInterval: int = Field(default=10, ge=5, le=60)

    showStations: bool = True
    showTrainRoute: bool = True
    showTrainPosition: bool = True

    aiPrediction: bool = True
    predictionConfidence: bool = True


@router.get("")
def get_settings() -> dict[str, Any]:
    return repository.get_settings()


@router.put("")
def update_settings(payload: SettingsPayload) -> dict[str, Any]:
    return repository.save_settings(
        payload.model_dump()
    )