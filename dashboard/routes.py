from datetime import datetime, timedelta
from fastapi import APIRouter
from sqlalchemy import func
from core.db import get_session
from core.models import Video, ApiKey, EmailThread, PipelineRun
from config.settings import load_platform_config

router = APIRouter()


@router.get("/videos")
async def get_videos(limit: int = 50, account: str = None):
    """Get recent videos with status and details."""
    with get_session() as session:
        query = session.query(Video).order_by(Video.created_at.desc())
        if account:
            query = query.filter(Video.account == account)
        videos = query.limit(limit).all()

        return [
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

        # Platform-specific counts
        tiktok_published = session.query(Video).filter(Video.tiktok_published == True).count()
        youtube_published = session.query(Video).filter(Video.youtube_published == True).count()

        avg_score = session.query(func.avg(Video.quality_score)).filter(
            Video.quality_score != None
        ).scalar()

        # Per account stats
        account_stats = {}
        for account in ["terror", "historias", "dinero"]:
            account_published = session.query(Video).filter(
                Video.account == account, Video.status == "published",
            ).count()
            account_today = session.query(Video).filter(
                Video.account == account, Video.created_at >= today,
            ).count()
            account_tiktok = session.query(Video).filter(
                Video.account == account, Video.tiktok_published == True,
            ).count()
            account_youtube = session.query(Video).filter(
                Video.account == account, Video.youtube_published == True,
            ).count()
            account_stats[account] = {
                "published_total": account_published,
                "today": account_today,
                "tiktok": account_tiktok,
                "youtube": account_youtube,
            }

        # Platform config
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
async def get_emails(limit: int = 50, account: str = None):
    """Get recent email classifications and responses."""
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
