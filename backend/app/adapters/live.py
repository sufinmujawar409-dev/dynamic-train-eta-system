"""Live railway data provider backed by the RailRadar adapter."""

from pathlib import Path
from collections.abc import Mapping, Sequence
from typing import Any

from ..config import Settings
from ..schemas import (
    Station,
    Train,
    TrainPosition,
    TrainTelemetry,
    WeatherData,
)
from .base import (
    ProviderConfigurationError,
    ProviderUnavailable,
    TrainDataProvider,
)
from .railradar import RailRadarProvider


class LiveRailwayDataProvider(TrainDataProvider):
    """Production live-provider boundary using RailRadar."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._provider = RailRadarProvider(settings)

    # =========================================================
    # CONFIGURATION
    # =========================================================

    def _ensure_configured(self) -> None:
        if not self._settings.railradar_api_base_url:
            raise ProviderConfigurationError(
                "RAILRADAR_API_BASE_URL is required "
                "for DATA_PROVIDER=live"
            )

        if not self._settings.railway_api_key:
            raise ProviderConfigurationError(
                "RAILWAY_API_KEY is required "
                "for DATA_PROVIDER=live"
            )

    # =========================================================
    # LIVE TRAIN NUMBERS
    # =========================================================

    def _live_train_numbers(self) -> list[str]:
        """
        Read LIVE_TRAIN_NUMBERS from the project root .env file.

        Example:

            LIVE_TRAIN_NUMBERS=12919,12952,22436
        """

        numbers: list[str] = []

        # File:
        # project/backend/app/adapters/live.py
        #
        # parents[0] -> adapters
        # parents[1] -> app
        # parents[2] -> backend
        # parents[3] -> project root

        env_path = (
            Path(__file__).resolve().parents[3] / ".env"
        )

        if not env_path.exists():
            return numbers

        try:
            content = env_path.read_text(
                encoding="utf-8"
            )
        except OSError:
            return numbers

        for line in content.splitlines():
            line = line.strip()

            if not line:
                continue

            if line.startswith("#"):
                continue

            if "=" not in line:
                continue

            key, value = line.split(
                "=",
                1,
            )

            if key.strip() != "LIVE_TRAIN_NUMBERS":
                continue

            value = (
                value.strip()
                .strip('"')
                .strip("'")
            )

            for item in value.split(","):
                train_number = item.strip()

                if (
                    train_number
                    and train_number not in numbers
                ):
                    numbers.append(train_number)

            break

        return numbers

    # =========================================================
    # TRAIN LIST
    # =========================================================

    def list_trains(self) -> Sequence[Train]:
        """
        Load configured live trains from RailRadar.

        Every configured train is attempted independently.
        One failed train does not hide useful errors from
        the rest of the fleet.
        """

        self._ensure_configured()

        train_numbers = self._live_train_numbers()

        if not train_numbers:
            raise ProviderConfigurationError(
                "LIVE_TRAIN_NUMBERS is required when "
                "DATA_PROVIDER=live. "
                "Example: LIVE_TRAIN_NUMBERS=12919"
            )

        trains: list[Train] = []
        errors: list[str] = []

        for train_number in train_numbers:
            try:
                train = self.get_train(
                    train_number
                )

                if train is not None:
                    trains.append(train)
                else:
                    errors.append(
                        f"{train_number}: "
                        "no train data returned"
                    )

            except Exception as exc:
                errors.append(
                    f"{train_number}: {str(exc)}"
                )

        # At least one real train worked.
        if trains:
            return trains

        # Nothing worked, so expose the actual errors instead
        # of hiding them behind a generic message.
        detail = (
            "No configured live trains are currently "
            "available from RailRadar"
        )

        if errors:
            detail += " | " + " ; ".join(errors)

        raise ProviderUnavailable(detail)

    # =========================================================
    # GET TRAIN
    # =========================================================

    def get_train(
        self,
        train_id: str,
    ) -> Train | None:
        self._ensure_configured()

        clean_train_id = str(
            train_id
        ).strip()

        if not clean_train_id:
            raise ProviderUnavailable(
                "Train number is required"
            )

        telemetry = self._provider.fetch_live_status(
            clean_train_id
        )

        if telemetry is None:
            raise ProviderUnavailable(
                f"No live data available for train "
                f"{clean_train_id}"
            )

        route = telemetry.route or []

        origin = "Unknown"
        destination = "Unknown"

        if route:
            first_station = route[0]
            last_station = route[-1]

            origin = str(
                first_station.get(
                    "station_name",
                    first_station.get(
                        "name",
                        first_station.get(
                            "station_code",
                            "Unknown",
                        ),
                    ),
                )
                or "Unknown"
            )

            destination = str(
                last_station.get(
                    "station_name",
                    last_station.get(
                        "name",
                        last_station.get(
                            "station_code",
                            "Unknown",
                        ),
                    ),
                )
                or "Unknown"
            )

        status = (
            "RUNNING"
            if telemetry.is_live
            else "UNAVAILABLE"
        )

        return Train(
            train_id=telemetry.train_id,
            name=(
                telemetry.train_name
                or f"Train {telemetry.train_number}"
            ),
            number=telemetry.train_number,
            status=status,
            origin=origin,
            destination=destination,
            data_source=telemetry.data_source,
            source=(
                telemetry.source
                or telemetry.data_source
            ),
            is_live=telemetry.is_live,
            data_quality=telemetry.data_quality,
            last_updated=telemetry.last_updated,
            weather=WeatherData.unavailable(),
            eta=None,
            eta_confidence=None,
        )

    # =========================================================
    # GET ROUTE
    # =========================================================

    def get_route(
        self,
        train_id: str,
    ) -> Sequence[Station] | None:
        self._ensure_configured()

        clean_train_id = str(
            train_id
        ).strip()

        telemetry = self._provider.fetch_live_status(
            clean_train_id
        )

        if telemetry is None:
            return []

        raw_route = telemetry.route or []

        stations: list[Station] = []

        for index, item in enumerate(
            raw_route,
            start=1,
        ):
            station_code = str(
                item.get(
                    "station_code",
                    "",
                )
                or ""
            ).strip()

            station_name = str(
                item.get(
                    "station_name",
                    "",
                )
                or ""
            ).strip()

            if (
                not station_code
                and not station_name
            ):
                continue

            latitude = item.get(
                "latitude"
            )

            longitude = item.get(
                "longitude"
            )

            sequence_value = item.get(
                "sequence",
                index,
            )

            try:
                sequence = int(
                    sequence_value
                )
            except (
                TypeError,
                ValueError,
            ):
                sequence = index

            try:
                parsed_latitude = (
                    float(latitude)
                    if latitude is not None
                    else None
                )
            except (
                TypeError,
                ValueError,
            ):
                parsed_latitude = None

            try:
                parsed_longitude = (
                    float(longitude)
                    if longitude is not None
                    else None
                )
            except (
                TypeError,
                ValueError,
            ):
                parsed_longitude = None

            stations.append(
                Station(
                    station_id=(
                        station_code
                        or (
                            f"{telemetry.train_id}"
                            f"-{sequence}"
                        )
                    ),
                    name=(
                        station_name
                        or station_code
                        or "Unknown Station"
                    ),
                    code=(
                        station_code
                        or station_name
                        or "UNKNOWN"
                    ),
                    sequence=sequence,
                    data_source="LIVE",
                    latitude=parsed_latitude,
                    longitude=parsed_longitude,
                )
            )

        stations.sort(
            key=lambda station: station.sequence
        )

        return stations

    # =========================================================
    # GET TELEMETRY
    # =========================================================

    def get_telemetry(
        self,
        train_id: str,
    ) -> TrainTelemetry | Mapping[str, Any] | None:
        self._ensure_configured()

        clean_train_id = str(
            train_id
        ).strip()

        return self._provider.fetch_live_status(
            clean_train_id
        )

    # =========================================================
    # GET LIVE POSITION
    # =========================================================

    def get_live_position(
        self,
        train_id: str,
    ) -> TrainPosition | None:
        self._ensure_configured()

        clean_train_id = str(
            train_id
        ).strip()

        telemetry = self._provider.fetch_live_status(
            clean_train_id
        )

        if telemetry is None:
            return None

        return TrainPosition(
            train_id=telemetry.train_id,
            latitude=telemetry.latitude,
            longitude=telemetry.longitude,
            speed_kmph=telemetry.speed_kmph,
            current_delay=telemetry.current_delay,
            recorded_at=telemetry.recorded_at,
            source=(
                telemetry.source
                or telemetry.data_source
            ),
            data_source=telemetry.data_source,
            is_live=telemetry.is_live,
            data_quality=telemetry.data_quality,
            last_updated=telemetry.last_updated,
            next_station=(
                telemetry.next_station
                or None
            ),
            distance_to_next_station=(
                telemetry.distance_to_next_station
            ),
            weather=WeatherData.unavailable(),
            eta=None,
            eta_confidence=None,
        )


__all__ = [
    "LiveRailwayDataProvider",
]