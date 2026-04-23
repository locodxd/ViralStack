"""System health snapshot for /api/health and Discord/CLI consumption."""
from __future__ import annotations

import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from config.settings import settings, list_account_ids, load_platform_config
from core.db import get_session
from core.models import Video

START_TIME = time.time()


def _disk_free_gb(path: str) -> float:
    try:
        usage = shutil.disk_usage(path)
        return round(usage.free / 1e9, 2)
    except Exception:
        return -1.0


def _ffmpeg_ok() -> bool:
    return shutil.which(settings.ffmpeg_path) is not None or Path(settings.ffmpeg_path).exists()


def health_snapshot() -> dict[str, Any]:
    snap: dict[str, Any] = {
        "ok": True,
        "version": settings.version,
        "uptime_seconds": int(time.time() - START_TIME),
        "ts": datetime.utcnow().isoformat() + "Z",
        "checks": {},
    }

    # DB reachable
    try:
        with get_session() as session:
            n = session.query(Video).count()
        snap["checks"]["database"] = {"ok": True, "videos": n}
    except Exception as e:
        snap["ok"] = False
        snap["checks"]["database"] = {"ok": False, "error": str(e)[:200]}

    # FFmpeg available
    snap["checks"]["ffmpeg"] = {"ok": _ffmpeg_ok(), "path": settings.ffmpeg_path}
    if not snap["checks"]["ffmpeg"]["ok"]:
        snap["ok"] = False

    # Required secrets
    snap["checks"]["secrets"] = {
        "vertex_ai": bool(settings.vertex_ai_api_key),
        "discord_bot": bool(settings.discord_bot_token),
        "youtube_oauth": bool(settings.youtube_client_id and settings.youtube_client_secret),
        "drive": settings.enable_drive_upload and Path(settings.google_service_account_file).exists(),
    }
    if not snap["checks"]["secrets"]["vertex_ai"]:
        snap["ok"] = False

    # Disk
    db_dir = str(Path(settings.db_path).parent)
    snap["checks"]["disk"] = {
        "db_dir": db_dir,
        "free_gb": _disk_free_gb(db_dir),
    }

    snap["accounts"] = list_account_ids()
    snap["platforms"] = load_platform_config()
    return snap
