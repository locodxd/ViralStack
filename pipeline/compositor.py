"""
Video compositor: combines images + narration + subtitles + music into final video.

Features:
- Ken Burns effect (zoom/pan animation) on each image — fixed 5.5-second cadence
- Horror filters for terror account (desaturation, vignette, grain, color grade)
- Background music mixing at low volume under narration
- Styled subtitle burning
- Each image is unique (no looping) — aligned to script chronologically
- Compressed output optimized for TikTok/YouTube Shorts
- Lightweight review copy for Gemini quality check
"""
import logging
import json
import math
import os
import random
import shutil
import subprocess
from pathlib import Path
from config.settings import settings

logger = logging.getLogger(__name__)

# Ken Burns effect parameters
_ZOOM_RANGE = (1.0, 1.15)
_PAN_PIXELS = 40

# CRF values — higher = smaller file, lower quality
_CRF_INTERMEDIATE = 28   # Ken Burns clips (throwaway, just need to look OK)
_CRF_FINAL = settings.video_crf  # Final published video (quality from settings)
_CRF_REVIEW = 35         # Compressed copy for Gemini quality check (~5-15 MB)
_REVIEW_SCALE = "540:960" # Half resolution for review


def _get_final_preset() -> str:
    """Prefer slower preset for smaller definitive output at same visual quality."""
    preset = (settings.video_preset or "medium").lower()
    if preset in {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium"}:
        return "slow"
    return preset


def _get_ffmpeg_path() -> str:
    """Get FFmpeg binary path."""
    custom = settings.ffmpeg_path
    if custom and custom != "ffmpeg":
        p = Path(custom)
        if p.exists():
            return str(p)
        p2 = Path(custom.replace("/", os.sep))
        if p2.exists():
            return str(p2)
    found = shutil.which("ffmpeg")
    if found:
        return found
    return "ffmpeg"


def _get_ffprobe_path() -> str:
    """Get FFprobe binary path (derived from FFmpeg path)."""
    ffmpeg = _get_ffmpeg_path()
    ffmpeg_path = Path(ffmpeg)
    return str(ffmpeg_path.parent / ffmpeg_path.name.replace("ffmpeg", "ffprobe"))


def _get_random_music(account: str) -> str | None:
    """Pick a random royalty-free music track for the account."""
    music_dir = Path(settings.db_path).parent.parent / "music" / "royalty_free" / account
    if not music_dir.exists():
        return None

    tracks = list(music_dir.glob("*.mp3")) + list(music_dir.glob("*.wav"))
    if not tracks:
        return None

    return str(random.choice(tracks))


def get_audio_duration(audio_path: str) -> float:
    """Get duration of audio file in seconds using ffprobe."""
    ffprobe = _get_ffprobe_path()

    try:
        result = subprocess.run(
            [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", audio_path],
            capture_output=True, text=True, timeout=30
        )
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception as e:
        logger.warning("Could not get audio duration: %s", e)
        return 60.0


def _sample_evenly(items: list[str], target_count: int) -> list[str]:
    """Trim an oversized sequence while preserving chronology across the whole video."""
    if target_count <= 0 or len(items) <= target_count:
        return list(items)
    if target_count == 1:
        return [items[-1]]

    last_index = len(items) - 1
    indices = [round(i * last_index / (target_count - 1)) for i in range(target_count)]
    return [items[idx] for idx in indices]


def _normalize_image_sequence(image_paths: list[str], narration_duration: float) -> list[str]:
    """Force the timeline to a 5.5-second cadence by trimming or padding images."""
    if not image_paths:
        return []

    target_count = max(1, math.ceil(narration_duration / settings.image_display_seconds))

    if len(image_paths) == target_count:
        return list(image_paths)

    if len(image_paths) > target_count:
        normalized = _sample_evenly(image_paths, target_count)
        logger.info(
            "Trimmed image sequence from %d to %d to match %.1fs cadence",
            len(image_paths), target_count, settings.image_display_seconds,
        )
        return normalized

    normalized = list(image_paths)
    while len(normalized) < target_count:
        normalized.append(normalized[-1])
    logger.info(
        "Padded image sequence from %d to %d to cover %.1fs cadence",
        len(image_paths), target_count, settings.image_display_seconds,
    )
    return normalized


def _build_ken_burns_filter(image_index: int, w: int, h: int, duration: float) -> str:
    """Build FFmpeg filter for Ken Burns (zoom + pan) animation on a single image."""
    random.seed(image_index * 42)

    zoom_in = random.choice([True, False])
    pan_dir = random.choice(["up", "down", "left", "right", "up-left", "down-right"])

    if zoom_in:
        zoom_start = 1.0
        zoom_end = random.uniform(1.08, 1.15)
    else:
        zoom_start = random.uniform(1.08, 1.15)
        zoom_end = 1.0

    fps = 30
    total_frames = int(duration * fps)

    z_expr = f"{zoom_start}+({zoom_end}-{zoom_start})*on/{total_frames}"

    max_pan = _PAN_PIXELS
    cx = "iw/2-(iw/zoom/2)"
    cy = "ih/2-(ih/zoom/2)"
    t = f"on/{total_frames}"

    if pan_dir == "up":
        x_expr = f"max(0\\,{cx})"
        y_expr = f"max(0\\,{cy}-{max_pan}*{t})"
    elif pan_dir == "down":
        x_expr = f"max(0\\,{cx})"
        y_expr = f"max(0\\,{cy}+{max_pan}*{t})"
    elif pan_dir == "left":
        x_expr = f"max(0\\,{cx}-{max_pan}*{t})"
        y_expr = f"max(0\\,{cy})"
    elif pan_dir == "right":
        x_expr = f"max(0\\,{cx}+{max_pan}*{t})"
        y_expr = f"max(0\\,{cy})"
    elif pan_dir == "up-left":
        x_expr = f"max(0\\,{cx}-{max_pan // 2}*{t})"
        y_expr = f"max(0\\,{cy}-{max_pan // 2}*{t})"
    else:  # down-right
        x_expr = f"max(0\\,{cx}+{max_pan // 2}*{t})"
        y_expr = f"max(0\\,{cy}+{max_pan // 2}*{t})"

    return (
        f"zoompan=z='{z_expr}':"
        f"x='{x_expr}':y='{y_expr}':"
        f"d={total_frames}:s={w}x{h}:fps={fps}"
    )


def _build_horror_filter() -> str:
    """Build FFmpeg filter chain for horror visual effect."""
    return (
        "eq=saturation=0.3:contrast=1.3:brightness=-0.05,"
        "colorbalance=rs=-0.15:gs=0.05:bs=0.15:rm=-0.1:gm=0.03:bm=0.1,"
        "vignette=PI/4,"
        "noise=alls=15:allf=t"
    )


def _calculate_image_duration() -> float:
    """Use a fixed image cadence across the entire pipeline."""
    return settings.image_display_seconds


def _build_subtitle_style() -> str:
    """Centralize ASS subtitle styling so size and positioning stay readable."""
    font_size = max(
        settings.subtitle_font_size,
        round(settings.video_height * settings.subtitle_font_scale),
    )
    outline = max(
        settings.subtitle_outline,
        round(font_size * settings.subtitle_outline_scale),
    )
    margin_v = max(
        settings.subtitle_margin_v,
        round(settings.video_height * settings.subtitle_margin_v_ratio),
    )
    margin_h = max(
        settings.subtitle_margin_h,
        round(settings.video_width * settings.subtitle_margin_h_ratio),
    )

    return (
        f"PlayResX={settings.video_width},"
        f"PlayResY={settings.video_height},"
        f"FontName={settings.subtitle_font_name},"
        f"FontSize={font_size},"
        "Bold=1,"
        "PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00101010,"
        "BackColour=&H00000000,"
        "BorderStyle=1,"
        f"Outline={outline},"
        f"Shadow={settings.subtitle_shadow},"
        "Alignment=2,"
        f"MarginL={margin_h},"
        f"MarginR={margin_h},"
        f"MarginV={margin_v},"
        "WrapStyle=2"
    )


def compose_video(
    image_paths: list,
    narration_path: str,
    subtitle_path: str,
    account: str,
    video_id: int,
) -> str:
    """Combine images + narration + subtitles + music into final video.

    Each image is unique and shown once — no looping.
    Duration per image adjusts to fill the narration evenly.
    Horror filter applied for terror account.

    Returns path to the final composed video.
    """
    ffmpeg = _get_ffmpeg_path()
    output_dir = Path(narration_path).parent
    final_path = output_dir / "final.mp4"

    narration_duration = get_audio_duration(narration_path)
    music_path = _get_random_music(account)
    if music_path:
        logger.info("Background music selected: %s", Path(music_path).name)
    else:
        logger.warning("No background music found for account '%s'", account)
    w, h = settings.video_width, settings.video_height

    image_paths = _normalize_image_sequence(image_paths, narration_duration)
    if not image_paths:
        raise RuntimeError("No images available to compose the video")

    # Calculate per-image duration that compensates for crossfade time loss.
    # With xfade, total = n * d - (n-1) * xfade.  We need total >= narration.
    # So d = (narration + (n-1) * xfade) / n, plus a small buffer.
    xfade_duration = 0.3
    n_clips = len(image_paths)
    xfade_loss = (n_clips - 1) * xfade_duration if n_clips > 1 else 0
    image_duration = (narration_duration + xfade_loss + 1.0) / n_clips  # +1s safety buffer

    effective_timeline = n_clips * image_duration - xfade_loss
    logger.info(
        "Compositing: %d images x %.2fs each = %.1fs effective timeline (narration: %.1fs, xfade loss: %.1fs)",
        n_clips, image_duration, effective_timeline, narration_duration, xfade_loss,
    )

    # Step 1: Create animated clips from each image with Ken Burns
    animated_clips = []
    for i, img_path in enumerate(image_paths):
        clip_path = output_dir / f"animated_{i:03d}.mp4"

        kb_filter = _build_ken_burns_filter(i, w, h, image_duration)

        if account == "terror":
            horror = _build_horror_filter()
            filter_chain = f"{kb_filter},{horror}"
        else:
            filter_chain = kb_filter

        cmd = [
            ffmpeg, "-y",
            "-loop", "1",
            "-i", img_path,
            "-vf", filter_chain,
            "-t", str(image_duration),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", str(_CRF_INTERMEDIATE),
            "-pix_fmt", "yuv420p",
            "-an",
            str(clip_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            logger.error("Ken Burns failed for image %d: %s", i, result.stderr[-300:])
            cmd_simple = [
                ffmpeg, "-y",
                "-loop", "1", "-i", img_path,
                "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black",
                "-t", str(image_duration),
                "-c:v", "libx264", "-preset", "fast", "-crf", str(_CRF_INTERMEDIATE),
                "-pix_fmt", "yuv420p", "-an",
                str(clip_path),
            ]
            subprocess.run(cmd_simple, capture_output=True, timeout=60, check=True)

        animated_clips.append(str(clip_path))

    # Step 2: Concatenate all animated clips
    concat_path = output_dir / "concat.mp4"

    if len(animated_clips) <= 1:
        shutil.copy2(animated_clips[0], str(concat_path))
    elif len(animated_clips) <= 10:
        # Use xfade filter for smooth crossfade transitions
        inputs = []
        for clip in animated_clips:
            inputs.extend(["-i", clip])

        filter_parts = []
        prev_label = "0:v"
        for i in range(1, len(animated_clips)):
            offset = round(image_duration * i - xfade_duration * i, 3)
            out_label = f"v{i}"
            filter_parts.append(
                f"[{prev_label}][{i}:v]xfade=transition=fade:duration={xfade_duration}:offset={offset}[{out_label}]"
            )
            prev_label = out_label

        filter_str = ";".join(filter_parts)
        cmd = [
            ffmpeg, "-y", *inputs,
            "-filter_complex", filter_str,
            "-map", f"[{prev_label}]",
            "-c:v", "libx264", "-preset", "fast", "-crf", str(_CRF_INTERMEDIATE),
            "-pix_fmt", "yuv420p", "-an",
            str(concat_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            logger.warning("Crossfade failed, falling back to simple concat: %s", result.stderr[-200:])
            _simple_concat(ffmpeg, animated_clips, concat_path)
    else:
        # Too many clips for xfade — simple concat
        _simple_concat(ffmpeg, animated_clips, concat_path)

    logger.info("Concatenated %d animated clips", len(animated_clips))

    # Step 3: Final composition (video + narration + subtitles + music)
    inputs = ["-i", str(concat_path), "-i", narration_path]
    filter_parts = []

    # Trim video to exact narration duration
    filter_parts.append(
        f"[0:v]trim=duration={narration_duration},setpts=PTS-STARTPTS[video]"
    )

    # Burn subtitles — clean outline style, no black box
    subtitle_escaped = str(Path(subtitle_path).resolve().as_posix()).replace(":", "\\:")
    filter_parts.append(
        f"[video]subtitles='{subtitle_escaped}':"
        f"force_style='{_build_subtitle_style()}'[subtitled]"
    )

    if music_path and Path(music_path).exists():
        inputs.extend(["-i", music_path])
        filter_parts.append(
            f"[1:a]volume=1.3[narr];"
            f"[2:a]volume=0.05,atrim=duration={narration_duration},asetpts=PTS-STARTPTS[bgm];"
            f"[narr][bgm]amix=inputs=2:duration=first:dropout_transition=3[audio]"
        )
        audio_map = "[audio]"
    else:
        audio_map = "1:a"

    filter_complex = ";".join(filter_parts)

    cmd = [
        ffmpeg, "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[subtitled]",
        "-map", audio_map,
        "-c:v", "libx264",
        "-preset", _get_final_preset(),
        "-crf", str(_CRF_FINAL),
        "-profile:v", "high",
        "-level", "4.1",
        "-c:a", "aac",
        "-b:a", settings.video_bitrate_audio,
        "-ar", "44100",
        "-movflags", "+faststart",
        str(final_path),
    ]

    logger.info("Compositing final video for %s (duration: %.1fs)", account, narration_duration)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        logger.error("FFmpeg error: %s", result.stderr[-1000:] if result.stderr else "no output")
        raise RuntimeError(f"FFmpeg composition failed: {result.stderr[-500:]}")

    # Cleanup intermediate files
    for clip in animated_clips:
        try:
            Path(clip).unlink(missing_ok=True)
        except Exception:
            pass
    for tmp in [concat_path, output_dir / "concat_list.txt"]:
        try:
            Path(tmp).unlink(missing_ok=True)
        except Exception:
            pass

    file_size_mb = final_path.stat().st_size / 1024 / 1024
    logger.info("Final video composed: %s (%.1f MB)", final_path, file_size_mb)
    return str(final_path)


def _simple_concat(ffmpeg: str, clips: list[str], output: Path):
    """Concatenate clips using FFmpeg concat demuxer (no transitions)."""
    concat_list = output.parent / "concat_list.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for clip in clips:
            f.write(f"file '{Path(clip).resolve().as_posix()}'\n")
    cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0",
           "-i", str(concat_list), "-c", "copy", str(output)]
    subprocess.run(cmd, capture_output=True, timeout=120, check=True)


def create_review_copy(video_path: str) -> str:
    """Create a lightweight compressed copy for Gemini quality review.

    If the original is under 50 MB, use it directly.
    Otherwise, reduces to 540x960 at high CRF.

    Returns path to the file to upload for review.
    """
    source = Path(video_path)
    original_size_mb = source.stat().st_size / 1024 / 1024

    # If already small enough, use the original directly
    if original_size_mb <= 50:
        logger.info("Video already small (%.1f MB), using original for review", original_size_mb)
        return video_path

    ffmpeg = _get_ffmpeg_path()
    review_path = source.parent / "review.mp4"

    cmd = [
        ffmpeg, "-y",
        "-i", str(source),
        "-vf", f"scale={_REVIEW_SCALE}",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", str(_CRF_REVIEW),
        "-c:a", "aac",
        "-b:a", "64k",
        "-ar", "22050",
        "-movflags", "+faststart",
        str(review_path),
    ]

    logger.info("Creating review copy: %s (%.1f MB) -> %s", source.name, original_size_mb, review_path.name)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        logger.warning("Review copy failed, using original: %s", result.stderr[-200:])
        return video_path

    review_size_mb = review_path.stat().st_size / 1024 / 1024
    logger.info(
        "Review copy: %.1f MB (original: %.1f MB, %.0f%% reduction)",
        review_size_mb, original_size_mb,
        (1 - review_size_mb / original_size_mb) * 100 if original_size_mb > 0 else 0,
    )

    return str(review_path)
