"""
Image generation using Vertex AI (Imagen 4.0 + Gemini Flash Image).

Strategy:
- Primary: imagen-4.0-fast-generate-001 (best quality while quota lasts)
- Fallback: gemini-2.5-flash-image via Vertex AI
- Reuse recent scene images when external generation fails
- Create a local emergency frame if every remote option is unavailable
"""
import asyncio
import base64
import hashlib
import logging
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from config.settings import settings
from core import discord_alerts

logger = logging.getLogger(__name__)

_IMAGEN_MODEL = "imagen-4.0-fast-generate-001"
_FLASH_IMAGE_MODELS = [
    "gemini-2.5-flash-image",
]
_IMAGEN_DAILY_LIMIT = settings.imagen_daily_limit
_FLASH_IMAGE_ATTEMPTS = 2
_REUSE_POOL_LIMIT = 24
_SUPPORTED_REUSE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

_imagen_daily_count = 0
_imagen_daily_reset = 0.0
_imagen_lock = threading.Lock()

_MINIMAL_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
)

_STYLE_SUFFIXES = {
    "terror": (
        "Dark horror atmosphere, eerie shadows, dim cold lighting, "
        "desaturated colors with blue-green tint, fog, cinematic horror movie style, "
        "high contrast, photorealistic, 9:16 vertical composition"
    ),
    "historias": (
        "Cinematic storytelling atmosphere, warm dramatic lighting, "
        "emotional and immersive, photorealistic, detailed textures, "
        "documentary style, 9:16 vertical composition"
    ),
    "dinero": (
        "Modern professional aesthetic, clean composition, "
        "luxury and success imagery, bright motivational lighting, "
        "business and finance visuals, photorealistic, 9:16 vertical composition"
    ),
}
_STYLE_FALLBACKS = {
    "terror": (
        "Abandoned room, ominous silhouette, eerie shadows, cinematic horror, "
        "photorealistic, vertical 9:16"
    ),
    "historias": (
        "Real-life dramatic moment, emotional storytelling, cinematic, "
        "photorealistic, vertical 9:16"
    ),
    "dinero": (
        "Modern finance success scene, clean composition, cinematic, "
        "photorealistic, vertical 9:16"
    ),
}
_EMERGENCY_COLORS = {
    "terror": "0x11171F",
    "historias": "0x2B211C",
    "dinero": "0x182328",
}


def _get_cache_dir() -> Path:
    return Path(settings.db_path).parent / "image_cache"


def _get_output_root() -> Path:
    return Path(settings.db_path).parent / "output"


def _get_cache_key(prompt: str, account: str) -> str:
    """Generate a cache key from prompt + account."""
    content = f"{account}:{prompt}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _check_cache(cache_key: str) -> Path | None:
    """Check if a cached image exists."""
    cached = _get_cache_dir() / f"{cache_key}.png"
    if cached.exists():
        logger.info("Image cache HIT: %s", cache_key)
        return cached
    return None


def _save_to_cache(cache_key: str, image_bytes: bytes) -> Path:
    """Save image bytes to cache."""
    cache_dir = _get_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / f"{cache_key}.png"
    cached.write_bytes(image_bytes)
    logger.info("Image cached: %s (%d bytes)", cache_key, len(image_bytes))
    return cached


def _get_recent_cached_images(limit: int = _REUSE_POOL_LIMIT) -> list[Path]:
    """Return recent cached images ordered newest first."""
    cache_dir = _get_cache_dir()
    if not cache_dir.exists():
        return []

    cached_images = sorted(
        cache_dir.glob("*.png"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return cached_images[:limit]


def _get_recent_cached_image() -> Path | None:
    """Best-effort fallback when generation is fully unavailable for a scene."""
    recent = _get_recent_cached_images(limit=1)
    return recent[0] if recent else None


def _check_imagen_quota() -> bool:
    """Check if we still have Imagen 4.0 quota for today."""
    global _imagen_daily_count, _imagen_daily_reset

    with _imagen_lock:
        now = time.time()
        if now - _imagen_daily_reset > 86400:
            _imagen_daily_count = 0
            _imagen_daily_reset = now

        return _imagen_daily_count < _IMAGEN_DAILY_LIMIT


def _is_quota_exhausted_error(error: Exception) -> bool:
    """Detect when Imagen is depleted so we stop retrying it for every scene."""
    message = str(error).lower()
    return any(
        token in message
        for token in (
            "resource_exhausted",
            "quota exceeded",
            "predictrequestsperday",
            "429",
        )
    )


def _disable_imagen_for_today(error: Exception):
    """Mark Imagen unavailable until the next daily reset window."""
    global _imagen_daily_count, _imagen_daily_reset

    with _imagen_lock:
        now = time.time()
        if not _imagen_daily_reset or now - _imagen_daily_reset > 86400:
            _imagen_daily_reset = now
        _imagen_daily_count = _IMAGEN_DAILY_LIMIT

    logger.warning("Imagen disabled for the rest of the day: %s", error)


def _increment_imagen_count():
    """Increment the daily Imagen usage counter."""
    global _imagen_daily_count
    with _imagen_lock:
        _imagen_daily_count += 1
        logger.info("Imagen daily usage: %d/%d", _imagen_daily_count, _IMAGEN_DAILY_LIMIT)


async def _generate_image_imagen(prompt: str) -> bytes:
    """Generate image using Imagen 4.0 Fast via Vertex AI."""
    from google.genai import types
    from core.vertex_client import get_client

    client = get_client()

    response = await asyncio.to_thread(
        client.models.generate_images,
        model=_IMAGEN_MODEL,
        prompt=prompt,
        config=types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio="9:16",
        ),
    )

    if not response.generated_images:
        raise RuntimeError("Imagen returned no images")

    image = response.generated_images[0]
    _increment_imagen_count()
    return image.image.image_bytes


def _extract_image_bytes(response) -> bytes | None:
    """Extract raw image bytes from a Gemini Flash Image response."""
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            inline_data = getattr(part, "inline_data", None)
            mime_type = getattr(inline_data, "mime_type", "") if inline_data else ""
            data = getattr(inline_data, "data", None) if inline_data else None
            if data and mime_type.startswith("image/"):
                return bytes(data)
    return None


def _extract_response_text(response) -> str:
    """Best-effort text extraction for debugging empty Flash responses."""
    snippets = []
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            text = getattr(part, "text", None)
            if text:
                snippets.append(text.strip())
    return " ".join(snippets).strip()


async def _generate_image_flash(prompt: str) -> bytes:
    """Generate image using Gemini Flash Image via Vertex AI."""
    from google.genai import types
    from core.vertex_client import get_client

    client = get_client()

    last_error = None
    for model_name in _FLASH_IMAGE_MODELS:
        for attempt in range(1, _FLASH_IMAGE_ATTEMPTS + 1):
            try:
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE", "TEXT"],
                        temperature=1.0,
                    ),
                )

                image_bytes = _extract_image_bytes(response)
                if image_bytes:
                    return image_bytes

                response_text = _extract_response_text(response)
                message = f"Model {model_name} returned no image data"
                if response_text:
                    message = f"{message}: {response_text[:160]}"
                last_error = RuntimeError(message)
                logger.warning(
                    "Flash image model returned no image (%s, attempt %d/%d)",
                    model_name,
                    attempt,
                    _FLASH_IMAGE_ATTEMPTS,
                )
            except Exception as error:
                last_error = error
                logger.warning(
                    "Flash image model failed (%s, attempt %d/%d): %s",
                    model_name,
                    attempt,
                    _FLASH_IMAGE_ATTEMPTS,
                    error,
                )

            if attempt < _FLASH_IMAGE_ATTEMPTS:
                await asyncio.sleep(0.5 * attempt)

    raise RuntimeError(f"All Flash image models failed: {last_error}")


def _clean_visual_prompt(prompt: str) -> str:
    """Remove text-overlay cues so generated frames stay text-free."""
    text = (prompt or "").strip()
    if not text:
        return text

    text = re.sub(r'"[^"\n]{1,40}"', "", text)
    text = re.sub(
        r"\b(subtitulos?|subtitles?|captions?|texto en pantalla|text overlay|watermark|logo)\b",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+", " ", text).strip(" ,.-")
    return text or prompt


def _truncate_words(text: str, max_words: int) -> str:
    """Trim prompt verbosity for fallback retries."""
    words = text.split()
    return " ".join(words[:max_words]).strip()


def _build_prompt_variants(prompt: str, account: str) -> list[str]:
    """Generate progressively simpler prompts for Flash fallback."""
    cleaned_prompt = _clean_visual_prompt(prompt) or _STYLE_FALLBACKS.get(
        account,
        "Photorealistic cinematic vertical scene",
    )
    no_text_guard = (
        "No visible text, no subtitles, no captions, no letters, no words, "
        "no watermarks, no logos."
    )

    first_clause = re.split(r"[.;:]", cleaned_prompt, maxsplit=1)[0].strip()
    concise_clause = _truncate_words(first_clause or cleaned_prompt, 26)
    broad_clause = _truncate_words(cleaned_prompt, 18)
    fallback_style = _STYLE_FALLBACKS.get(account, "Photorealistic cinematic vertical scene")

    candidates = [
        f"{cleaned_prompt}. {_STYLE_SUFFIXES.get(account, '')}. {no_text_guard}",
        f"{concise_clause}. {fallback_style}. {no_text_guard}",
        f"{broad_clause}. {fallback_style}. {no_text_guard}",
        f"{fallback_style}. {no_text_guard}",
    ]

    variants = []
    seen = set()
    for candidate in candidates:
        normalized = re.sub(r"\s+", " ", candidate).strip(" ,.-")
        if not normalized:
            continue
        normalized = _truncate_words(normalized, 60)
        dedupe_key = normalized.lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        variants.append(normalized)
    return variants


def _get_ffmpeg_path() -> str:
    """Resolve FFmpeg for emergency local frame creation."""
    custom = settings.ffmpeg_path
    if custom and custom != "ffmpeg":
        candidate = Path(custom)
        if candidate.exists():
            return str(candidate)
    return shutil.which("ffmpeg") or "ffmpeg"


def _get_recent_output_images(
    account: str,
    output_dir: Path,
    limit: int = _REUSE_POOL_LIMIT,
) -> list[Path]:
    """Collect recent scene images from previous runs of the same account."""
    account_dir = _get_output_root() / account
    if not account_dir.exists():
        return []

    current_output = output_dir.resolve()
    candidates = []
    for path in account_dir.rglob("scene_*"):
        if path.suffix.lower() not in _SUPPORTED_REUSE_EXTENSIONS:
            continue
        try:
            if current_output in path.resolve().parents:
                continue
            candidates.append(path)
        except OSError:
            continue

    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[:limit]


def _build_reuse_pool(account: str, output_dir: Path) -> list[Path]:
    """Build a pool of reusable images so generation failures never halt the run."""
    pool = []
    seen = set()

    for candidate in _get_recent_output_images(account, output_dir):
        resolved = str(candidate.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        pool.append(candidate)

    for candidate in _get_recent_cached_images():
        resolved = str(candidate.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        pool.append(candidate)

    return pool[:_REUSE_POOL_LIMIT]


def _copy_reused_image(source: Path, output_dir: Path, index: int) -> str:
    """Copy a reusable image into the current output directory."""
    suffix = source.suffix if source.suffix.lower() in _SUPPORTED_REUSE_EXTENSIONS else ".png"
    fallback_path = output_dir / f"scene_{index:03d}{suffix}"
    shutil.copy2(source, fallback_path)
    return str(fallback_path)


def _create_emergency_frame(output_dir: Path, account: str, index: int) -> str:
    """Create a local frame when every external image source is unavailable."""
    fallback_path = output_dir / f"scene_{index:03d}_emergency.png"
    ffmpeg = _get_ffmpeg_path()
    color = _EMERGENCY_COLORS.get(account, "0x1C1C1C")

    try:
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s={settings.video_width}x{settings.video_height}",
            "-frames:v",
            "1",
            str(fallback_path),
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)
        logger.warning("Scene %d replaced with local emergency frame", index)
        return str(fallback_path)
    except Exception as error:
        logger.warning("Emergency FFmpeg frame failed for scene %d: %s", index, error)

    fallback_path.write_bytes(_MINIMAL_PNG_BYTES)
    logger.warning("Scene %d replaced with embedded emergency pixel fallback", index)
    return str(fallback_path)


def _recover_scene_from_failure(
    account: str,
    index: int,
    output_dir: Path,
    image_paths: list[str],
    reuse_pool: list[Path],
) -> str:
    """Recover a failed scene without aborting the whole video."""
    if image_paths:
        previous = Path(image_paths[-1])
        if previous.exists():
            fallback = _copy_reused_image(previous, output_dir, index)
            logger.warning("Scene %d replaced with previous frame fallback", index)
            return fallback

    for offset in range(len(reuse_pool)):
        candidate = reuse_pool[(index + offset) % len(reuse_pool)]
        if not candidate.exists():
            continue
        fallback = _copy_reused_image(candidate, output_dir, index)
        logger.warning("Scene %d replaced with historical image fallback: %s", index, candidate)
        return fallback

    cached = _get_recent_cached_image()
    if cached and cached.exists():
        fallback = _copy_reused_image(cached, output_dir, index)
        logger.warning("Scene %d replaced with recent cache fallback", index)
        return fallback

    return _create_emergency_frame(output_dir, account, index)


async def _generate_single_image(
    prompt: str,
    account: str,
    index: int,
    output_dir: Path,
) -> str:
    """Generate a single image with caching, retries, and model fallback."""
    prompt_variants = _build_prompt_variants(prompt, account)
    enhanced_prompt = prompt_variants[0]

    cache_key = _get_cache_key(enhanced_prompt, account)
    cached = _check_cache(cache_key)
    if cached:
        output_path = output_dir / f"scene_{index:03d}.png"
        output_path.write_bytes(cached.read_bytes())
        return str(output_path)

    image_bytes = None

    # Try Imagen 4.0 first
    if _check_imagen_quota():
        try:
            logger.info("Generating with Imagen 4.0 (Vertex AI): scene %d", index)
            image_bytes = await _generate_image_imagen(enhanced_prompt)
            logger.info("Imagen 4.0 success for scene %d", index)
        except Exception as error:
            if _is_quota_exhausted_error(error):
                _disable_imagen_for_today(error)
            logger.warning("Imagen 4.0 failed for scene %d: %s", index, error)

    # Fallback to Flash Image
    if image_bytes is None:
        last_error = None

        for variant_index, prompt_variant in enumerate(prompt_variants, start=1):
            try:
                logger.info(
                    "Generating with Flash Image fallback (variant %d/%d, Vertex AI): scene %d",
                    variant_index,
                    len(prompt_variants),
                    index,
                )
                image_bytes = await _generate_image_flash(prompt_variant)
                logger.info(
                    "Flash Image success for scene %d (variant %d)",
                    index,
                    variant_index,
                )
                break
            except Exception as error:
                last_error = error
                logger.warning(
                    "Flash Image failed for scene %d with variant %d: %s",
                    index,
                    variant_index,
                    error,
                )

        if image_bytes is None:
            logger.error("All image generation failed for scene %d", index)
            raise RuntimeError(f"All image generation failed for scene {index}: {last_error}")

    output_path = output_dir / f"scene_{index:03d}.png"
    output_path.write_bytes(image_bytes)
    _save_to_cache(cache_key, image_bytes)
    return str(output_path)


async def generate_video(visual_prompts: list, account: str, video_id: int) -> list:
    """Generate images from visual prompts using Vertex AI image models."""
    output_dir = _get_output_root() / account / str(video_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    prompts = list(visual_prompts or [])
    if not prompts:
        prompts = [_STYLE_FALLBACKS.get(account, "Photorealistic cinematic vertical scene")]
        logger.warning(
            "No visual prompts received for %s video %d, using generic fallback scene",
            account,
            video_id,
        )

    reuse_pool = _build_reuse_pool(account, output_dir)

    discord_alerts.send_info(
        f"Generando {len(prompts)} imagenes para video #{video_id}...\n"
        f"Imagen quota: {_imagen_daily_count}/{_IMAGEN_DAILY_LIMIT}",
        account=account,
    )

    image_paths = []
    for index, prompt in enumerate(prompts):
        logger.info(
            "Generating image %d/%d for %s: %s",
            index + 1,
            len(prompts),
            account,
            prompt[:80],
        )

        try:
            path = await _generate_single_image(prompt, account, index, output_dir)
        except Exception as error:
            logger.error("Failed to generate image %d: %s", index, error)
            path = _recover_scene_from_failure(
                account,
                index,
                output_dir,
                image_paths,
                reuse_pool,
            )

        image_paths.append(path)
        reuse_pool.insert(0, Path(path))
        reuse_pool = reuse_pool[:_REUSE_POOL_LIMIT]

    if not image_paths:
        image_paths.append(_create_emergency_frame(output_dir, account, 0))

    logger.info("Generated %d images for %s video %d", len(image_paths), account, video_id)
    return image_paths
