"""Contracts for replaceable train telemetry adapters."""

from collections.abc import Mapping, Sequence
from typing import Any
from typing import Protocol

from ..schemas import Station, Train, TrainPosition, TrainTelemetry


class ProviderUnavailable(RuntimeError):
    """Raised when an external provider cannot return data."""


class ProviderConfigurationError(ProviderUnavailable):
    """Raised when an external provider lacks required configuration."""


class TrainDataProvider(Protocol):
    """Source boundary shared by DEMO and future authorized live adapters."""

    def list_trains(self) -> Sequence[Train]: ...

    def get_train(self, train_id: str) -> Train | None: ...

    def get_route(self, train_id: str) -> Sequence[Station] | None: ...

    def get_telemetry(self, train_id: str) -> TrainTelemetry | Mapping[str, Any] | None: ...

    def get_live_position(self, train_id: str) -> TrainPosition | None: ...


TrainDataAdapter = TrainDataProvider
