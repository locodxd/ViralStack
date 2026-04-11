import asyncio
import json
import logging
import os
import random
import re
import subprocess
import sys
from pathlib import Path
from config.settings import settings, ACCOUNTS

logger = logging.getLogger(__name__)
_UPLOAD_WORKER = Path(__file__).resolve().parent.parent / "tools" / "tiktok_upload_worker.py"
_MAX_UPLOAD_ATTEMPTS = 2


async def publish_to_tiktok(
    video_path: str,
    title: str,
    account: str,
    hashtags: list = None,
) -> str:
    """Publish a video to TikTok using tiktok-uploader.

    Runs the synchronous uploader in a separate process so Playwright does not
    collide with the asyncio event loop. Returns the TikTok URL when available,
    otherwise falls back to the profile URL after a confirmed successful upload.
    """
    cookies_path = settings.get_cookies_path(account)
    if not cookies_path or not Path(cookies_path).exists():
        logger.error("No cookies found for account %s at %s", account, cookies_path)
        raise FileNotFoundError(f"TikTok cookies not found for {account}: {cookies_path}")

    account_config = ACCOUNTS.get(account, {})
    default_hashtags = account_config.get("hashtags", [])

    all_hashtags = list(set((hashtags or []) + default_hashtags))
    hashtag_str = " ".join(all_hashtags[:15])  # TikTok limit

    description = f"{title} {hashtag_str}"

    # Human-like delay before upload (2-8 seconds)
    delay = random.uniform(2, 8)
    logger.info("Waiting %.1fs before upload (human-like delay)", delay)
    await asyncio.sleep(delay)

    payload = {
        "video_path": video_path,
        "description": description[:2200],
        "cookies_path": cookies_path,
        "account": account,
    }

    errors = []
    for attempt in range(1, _MAX_UPLOAD_ATTEMPTS + 1):
        logger.info(
            "Publishing to TikTok [%s] attempt %d/%d: %s",
            account,
            attempt,
            _MAX_UPLOAD_ATTEMPTS,
            title[:50],
        )

        result = await asyncio.to_thread(_run_upload_worker, payload)
        if result.get("ok"):
            video_url = _extract_video_url(
                result.get("video_url") or result.get("result"),
                account,
            )
            logger.info("Successfully published to TikTok [%s]: %s", account, video_url)
            return video_url

        error = result.get("error") or "TikTok uploader returned a failure"
        errors.append(error)
        logger.warning(
            "TikTok upload attempt %d/%d failed for %s: %s",
            attempt,
            _MAX_UPLOAD_ATTEMPTS,
            account,
            error,
        )

        if attempt < _MAX_UPLOAD_ATTEMPTS:
            await asyncio.sleep(4 * attempt)

    final_error = " | ".join(errors[-_MAX_UPLOAD_ATTEMPTS:])
    logger.error("TikTok upload failed for %s: %s", account, final_error)
    raise RuntimeError(final_error)


def _run_upload_worker(payload: dict) -> dict:
    """Execute the sync TikTok uploader in a subprocess and parse its JSON result."""
    if not _UPLOAD_WORKER.exists():
        raise FileNotFoundError(f"TikTok upload worker not found: {_UPLOAD_WORKER}")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    cmd = [
        sys.executable,
        str(_UPLOAD_WORKER),
        json.dumps(payload, ensure_ascii=False),
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=False,
        timeout=1200,
        env=env,
    )

    stdout = _decode_process_output(result.stdout)
    stderr = _decode_process_output(result.stderr)

    worker_output = _parse_worker_output(stdout) or _parse_worker_output(stderr)
    if worker_output is None:
        detail = (stderr or stdout or "No output from TikTok worker").strip()
        return {"ok": False, "error": detail}

    if result.returncode != 0 and worker_output.get("ok"):
        worker_output["ok"] = False
        worker_output["error"] = worker_output.get("error") or "TikTok worker exited with failure"

    if not worker_output.get("ok"):
        details = "\n".join(part for part in [stderr.strip(), stdout.strip()] if part.strip())
        if details:
            base_error = worker_output.get("error") or "TikTok worker failed"
            worker_output["error"] = f"{base_error}\n{details}".strip()

    return worker_output


def _parse_worker_output(stream: str) -> dict | None:
    """Read the last JSON line emitted by the worker process."""
    for line in reversed((stream or "").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return None


def _decode_process_output(raw: bytes) -> str:
    """Decode subprocess output robustly even when libraries emit mixed encodings."""
    if not raw:
        return ""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def _extract_video_url(result, account: str) -> str:
    """Extract real video URL from upload result, with fallback to profile URL."""
    fallback = f"https://tiktok.com/@{account}"

    if result is None:
        return fallback

    if isinstance(result, list):
        if result:
            raise RuntimeError(f"TikTok uploader reported {len(result)} failed upload(s)")
        return fallback

    # If result is a string, check if it contains a TikTok URL
    if isinstance(result, str):
        match = re.search(r'https?://(?:www\.)?tiktok\.com/@[^/]+/video/\d+', result)
        if match:
            return match.group(0)
        # Check for video ID pattern
        vid_match = re.search(r'(\d{19,})', result)
        if vid_match:
            return f"https://tiktok.com/@{account}/video/{vid_match.group(1)}"
        return fallback

    # If result is dict-like, look for common URL fields
    if isinstance(result, dict):
        for key in ("url", "video_url", "share_url", "link"):
            if key in result and result[key]:
                return str(result[key])
        # Look for video_id
        for key in ("video_id", "id", "item_id"):
            if key in result and result[key]:
                return f"https://tiktok.com/@{account}/video/{result[key]}"

    return fallback
