import json
import logging
import asyncio
from datetime import datetime
from core.db import get_session
from core.models import Video, PipelineRun
from core import discord_alerts, audit
from config.settings import (
    enabled_platforms_for,
    get_platform_info,
    is_platform_enabled,
    platform_display_name,
    platform_hashtags_for,
    platform_short_name,
    settings,
)
from pipeline import script_gen, video_gen, tts, subtitles, compositor, quality_check
from pipeline import drive_upload, platform_publishers

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


def _load_json_map(value: str | None) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _merge_hashtags(*groups: list | None) -> list[str]:
    seen = set()
    merged = []
    for group in groups:
        for raw in group or []:
            tag = str(raw).strip()
            if not tag:
                continue
            if not tag.startswith("#"):
                tag = f"#{tag}"
            key = tag.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(tag)
    return merged


def _record_platform_result(video_id: int, result: platform_publishers.PublishResult) -> None:
    """Persist a platform result in generic JSON fields and legacy columns."""
    info = get_platform_info(result.platform)
    with get_session() as session:
        video = session.query(Video).filter_by(id=video_id).first()
        if not video:
            return

        results = _load_json_map(video.platform_results_json)
        errors = _load_json_map(video.platform_errors_json)
        results[result.platform] = result.to_dict()
        if result.error:
            errors[result.platform] = result.error
        else:
            errors.pop(result.platform, None)

        video.platform_results_json = json.dumps(results, ensure_ascii=False)
        video.platform_errors_json = json.dumps(errors, ensure_ascii=False) if errors else None

        url_field = info.get("url_field")
        published_field = info.get("published_field")
        if url_field and hasattr(video, url_field):
            setattr(video, url_field, result.url or getattr(video, url_field))
        if published_field and hasattr(video, published_field):
            setattr(video, published_field, bool(result.ok))


async def _publish_platform(
    video_id: int,
    platform: str,
    final_path: str,
    title: str,
    account: str,
    hashtags: list[str],
) -> platform_publishers.PublishResult:
    """Publish to one configured platform and persist/log the result."""
    step_start = datetime.utcnow()
    result = await platform_publishers.publish_to_platform(
        platform,
        final_path,
        title,
        account,
        hashtags=hashtags,
    )
    _record_platform_result(video_id, result)

    if result.ok:
        _log_step(video_id, f"{platform}_publish", "success", step_start, metadata=result.to_dict())
    elif result.skipped:
        _log_step(video_id, f"{platform}_publish", "skipped", step_start, result.error, result.to_dict())
        logger.warning("%s publish skipped for %s: %s", platform_display_name(platform), account, result.error)
    else:
        _log_step(video_id, f"{platform}_publish", "failed", step_start, result.error, result.to_dict())
        discord_alerts.send_error(
            f"{platform_display_name(platform)} publish fallo: {result.error}",
            account=account,
        )

    return result


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
    target_platforms = enabled_platforms_for(account)
    platform_enabled_map = {
        platform: is_platform_enabled(account, platform)
        for platform in target_platforms
    }

    if not target_platforms:
        logger.warning("All platforms disabled for %s, skipping", account)
        discord_alerts.send_warning(
            f"Todas las plataformas deshabilitadas para {account}, saltando.",
            account=account,
        )
        return

    platforms_str = [platform_display_name(platform) for platform in target_platforms]
    logger.info("Target platforms: %s", " + ".join(platforms_str))

    # Create video record
    with get_session() as session:
        video = Video(
            account=account,
            status="pending",
            tiktok_enabled=is_platform_enabled(account, "tiktok"),
            youtube_enabled=is_platform_enabled(account, "youtube"),
            platforms_enabled_json=json.dumps(platform_enabled_map, ensure_ascii=False),
        )
        session.add(video)
        session.flush()
        video_id = video.id

    max_retries = settings.max_retries_per_video
    quality_threshold = settings.quality_threshold_for(account)
    audit.record("pipeline_start", actor="scheduler", target=account,
                 details={"video_id": video_id, "platforms": target_platforms})

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
            if avg_score:
                review["approved"] = avg_score >= quality_threshold
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

            # Step 8: Publish to enabled platforms IN PARALLEL
            step_start = datetime.utcnow()
            _update_video(video_id, status="publishing")

            script_hashtags = script.get("hashtags", [])
            inter_delay = max(0.0, settings.publish_inter_platform_delay)

            async def _delayed(coro, delay: float):
                if delay > 0:
                    await asyncio.sleep(delay)
                return await coro

            publish_tasks = []
            for index, platform in enumerate(target_platforms):
                platform_hashtags = _merge_hashtags(
                    script_hashtags,
                    platform_hashtags_for(account, platform),
                )
                publish_tasks.append(_delayed(
                    _publish_platform(
                        video_id,
                        platform,
                        final_path,
                        script["title"],
                        account,
                        platform_hashtags,
                    ),
                    delay=inter_delay * index,
                ))

            # Run all platform uploads in parallel (with optional stagger between)
            results = await asyncio.gather(*publish_tasks, return_exceptions=False)

            # Determine final status
            any_success = any(result.ok for result in results)
            any_failed = any((not result.ok) and (not result.skipped) for result in results)
            result_map = {result.platform: result.to_dict() for result in results}

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
                    error_message="No platform publishes succeeded",
                )

            # Build success notification
            parts = [f"Video publicado: '{script['title']}'"]
            parts.append(f"Score: {review['average_score']:.1f}/10")
            for result in results:
                if result.ok:
                    status_text = "OK"
                elif result.skipped:
                    status_text = "SKIP"
                else:
                    status_text = "FALLO"
                parts.append(f"{platform_short_name(result.platform)}: {status_text}")
            parts.append(f"Drive: {drive_link}")

            if any_success or not any_failed:
                discord_alerts.send_info("\n".join(parts), account=account)
            else:
                discord_alerts.send_warning("\n".join(parts), account=account)
            audit.record("pipeline_published", actor="scheduler", target=account, details={
                "video_id": video_id,
                "score": avg_score,
                "platforms": result_map,
            })

            logger.info(
                "Video %d pipeline complete for %s: %s [%s]",
                video_id, account, script["title"],
                " ".join(
                    f"{platform_short_name(result.platform)}={'OK' if result.ok else 'SKIP' if result.skipped else 'FAIL'}"
                    for result in results
                ),
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
