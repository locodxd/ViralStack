import asyncio
import logging
import sys
import threading
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import settings
from core.db import init_db
from core.key_rotation import seed_keys_from_settings
from core.scheduler import setup_scheduler
from core import discord_alerts


def setup_logging():
    """Configure logging for the application."""
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    log_dir = Path("storage")
    log_dir.mkdir(exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("storage/automation.log", encoding="utf-8"),
        ],
    )


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
    logger = logging.getLogger(__name__)

    setup_logging()
    logger.info("=" * 60)
    logger.info("ViralStack — TikTok + YouTube Shorts Automation")
    logger.info("=" * 60)

    # Initialize database
    init_db()
    logger.info("Database initialized")

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

    # Send startup notification
    discord_alerts.send_info(
        "Sistema de automatización iniciado.\n"
        f"Plataformas: TikTok + YouTube Shorts\n"
        f"Dashboard: http://localhost:{settings.dashboard_port}\n"
        f"Cuentas activas: Terror, Historias, Dinero\n"
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
