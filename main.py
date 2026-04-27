import asyncio
import logging
import sys
import threading
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import settings, list_account_ids, list_platform_ids, platform_display_name, ACCOUNTS
from core.db import init_db
from core.key_rotation import seed_keys_from_settings
from core.scheduler import setup_scheduler
from core import discord_alerts
from core.logging_config import setup_logging
from core.health import health_snapshot


def start_dashboard():
    """Start the FastAPI dashboard in a separate thread."""
    try:
        import uvicorn
        from dashboard.app import app
        uvicorn.run(
            app,
            host=settings.dashboard_host,
            port=settings.dashboard_port,
            log_level="warning",
        )
    except Exception as e:
        logging.getLogger(__name__).error("Dashboard failed to start: %s", e)


async def main():
    """Main entry point."""
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("ViralStack v%s - Short-form automation", settings.version)
    logger.info("=" * 60)

    # Initialize database
    init_db()
    logger.info("Database initialized")

    # Health snapshot at startup — warn loudly on failures
    snap = health_snapshot()
    for name, check in snap.get("checks", {}).items():
        if not check.get("ok"):
            logger.warning("Healthcheck FAIL [%s]: %s", name, check.get("detail"))
        else:
            logger.info("Healthcheck OK   [%s]: %s", name, check.get("detail"))

    # Seed API keys from .env
    seed_keys_from_settings()
    logger.info("API keys loaded")

    # Start dashboard in background thread
    dashboard_thread = threading.Thread(target=start_dashboard, daemon=True)
    dashboard_thread.start()
    logger.info("Dashboard started at http://%s:%d", settings.dashboard_host, settings.dashboard_port)

    # Initialize Discord bot
    bot = None
    if settings.discord_bot_token:
        from bot.client import bot as discord_bot
        bot = discord_bot

        # Set bot reference in alerts system
        discord_alerts.set_bot(bot)

        logger.info("Discord bot configured")
    else:
        logger.warning("DISCORD_BOT_TOKEN not set — using webhook alerts only")

    # Setup and start scheduler (pass bot for stats job)
    scheduler = setup_scheduler(bot=bot)
    scheduler.start()
    logger.info("Scheduler started")

    # Send startup notification — dynamic account list
    account_names = ", ".join(
        ACCOUNTS.get(a, {}).get("display_name", a) for a in list_account_ids()
    ) or "(none)"
    platform_names = ", ".join(platform_display_name(p) for p in list_platform_ids()) or "(none)"
    discord_alerts.send_info(
        f"ViralStack v{settings.version} iniciado.\n"
        f"Plataformas: {platform_names}\n"
        f"Dashboard: http://localhost:{settings.dashboard_port}\n"
        f"Cuentas activas: {account_names}\n"
        f"Idioma: {settings.language.upper()}"
    )

    # Print scheduled jobs
    jobs = scheduler.get_jobs()
    logger.info("Scheduled jobs (%d):", len(jobs))
    for job in jobs:
        logger.info("  - %s: next run at %s", job.name, job.next_run_time)

    # Run Discord bot (blocking) or just keep scheduler alive
    if bot:
        logger.info("Starting Discord bot...")
        try:
            await bot.start(settings.discord_bot_token)
        except KeyboardInterrupt:
            pass
        finally:
            logger.info("Shutting down...")
            scheduler.shutdown()
            await bot.close()
            discord_alerts.send_info("Sistema de automatización detenido.")
    else:
        # No bot — keep running with just scheduler
        try:
            while True:
                await asyncio.sleep(60)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Shutting down...")
            scheduler.shutdown()
            discord_alerts.send_info("Sistema de automatización detenido.")


if __name__ == "__main__":
    asyncio.run(main())
