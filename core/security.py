"""Lightweight security helpers: secret masking + dashboard API key auth."""
from __future__ import annotations

import re
from typing import Optional

from fastapi import Header, HTTPException, status

from config.settings import settings

_KEY_LIKE = re.compile(r"^[A-Za-z0-9_\-\.]{16,}$")


def mask_secret(value: Optional[str], keep: int = 4) -> str:
    """Mask all but the first/last few chars of a secret-like value."""
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}…{value[-keep:]}"


async def require_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> None:
    """FastAPI dependency that enforces dashboard auth if `dashboard_api_key` is set.

    If `settings.dashboard_api_key` is empty, this is a no-op (back-compat).
    """
    expected = settings.dashboard_api_key.strip()
    if not expected:
        return
    if not x_api_key or x_api_key.strip() != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-API-Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
