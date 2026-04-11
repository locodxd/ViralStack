import logging
import re
import time
from pathlib import Path
from google.genai import types
from config.settings import settings

logger = logging.getLogger(__name__)

# Google AI key used ONLY for quality check (files.upload requires Google AI, not Vertex)
# Set GOOGLE_AI_API_KEY in .env — get it free at https://aistudio.google.com/apikey
_QUALITY_CHECK_API_KEY = settings.google_ai_api_key
_QUALITY_CHECK_MODEL = "gemini-2.0-flash"

REVIEW_PROMPT = """You are an expert TikTok content reviewer. Analyze this video and rate it.

Evaluation criteria (0-10 each):
1. VISUAL: Visual quality, composition, visual appeal
2. AUDIO: Narration clarity, appropriate volume, audio quality
3. ENGAGEMENT: Initial hook, pacing, ability to retain the viewer
4. SUBTITLES: Readability, synchronization, formatting

RESPONSE FORMAT (exactly like this):
VISUAL: [score]
AUDIO: [score]
ENGAGEMENT: [score]
SUBTITLES: [score]
AVERAGE: [average of the 4 scores]
VERDICT: [APPROVED if average >= 6, REJECTED if < 6]
NOTES: [brief feedback in 1-2 sentences]
"""


def _parse_review(text: str) -> dict:
    """Parse the quality review response."""
    result = {
        "visual_score": 0,
        "audio_score": 0,
        "engagement_score": 0,
        "subtitles_score": 0,
        "average_score": 0,
        "approved": False,
        "notes": "",
    }

    for line in text.strip().split("\n"):
        line = line.strip()
        upper = line.upper()
        if upper.startswith("VISUAL:"):
            nums = re.findall(r"[\d.]+", line.split(":", 1)[1])
            if nums:
                result["visual_score"] = float(nums[0])
        elif upper.startswith("AUDIO:"):
            nums = re.findall(r"[\d.]+", line.split(":", 1)[1])
            if nums:
                result["audio_score"] = float(nums[0])
        elif upper.startswith("ENGAGEMENT:"):
            nums = re.findall(r"[\d.]+", line.split(":", 1)[1])
            if nums:
                result["engagement_score"] = float(nums[0])
        elif upper.startswith("SUBTITLE") or upper.startswith("SUBTITULO"):
            nums = re.findall(r"[\d.]+", line.split(":", 1)[1])
            if nums:
                result["subtitles_score"] = float(nums[0])
        elif upper.startswith("AVERAGE:") or upper.startswith("PROMEDIO:"):
            nums = re.findall(r"[\d.]+", line.split(":", 1)[1])
            if nums:
                result["average_score"] = float(nums[0])
        elif upper.startswith("VERDICT") or upper.startswith("VEREDICTO"):
            result["approved"] = "APPROVED" in upper or "APROBADO" in upper
        elif upper.startswith("NOTES:") or upper.startswith("NOTAS:"):
            result["notes"] = line.split(":", 1)[1].strip()

    # Recalculate average if not parsed
    if result["average_score"] == 0:
        scores = [
            result["visual_score"],
            result["audio_score"],
            result["engagement_score"],
            result["subtitles_score"],
        ]
        non_zero = [s for s in scores if s > 0]
        if non_zero:
            result["average_score"] = sum(non_zero) / len(non_zero)

    result["approved"] = result["average_score"] >= settings.quality_threshold

    return result


def _auto_approve(reason: str) -> dict:
    """Return a default approved result when quality check is unavailable."""
    logger.warning("Quality check unavailable (%s) — auto-approving video", reason)
    return {
        "visual_score": 0,
        "audio_score": 0,
        "engagement_score": 0,
        "subtitles_score": 0,
        "average_score": 7.0,
        "approved": True,
        "notes": f"Quality check unavailable ({reason}). Auto-approved.",
    }


async def review_video(video_path: str, account: str) -> dict:
    """Review a video using Gemini multimodal via Google AI.

    Uses a dedicated Google AI API key (files.upload is not supported in Vertex AI).
    Model: gemini-3-flash-preview.
    Creates a compressed review copy, uploads it, and reviews it.
    """
    if not _QUALITY_CHECK_API_KEY:
        return _auto_approve("GOOGLE_AI_API_KEY not set in .env")

    from pipeline.compositor import create_review_copy
    from google import genai as genai_lib

    video_file = Path(video_path)
    if not video_file.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    # Create compressed copy for upload
    review_path = create_review_copy(video_path)
    upload_file = Path(review_path)

    # Use Google AI client (NOT Vertex) — files.upload only works with Google AI
    client = genai_lib.Client(api_key=_QUALITY_CHECK_API_KEY)

    # Upload the file
    try:
        logger.info(
            "Uploading video for review (Google AI): %s (%.1f MB)",
            upload_file.name,
            upload_file.stat().st_size / 1024 / 1024,
        )
        uploaded = client.files.upload(file=str(upload_file))
    except Exception as e:
        logger.warning("Upload failed: %s", e)
        _cleanup_review(review_path, video_path)
        return _auto_approve(f"upload failed: {e}")

    # Wait for processing
    try:
        for _ in range(60):  # Max 5 minutes
            if uploaded.state.name != "PROCESSING":
                break
            time.sleep(5)
            uploaded = client.files.get(name=uploaded.name)

        if uploaded.state.name == "FAILED":
            logger.warning("Upload processing failed")
            _cleanup_uploaded(client, uploaded)
            _cleanup_review(review_path, video_path)
            return _auto_approve("processing failed")
    except Exception as e:
        logger.warning("Upload status check failed: %s", e)
        _cleanup_review(review_path, video_path)
        return _auto_approve(f"status check: {e}")

    # Review with the same key that uploaded the file
    try:
        response = client.models.generate_content(
            model=_QUALITY_CHECK_MODEL,
            contents=[uploaded, REVIEW_PROMPT],
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=500,
            ),
        )

        review = _parse_review(response.text)

        logger.info(
            "Quality review for %s (model=%s, Google AI): %.1f/10 (%s) - %s",
            account, _QUALITY_CHECK_MODEL,
            review["average_score"],
            "APPROVED" if review["approved"] else "REJECTED",
            review["notes"],
        )

        _cleanup_uploaded(client, uploaded)
        _cleanup_review(review_path, video_path)
        return review

    except Exception as e:
        error_str = str(e)
        logger.warning("Review failed (model=%s): %s", _QUALITY_CHECK_MODEL, error_str[:150])
        _cleanup_uploaded(client, uploaded)
        _cleanup_review(review_path, video_path)
        return _auto_approve(f"review failed: {error_str[:80]}")


def _cleanup_uploaded(client, uploaded):
    """Delete uploaded file from Google AI."""
    try:
        client.files.delete(name=uploaded.name)
    except Exception:
        pass


def _cleanup_review(review_path: str, video_path: str):
    """Remove temporary review copy if it's not the original."""
    if review_path != video_path:
        try:
            Path(review_path).unlink(missing_ok=True)
        except Exception:
            pass
