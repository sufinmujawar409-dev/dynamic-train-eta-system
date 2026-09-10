"""Health check route."""

from fastapi import APIRouter

from ..config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "dynamic-train-eta",
        "environment": settings.environment,
    }
