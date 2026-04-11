import logging
import random
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from config.settings import settings, ACCOUNTS

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
            "misfire_grace_time": 3600,
        },
    )

    return scheduler


def register_video_jobs(scheduler: AsyncIOScheduler):
    """Register video production jobs for all accounts.

    Times are pre-randomized in settings.py to non-round minutes
    (avoids :00, :15, :30, :45 to look human).
    Additional ±10min jitter is added by APScheduler.
    """
    from pipeline.orchestrator import produce_video

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

            scheduler.add_job(
                produce_video,
                trigger=CronTrigger(
                    hour=hour,
                    minute=minute,
                    second=jitter_secs,
                    jitter=600,  # ±10 min additional jitter from APScheduler
                    timezone=settings.timezone,
                ),
                args=[account],
                id=job_id,
                name=f"Video {config['display_name']} #{i+1}",
                replace_existing=True,
            )

            logger.info(
                "Scheduled %s video #%d at %02d:%02d:%02d %s (±10min jitter)",
                account, i + 1, hour, minute, jitter_secs, settings.timezone,
            )

        logger.info("Account %s: %d videos/day scheduled", account, vpd)


def register_email_job(scheduler: AsyncIOScheduler):
    """Register the email polling job (polls all 3 accounts)."""
    from email_agent.gmail_client import poll_and_process

    scheduler.add_job(
        poll_and_process,
        trigger=IntervalTrigger(
            minutes=30,
            jitter=300,
            timezone=settings.timezone,
        ),
        id="email_poll",
        name="Email Agent Poll (all accounts)",
        replace_existing=True,
    )
    logger.info("Scheduled email polling every 30 minutes (all accounts)")


def register_daily_stats_job(scheduler: AsyncIOScheduler, bot=None):
    """Register daily stats reporting via Discord bot."""
    if not bot:
        logger.info("No bot provided, skipping daily stats job")
        return

    from bot.stats import send_daily_stats

    async def _send_stats():
        await send_daily_stats(bot)

    # Send daily stats at 23:55 (end of day summary)
    scheduler.add_job(
        _send_stats,
        trigger=CronTrigger(
            hour=23,
            minute=55,
            timezone=settings.timezone,
        ),
        id="daily_stats",
        name="Daily Stats Report",
        replace_existing=True,
    )

    # Also send a morning briefing at 08:00
    scheduler.add_job(
        _send_stats,
        trigger=CronTrigger(
            hour=8,
            minute=0,
            timezone=settings.timezone,
        ),
        id="morning_stats",
        name="Morning Stats Briefing",
        replace_existing=True,
    )

    logger.info("Scheduled daily stats at 08:00 and 23:55 %s", settings.timezone)


def setup_scheduler(bot=None) -> AsyncIOScheduler:
    """Create scheduler and register all jobs."""
    scheduler = create_scheduler()
    register_video_jobs(scheduler)

    try:
        register_email_job(scheduler)
    except Exception as e:
        logger.warning("Email agent not configured, skipping: %s", e)

    register_daily_stats_job(scheduler, bot=bot)

    return scheduler
