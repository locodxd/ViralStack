"""
YouTube Shorts publisher using YouTube Data API v3.

Each account has its own OAuth2 token (separate Google account).
Videos are uploaded as Shorts (vertical, <=60s, #shorts tag).
"""
import logging
import random
import asyncio
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from config.settings import settings, ACCOUNTS

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# YouTube Shorts category IDs by content type
_CATEGORY_IDS = {
    "terror": "24",       # Entertainment
    "historias": "24",    # Entertainment
    "dinero": "27",       # Education
}


def _get_youtube_credentials(account: str) -> Credentials:
    """Get or refresh YouTube OAuth credentials for an account."""
    token_path = Path(settings.get_youtube_token_path(account))

    if not token_path.exists():
        raise FileNotFoundError(
            f"YouTube token not found for {account}: {token_path}\n"
            f"Run: python scripts/setup_youtube.py {account}"
        )

    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json())
            logger.info("YouTube token refreshed for %s", account)
        else:
            raise RuntimeError(
                f"YouTube token expired and cannot refresh for {account}. "
                f"Re-run: python scripts/setup_youtube.py {account}"
            )

    return creds


def _build_youtube_service(account: str):
    """Build YouTube API service for an account."""
    creds = _get_youtube_credentials(account)
    return build("youtube", "v3", credentials=creds)


async def publish_to_youtube(
    video_path: str,
    title: str,
    account: str,
    description: str = None,
    hashtags: list = None,
) -> str:
    """Publish a video as a YouTube Short.

    Returns the YouTube video URL or raises exception.
    """
    account_config = ACCOUNTS.get(account, {})
    default_hashtags = account_config.get("hashtags_youtube", [])

    all_hashtags = list(set((hashtags or []) + default_hashtags))
    # Ensure #shorts is always present for YouTube Shorts detection
    if "#shorts" not in [h.lower() for h in all_hashtags]:
        all_hashtags.insert(0, "#Shorts")

    hashtag_str = " ".join(all_hashtags[:15])

    # Build description
    if not description:
        lang = settings.language.lower()
        if lang.startswith("es"):
            description = f"{title}\n\n{hashtag_str}"
        else:
            description = f"{title}\n\n{hashtag_str}"
    else:
        description = f"{description}\n\n{hashtag_str}"

    # YouTube Shorts title — keep it concise, add #Shorts
    yt_title = title[:90]  # YouTube title limit is 100 chars
    if "#shorts" not in yt_title.lower():
        yt_title = f"{yt_title} #Shorts"
    yt_title = yt_title[:100]

    category_id = _CATEGORY_IDS.get(account, "24")

    # Default language based on system config
    default_lang = "es" if not settings.is_english else "en"

    body = {
        "snippet": {
            "title": yt_title,
            "description": description[:5000],  # YouTube description limit
            "tags": [h.replace("#", "") for h in all_hashtags[:30]],
            "categoryId": category_id,
            "defaultLanguage": default_lang,
            "defaultAudioLanguage": default_lang,
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "embeddable": True,
        },
    }

    # Human-like delay before upload (2-8 seconds)
    delay = random.uniform(2, 8)
    logger.info("Waiting %.1fs before YouTube upload (human-like delay)", delay)
    await asyncio.sleep(delay)

    try:
        service = _build_youtube_service(account)

        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=10 * 1024 * 1024,  # 10MB chunks for efficiency
        )

        logger.info("Publishing to YouTube Shorts [%s]: %s", account, yt_title[:50])

        # Execute upload in thread pool to avoid blocking async loop
        request = service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        response = await asyncio.to_thread(_execute_resumable_upload, request)

        video_id = response["id"]
        video_url = f"https://youtube.com/shorts/{video_id}"

        logger.info("Successfully published to YouTube [%s]: %s", account, video_url)
        return video_url

    except Exception as e:
        logger.error("YouTube upload failed for %s: %s", account, e)
        raise


def _execute_resumable_upload(request) -> dict:
    """Execute a resumable upload with progress logging."""
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logger.debug("YouTube upload progress: %.1f%%", status.progress() * 100)
    return response
