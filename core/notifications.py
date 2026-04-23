"""Multi-channel notifications: Slack, Telegram, generic webhook.

Discord is handled by `core.discord_alerts` (kept for backward compatibility);
this module is fanned-out from there so a single alert reaches every channel
the user has configured.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from typing import Optional

from config.settings import settings

logger = logging.getLogger(__name__)

_LEVELS = {"info": 0, "warning": 1, "error": 2, "urgent": 3}
_lock = threading.Lock()
_recent_sends: deque[float] = deque(maxlen=500)


def _rate_limited() -> bool:
    limit = max(0, settings.notification_rate_limit_per_minute)
    if limit <= 0:
        return False
    now = time.time()
    with _lock:
        # Drop entries older than 60s
        while _recent_sends and now - _recent_sends[0] > 60:
            _recent_sends.popleft()
        if len(_recent_sends) >= limit:
            return True
        _recent_sends.append(now)
    return False


def _level_passes(level: str) -> bool:
    min_lvl = _LEVELS.get(settings.notification_min_level.lower(), 0)
    return _LEVELS.get(level.lower(), 0) >= min_lvl


def _post_json(url: str, payload: dict, timeout: float = 8.0) -> None:
    """Best-effort sync HTTP POST. Failures only log, never raise."""
    try:
        import httpx
        with httpx.Client(timeout=timeout) as client:
            r = client.post(url, json=payload)
            if r.status_code >= 400:
                logger.warning("Notification POST %s -> %s", _redact_url(url), r.status_code)
    except Exception as e:
        logger.warning("Notification POST failed for %s: %s", _redact_url(url), e)


def _redact_url(url: str) -> str:
    # Hide the token portion of well-known webhook URLs
    return url.split("?")[0][:60] + "…" if url else "(empty)"


def _send_slack(level: str, title: str, description: str, account: Optional[str]) -> None:
    if not settings.slack_webhook_url:
        return
    color = {"info": "#3498db", "warning": "#e67e22", "error": "#e74c3c", "urgent": "#992d22"}.get(level, "#3498db")
    fields = []
    if account:
        fields.append({"title": "Account", "value": account, "short": True})
    fields.append({"title": "Level", "value": level.upper(), "short": True})
    payload = {
        "attachments": [{
            "fallback": f"[{level.upper()}] {title}: {description[:200]}",
            "color": color,
            "title": title,
            "text": description[:3500],
            "fields": fields,
            "footer": "ViralStack",
            "ts": int(time.time()),
        }]
    }
    _post_json(settings.slack_webhook_url, payload)


def _send_telegram(level: str, title: str, description: str, account: Optional[str]) -> None:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return
    icon = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "urgent": "🚨"}.get(level, "•")
    text = f"{icon} *{title}*"
    if account:
        text += f"  _{account}_"
    text += f"\n\n{description[:3500]}"
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    _post_json(url, {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    })


def _send_generic(level: str, title: str, description: str, account: Optional[str]) -> None:
    if not settings.generic_webhook_url:
        return
    _post_json(settings.generic_webhook_url, {
        "level": level,
        "title": title,
        "description": description,
        "account": account,
        "ts": time.time(),
        "source": "viralstack",
    })


def fanout(level: str, title: str, description: str, account: Optional[str] = None) -> None:
    """Fan-out to every configured non-Discord channel."""
    if not _level_passes(level):
        return
    if _rate_limited():
        logger.debug("Notification rate-limited (level=%s)", level)
        return

    # Run each channel in its own short-lived thread so a slow webhook never blocks the pipeline.
    for fn in (_send_slack, _send_telegram, _send_generic):
        t = threading.Thread(
            target=fn, args=(level, title, description, account),
            daemon=True, name=f"notify-{fn.__name__}",
        )
        t.start()
