"""Health endpoints."""

from fastapi import APIRouter

from flowcept.configs import WEBSERVER_CAMPAIGN_DASHBOARD, WEBSERVER_WORKFLOW_DASHBOARD
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
    """Service name, installed version, and configured dashboard charts."""
    return {
        "service": "flowcept",
        "version": __version__,
        "workflow_dashboard": WEBSERVER_WORKFLOW_DASHBOARD,
        "campaign_dashboard": WEBSERVER_CAMPAIGN_DASHBOARD,
    }
