"""Health endpoints."""

from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live() -> dict:
    """Liveness check."""
    return {"status": "ok"}


@router.get("/ready")
def ready() -> dict:
    """Readiness check."""
    return {"status": "ready"}
