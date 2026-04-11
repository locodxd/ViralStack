"""
Slash commands for the automation Discord bot.

Commands:
- /status — System status overview
- /publish <account> [platform] — Force manual video publication
- /toggle <account> <platform> — Enable/disable platform for account
- /config — View current configuration
- /schedule — View upcoming scheduled videos
- /emails [account] — View recent email activity
"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional
import discord
from discord import app_commands
from config.settings import (
    settings, ACCOUNTS, load_platform_config, toggle_platform, is_platform_enabled,
)
from core.db import get_session
from core.models import Video, EmailThread

logger = logging.getLogger(__name__)

ACCOUNT_CHOICES = [
    app_commands.Choice(name="Terror", value="terror"),
    app_commands.Choice(name="Historias", value="historias"),
    app_commands.Choice(name="Dinero", value="dinero"),
]

PLATFORM_CHOICES = [
    app_commands.Choice(name="TikTok", value="tiktok"),
    app_commands.Choice(name="YouTube", value="youtube"),
]


def setup_commands(bot):
    """Register all slash commands on the bot."""
    from bot.client import owner_only, GUILD_ID

    @bot.tree.command(name="status", description="Ver estado del sistema")
    @owner_only()
    async def status_cmd(interaction: discord.Interaction):
        await interaction.response.defer()

        now = datetime.utcnow()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = now - timedelta(days=7)

        with get_session() as session:
            total = session.query(Video).count()
            published = session.query(Video).filter(Video.status == "published").count()
            failed = session.query(Video).filter(Video.status == "failed").count()
            today_count = session.query(Video).filter(Video.created_at >= today).count()
            week_count = session.query(Video).filter(Video.created_at >= week_ago).count()

            # Per-account counts
            account_lines = []
            for acc_name in ["terror", "historias", "dinero"]:
                acc_pub = session.query(Video).filter(
                    Video.account == acc_name, Video.status == "published"
                ).count()
                acc_today = session.query(Video).filter(
                    Video.account == acc_name, Video.created_at >= today
                ).count()

                tt = is_platform_enabled(acc_name, "tiktok")
                yt = is_platform_enabled(acc_name, "youtube")
                platforms = []
                if tt:
                    platforms.append("TT")
                if yt:
                    platforms.append("YT")

                acc_display = ACCOUNTS.get(acc_name, {}).get("display_name", acc_name)
                account_lines.append(
                    f"**{acc_display}**: {acc_pub} publicados | "
                    f"Hoy: {acc_today} | "
                    f"Plataformas: {' + '.join(platforms) if platforms else 'NINGUNA'}"
                )

        config = load_platform_config()

        embed = discord.Embed(
            title="Estado del Sistema",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow(),
        )
        embed.add_field(
            name="General",
            value=(
                f"Total videos: **{total}**\n"
                f"Publicados: **{published}**\n"
                f"Fallidos: **{failed}**\n"
                f"Hoy: **{today_count}** | Semana: **{week_count}**"
            ),
            inline=False,
        )
        embed.add_field(
            name="Cuentas",
            value="\n".join(account_lines),
            inline=False,
        )
        embed.add_field(
            name="Idioma",
            value=settings.language.upper(),
            inline=True,
        )
        embed.add_field(
            name="Dashboard",
            value=f"http://localhost:{settings.dashboard_port}",
            inline=True,
        )

        await interaction.followup.send(embed=embed)

    @bot.tree.command(name="publish", description="Forzar publicación manual de un video")
    @app_commands.describe(
        account="Cuenta a publicar",
        platform="Plataforma específica (opcional, por defecto ambas)",
    )
    @app_commands.choices(account=ACCOUNT_CHOICES, platform=PLATFORM_CHOICES)
    @owner_only()
    async def publish_cmd(
        interaction: discord.Interaction,
        account: app_commands.Choice[str],
        platform: Optional[app_commands.Choice[str]] = None,
    ):
        await interaction.response.defer()

        acc = account.value

        # Temporarily override platform config if specific platform requested
        if platform:
            plat = platform.value
            other = "youtube" if plat == "tiktok" else "tiktok"
            # Save current state
            orig_other = is_platform_enabled(acc, other)
            toggle_platform(acc, other, False)
            toggle_platform(acc, plat, True)

        await interaction.followup.send(
            f"Iniciando producción manual para **{account.name}**... "
            f"{'(' + platform.name + ' only)' if platform else '(todas las plataformas)'}\n"
            f"Te notificaré cuando termine."
        )

        try:
            from pipeline.orchestrator import produce_video
            await produce_video(acc)
        except Exception as e:
            logger.error("Manual publish failed: %s", e)
            await interaction.followup.send(f"Error en publicación manual: {e}")
        finally:
            # Restore platform config if we changed it
            if platform:
                toggle_platform(acc, other, orig_other)

    @bot.tree.command(name="toggle", description="Habilitar/deshabilitar plataforma para una cuenta")
    @app_commands.describe(
        account="Cuenta a modificar",
        platform="Plataforma a cambiar",
    )
    @app_commands.choices(account=ACCOUNT_CHOICES, platform=PLATFORM_CHOICES)
    @owner_only()
    async def toggle_cmd(
        interaction: discord.Interaction,
        account: app_commands.Choice[str],
        platform: app_commands.Choice[str],
    ):
        acc = account.value
        plat = platform.value

        current = is_platform_enabled(acc, plat)
        new_state = not current
        toggle_platform(acc, plat, new_state)

        state_str = "HABILITADA" if new_state else "DESHABILITADA"
        emoji = "ON" if new_state else "OFF"

        embed = discord.Embed(
            title="Plataforma Actualizada",
            description=(
                f"**{account.name}** - **{platform.name}**: {state_str} [{emoji}]"
            ),
            color=discord.Color.green() if new_state else discord.Color.red(),
            timestamp=datetime.utcnow(),
        )

        # Show full config
        config = load_platform_config()
        config_lines = []
        for a, platforms in config.items():
            display = ACCOUNTS.get(a, {}).get("display_name", a)
            tt = "ON" if platforms.get("tiktok") else "OFF"
            yt = "ON" if platforms.get("youtube") else "OFF"
            config_lines.append(f"{display}: TikTok={tt} | YouTube={yt}")

        embed.add_field(
            name="Configuración Actual",
            value="\n".join(config_lines),
            inline=False,
        )

        await interaction.response.send_message(embed=embed)

    @bot.tree.command(name="config", description="Ver configuración actual del sistema")
    @owner_only()
    async def config_cmd(interaction: discord.Interaction):
        config = load_platform_config()

        embed = discord.Embed(
            title="Configuración del Sistema",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow(),
        )

        # Platform toggles
        for acc_name in ["terror", "historias", "dinero"]:
            display = ACCOUNTS.get(acc_name, {}).get("display_name", acc_name)
            vpd = ACCOUNTS.get(acc_name, {}).get("videos_per_day", 0)
            tt = "ON" if config.get(acc_name, {}).get("tiktok") else "OFF"
            yt = "ON" if config.get(acc_name, {}).get("youtube") else "OFF"
            windows = ACCOUNTS.get(acc_name, {}).get("schedule_windows", [])
            times = ", ".join([f"{w['hour']:02d}:{w['minute']:02d}" for w in windows])

            embed.add_field(
                name=f"{display}",
                value=(
                    f"Videos/día: **{vpd}**\n"
                    f"TikTok: **{tt}** | YouTube: **{yt}**\n"
                    f"Horarios: {times or 'N/A'}"
                ),
                inline=False,
            )

        # General settings
        embed.add_field(
            name="General",
            value=(
                f"Idioma: **{settings.language.upper()}**\n"
                f"Calidad mínima: **{settings.quality_threshold}/10**\n"
                f"Max reintentos: **{settings.max_retries_per_video}**\n"
                f"Timezone: **{settings.timezone}**\n"
                f"Resolución: **{settings.video_width}x{settings.video_height}**"
            ),
            inline=False,
        )

        await interaction.response.send_message(embed=embed)

    @bot.tree.command(name="schedule", description="Ver próximos videos programados")
    @owner_only()
    async def schedule_cmd(interaction: discord.Interaction):
        embed = discord.Embed(
            title="Próximos Videos Programados",
            color=discord.Color.purple(),
            timestamp=datetime.utcnow(),
        )

        for acc_name in ["terror", "historias", "dinero"]:
            acc_cfg = ACCOUNTS.get(acc_name, {})
            display = acc_cfg.get("display_name", acc_name)
            vpd = acc_cfg.get("videos_per_day", 0)
            windows = acc_cfg.get("schedule_windows", [])

            if vpd == 0:
                embed.add_field(
                    name=display,
                    value="DESHABILITADA",
                    inline=False,
                )
                continue

            tt = "ON" if is_platform_enabled(acc_name, "tiktok") else "OFF"
            yt = "ON" if is_platform_enabled(acc_name, "youtube") else "OFF"

            schedule_lines = []
            for i, w in enumerate(windows):
                schedule_lines.append(
                    f"#{i+1}: **{w['hour']:02d}:{w['minute']:02d}** (±10min)"
                )

            schedule_lines.append(f"\nPlataformas: TikTok={tt} | YouTube={yt}")

            embed.add_field(
                name=f"{display} ({vpd} videos/día)",
                value="\n".join(schedule_lines),
                inline=False,
            )

        embed.set_footer(text=f"Timezone: {settings.timezone}")
        await interaction.response.send_message(embed=embed)

    @bot.tree.command(name="emails", description="Ver actividad reciente de emails")
    @app_commands.describe(account="Filtrar por cuenta (opcional)")
    @app_commands.choices(account=ACCOUNT_CHOICES)
    @owner_only()
    async def emails_cmd(
        interaction: discord.Interaction,
        account: Optional[app_commands.Choice[str]] = None,
    ):
        await interaction.response.defer()

        with get_session() as session:
            query = session.query(EmailThread).order_by(EmailThread.created_at.desc())
            if account:
                query = query.filter(EmailThread.account == account.value)
            emails = query.limit(10).all()

            if not emails:
                await interaction.followup.send("No hay emails recientes.")
                return

            embed = discord.Embed(
                title="Emails Recientes",
                color=discord.Color.teal(),
                timestamp=datetime.utcnow(),
            )

            for email in emails:
                status = ""
                if email.needs_attention:
                    status = "REQUIERE ATENCION"
                elif email.auto_responded:
                    status = "Auto-respondido"
                else:
                    status = email.category or "pendiente"

                acc_label = f"[{email.account}] " if email.account else ""
                embed.add_field(
                    name=f"{acc_label}{email.subject or 'Sin asunto'}",
                    value=(
                        f"De: {email.sender or 'Desconocido'}\n"
                        f"Categoría: **{email.category}** | {status}\n"
                        f"Fecha: {email.created_at.strftime('%d/%m %H:%M') if email.created_at else 'N/A'}"
                    ),
                    inline=False,
                )

        await interaction.followup.send(embed=embed)
