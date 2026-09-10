"""Development helper for creating tables without running migrations."""

from .database import Base, engine
from . import models  # noqa: F401


def init_db() -> None:
    """Create database tables for local development only."""
    Base.metadata.create_all(bind=engine)
