"""Opt-in RailRadar connectivity adapter."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from ..config import Settings
from ..schemas import Station, Train, TrainPosition, TrainTelemetry
from .base import ProviderConfigurationError, ProviderUnavailable


class RailRadarProvider:
    """Diagnostic-only RailRadar provider."""

    def __init__(self, settings: Settings, client: Any = httpx) -> None:
        self._settings = settings
        self._client = client

    def _configuration(self) -> None:
        required = {
            "RAILRADAR_API_BASE_URL": self._settings.railradar_api_base_url
        }

        missing = [
            name for name, value in required.items()
            if not value
        ]

        if not self._settings.railway_api_key:
            missing.append("RAILWAY_API_KEY")

        if missing:
            raise ProviderConfigurationError(
                f"RailRadar configuration missing: {', '.join(missing)}"
            )

    @staticmethod
    def _coordinates(
        payload: Mapping[str, Any],
        data: Mapping[str, Any],
    ) -> tuple[float, float]:

        # 1. Try top-level geometry
        geometry = payload.get("geometry")

        if isinstance(geometry, Mapping):
            coordinates = geometry.get("coordinates")

            if isinstance(coordinates, list) and len(coordinates) >= 2:
                return float(coordinates[1]), float(coordinates[0])

        # 2. Try data.geometry
        geometry = data.get("geometry")

        if isinstance(geometry, Mapping):
            coordinates = geometry.get("coordinates")

            if isinstance(coordinates, list) and len(coordinates) >= 2:
                return float(coordinates[1]), float(coordinates[0])

        # 3. Try currentLocation.coordinates
        location = data.get("currentLocation")

        if isinstance(location, Mapping):
            coordinates = location.get("coordinates")

            if isinstance(coordinates, list) and len(coordinates) >= 2:
                return float(coordinates[1]), float(coordinates[0])

        # 4. Fallback to current station coordinates
        route = data.get("route") or []

        station_code = (
            location.get("stationCode")
            if isinstance(location, Mapping)
            else None
        )

        if isinstance(route, list) and station_code:

            for station in route:

                if not isinstance(station, Mapping):
                    continue

                if str(station.get("stationCode")) == str(station_code):

                    lat = station.get("lat")
                    lng = station.get("lng")

                    if lat is not None and lng is not None:
                        return float(lat), float(lng)

        raise KeyError("No usable train coordinates found")

    def fetch_live_status(
        self,
        train_number: str,
    ) -> TrainTelemetry:

        self._configuration()

        url = (
            f"{self._settings.railradar_api_base_url.rstrip('/')}"
            f"/v1/trains/{quote(train_number, safe='')}/live"
        )

        try:

            response = self._client.get(
                url,
                params={
                    "authoritative": "true",
                    "geometry": "true",
                    "format": "geojson",
                    "includeCoordinates": "true",
                },
                headers={
                    "Authorization": (
                        f"Bearer {self._settings.railway_api_key}"
                    )
                },
                timeout=self._settings.weather_timeout_seconds,
            )

            if response.status_code == 429:
                raise ProviderUnavailable(
                    "RailRadar rate limit reached"
                )

            response.raise_for_status()

            payload = response.json()

            print("RAILRADAR RESPONSE RECEIVED")

            if (
                not isinstance(payload, Mapping)
                or not isinstance(payload.get("data"), Mapping)
            ):
                raise ProviderUnavailable(
                    "RailRadar response could not be normalized"
                )

            data = payload["data"]

            location = data["currentLocation"]

            next_halt = data.get("nextHalt") or {}

            latitude, longitude = self._coordinates(
                payload,
                data,
            )

            route = data.get("route") or []

            if not isinstance(route, list):
                raise ProviderUnavailable(
                    "RailRadar station route has invalid shape"
                )

            recorded_at = datetime.fromisoformat(
                str(data["lastUpdatedAt"]).replace(
                    "Z",
                    "+00:00",
                )
            )

            actual_train_number = str(
                data["trainNumber"]
            )

            return TrainTelemetry(
                train_id=actual_train_number,
                train_number=actual_train_number,
                train_name=str(data["trainName"]),
                latitude=latitude,
                longitude=longitude,
                speed_kmph=float(
    location.get("speedKmh", 0)
    or location.get("speed", 0)
    or 0
),
                current_delay=data["delayMinutes"],
                current_station=str(
                    location["stationCode"]
                ),
                next_station=str(
                    next_halt.get("stationCode", "")
                ),
                recorded_at=recorded_at,
                timestamp=recorded_at,
                data_source="LIVE",
                data_quality="LIVE",
                source="LIVE",
                is_live=bool(data["isLive"]),
                last_updated=recorded_at,
                distance_to_next_station=0,
                route=[
                    self._normalize_route_item(item)
                    for item in route
                    if isinstance(item, Mapping)
                ],
            )

        except ProviderUnavailable:
            raise

        except (
            httpx.TimeoutException,
            httpx.ConnectError,
        ) as error:

            raise ProviderUnavailable(
                "RailRadar request timed out or could not connect"
            ) from error

        except httpx.HTTPError as error:

            raise ProviderUnavailable(
                "RailRadar returned an HTTP error"
            ) from error

        except (
            KeyError,
            TypeError,
            ValueError,
            ValidationError,
        ) as error:

            raise ProviderUnavailable(
                "RailRadar response could not be normalized"
            ) from error

    @staticmethod
    def _normalize_route_item(
        item: Mapping[str, Any],
    ) -> dict[str, object]:

        return {
            "station_code": item["stationCode"],
            "station_name": item["stationName"],
            "latitude": item["lat"],
            "longitude": item["lng"],
            "scheduled_arrival": item.get(
                "scheduledArrival"
            ),
            "actual_arrival": item.get(
                "actualArrival"
            ),
            "delay_minutes": item.get(
                "delayMinutes",
                0,
            ),
            "status": item.get("status"),
        }

    def normalize_stations(
        self,
        items: Sequence[Mapping[str, Any]],
    ) -> Sequence[Station]:

        stations: list[Station] = []

        for index, item in enumerate(
            items,
            start=1,
        ):

            stations.append(
                Station(
                    station_id=str(
                        item.get(
                            "station_id",
                            item.get("id", index),
                        )
                    ),
                    name=str(item["name"]),
                    code=str(
                        item.get(
                            "code",
                            item.get(
                                "station_code",
                                "",
                            ),
                        )
                    ),
                    sequence=int(
                        item.get(
                            "sequence",
                            index,
                        )
                    ),
                    data_source="LIVE",
                    latitude=item.get("latitude"),
                    longitude=item.get("longitude"),
                )
            )

        return stations

    def list_trains(self) -> Sequence[Train]:
        raise ProviderUnavailable(
            "RailRadar connectivity adapter is diagnostic-only"
        )

    def get_train(
        self,
        train_id: str,
    ) -> Train | None:

        raise ProviderUnavailable(
            "RailRadar connectivity adapter is diagnostic-only"
        )

    def get_route(
        self,
        train_id: str,
    ) -> Sequence[Station] | None:

        raise ProviderUnavailable(
            "RailRadar connectivity adapter is diagnostic-only"
        )

    def get_telemetry(
        self,
        train_id: str,
    ) -> TrainTelemetry | None:

        raise ProviderUnavailable(
            "Use fetch_live_status with an official train number"
        )

    def get_live_position(
        self,
        train_id: str,
    ) -> TrainPosition | None:

        raise ProviderUnavailable(
            "RailRadar connectivity adapter is diagnostic-only"
        )