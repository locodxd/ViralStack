import logging
import random
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from config.settings import settings, ACCOUNTS, load_blackout_dates

logger = logging.getLogger(__name__)


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the APScheduler instance."""
    jobstores = {
        "default": SQLAlchemyJobStore(url=f"sqlite:///{settings.db_path}")
    }

    scheduler = AsyncIOScheduler(
        jobstores=jobstores,
        timezone=settings.timezone,
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": settings.schedule_misfire_grace_seconds,
        },
    )

    return scheduler


async def _produce_video_guarded(account: str):
    """Wrapper around produce_video with blackout-date + weekend gating."""
    from pipeline.orchestrator import produce_video

    today = datetime.now().date().isoformat()
    if today in load_blackout_dates():
        logger.info("Skipping %s production: %s is a blackout date", account, today)
        return

    if settings.schedule_skip_weekends and datetime.now().weekday() >= 5:
        logger.info("Skipping %s production: weekend disabled in settings", account)
        return

    await produce_video(account)


def register_video_jobs(scheduler: AsyncIOScheduler):
    """Register video production jobs for all accounts."""

    for account, config in ACCOUNTS.items():
        vpd = config.get("videos_per_day", 0)
        windows = config.get("schedule_windows", [])

        if vpd == 0 or not windows:
            logger.info("Account %s DISABLED (videos_per_day=0)", account)
            continue

        for i, window in enumerate(windows):
            hour = window["hour"]
            minute = window["minute"]

            # Extra random seconds offset (0-59s) so it's never exactly on the minute
            jitter_secs = random.randint(0, 59)

            job_id = f"video_{account}_{i}"

            day_of_week = "mon-fri" if settings.schedule_skip_weekends else "*"

            scheduler.add_job(
                _produce_video_guarded,
                trigger=CronTrigger(
                    day_of_week=day_of_week,
                    hour=hour,
                    minute=minute,
                    second=jitter_secs,
                    jitter=settings.schedule_jitter_seconds,
                    timezone=settings.timezone,
                ),
                args=[account],
                id=job_id,
                name=f"Video {config['display_name']} #{i+1}",
                replace_existing=True,
            )

            logger.info(
                "Scheduled %s video #%d at %02d:%02d:%02d %s (±%ds jitter)",
                account, i + 1, hour, minute, jitter_secs,
                settings.timezone, settings.schedule_jitter_seconds,
            )

        logger.info("Account %s: %d videos/day scheduled", account, vpd)


def register_email_job(scheduler: AsyncIOScheduler):
    """Register the email polling job (polls all accounts)."""
    from email_agent.gmail_client import poll_and_process

    interval = max(1, settings.email_poll_interval_minutes)
    scheduler.add_job(
        poll_and_process,
        trigger=IntervalTrigger(
            minutes=interval,
            jitter=300,
            timezone=settings.timezone,
        ),
        id="email_poll",
        name="Email Agent Poll (all accounts)",
        replace_existing=True,
    )
    logger.info("Scheduled email polling every %d minutes (all accounts)", interval)


def register_daily_stats_job(scheduler: AsyncIOScheduler, bot=None):
    """Register daily stats reporting via Discord bot."""
    if not bot:
        logger.info("No bot provided, skipping daily stats job")
        return

    from bot.stats import send_daily_stats

    async def _send_stats():
        await send_daily_stats(bot)

    scheduler.add_job(
        _send_stats,
        trigger=CronTrigger(
            hour=settings.daily_stats_hour,
            minute=settings.daily_stats_minute,
            timezone=settings.timezone,
        ),
        id="daily_stats",
        name="Daily Stats Report",
        replace_existing=True,
    )

    scheduler.add_job(
        _send_stats,
        trigger=CronTrigger(
            hour=settings.morning_stats_hour,
            minute=settings.morning_stats_minute,
            timezone=settings.timezone,
        ),
        id="morning_stats",
        name="Morning Stats Briefing",
        replace_existing=True,
    )

    logger.info(
        "Scheduled daily stats at %02d:%02d and %02d:%02d %s",
        settings.morning_stats_hour, settings.morning_stats_minute,
        settings.daily_stats_hour, settings.daily_stats_minute,
        settings.timezone,
    )


def register_backup_job(scheduler: AsyncIOScheduler):
    """Register a daily SQLite backup job."""
    if not settings.enable_db_backup:
        logger.info("DB backup disabled in settings")
        return
    from core.backup import backup_database

    scheduler.add_job(
        backup_database,
        trigger=CronTrigger(
            hour=settings.db_backup_hour,
            minute=0,
            timezone=settings.timezone,
        ),
        id="db_backup",
        name="Daily SQLite Backup",
        replace_existing=True,
    )
    logger.info("Scheduled daily DB backup at %02d:00 %s", settings.db_backup_hour, settings.timezone)


def setup_scheduler(bot=None) -> AsyncIOScheduler:
    """Create scheduler and register all jobs."""
    scheduler = create_scheduler()
    register_video_jobs(scheduler)

    try:
        register_email_job(scheduler)
    except Exception as e:
        logger.warning("Email agent not configured, skipping: %s", e)

    register_daily_stats_job(scheduler, bot=bot)
    register_backup_job(scheduler)

    return scheduler
