"""Configuration-driven provider construction."""

from ..config import Settings

from .base import TrainDataProvider
from .demo import DemoDataAdapter
from .live import LiveRailwayDataProvider
from .ntes import NTESProvider


def build_train_provider(
    settings: Settings,
) -> TrainDataProvider:
    """
    Build the configured train data provider.

    Supported providers:

    demo
        Local simulated/demo railway data.

    live
        RailRadar-based live railway data.

    ntes
        NTES-based live railway data.
    """

    # ---------------------------------------------------------
    # DEMO PROVIDER
    # ---------------------------------------------------------

    if settings.data_provider == "demo":
        return DemoDataAdapter()

    # ---------------------------------------------------------
    # NTES PROVIDER
    # ---------------------------------------------------------

    if settings.data_provider == "ntes":
        return NTESProvider()

    # ---------------------------------------------------------
    # RAILRADAR LIVE PROVIDER
    # ---------------------------------------------------------

    return LiveRailwayDataProvider(settings)


__all__ = [
    "build_train_provider",
]