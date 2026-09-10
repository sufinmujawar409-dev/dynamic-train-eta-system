"""Train API and realtime WebSocket routes."""

import asyncio

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError

from ..adapters.base import ProviderUnavailable
from ..adapters.factory import build_train_provider
from ..config import settings
from ..adapters.railradar import RailRadarProvider
from ..db.telemetry_repository import TelemetryRepository
from ..schemas import AlertRecord, ETAPrediction, Station, Train, TrainPosition
from ..services.train_service import TrainNotFoundError, TrainService
from ..weather.factory import build_weather_provider


router = APIRouter(prefix="/api/trains", tags=["trains"])
alerts_router = APIRouter(prefix="/api/alerts", tags=["alerts"])
realtime_router = APIRouter(tags=["realtime"])
diagnostics_router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


service = TrainService(
    data_source=build_train_provider(settings),
    weather=build_weather_provider(settings),
    stale_after_seconds=settings.stale_after_seconds,
    persistence=TelemetryRepository(),
)


def _not_found(train_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Train '{train_id}' was not found",
    )


def _provider_error(error: ProviderUnavailable) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=str(error),
    )


def _invalid_provider_data(error: ValidationError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=str(error),
    )


@router.get("", response_model=list[Train])
def list_trains() -> list[Train]:
    try:
        return list(service.list_trains())
    except ProviderUnavailable as error:
        raise _provider_error(error) from error
    except ValidationError as error:
        raise _invalid_provider_data(error) from error


@router.get("/metadata")
def get_metadata() -> dict[str, object]:
    return {
        "service": "dynamic-train-eta",
        "environment": settings.environment,
        "data_provider": settings.data_provider,
        "data_source": "LIVE" if settings.data_provider == "live" else "DEMO",
        "is_live": settings.data_provider == "live",
        "weather_configured": bool(
            settings.weather_api_base_url and settings.weather_api_key
        ),
        "realtime_interval_seconds": settings.realtime_interval_seconds,
        "model_version": service._predictor.metadata.get(
            "model_version",
            "unknown",
        ),
    }


@router.get("/analytics")
def get_analytics() -> dict[str, object]:
    return service.analytics()


@diagnostics_router.get("/railradar")
def test_railradar(train_number: str) -> dict[str, object]:
    """Make one opt-in RailRadar request; never switch the application provider."""
    telemetry = RailRadarProvider(settings).fetch_live_status(train_number)
    return telemetry.model_dump(mode="json")


# ---------------------------------------------------------
# DIRECT RAILRADAR LIVE TEST
# ---------------------------------------------------------

@router.get("/{train_id}/live-radar", response_model=TrainPosition)
def get_live_radar_position(train_id: str) -> TrainPosition:
    """Fetch one train directly from the authorized RailRadar provider."""

    try:
        provider = RailRadarProvider(settings)

        telemetry = provider.fetch_live_status(train_id)

        return TrainPosition(
            train_id=telemetry.train_id,
            latitude=telemetry.latitude,
            longitude=telemetry.longitude,
            speed_kmph=telemetry.speed_kmph,
            current_delay=telemetry.current_delay,
            recorded_at=telemetry.recorded_at,
            source=telemetry.source,
            is_live=telemetry.is_live,
            data_quality=telemetry.data_quality,
            last_updated=telemetry.last_updated,
            next_station=telemetry.next_station,
            distance_to_next_station=telemetry.distance_to_next_station,
            eta=None,
            eta_confidence=None,
        )

    except ProviderUnavailable as error:
        raise _provider_error(error) from error

    except ValidationError as error:
        raise _invalid_provider_data(error) from error


@router.get("/{train_id}", response_model=Train)
def get_train(train_id: str) -> Train:
    try:
        return service.get_train(train_id)
    except TrainNotFoundError:
        raise _not_found(train_id) from None
    except ProviderUnavailable as error:
        raise _provider_error(error) from error
    except ValidationError as error:
        raise _invalid_provider_data(error) from error


@router.get("/{train_id}/live", response_model=TrainPosition)
def get_live_position(train_id: str) -> TrainPosition:
    try:
        return service.get_live_position(train_id)
    except TrainNotFoundError:
        raise _not_found(train_id) from None
    except ProviderUnavailable as error:
        raise _provider_error(error) from error
    except ValidationError as error:
        raise _invalid_provider_data(error) from error


@router.get("/{train_id}/route", response_model=list[Station])
def get_route(train_id: str) -> list[Station]:
    try:
        return list(service.get_route(train_id))
    except TrainNotFoundError:
        raise _not_found(train_id) from None
    except ProviderUnavailable as error:
        raise _provider_error(error) from error
    except ValidationError as error:
        raise _invalid_provider_data(error) from error


@router.get("/{train_id}/eta", response_model=list[ETAPrediction])
def get_eta(train_id: str) -> list[ETAPrediction]:
    try:
        return list(service.get_eta(train_id))
    except TrainNotFoundError:
        raise _not_found(train_id) from None
    except ProviderUnavailable as error:
        raise _provider_error(error) from error
    except ValidationError as error:
        raise _invalid_provider_data(error) from error


@alerts_router.get("", response_model=list[AlertRecord])
def list_alerts(
    train_id: str | None = None,
    severity: str | None = None,
    type: str | None = None,
    acknowledged: bool | None = None,
) -> list[AlertRecord]:
    return service.list_alerts(
        train_id=train_id,
        severity=severity,
        alert_type=type,
        acknowledged=acknowledged,
    )


@alerts_router.get("/{alert_id}", response_model=AlertRecord)
def get_alert(alert_id: str) -> AlertRecord:
    alert = service.get_alert(alert_id)

    if alert is None:
        raise HTTPException(
            status_code=404,
            detail=f"Alert '{alert_id}' was not found",
        )

    return alert


@alerts_router.post(
    "/{alert_id}/acknowledge",
    response_model=AlertRecord,
)
def acknowledge_alert(alert_id: str) -> AlertRecord:
    alert = service.acknowledge_alert(alert_id)

    if alert is None:
        raise HTTPException(
            status_code=404,
            detail=f"Alert '{alert_id}' was not found",
        )

    return alert


@realtime_router.websocket("/ws/trains/{train_id}")
async def train_stream(websocket: WebSocket, train_id: str) -> None:
    await websocket.accept()

    try:
        service.get_train(train_id)

        while True:
            event = service.get_realtime_event(train_id)

            await websocket.send_json(
                event.model_dump(mode="json")
            )

            await asyncio.sleep(2)

    except TrainNotFoundError:
        await websocket.close(
            code=1008,
            reason="Unknown train",
        )

    except ProviderUnavailable as error:
        await websocket.close(
            code=1013,
            reason=str(error),
        )

    except ValidationError:
        await websocket.close(
            code=1003,
            reason="Invalid provider data",
        )

    except WebSocketDisconnect:
        return