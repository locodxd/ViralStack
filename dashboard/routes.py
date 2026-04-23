from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Body
from sqlalchemy import func, case

from core.db import get_session
from core.models import Video, ApiKey, EmailThread, PipelineRun, AuditLog, VideoMetrics
from core import audit
from config.settings import (
    settings,
    load_platform_config,
    save_platform_config,
    toggle_platform,
    load_blackout_dates,
    save_blackout_dates,
    list_account_ids,
    ACCOUNTS,
    BASE_DIR,
)

router = APIRouter()


def _page_size(limit: int) -> int:
    return max(1, min(settings.dashboard_max_page_size, limit))


@router.get("/videos")
async def get_videos(
    limit: int = Query(default=None, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    account: Optional[str] = None,
    status: Optional[str] = None,
):
    """Get recent videos with status and details. Paginated + filterable."""
    limit = _page_size(limit or settings.dashboard_default_page_size)
    with get_session() as session:
        query = session.query(Video).order_by(Video.created_at.desc())
        if account:
            query = query.filter(Video.account == account)
        if status:
            query = query.filter(Video.status == status)
        total = query.count()
        videos = query.offset(offset).limit(limit).all()

        items = [
            {
                "id": v.id,
                "account": v.account,
                "status": v.status,
                "title": v.title,
                "quality_score": v.quality_score,
                "drive_url": v.drive_url,
                "tiktok_url": v.tiktok_url,
                "youtube_url": v.youtube_url,
                "tiktok_published": v.tiktok_published,
                "youtube_published": v.youtube_published,
                "retry_count": v.retry_count,
                "error_message": v.error_message,
                "created_at": v.created_at.isoformat() if v.created_at else None,
                "published_at": v.published_at.isoformat() if v.published_at else None,
            }
            for v in videos
        ]

    return {"total": total, "limit": limit, "offset": offset, "items": items}


@router.get("/videos/{video_id}")
async def get_video(video_id: int):
    with get_session() as session:
        v = session.query(Video).filter_by(id=video_id).first()
        if not v:
            raise HTTPException(404, "Video not found")
        return {
            "id": v.id,
            "account": v.account,
            "status": v.status,
            "title": v.title,
            "hook": v.hook,
            "script_text": v.script_text,
            "quality_score": v.quality_score,
            "quality_notes": v.quality_notes,
            "drive_url": v.drive_url,
            "tiktok_url": v.tiktok_url,
            "youtube_url": v.youtube_url,
            "retry_count": v.retry_count,
            "error_message": v.error_message,
            "estimated_duration": v.estimated_duration,
            "final_path": v.final_path,
            "created_at": v.created_at.isoformat() if v.created_at else None,
            "published_at": v.published_at.isoformat() if v.published_at else None,
        }


@router.delete("/videos/{video_id}")
async def delete_video(video_id: int, purge_files: bool = False):
    """Delete a video record (and optionally its on-disk artefacts)."""
    with get_session() as session:
        v = session.query(Video).filter_by(id=video_id).first()
        if not v:
            raise HTTPException(404, "Video not found")
        files_to_purge = [v.final_path, v.narration_path, v.subtitle_path]
        session.delete(v)
        # cascade-ish cleanup
        session.query(PipelineRun).filter_by(video_id=video_id).delete()
        session.query(VideoMetrics).filter_by(video_id=video_id).delete()

    if purge_files:
        for p in files_to_purge:
            if not p:
                continue
            try:
                Path(p).unlink(missing_ok=True)
            except Exception:
                pass

    audit.record("video_deleted", actor="dashboard", target=str(video_id),
                 details={"purge_files": purge_files})
    return {"deleted": True, "video_id": video_id}


@router.post("/videos/{video_id}/retry")
async def retry_video(video_id: int):
    """Re-queue a failed/rejected video by spawning a new production for its account."""
    with get_session() as session:
        v = session.query(Video).filter_by(id=video_id).first()
        if not v:
            raise HTTPException(404, "Video not found")
        account = v.account

    audit.record("video_retry", actor="dashboard", target=str(video_id),
                 details={"account": account})

    import asyncio
    from pipeline.orchestrator import produce_video
    asyncio.create_task(produce_video(account))
    return {"queued": True, "account": account}


@router.post("/publish/{account}")
async def manual_publish(account: str):
    """Force a manual production for an account."""
    if account not in list_account_ids():
        raise HTTPException(404, f"Unknown account: {account}")

    audit.record("manual_publish", actor="dashboard", target=account)

    import asyncio
    from pipeline.orchestrator import produce_video
    asyncio.create_task(produce_video(account))
    return {"queued": True, "account": account}


@router.get("/stats")
async def get_stats():
    """Get aggregate statistics."""
    now = datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    with get_session() as session:
        total = session.query(Video).count()
        today_count = session.query(Video).filter(Video.created_at >= today).count()
        week_count = session.query(Video).filter(Video.created_at >= week_ago).count()
        month_count = session.query(Video).filter(Video.created_at >= month_ago).count()

        published = session.query(Video).filter(Video.status == "published").count()
        failed = session.query(Video).filter(Video.status == "failed").count()
        rejected = session.query(Video).filter(Video.status == "rejected").count()

        tiktok_published = session.query(Video).filter(Video.tiktok_published == True).count()  # noqa: E712
        youtube_published = session.query(Video).filter(Video.youtube_published == True).count()  # noqa: E712

        avg_score = session.query(func.avg(Video.quality_score)).filter(
            Video.quality_score != None  # noqa: E711
        ).scalar()

        # Per account stats — DYNAMIC across all registered accounts (built-in + custom)
        account_stats = {}
        for account in list_account_ids():
            account_published = session.query(Video).filter(
                Video.account == account, Video.status == "published",
            ).count()
            account_today = session.query(Video).filter(
                Video.account == account, Video.created_at >= today,
            ).count()
            account_tiktok = session.query(Video).filter(
                Video.account == account, Video.tiktok_published == True,  # noqa: E712
            ).count()
            account_youtube = session.query(Video).filter(
                Video.account == account, Video.youtube_published == True,  # noqa: E712
            ).count()
            account_stats[account] = {
                "display_name": ACCOUNTS.get(account, {}).get("display_name", account),
                "published_total": account_published,
                "today": account_today,
                "tiktok": account_tiktok,
                "youtube": account_youtube,
            }

        platform_config = load_platform_config()

        return {
            "total_videos": total,
            "published": published,
            "failed": failed,
            "rejected": rejected,
            "tiktok_published": tiktok_published,
            "youtube_published": youtube_published,
            "today": today_count,
            "this_week": week_count,
            "this_month": month_count,
            "avg_quality_score": round(avg_score, 1) if avg_score else 0,
            "failure_rate": round(failed / total * 100, 1) if total > 0 else 0,
            "accounts": account_stats,
            "platforms": platform_config,
        }


@router.get("/keys")
async def get_keys():
    """Get API key pool health status."""
    with get_session() as session:
        keys = session.query(ApiKey).all()
        now = datetime.utcnow()

        return [
            {
                "id": k.id,
                "provider": k.provider,
                "label": k.label,
                "enabled": k.enabled,
                "usage_count": k.usage_count,
                "usage_chars": k.usage_chars,
                "failure_count": k.failure_count,
                "in_cooldown": k.cooldown_until is not None and k.cooldown_until > now,
                "cooldown_until": k.cooldown_until.isoformat() if k.cooldown_until else None,
                "last_used": k.last_used_at.isoformat() if k.last_used_at else None,
            }
            for k in keys
        ]


@router.get("/emails")
async def get_emails(
    limit: int = Query(default=None, ge=1, le=500),
    account: Optional[str] = None,
):
    """Get recent email classifications and responses."""
    limit = _page_size(limit or settings.dashboard_default_page_size)
    with get_session() as session:
        query = session.query(EmailThread).order_by(EmailThread.created_at.desc())
        if account:
            query = query.filter(EmailThread.account == account)
        emails = query.limit(limit).all()

        return [
            {
                "id": e.id,
                "account": e.account,
                "sender": e.sender,
                "subject": e.subject,
                "category": e.category,
                "auto_responded": e.auto_responded,
                "needs_attention": e.needs_attention,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in emails
        ]


@router.get("/pipeline/{video_id}")
async def get_pipeline_details(video_id: int):
    """Get pipeline execution details for a specific video."""
    with get_session() as session:
        runs = (
            session.query(PipelineRun)
            .filter_by(video_id=video_id)
            .order_by(PipelineRun.started_at)
            .all()
        )

        return [
            {
                "step": r.step,
                "status": r.status,
                "duration_ms": r.duration_ms,
                "error": r.error_message,
                "started_at": r.started_at.isoformat() if r.started_at else None,
            }
            for r in runs
        ]


@router.get("/platforms")
async def get_platforms():
    """Get platform toggle configuration."""
    return load_platform_config()


@router.post("/platforms/{account}/{platform}")
async def set_platform(account: str, platform: str, enabled: bool = Body(..., embed=True)):
    """Enable or disable a platform for an account."""
    if account not in list_account_ids():
        raise HTTPException(404, f"Unknown account: {account}")
    if platform not in {"tiktok", "youtube"}:
        raise HTTPException(400, "Platform must be 'tiktok' or 'youtube'")
    cfg = toggle_platform(account, platform, bool(enabled))
    audit.record("platform_toggle", actor="dashboard",
                 target=f"{account}:{platform}", details={"enabled": bool(enabled)})
    return cfg


@router.get("/calendar")
async def get_calendar(days: int = Query(7, ge=1, le=30)):
    """Return the upcoming scheduled video productions for the next N days."""
    out = []
    for acc, cfg in ACCOUNTS.items():
        for w in cfg.get("schedule_windows", []):
            out.append({
                "account": acc,
                "display_name": cfg.get("display_name", acc),
                "hour": w["hour"],
                "minute": w["minute"],
                "timezone": settings.timezone,
            })
    out.sort(key=lambda x: (x["hour"], x["minute"], x["account"]))
    return {
        "windows": out,
        "blackout_dates": load_blackout_dates(),
        "skip_weekends": settings.schedule_skip_weekends,
    }


@router.get("/blackout")
async def get_blackout():
    return {"dates": load_blackout_dates()}


@router.post("/blackout")
async def add_blackout(date: str = Body(..., embed=True)):
    """Add a YYYY-MM-DD date on which production should NOT run."""
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")
    dates = load_blackout_dates()
    if date not in dates:
        dates.append(date)
        save_blackout_dates(dates)
    audit.record("blackout_add", actor="dashboard", target=date)
    return {"dates": load_blackout_dates()}


@router.delete("/blackout/{date}")
async def remove_blackout(date: str):
    dates = [d for d in load_blackout_dates() if d != date]
    save_blackout_dates(dates)
    audit.record("blackout_remove", actor="dashboard", target=date)
    return {"dates": dates}


@router.get("/accounts")
async def get_accounts():
    """Return the full live ACCOUNTS config (read-only)."""
    out = {}
    for acc, cfg in ACCOUNTS.items():
        # Avoid leaking absolute paths to tokens; report only their existence.
        safe = {k: v for k, v in cfg.items()
                if k not in {"youtube_token_path", "tiktok_cookies_path", "gmail_token_path"}}
        safe["has_youtube_token"] = bool(cfg.get("youtube_token_path"))
        safe["has_tiktok_cookies"] = bool(cfg.get("tiktok_cookies_path"))
        out[acc] = safe
    return out


@router.get("/prompts/{account}")
async def get_prompt(account: str):
    """Read a prompt YAML file. Falls back to config/prompts/{account}.yaml."""
    cfg = ACCOUNTS.get(account, {})
    path = Path(cfg.get("prompt_file") or BASE_DIR / "config" / "prompts" / f"{account}.yaml")
    if not path.exists():
        raise HTTPException(404, f"Prompt file not found: {path}")
    return {"path": str(path), "content": path.read_text(encoding="utf-8")}


@router.put("/prompts/{account}")
async def put_prompt(account: str, content: str = Body(..., embed=True)):
    """Replace a prompt YAML file. Validates YAML before writing."""
    cfg = ACCOUNTS.get(account, {})
    path = Path(cfg.get("prompt_file") or BASE_DIR / "config" / "prompts" / f"{account}.yaml")
    try:
        import yaml
        yaml.safe_load(content)
    except Exception as e:
        raise HTTPException(400, f"Invalid YAML: {e}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    audit.record("prompt_updated", actor="dashboard", target=account, details={"bytes": len(content)})
    return {"saved": True, "path": str(path)}


@router.get("/audit")
async def get_audit(limit: int = Query(100, ge=1, le=1000)):
    with get_session() as session:
        rows = session.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()
        return [
            {
                "id": r.id,
                "actor": r.actor,
                "action": r.action,
                "target": r.target,
                "details": r.details,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


@router.post("/backup")
async def trigger_backup():
    """Trigger an on-demand SQLite backup."""
    from core.backup import backup_database
    path = backup_database()
    if not path:
        raise HTTPException(500, "Backup failed")
    audit.record("backup", actor="dashboard", target=str(path))
    return {"path": str(path), "size_bytes": Path(path).stat().st_size}


@router.get("/analytics/timeseries")
async def analytics_timeseries(days: int = Query(30, ge=1, le=180)):
    """Return per-day published counts for the last N days, grouped by account."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    with get_session() as session:
        rows = (
            session.query(
                func.date(Video.created_at).label("day"),
                Video.account,
                func.count(Video.id).label("total"),
                func.sum(
                    case((Video.status == "published", 1), else_=0)
                ).label("published"),
            )
            .filter(Video.created_at >= cutoff)
            .group_by("day", Video.account)
            .all()
        )

    series: dict = {}
    for r in rows:
        day = str(r.day)
        series.setdefault(day, {})[r.account] = {
            "total": int(r.total or 0),
            "published": int(r.published or 0),
        }
    return {"days": days, "series": series, "accounts": list_account_ids()}


@router.get("/llm/providers")
async def llm_providers_status():
    """Return the list of LLM providers and which ones are currently usable."""
    from core import llm_providers as _llm
    reg = _llm._registry()
    chain_names = [n.strip() for n in (settings.script_provider_chain or "").split(",") if n.strip()]
    out = []
    for name, prov in reg.items():
        out.append({
            "name": name,
            "available": prov.is_available(),
            "models": prov.models()[:8],
            "in_chain": name in chain_names,
            "chain_position": chain_names.index(name) + 1 if name in chain_names else None,
        })
    out.sort(key=lambda x: (x["chain_position"] is None, x["chain_position"] or 99, x["name"]))
    return {
        "chain": chain_names,
        "providers": out,
    }


@router.get("/settings")
async def safe_settings():
    """Return a *safe* (non-secret) view of settings. Useful for the UI."""
    keep = {
        "version", "language", "timezone",
        "quality_threshold", "max_retries_per_video", "pipeline_timeout_seconds",
        "min_video_seconds", "max_video_seconds", "image_display_seconds",
        "video_width", "video_height", "video_crf", "video_preset",
        "schedule_hour_start", "schedule_hour_end", "schedule_skip_weekends",
        "email_poll_interval_minutes", "enable_drive_upload",
        "music_volume_percent", "narration_volume_boost",
        "whisper_model", "whisper_device",
        "dashboard_auto_refresh_seconds",
    }
    return {k: getattr(settings, k) for k in keep if hasattr(settings, k)}
