"""Health endpoints."""

from fastapi import APIRouter

from flowcept.version import __version__

router = APIRouter(prefix="/health", tags=["health"])
info_router = APIRouter(tags=["health"])


@router.get("/live")
def live() -> dict:
    """Liveness check."""
    return {"status": "ok"}


@router.get("/ready")
def ready() -> dict:
    """Readiness check."""
    return {"status": "ready"}


@info_router.get("/info")
def info() -> dict:
    """Service name and installed version."""
    return {"service": "flowcept", "version": __version__}
