from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pathlib import Path
from dashboard.routes import router

app = FastAPI(title="TikTok Automation Dashboard")

# Mount static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include API routes
app.include_router(router, prefix="/api")


@app.get("/", response_class=HTMLResponse)
async def index():
    template_path = Path(__file__).parent / "templates" / "index.html"
    return template_path.read_text(encoding="utf-8")
