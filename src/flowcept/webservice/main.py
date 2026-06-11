"""FastAPI entrypoint for Flowcept webservice."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import (
    WEBSERVER_CORS_ORIGINS,
    WEBSERVER_HOST,
    WEBSERVER_PORT,
    WEBSERVER_UI_ENABLED,
)
from flowcept.webservice.routers.agents import router as agents_router
from flowcept.webservice.routers.campaigns import router as campaigns_router
from flowcept.webservice.routers.dashboards import router as dashboards_router
from flowcept.webservice.routers.datasets import router as datasets_router
from flowcept.webservice.routers.health import info_router, router as health_router
from flowcept.webservice.routers.models import router as models_router
from flowcept.webservice.routers.objects import router as objects_router
from flowcept.webservice.routers.query import router as query_router
from flowcept.webservice.routers.stats import router as stats_router
from flowcept.webservice.routers.stream import router as stream_router
from flowcept.webservice.routers.tasks import router as tasks_router
from flowcept.webservice.routers.workflows import router as workflows_router


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="Flowcept Webservice API",
        version="1.0.0",
        description=(
            "Read-only REST API for Flowcept provenance data. "
            "Provides workflows, tasks, and objects endpoints with query support."
        ),
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    @app.exception_handler(ValueError)
    async def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    if WEBSERVER_CORS_ORIGINS:
        from fastapi.middleware.cors import CORSMiddleware

        app.add_middleware(
            CORSMiddleware,
            allow_origins=WEBSERVER_CORS_ORIGINS,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(info_router, prefix="/api/v1")
    app.include_router(campaigns_router, prefix="/api/v1")
    app.include_router(workflows_router, prefix="/api/v1")
    app.include_router(tasks_router, prefix="/api/v1")
    app.include_router(objects_router, prefix="/api/v1")
    app.include_router(datasets_router, prefix="/api/v1")
    app.include_router(models_router, prefix="/api/v1")
    app.include_router(agents_router, prefix="/api/v1")
    app.include_router(stats_router, prefix="/api/v1")
    app.include_router(dashboards_router, prefix="/api/v1")
    app.include_router(stream_router, prefix="/api/v1")
    try:
        from flowcept.webservice.routers.chat import router as chat_router

        app.include_router(chat_router, prefix="/api/v1")
    except Exception as e:
        FlowceptLogger().warning(f"Chat endpoint not available: {e}")
    app.include_router(query_router, prefix="/api/v1")

    _mount_ui(app)

    return app


def _mount_ui(app: FastAPI) -> None:
    """Serve the built SPA when its assets are present; otherwise expose a status root."""
    ui_dir = Path(__file__).parent / "ui_build"
    index_html = ui_dir / "index.html"

    if not (WEBSERVER_UI_ENABLED and index_html.exists()):
        if WEBSERVER_UI_ENABLED:
            FlowceptLogger().warning(
                f"Web UI assets not found at {ui_dir}; serving API only. Build the UI with `make ui-build`."
            )

        @app.get("/", tags=["health"])
        def root() -> dict:
            return {
                "status": "up",
                "service": "flowcept-webservice",
                "host": WEBSERVER_HOST,
                "port": WEBSERVER_PORT,
            }

        return

    from fastapi.staticfiles import StaticFiles

    assets_dir = ui_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        reserved = ("api/", "docs", "redoc", "openapi.json", "assets/")
        if full_path.startswith(reserved):
            return JSONResponse(status_code=404, content={"detail": f"Not found: /{full_path}"})
        candidate = ui_dir / full_path
        if full_path and candidate.is_file() and candidate.resolve().is_relative_to(ui_dir.resolve()):
            return FileResponse(candidate)
        return FileResponse(index_html)


app = create_app()
