"""ViralStack v1.2 dashboard.

Adds optional API-key auth, CORS, GZip, /health, platform controls, and admin APIs.
"""
from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pathlib import Path

from config.settings import settings
from core.health import health_snapshot
from core.security import require_api_key
from dashboard.routes import router

app = FastAPI(
    title="ViralStack Dashboard",
    version=settings.version,
    description="Admin & monitoring API for the ViralStack automation system.",
)

# Optional CORS
if settings.dashboard_enable_cors:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# GZip large JSON responses
app.add_middleware(GZipMiddleware, minimum_size=1024)

# Mount static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include API routes (gated by optional API-key auth)
app.include_router(router, prefix="/api", dependencies=[Depends(require_api_key)])


@app.get("/", response_class=HTMLResponse)
async def index():
    template_path = Path(__file__).parent / "templates" / "index.html"
    return template_path.read_text(encoding="utf-8")


@app.get("/health")
async def health() -> JSONResponse:
    """Public health endpoint suitable for Docker/Kubernetes liveness probes."""
    snap = health_snapshot()
    return JSONResponse(snap, status_code=200 if snap["ok"] else 503)


@app.get("/version")
async def version() -> dict:
    return {"version": settings.version, "name": "ViralStack"}
