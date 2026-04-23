"""Tiny helper to record audit events without polluting call sites."""
from __future__ import annotations

import json
import logging
from typing import Any

from core.db import get_session
from core.models import AuditLog

logger = logging.getLogger(__name__)


def record(action: str, *, actor: str = "system", target: str = "",
           details: Any | None = None) -> None:
    """Insert an audit row. Failures only log."""
    try:
        with get_session() as session:
            row = AuditLog(
                actor=str(actor)[:100],
                action=str(action)[:80],
                target=str(target)[:200],
                details=json.dumps(details, default=str, ensure_ascii=False) if details is not None else None,
            )
            session.add(row)
    except Exception as e:
        logger.debug("Audit insert failed for action=%s: %s", action, e)
