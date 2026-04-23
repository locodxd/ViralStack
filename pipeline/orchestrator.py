import json
import logging
import asyncio
from datetime import datetime
from core.db import get_session
from core.models import Video, PipelineRun
from core import discord_alerts, audit
from config.settings import settings, is_platform_enabled
from pipeline import script_gen, video_gen, tts, subtitles, compositor, quality_check
from pipeline import drive_upload, tiktok_publish, youtube_publish

logger = logging.getLogger(__name__)


def _log_step(video_id: int, step: str, status: str, started: datetime,
              error: str = None, metadata: dict = None):
    """Log a pipeline step execution."""
    completed = datetime.utcnow()
    duration_ms = int((completed - started).total_seconds() * 1000)

    with get_session() as session:
        run = PipelineRun(
            video_id=video_id,
            step=step,
            status=status,
            started_at=started,
            completed_at=completed,
            duration_ms=duration_ms,
            error_message=error,
            metadata_json=json.dumps(metadata) if metadata else None,
        )
        session.add(run)


def _update_video(video_id: int, **kwargs):
    """Update video record fields."""
    with get_session() as session:
        video = session.query(Video).filter_by(id=video_id).first()
        if video:
            for key, value in kwargs.items():
                setattr(video, key, value)


async def _publish_tiktok(video_id: int, final_path: str, title: str,
                          account: str, hashtags: list) -> str:
    """Publish to TikTok. Returns URL or empty string."""
    step_start = datetime.utcnow()
    try:
        tiktok_url = await tiktok_publish.publish_to_tiktok(
            final_path, title, account, hashtags,
        )
        _update_video(video_id, tiktok_url=tiktok_url, tiktok_published=True)
        _log_step(video_id, "tiktok_publish", "success", step_start)
        return tiktok_url
    except Exception as e:
        logger.error("TikTok publish failed for %s: %s", account, e)
        _log_step(video_id, "tiktok_publish", "failed", step_start, str(e))
        discord_alerts.send_error(
            f"TikTok publish fallo: {e}", exception=e, account=account,
        )
        return ""


async def _publish_youtube(video_id: int, final_path: str, title: str,
                           account: str, hashtags: list) -> str:
    """Publish to YouTube Shorts. Returns URL or empty string."""
    step_start = datetime.utcnow()
    try:
        youtube_url = await youtube_publish.publish_to_youtube(
            final_path, title, account, hashtags=hashtags,
        )
        _update_video(video_id, youtube_url=youtube_url, youtube_published=True)
        _log_step(video_id, "youtube_publish", "success", step_start)
        return youtube_url
    except Exception as e:
        logger.error("YouTube publish failed for %s: %s", account, e)
        _log_step(video_id, "youtube_publish", "failed", step_start, str(e))
        discord_alerts.send_error(
            f"YouTube Shorts publish fallo: {e}", exception=e, account=account,
        )
        return ""


async def produce_video(account: str):
    """Run the complete video production pipeline for an account.

    Wraps `_produce_video_inner` with a hard timeout so a hung step
    can never block the scheduler forever.
    """
    timeout = max(60, settings.pipeline_timeout_seconds)
    try:
        await asyncio.wait_for(_produce_video_inner(account), timeout=timeout)
    except asyncio.TimeoutError:
        msg = f"Pipeline timeout ({timeout}s) for {account}"
        logger.error(msg)
        discord_alerts.send_urgent(msg, account=account)
        audit.record("pipeline_timeout", actor="scheduler", target=account,
                     details={"timeout_seconds": timeout})


async def _produce_video_inner(account: str):
    """Real pipeline body — produces ONE video and publishes it everywhere."""
    logger.info("=" * 60)
    logger.info("Starting video production for account: %s", account)
    logger.info("=" * 60)

    # Notify Discord that production is starting
    discord_alerts.send_info(
        f"Iniciando producción de video...\n"
        f"Cuenta: **{account.upper()}**",
        account=account,
    )

    # Check which platforms are enabled for this account
    tiktok_on = is_platform_enabled(account, "tiktok")
    youtube_on = is_platform_enabled(account, "youtube")

    if not tiktok_on and not youtube_on:
        logger.warning("All platforms disabled for %s, skipping", account)
        discord_alerts.send_warning(
            f"Todas las plataformas deshabilitadas para {account}, saltando.",
            account=account,
        )
        return

    platforms_str = []
    if tiktok_on:
        platforms_str.append("TikTok")
    if youtube_on:
        platforms_str.append("YouTube")
    logger.info("Target platforms: %s", " + ".join(platforms_str))

    # Create video record
    with get_session() as session:
        video = Video(
            account=account,
            status="pending",
            tiktok_enabled=tiktok_on,
            youtube_enabled=youtube_on,
        )
        session.add(video)
        session.flush()
        video_id = video.id

    max_retries = settings.max_retries_per_video
    quality_threshold = settings.quality_threshold_for(account)
    audit.record("pipeline_start", actor="scheduler", target=account,
                 details={"video_id": video_id, "tiktok": tiktok_on, "youtube": youtube_on})

    for attempt in range(1, max_retries + 1):
        # `step_start` is referenced in the broad `except` below — initialise
        # it now so we never raise NameError when the very first step fails.
        step_start = datetime.utcnow()
        if attempt > 1:
            logger.info("Retry attempt %d/%d for %s", attempt, max_retries, account)
            _update_video(video_id, retry_count=attempt - 1)

        try:
            # Step 1: Generate script
            step_start = datetime.utcnow()
            _update_video(video_id, status="scripting")

            script = await script_gen.generate_script(account)

            _update_video(
                video_id,
                title=script["title"],
                script_text=script["script_text"],
                hook=script["hook"],
                visual_prompts=json.dumps(script["visual_prompts"]),
                hashtags=json.dumps(script.get("hashtags", [])),
                estimated_duration=script.get("estimated_duration", 60),
            )
            _log_step(video_id, "script_gen", "success", step_start)

            discord_alerts.send_info(
                f"Guión generado: **{script['title']}**\n"
                f"Duración estimada: {script.get('estimated_duration', 60)}s\n"
                f"Escenas visuales: {len(script.get('visual_prompts', []))}",
                account=account,
            )

            # Step 2: Generate video clips
            step_start = datetime.utcnow()
            _update_video(video_id, status="generating_video")

            clips = await video_gen.generate_video(
                script["visual_prompts"], account, video_id
            )

            if not clips:
                raise RuntimeError(
                    f"No images generated (visual_prompts={len(script.get('visual_prompts', []))}). "
                    f"Check image generation API keys and quota."
                )

            _update_video(video_id, video_clips=json.dumps(clips))
            _log_step(video_id, "video_gen", "success", step_start)

            # Step 3: Generate TTS narration
            step_start = datetime.utcnow()
            _update_video(video_id, status="generating_tts")

            narration_path = await tts.generate_tts(
                script["script_text"], account, video_id
            )

            actual_duration = compositor.get_audio_duration(narration_path)
            min_duration = settings.min_video_seconds
            max_duration = settings.max_video_seconds
            if not (min_duration <= actual_duration <= max_duration):
                raise RuntimeError(
                    f"Narration duration out of range: {actual_duration:.1f}s "
                    f"(expected {min_duration}-{max_duration}s)"
                )

            _update_video(
                video_id,
                narration_path=narration_path,
                estimated_duration=actual_duration,
            )
            _log_step(video_id, "tts", "success", step_start)

            # Step 4: Generate subtitles
            step_start = datetime.utcnow()
            _update_video(video_id, status="subtitling")

            subtitle_path = subtitles.generate_subtitles(
                narration_path, video_id, account
            )

            _update_video(video_id, subtitle_path=subtitle_path)
            _log_step(video_id, "subtitles", "success", step_start)

            # Step 5: Compose final video
            step_start = datetime.utcnow()
            _update_video(video_id, status="compositing")

            final_path = compositor.compose_video(
                clips, narration_path, subtitle_path, account, video_id
            )

            _update_video(video_id, final_path=final_path)
            _log_step(video_id, "compositor", "success", step_start)

            # Step 6: Quality check
            step_start = datetime.utcnow()
            _update_video(video_id, status="reviewing")

            review = await quality_check.review_video(final_path, account)

            _update_video(
                video_id,
                quality_score=review["average_score"],
                quality_notes=review["notes"],
            )
            _log_step(video_id, "quality_check", "success", step_start,
                       metadata=review)

            # Apply per-account quality threshold (overrides review's default).
            avg_score = review.get("average_score") or 0.0
            if avg_score and avg_score < quality_threshold:
                review["approved"] = False
            if not review["approved"]:
                discord_alerts.send_warning(
                    f"Video rechazado (score: {avg_score:.1f}/{quality_threshold:.1f}): "
                    f"{review['notes']}\nReintentando ({attempt}/{max_retries})...",
                    account=account,
                )
                if attempt < max_retries:
                    continue
                else:
                    _update_video(video_id, status="rejected")
                    discord_alerts.send_error(
                        f"Video rechazado tras {max_retries} intentos. "
                        f"Ultimo score: {review['average_score']:.1f}/10",
                        account=account,
                    )
                    return

            # Step 7: Upload to Google Drive (non-fatal)
            step_start = datetime.utcnow()
            drive_link = "N/A"
            if settings.enable_drive_upload:
                _update_video(video_id, status="uploading_drive")

                try:
                    drive_result = await drive_upload.upload_to_drive(
                        final_path, account, script["title"]
                    )
                    _update_video(
                        video_id,
                        drive_file_id=drive_result["file_id"],
                        drive_url=drive_result["web_link"],
                    )
                    drive_link = drive_result["web_link"]
                    _log_step(video_id, "drive_upload", "success", step_start)
                except Exception as e:
                    logger.error("Drive upload failed (non-fatal): %s", e)
                    _log_step(video_id, "drive_upload", "failed", step_start, str(e))
                    discord_alerts.send_warning(
                        f"Drive upload fallo (continuando): {e}", account=account
                    )
            else:
                _log_step(
                    video_id,
                    "drive_upload",
                    "skipped",
                    step_start,
                    metadata={"reason": "disabled_in_settings"},
                )

            # Step 8: Publish to platforms IN PARALLEL
            step_start = datetime.utcnow()
            _update_video(video_id, status="publishing")

            hashtags = script.get("hashtags", [])
            inter_delay = max(0.0, settings.publish_inter_platform_delay)

            async def _delayed(coro, delay: float):
                if delay > 0:
                    await asyncio.sleep(delay)
                return await coro

            publish_tasks = []
            platform_order = []  # tracks which platform each result corresponds to
            if tiktok_on:
                publish_tasks.append(_delayed(
                    _publish_tiktok(video_id, final_path, script["title"], account, hashtags),
                    delay=0.0,
                ))
                platform_order.append("tiktok")
            if youtube_on:
                publish_tasks.append(_delayed(
                    _publish_youtube(video_id, final_path, script["title"], account, hashtags),
                    delay=inter_delay if tiktok_on else 0.0,
                ))
                platform_order.append("youtube")

            # Run all platform uploads in parallel (with optional stagger between)
            results = await asyncio.gather(*publish_tasks, return_exceptions=True)

            # Determine final status
            tiktok_url = ""
            youtube_url = ""
            any_success = False

            for plat, r in zip(platform_order, results):
                url = r if isinstance(r, str) else ""
                if plat == "tiktok":
                    tiktok_url = url
                elif plat == "youtube":
                    youtube_url = url
                if url:
                    any_success = True

            if any_success:
                _update_video(
                    video_id,
                    status="published",
                    published_at=datetime.utcnow(),
                )
            else:
                _update_video(
                    video_id,
                    status="uploaded_drive_only" if drive_link != "N/A" else "failed",
                    error_message="All platform publishes failed",
                )

            # Build success notification
            parts = [f"Video publicado: '{script['title']}'"]
            parts.append(f"Score: {review['average_score']:.1f}/10")
            if tiktok_on:
                parts.append(f"TikTok: {'OK' if tiktok_url else 'FALLO'}")
            if youtube_on:
                parts.append(f"YouTube: {'OK' if youtube_url else 'FALLO'}")
            parts.append(f"Drive: {drive_link}")

            discord_alerts.send_info("\n".join(parts), account=account)
            audit.record("pipeline_published", actor="scheduler", target=account, details={
                "video_id": video_id,
                "score": avg_score,
                "tiktok": bool(tiktok_url),
                "youtube": bool(youtube_url),
            })

            logger.info(
                "Video %d pipeline complete for %s: %s [TT=%s YT=%s]",
                video_id, account, script["title"],
                "OK" if tiktok_url else "SKIP/FAIL",
                "OK" if youtube_url else "SKIP/FAIL",
            )
            return

        except Exception as e:
            logger.error("Pipeline error for %s (attempt %d): %s", account, attempt, e)
            _update_video(video_id, status="failed", error_message=str(e))
            _log_step(video_id, "pipeline", "failed", step_start, str(e))

            discord_alerts.send_error(
                f"Pipeline fallo (attempt {attempt}/{max_retries}): {e}",
                exception=e,
                account=account,
            )

            if attempt >= max_retries:
                discord_alerts.send_urgent(
                    f"Video fallo tras {max_retries} intentos para {account}: {e}",
                    account=account,
                )
                return
