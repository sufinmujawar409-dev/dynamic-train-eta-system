"""Train API and realtime WebSocket routes."""

import asyncio
import json
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Any, Callable, TypeVar

from fastapi import (
    APIRouter,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import ValidationError

from ..adapters.base import ProviderUnavailable
from ..adapters.factory import build_train_provider
from ..config import settings
from ..db.telemetry_repository import TelemetryRepository
from ..schemas import (
    AlertRecord,
    ETAPrediction,
    Station,
    Train,
    TrainPosition,
)
from ..services.train_service import (
    TrainNotFoundError,
    TrainService,
)
from ..weather.factory import build_weather_provider


# ============================================================
# ROUTERS
# ============================================================

router = APIRouter(
    prefix="/api/trains",
    tags=["trains"],
)

alerts_router = APIRouter(
    prefix="/api/alerts",
    tags=["alerts"],
)

realtime_router = APIRouter(
    tags=["realtime"],
)

diagnostics_router = APIRouter(
    prefix="/api/diagnostics",
    tags=["diagnostics"],
)


# ============================================================
# SERVICE
# ============================================================

service = TrainService(
    data_source=build_train_provider(settings),
    weather=build_weather_provider(settings),
    stale_after_seconds=settings.stale_after_seconds,
    persistence=TelemetryRepository(),
)


# ============================================================
# SHARED RESPONSE CACHE
# ============================================================

T = TypeVar("T")

DEFAULT_RESPONSE_CACHE_TTL_SECONDS = 20.0
DEFAULT_STALE_RESPONSE_CACHE_TTL_SECONDS = 300.0


def _response_cache_ttl() -> float:
    """
    Reuse backend realtime interval while ensuring
    the cache does not refresh too aggressively.
    """

    try:
        configured = float(
            settings.realtime_interval_seconds
        )

        return max(
            10.0,
            configured,
        )

    except (
        TypeError,
        ValueError,
        AttributeError,
    ):
        return (
            DEFAULT_RESPONSE_CACHE_TTL_SECONDS
        )


def _stale_response_cache_ttl() -> float:
    return max(
        _response_cache_ttl(),
        DEFAULT_STALE_RESPONSE_CACHE_TTL_SECONDS,
    )


# ------------------------------------------------------------
# Cache:
#
# (endpoint_name, train_id)
# ->
# (monotonic_time, response)
# ------------------------------------------------------------

_response_cache: dict[
    tuple[str, str],
    tuple[float, Any],
] = {}

_stale_response_cache: dict[
    tuple[str, str],
    tuple[float, Any],
] = {}

_train_locks: dict[
    str,
    Lock,
] = {}

_cache_lock = Lock()


# ============================================================
# CACHE HELPERS
# ============================================================

def _get_train_lock(
    train_id: str,
) -> Lock:
    """Return a shared lock for a train."""

    key = str(
        train_id
    ).strip()

    with _cache_lock:

        lock = _train_locks.get(
            key
        )

        if lock is None:
            lock = Lock()

            _train_locks[
                key
            ] = lock

        return lock


def _get_cached_response(
    key: tuple[str, str],
) -> Any | None:

    with _cache_lock:
        cached = _response_cache.get(
            key
        )

    if cached is None:
        return None

    cached_at, value = cached

    age = (
        monotonic()
        - cached_at
    )

    if age > _response_cache_ttl():
        return None

    return value


def _get_stale_response(
    key: tuple[str, str],
) -> Any | None:

    with _cache_lock:
        cached = _stale_response_cache.get(
            key
        )

    if cached is None:
        return None

    cached_at, value = cached

    age = (
        monotonic()
        - cached_at
    )

    if age > _stale_response_cache_ttl():
        return None

    return value


def _store_response(
    key: tuple[str, str],
    value: Any,
) -> None:

    now = monotonic()

    with _cache_lock:

        _response_cache[
            key
        ] = (
            now,
            value,
        )

        _stale_response_cache[
            key
        ] = (
            now,
            value,
        )


def _clear_train_cache(
    train_id: str,
) -> None:

    clean_id = str(
        train_id
    ).strip()

    with _cache_lock:

        fresh_keys = [
            key
            for key in _response_cache
            if key[1] == clean_id
        ]

        for key in fresh_keys:
            _response_cache.pop(
                key,
                None,
            )

        stale_keys = [
            key
            for key in _stale_response_cache
            if key[1] == clean_id
        ]

        for key in stale_keys:
            _stale_response_cache.pop(
                key,
                None,
            )


def _cached_service_call(
    endpoint_name: str,
    train_id: str,
    function: Callable[[], T],
) -> T:
    """
    Cache + request coalescing.

    Multiple requests for the same train and endpoint
    reuse one backend result.
    """

    clean_id = str(
        train_id
    ).strip()

    key = (
        endpoint_name,
        clean_id,
    )

    # --------------------------------------------------------
    # Fresh response
    # --------------------------------------------------------

    cached = _get_cached_response(
        key
    )

    if cached is not None:
        return cached

    # --------------------------------------------------------
    # Per-train request lock
    # --------------------------------------------------------

    train_lock = _get_train_lock(
        clean_id
    )

    with train_lock:

        cached = _get_cached_response(
            key
        )

        if cached is not None:
            return cached

        try:

            result = function()

            _store_response(
                key,
                result,
            )

            return result

        except ProviderUnavailable:

            stale = _get_stale_response(
                key
            )

            if stale is not None:
                return stale

            raise


# ============================================================
# TRAIN CATALOG
# ============================================================

CATALOG_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "train_catalog.json"
)


def _load_train_catalog() -> list[
    dict[str, object]
]:
    """
    Optional catalogue used for name search.

    Live train information still comes from
    the configured provider.
    """

    if not CATALOG_PATH.exists():
        return []

    try:

        raw = CATALOG_PATH.read_text(
            encoding="utf-8"
        )

        payload = json.loads(
            raw
        )

        if not isinstance(
            payload,
            list,
        ):
            return []

        result: list[
            dict[str, object]
        ] = []

        for item in payload:

            if isinstance(
                item,
                dict,
            ):
                result.append(
                    item
                )

        return result

    except (
        OSError,
        json.JSONDecodeError,
    ):
        return []


# ============================================================
# ERROR HELPERS
# ============================================================

def _not_found(
    train_id: str,
) -> HTTPException:

    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=(
            f"Train '{train_id}' "
            "was not found"
        ),
    )


def _provider_error(
    error: ProviderUnavailable,
) -> HTTPException:

    return HTTPException(
        status_code=(
            status.HTTP_503_SERVICE_UNAVAILABLE
        ),
        detail=str(error),
    )


def _invalid_provider_data(
    error: ValidationError,
) -> HTTPException:

    return HTTPException(
        status_code=(
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ),
        detail=str(error),
    )


# ============================================================
# LIST CONFIGURED TRAINS
# ============================================================

@router.get(
    "",
    response_model=list[Train],
)
def list_trains() -> list[Train]:

    try:

        result = service.list_trains()

        return list(result)

    except ProviderUnavailable as error:

        raise _provider_error(
            error
        ) from error

    except ValidationError as error:

        raise _invalid_provider_data(
            error
        ) from error


# ============================================================
# TRAIN SEARCH
# ============================================================

@router.get(
    "/search",
)
def search_trains(
    q: str,
) -> list[dict[str, object]]:

    query = q.strip()

    if not query:
        return []

    # --------------------------------------------------------
    # NUMERIC SEARCH
    # --------------------------------------------------------

    if query.isdigit():

        try:

            train = _cached_service_call(
                "search-train",
                query,
                lambda: service.get_train(
                    query
                ),
            )

            return [
                {
                    "train_id": train.train_id,
                    "train_number": train.number,
                    "train_name": train.name,
                    "origin": train.origin,
                    "destination": train.destination,
                    "status": train.status,
                    "data_source": train.data_source,
                    "is_live": train.is_live,
                    "data_quality": train.data_quality,
                    "last_updated": train.last_updated,
                }
            ]

        except TrainNotFoundError:

            return []

        except ProviderUnavailable as error:

            raise _provider_error(
                error
            ) from error

        except ValidationError as error:

            raise _invalid_provider_data(
                error
            ) from error

    # --------------------------------------------------------
    # NAME SEARCH
    # --------------------------------------------------------

    catalog = _load_train_catalog()

    query_lower = query.lower()

    matches: list[
        dict[str, object]
    ] = []

    for item in catalog:

        train_number = str(
            item.get(
                "train_number",
                item.get(
                    "number",
                    "",
                ),
            )
            or ""
        )

        train_name = str(
            item.get(
                "train_name",
                item.get(
                    "name",
                    "",
                ),
            )
            or ""
        )

        if (
            query_lower
            in train_name.lower()
            or query_lower
            in train_number.lower()
        ):

            matches.append(
                {
                    "train_id": train_number,
                    "train_number": train_number,
                    "train_name": train_name,
                    "origin": item.get(
                        "origin",
                        "",
                    ),
                    "destination": item.get(
                        "destination",
                        "",
                    ),
                    "data_source": "CATALOG",
                }
            )

        if len(matches) >= 20:
            break

    return matches


# ============================================================
# METADATA
# ============================================================

@router.get(
    "/metadata",
)
def get_metadata() -> dict[str, object]:

    provider = (
        str(
            settings.data_provider
        ).lower()
    )

    is_live_provider = (
        provider
        in {
            "live",
            "ntes",
        }
    )

    if provider == "ntes":
        data_source = "LIVE"
    elif provider == "live":
        data_source = "LIVE"
    else:
        data_source = "DEMO"

    weather_configured = bool(
        settings.weather_api_base_url
        and settings.weather_api_key
    )

    return {
        "service": (
            "dynamic-train-eta"
        ),

        "environment": (
            settings.environment
        ),

        "data_provider": (
            provider
        ),

        "data_source": (
            data_source
        ),

        "is_live": (
            is_live_provider
        ),

        "weather_configured": (
            weather_configured
        ),

        "realtime_interval_seconds": (
            settings.realtime_interval_seconds
        ),

        "response_cache_ttl_seconds": (
            _response_cache_ttl()
        ),

        "stale_response_cache_ttl_seconds": (
            _stale_response_cache_ttl()
        ),

        "model_version": (
            service._predictor.metadata.get(
                "model_version",
                "unknown",
            )
        ),
    }


# ============================================================
# ANALYTICS
# ============================================================

@router.get(
    "/analytics",
)
def get_analytics() -> dict[str, object]:

    return service.analytics()


# ============================================================
# LIVE TRAIN
# ============================================================

@router.get(
    "/{train_id}/live",
    response_model=TrainPosition,
)
def get_live_position(
    train_id: str,
) -> TrainPosition:

    try:

        return _cached_service_call(
            "live",
            train_id,
            lambda: service.get_live_position(
                train_id
            ),
        )

    except TrainNotFoundError:

        raise _not_found(
            train_id
        ) from None

    except ProviderUnavailable as error:

        raise _provider_error(
            error
        ) from error

    except ValidationError as error:

        raise _invalid_provider_data(
            error
        ) from error


# ============================================================
# GET TRAIN
# ============================================================

@router.get(
    "/{train_id}",
    response_model=Train,
)
def get_train(
    train_id: str,
) -> Train:

    try:

        return _cached_service_call(
            "train",
            train_id,
            lambda: service.get_train(
                train_id
            ),
        )

    except TrainNotFoundError:

        raise _not_found(
            train_id
        ) from None

    except ProviderUnavailable as error:

        raise _provider_error(
            error
        ) from error

    except ValidationError as error:

        raise _invalid_provider_data(
            error
        ) from error


# ============================================================
# ROUTE
# ============================================================

@router.get(
    "/{train_id}/route",
    response_model=list[Station],
)
def get_route(
    train_id: str,
) -> list[Station]:

    try:

        result = _cached_service_call(
            "route",
            train_id,
            lambda: list(
                service.get_route(
                    train_id
                )
            ),
        )

        return list(result)

    except TrainNotFoundError:

        raise _not_found(
            train_id
        ) from None

    except ProviderUnavailable as error:

        raise _provider_error(
            error
        ) from error

    except ValidationError as error:

        raise _invalid_provider_data(
            error
        ) from error


# ============================================================
# ETA
# ============================================================

@router.get(
    "/{train_id}/eta",
    response_model=list[ETAPrediction],
)
def get_eta(
    train_id: str,
) -> list[ETAPrediction]:

    try:

        result = _cached_service_call(
            "eta",
            train_id,
            lambda: list(
                service.get_eta(
                    train_id
                )
            ),
        )

        return list(result)

    except TrainNotFoundError:

        raise _not_found(
            train_id
        ) from None

    except ProviderUnavailable as error:

        raise _provider_error(
            error
        ) from error

    except ValidationError as error:

        raise _invalid_provider_data(
            error
        ) from error


# ============================================================
# ALERTS
# ============================================================

@alerts_router.get(
    "",
    response_model=list[AlertRecord],
)
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


@alerts_router.get(
    "/{alert_id}",
    response_model=AlertRecord,
)
def get_alert(
    alert_id: str,
) -> AlertRecord:

    alert = service.get_alert(
        alert_id
    )

    if alert is None:

        raise HTTPException(
            status_code=404,
            detail=(
                f"Alert '{alert_id}' "
                "was not found"
            ),
        )

    return alert


@alerts_router.post(
    "/{alert_id}/acknowledge",
    response_model=AlertRecord,
)
def acknowledge_alert(
    alert_id: str,
) -> AlertRecord:

    alert = service.acknowledge_alert(
        alert_id
    )

    if alert is None:

        raise HTTPException(
            status_code=404,
            detail=(
                f"Alert '{alert_id}' "
                "was not found"
            ),
        )

    return alert


# ============================================================
# REALTIME WEBSOCKET
# ============================================================

@realtime_router.websocket(
    "/ws/trains/{train_id}"
)
async def train_stream(
    websocket: WebSocket,
    train_id: str,
) -> None:

    await websocket.accept()

    clean_train_id = str(
        train_id
    ).strip()

    if not clean_train_id:

        await websocket.close(
            code=1008,
            reason="Invalid train id",
        )

        return

    try:

        while True:

            try:

                event = _cached_service_call(
                    "realtime-event",
                    clean_train_id,
                    lambda: (
                        service.get_realtime_event(
                            clean_train_id
                        )
                    ),
                )

                await websocket.send_json(
                    event.model_dump(
                        mode="json"
                    )
                )

            except TrainNotFoundError:

                await websocket.close(
                    code=1008,
                    reason="Unknown train",
                )

                return

            except ValidationError:

                await websocket.close(
                    code=1003,
                    reason="Invalid provider data",
                )

                return

            except ProviderUnavailable:

                # Provider temporarily unavailable.
                # Try again after a small delay.
                await asyncio.sleep(5)

                continue

            except Exception:

                # Unexpected websocket-side error.
                await asyncio.sleep(5)

                continue

            # ------------------------------------------------
            # The backend cache controls provider frequency.
            #
            # WebSocket polls every 10 sec, while service/
            # provider caching prevents excessive NTES calls.
            # ------------------------------------------------

            await asyncio.sleep(10)

    except WebSocketDisconnect:
        return

    except Exception:

        try:

            await websocket.close(
                code=1011,
                reason="Realtime stream error",
            )

        except Exception:
            pass


__all__ = [
    "router",
    "alerts_router",
    "realtime_router",
    "diagnostics_router",
]