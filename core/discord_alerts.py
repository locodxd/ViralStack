"""
Discord alert system + multi-channel fan-out.

Uses the Discord bot when available, falls back to webhooks.
All alerts are sent as rich embeds. Every alert is also fanned-out to the
optional Slack / Telegram / generic webhooks configured in settings.

v1.1 additions:
- Per-process rate limiting to avoid Discord 429s during error storms
- Optional traceback suppression for production (`settings.discord_send_tracebacks`)
- Secret-masking of message content (best-effort)
- Fan-out to `core.notifications`
"""
import logging
import asyncio
import re
import threading
import time
import traceback
from collections import deque
from datetime import datetime
from typing import Optional

from config.settings import settings
from core import notifications

logger = logging.getLogger(__name__)

WEBHOOK_URL = settings.discord_webhook_url
USER_ID = settings.discord_user_id

# Reference to the bot instance (set by main.py after bot starts)
_bot_instance = None
_webhook_disabled_logged = False

_rl_lock = threading.Lock()
_rl_recent: deque[float] = deque(maxlen=200)
_RL_PER_MIN = 30  # safety cap regardless of settings


_SECRET_RE = re.compile(r"(AIza[0-9A-Za-z_\-]{20,}|sk-[A-Za-z0-9]{20,}|eyJ[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)")


def _sanitize(text: Optional[str]) -> str:
    if not text:
        return text or ""
    return _SECRET_RE.sub(lambda m: m.group(0)[:6] + "…REDACTED…" + m.group(0)[-4:], text)


def _allow_send() -> bool:
    now = time.time()
    with _rl_lock:
        while _rl_recent and now - _rl_recent[0] > 60:
            _rl_recent.popleft()
        if len(_rl_recent) >= _RL_PER_MIN:
            return False
        _rl_recent.append(now)
    return True


def set_bot(bot):
    """Set the bot instance for sending alerts via bot channels."""
    global _bot_instance
    _bot_instance = bot


def _send_via_webhook(content: str = None, embed_data: dict = None):
    """Send via Discord webhook (legacy fallback)."""
    global _webhook_disabled_logged

    if not WEBHOOK_URL:
        if not _webhook_disabled_logged:
            logger.warning("Discord webhook URL not configured, skipping alert")
            _webhook_disabled_logged = True
        return

    if "YOUR_WEBHOOK_ID" in WEBHOOK_URL or "YOUR_WEBHOOK_TOKEN" in WEBHOOK_URL:
        if not _webhook_disabled_logged:
            logger.warning("Discord webhook URL is still a placeholder, skipping alert")
            _webhook_disabled_logged = True
        return

    try:
        from discord_webhook import DiscordWebhook, DiscordEmbed

        webhook = DiscordWebhook(url=WEBHOOK_URL, content=content)
        if embed_data:
            embed = DiscordEmbed(
                title=embed_data.get("title", ""),
                description=embed_data.get("description", ""),
                color=embed_data.get("color", "03b2f8"),
            )
            embed.set_timestamp(datetime.utcnow().isoformat())
            if embed_data.get("account"):
                embed.add_embed_field(
                    name="Cuenta", value=embed_data["account"], inline=True
                )
            webhook.add_embed(embed)
        response = webhook.execute()
        if response and hasattr(response, 'status_code') and response.status_code not in (200, 204):
            logger.error("Discord webhook failed with status %s", response.status_code)
    except Exception as e:
        logger.error("Failed to send Discord webhook alert: %s", e)


def _send_via_bot(embed_data: dict, urgent: bool = False):
    """Send via the Discord bot's alerts channel."""
    try:
        from bot.stats import build_alert_embed

        embed = build_alert_embed(
            title=embed_data.get("title", ""),
            message=embed_data.get("description", ""),
            level=embed_data.get("level", "info"),
            account=embed_data.get("account"),
        )

        # Schedule the coroutine on the bot's event loop
        loop = _bot_instance.loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(
                _bot_instance.send_alert(embed, urgent=urgent),
                loop,
            )
        else:
            logger.warning("Bot event loop not running, falling back to webhook")
            _send_via_webhook(
                content=f"<@{USER_ID}> ALERTA URGENTE" if urgent else None,
                embed_data=embed_data,
            )
    except Exception as e:
        logger.error("Failed to send via bot, falling back to webhook: %s", e)
        _send_via_webhook(embed_data=embed_data)


def _send(embed_data: dict, urgent: bool = False):
    """Send alert — bot if available, webhook as fallback. Also fans-out to other channels."""
    # Sanitize and fan-out first (cheap and never blocks)
    embed_data["description"] = _sanitize(embed_data.get("description", ""))
    embed_data["title"] = _sanitize(embed_data.get("title", ""))

    notifications.fanout(
        level=embed_data.get("level", "info"),
        title=embed_data.get("title", ""),
        description=embed_data.get("description", ""),
        account=embed_data.get("account"),
    )

    if not _allow_send():
        logger.debug("Discord rate-limited, dropped: %s", embed_data.get("title"))
        return

    if _bot_instance and _bot_instance.is_ready():
        _send_via_bot(embed_data, urgent=urgent)
    else:
        content = None
        if urgent:
            content = f"<@{USER_ID}> ALERTA URGENTE"
        _send_via_webhook(content=content, embed_data=embed_data)


def send_info(message: str, account: str = None):
    """Send an informational message (success, status update)."""
    _send({
        "title": "Info",
        "description": message,
        "color": "03b2f8",
        "level": "info",
        "account": account,
    })


def send_warning(message: str, account: str = None):
    """Send a warning message (quality check failed, retry)."""
    _send({
        "title": "Warning",
        "description": message,
        "color": "ffa500",
        "level": "warning",
        "account": account,
    })


def send_error(message: str, exception: Exception = None, account: str = None):
    """Send an error message (step failed, key exhausted)."""
    desc = message
    if exception:
        # Always log the full traceback locally; only send to Discord if explicitly enabled.
        tb = traceback.format_exception(type(exception), exception, exception.__traceback__)
        logger.error("Exception detail:\n%s", "".join(tb))
        if settings.discord_send_tracebacks:
            desc += f"\n```\n{''.join(tb[-3:])}\n```"
        else:
            desc += f"\n`{type(exception).__name__}: {str(exception)[:200]}`"

    _send({
        "title": "Error",
        "description": desc[:4000],
        "color": "ff0000",
        "level": "error",
        "account": account,
    })


def send_urgent(message: str, account: str = None):
    """Send an urgent alert with user ping (legal email, all keys down)."""
    _send({
        "title": "URGENTE",
        "description": message[:4000],
        "color": "ff0000",
        "level": "urgent",
        "account": account,
    }, urgent=True)

