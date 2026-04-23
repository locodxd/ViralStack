"""Structured logging with optional JSON output and secret masking.

Configured by `settings.log_level`, `settings.log_format`, `settings.log_mask_secrets`.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

from config.settings import settings

# Patterns that look like secrets — we redact their values in log records.
_SECRET_PATTERNS = [
    re.compile(r"(AIza[0-9A-Za-z_\-]{20,})"),               # Google API keys
    re.compile(r"(sk-[A-Za-z0-9]{20,})"),                   # OpenAI-style
    re.compile(r"(xox[baprs]-[A-Za-z0-9\-]{10,})"),         # Slack tokens
    re.compile(r"(eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)"),  # JWT
    re.compile(r"(ghp_[A-Za-z0-9]{20,})"),                  # GitHub PAT
    re.compile(r"(Bearer\s+[A-Za-z0-9._\-]{16,})", re.I),
]


def _mask(text: str) -> str:
    if not text:
        return text
    for p in _SECRET_PATTERNS:
        text = p.sub(lambda m: m.group(0)[:6] + "…REDACTED…" + m.group(0)[-4:], text)
    return text


class _SecretMaskingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        try:
            if isinstance(record.msg, str):
                record.msg = _mask(record.msg)
            if record.args:
                record.args = tuple(_mask(str(a)) if isinstance(a, str) else a
                                    for a in record.args)
        except Exception:
            pass
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload = {
            "ts": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        for k in ("account", "video_id", "step"):
            if hasattr(record, k):
                payload[k] = getattr(record, k)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(extra_handlers: Iterable[logging.Handler] | None = None) -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    log_dir = Path("storage")
    log_dir.mkdir(exist_ok=True)

    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_dir / "automation.log", encoding="utf-8"),
    ]
    if extra_handlers:
        handlers.extend(extra_handlers)

    if settings.log_format.lower() == "json":
        formatter: logging.Formatter = _JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )

    for h in handlers:
        h.setFormatter(formatter)
        if settings.log_mask_secrets:
            h.addFilter(_SecretMaskingFilter())

    root = logging.getLogger()
    root.handlers.clear()
    for h in handlers:
        root.addHandler(h)
    root.setLevel(level)

    # Quiet noisy loggers a bit
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
