"""
Scheduled stats reporting via the Discord bot.

Sends daily summary and real-time alerts through bot channels
instead of webhooks.
"""
import logging
import json
from datetime import datetime, timedelta
import discord
from config.settings import (
    ACCOUNTS,
    enabled_platforms_for,
    is_platform_enabled,
    list_account_ids,
    platform_short_name,
    settings,
)
from core.db import get_session
from core.models import Video, EmailThread

logger = logging.getLogger(__name__)


def setup_stats(bot):
    """Register stats-related functionality on the bot."""
    # Stats are sent via scheduler calling send_daily_stats()
    pass


async def send_daily_stats(bot):
    """Send a daily summary embed to the stats channel. Called by scheduler."""
    if not bot.is_ready():
        return

    now = datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)

    with get_session() as session:
        # Today's stats
        today_published = session.query(Video).filter(
            Video.status == "published",
            Video.published_at >= today,
        ).count()

        today_failed = session.query(Video).filter(
            Video.status.in_(["failed", "rejected"]),
            Video.created_at >= today,
        ).count()

        # Yesterday's stats for comparison
        yesterday_published = session.query(Video).filter(
            Video.status == "published",
            Video.published_at >= yesterday,
            Video.published_at < today,
        ).count()

        # Platform breakdown (legacy columns + v1.2 generic JSON)
        legacy_tiktok = session.query(Video).filter(
            Video.tiktok_published == True,
            Video.published_at >= today,
        ).count()

        legacy_youtube = session.query(Video).filter(
            Video.youtube_published == True,
            Video.published_at >= today,
        ).count()

        platform_counts = {}
        platform_rows = session.query(Video.platform_results_json).filter(
            Video.created_at >= today,
        ).all()
        for (raw_results,) in platform_rows:
            if not raw_results:
                continue
            try:
                results = json.loads(raw_results)
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(results, dict):
                continue
            for platform, result in results.items():
                if isinstance(result, dict) and result.get("ok"):
                    platform_counts[platform] = platform_counts.get(platform, 0) + 1

        platform_counts.setdefault("tiktok", legacy_tiktok)
        platform_counts.setdefault("youtube", legacy_youtube)

        # Per-account breakdown
        account_stats = {}
        for acc_name in list_account_ids():
            pub = session.query(Video).filter(
                Video.account == acc_name,
                Video.status == "published",
                Video.published_at >= today,
            ).count()
            total = session.query(Video).filter(
                Video.account == acc_name,
                Video.status == "published",
            ).count()
            account_stats[acc_name] = {"today": pub, "total": total}

        # Average quality today
        from sqlalchemy import func
        avg_score = session.query(func.avg(Video.quality_score)).filter(
            Video.quality_score != None,
            Video.created_at >= today,
        ).scalar()

        # Email stats
        emails_today = session.query(EmailThread).filter(
            EmailThread.created_at >= today,
        ).count()

        emails_attention = session.query(EmailThread).filter(
            EmailThread.needs_attention == True,
        ).count()

    # Build embed
    embed = discord.Embed(
        title="Resumen Diario",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow(),
    )

    # Trend indicator
    trend = ""
    if today_published > yesterday_published:
        trend = " (subiendo)"
    elif today_published < yesterday_published:
        trend = " (bajando)"

    embed.add_field(
        name="Hoy",
        value=(
            f"Publicados: **{today_published}**{trend}\n"
            f"Fallidos: **{today_failed}**\n"
            f"Plataformas: **{_format_platform_counts(platform_counts)}**\n"
            f"Calidad promedio: **{avg_score:.1f}/10**" if avg_score else
            f"Publicados: **{today_published}**{trend}\n"
            f"Fallidos: **{today_failed}**\n"
            f"Plataformas: **{_format_platform_counts(platform_counts)}**"
        ),
        inline=False,
    )

    # Per-account
    for acc_name, stats in account_stats.items():
        display = ACCOUNTS.get(acc_name, {}).get("display_name", acc_name)
        enabled = enabled_platforms_for(acc_name)
        platform_line = " | ".join(
            f"{platform_short_name(platform)}={'ON' if is_platform_enabled(acc_name, platform) else 'OFF'}"
            for platform in enabled
        ) or "NINGUNA"

        embed.add_field(
            name=display,
            value=(
                f"Hoy: **{stats['today']}** | Total: **{stats['total']}**\n"
                f"{platform_line}"
            ),
            inline=True,
        )

    # Emails
    if emails_today > 0 or emails_attention > 0:
        embed.add_field(
            name="Emails",
            value=(
                f"Hoy: **{emails_today}**\n"
                f"Requieren atención: **{emails_attention}**"
            ),
            inline=False,
        )

    embed.set_footer(text=f"Ayer: {yesterday_published} publicados | {settings.timezone}")

    await bot.send_stats(embed)
    logger.info("Daily stats sent to Discord")


def _format_platform_counts(counts: dict) -> str:
    if not counts:
        return "0"
    return " | ".join(
        f"{platform_short_name(platform)}:{count}"
        for platform, count in sorted(counts.items())
    )


def build_alert_embed(
    title: str,
    message: str,
    level: str = "info",
    account: str = None,
) -> discord.Embed:
    """Build a Discord embed for alerts."""
    colors = {
        "info": discord.Color.blue(),
        "warning": discord.Color.orange(),
        "error": discord.Color.red(),
        "urgent": discord.Color.red(),
        "success": discord.Color.green(),
    }

    embed = discord.Embed(
        title=title,
        description=message[:4000],
        color=colors.get(level, discord.Color.greyple()),
        timestamp=datetime.utcnow(),
    )

    if account:
        display = ACCOUNTS.get(account, {}).get("display_name", account)
        embed.add_field(name="Cuenta", value=display, inline=True)

    return embed
