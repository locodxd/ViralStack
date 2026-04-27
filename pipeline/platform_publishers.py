"""Generic platform publishing dispatcher for ViralStack v1.2."""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from config.settings import (
    get_platform_info,
    platform_display_name,
    platform_webhook_url,
    settings,
)

logger = logging.getLogger(__name__)


@dataclass
class PublishResult:
    platform: str
    ok: bool = False
    status: str = "failed"  # success | failed | skipped
    url: str = ""
    error: str = ""
    skipped: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


async def publish_to_platform(
    platform: str,
    video_path: str,
    title: str,
    account: str,
    hashtags: list[str] | None = None,
    description: str | None = None,
) -> PublishResult:
    """Publish a video using the platform registry configuration."""
    info = get_platform_info(platform)
    if not info:
        return PublishResult(
            platform=platform,
            status="skipped",
            skipped=True,
            error=f"Unsupported platform: {platform}",
        )

    publisher = str(info.get("publisher") or "manual").strip().lower()
    try:
        if publisher == "builtin:tiktok":
            from pipeline.tiktok_publish import publish_to_tiktok

            url = await publish_to_tiktok(video_path, title, account, hashtags or [])
            return PublishResult(
                platform=platform,
                ok=bool(url),
                status="success" if url else "failed",
                url=url,
                error="TikTok publisher returned no URL" if not url else "",
            )

        if publisher == "builtin:youtube":
            from pipeline.youtube_publish import publish_to_youtube

            url = await publish_to_youtube(
                video_path,
                title,
                account,
                description=description,
                hashtags=hashtags or [],
            )
            return PublishResult(
                platform=platform,
                ok=bool(url),
                status="success" if url else "failed",
                url=url,
                error="YouTube publisher returned no URL" if not url else "",
            )

        if publisher == "webhook":
            return await _publish_via_webhook(platform, info, video_path, title, account, hashtags or [], description)

        return _manual_or_skipped(platform, info, account, f"No direct publisher configured ({publisher})")
    except Exception as exc:
        logger.error("%s publish failed for %s: %s", platform_display_name(platform), account, exc)
        return PublishResult(platform=platform, status="failed", error=str(exc))


async def _publish_via_webhook(
    platform: str,
    info: dict[str, Any],
    video_path: str,
    title: str,
    account: str,
    hashtags: list[str],
    description: str | None,
) -> PublishResult:
    webhook_url = platform_webhook_url(platform)
    if not webhook_url:
        return _manual_or_skipped(
            platform,
            info,
            account,
            f"{platform_display_name(platform)} webhook is not configured",
        )

    video_file = Path(video_path)
    if not video_file.exists():
        return PublishResult(platform=platform, status="failed", error=f"Video not found: {video_path}")

    payload = {
        "platform": platform,
        "account": account,
        "title": title,
        "description": description or title,
        "hashtags": " ".join(hashtags),
        "video_path": str(video_file),
    }

    timeout = max(10, settings.platform_webhook_timeout_seconds)
    try:
        import httpx

        send_file = bool(info.get("send_file", True))
        async with httpx.AsyncClient(timeout=timeout) as client:
            if send_file:
                with video_file.open("rb") as handle:
                    response = await client.post(
                        webhook_url,
                        data=payload,
                        files={"video": (video_file.name, handle, "video/mp4")},
                    )
            else:
                response = await client.post(webhook_url, json=payload)

        response.raise_for_status()
        metadata = _response_metadata(response)
        url = _extract_url(metadata) or str(info.get("manual_url_template", "")).format(account=account)
        return PublishResult(
            platform=platform,
            ok=True,
            status="success",
            url=url,
            metadata=metadata,
        )
    except Exception as exc:
        return PublishResult(platform=platform, status="failed", error=str(exc))


def _response_metadata(response) -> dict[str, Any]:
    try:
        data = response.json()
        return data if isinstance(data, dict) else {"response": data}
    except Exception:
        text = (response.text or "").strip()
        return {"response_text": text[:1000]} if text else {}


def _extract_url(metadata: dict[str, Any]) -> str:
    for key in ("url", "video_url", "share_url", "permalink", "link"):
        if metadata.get(key):
            return str(metadata[key])
    return ""


def _manual_or_skipped(platform: str, info: dict[str, Any], account: str, reason: str) -> PublishResult:
    template = str(info.get("manual_url_template") or "")
    url = template.format(account=account) if template else ""
    return PublishResult(
        platform=platform,
        status="skipped",
        url=url,
        error=reason,
        skipped=True,
        metadata={"reason": reason},
    )
