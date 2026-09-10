"""Configuration-driven provider construction."""

from ..config import Settings
from .base import TrainDataProvider
from .demo import DemoDataAdapter
from .live import LiveRailwayDataProvider


def build_train_provider(settings: Settings) -> TrainDataProvider:
    if settings.data_provider == "demo":
        return DemoDataAdapter()
    return LiveRailwayDataProvider(settings)
