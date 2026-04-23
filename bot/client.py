"""
Discord bot for controlling the ViralStack automation system.

Restrictions:
- Only operates in the guild configured via DISCORD_GUILD_ID in .env
- Only the user configured via DISCORD_OWNER_ID can execute commands
- All other access is blocked
"""
import logging
import discord
from discord import app_commands
from config.settings import settings

logger = logging.getLogger(__name__)

GUILD_ID = discord.Object(id=settings.discord_guild_id)
OWNER_ID = settings.discord_owner_id


class AutomationBot(discord.Client):
    """Main Discord bot client."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = False  # We only use slash commands
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self._alerts_channel = None
        self._stats_channel = None

    async def setup_hook(self):
        """Called when the bot is starting up. Register commands to the guild."""
        # Import and add command cogs
        from bot.commands import setup_commands
        from bot.stats import setup_stats

        setup_commands(self)
        setup_stats(self)

        # Sync commands to the specific guild only
        self.tree.copy_global_to(guild=GUILD_ID)
        await self.tree.sync(guild=GUILD_ID)
        logger.info("Slash commands synced to guild %s", settings.discord_guild_id)

    async def on_ready(self):
        logger.info("Discord bot logged in as %s (ID: %s)", self.user, self.user.id)

        # Cache channel references
        if settings.discord_alerts_channel_id:
            self._alerts_channel = self.get_channel(settings.discord_alerts_channel_id)
        if settings.discord_stats_channel_id:
            self._stats_channel = self.get_channel(settings.discord_stats_channel_id)

        # Set status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=settings.discord_status_message or f"ViralStack v{settings.version}",
            )
        )

    async def on_guild_join(self, guild: discord.Guild):
        """Leave any guild that isn't the authorized one."""
        if guild.id != settings.discord_guild_id:
            logger.warning("Joined unauthorized guild %s (%s), leaving...", guild.name, guild.id)
            await guild.leave()

    @property
    def alerts_channel(self):
        return self._alerts_channel

    @property
    def stats_channel(self):
        return self._stats_channel

    async def send_alert(self, embed: discord.Embed, urgent: bool = False):
        """Send an alert embed to the alerts channel."""
        channel = self._alerts_channel
        if not channel:
            logger.warning("Alerts channel not configured")
            return

        content = None
        if urgent:
            content = f"<@{OWNER_ID}> ALERTA URGENTE"

        try:
            await channel.send(content=content, embed=embed)
        except Exception as e:
            logger.error("Failed to send bot alert: %s", e)

    async def send_stats(self, embed: discord.Embed):
        """Send a stats embed to the stats channel."""
        channel = self._stats_channel or self._alerts_channel
        if not channel:
            return

        try:
            await channel.send(embed=embed)
        except Exception as e:
            logger.error("Failed to send bot stats: %s", e)


def owner_only():
    """Check that only the owner can use commands."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message(
                "No tienes permiso para usar este comando.", ephemeral=True
            )
            return False
        return True
    return app_commands.check(predicate)


# Singleton bot instance
bot = AutomationBot()
