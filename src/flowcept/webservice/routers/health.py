"""Health endpoints."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from flowcept.version import __version__

router = APIRouter(prefix="/health", tags=["health"])
info_router = APIRouter(tags=["health"])


@router.get("/live")
def live() -> dict:
    """Liveness check — process is running."""
    return {"status": "ok"}


@router.get("/ready")
def ready() -> JSONResponse:
    """Readiness check — verifies all enabled services via ``Flowcept.services_alive()``.

    Which services are checked is driven by settings.yaml (MQ, KVDB, MongoDB, LMDB, LLM).
    Returns HTTP 200 when all enabled services are reachable, HTTP 503 otherwise.
    The response body includes per-service status so callers can identify which
    service is down without reading server logs.
    """
    from flowcept.flowcept_api.flowcept_controller import Flowcept

    result = Flowcept.services_alive()
    status = "ready" if result else "degraded"
    return JSONResponse(
        status_code=200 if result else 503,
        content={"status": status, "services": dict(result)},
    )


@info_router.get("/info")
def info() -> dict:
    """Service name and installed version."""
    return {"service": "flowcept", "version": __version__}
