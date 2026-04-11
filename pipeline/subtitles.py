import logging
from pathlib import Path
from config.settings import settings, WHISPER_LANG

logger = logging.getLogger(__name__)


def _format_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _clean_word_text(word) -> str:
    """Normalize Whisper word fragments into subtitle-safe tokens."""
    return (getattr(word, "word", "") or "").strip()


def _format_cue_text(words: list) -> str:
    """Format a subtitle cue into one or two balanced lines for large captions."""
    tokens = [_clean_word_text(word) for word in words if _clean_word_text(word)]
    if len(tokens) <= 2:
        return " ".join(tokens)

    split_at = (len(tokens) + 1) // 2
    first_line = " ".join(tokens[:split_at]).strip()
    second_line = " ".join(tokens[split_at:]).strip()
    if not second_line:
        return first_line
    return f"{first_line}\n{second_line}"


def _build_word_groups(words: list) -> list[list]:
    """Group words into readable subtitle chunks instead of tiny flashes."""
    groups: list[list] = []
    current: list = []
    min_duration = settings.subtitle_min_cue_seconds
    target_words = max(1, settings.subtitle_words_per_cue)
    max_words = max(target_words, settings.subtitle_max_words_per_cue)

    for word in words:
        if not _clean_word_text(word):
            continue

        current.append(word)
        start = getattr(current[0], "start", None)
        end = getattr(current[-1], "end", None)
        duration = (end - start) if start is not None and end is not None else 0

        if len(current) >= max_words:
            groups.append(current)
            current = []
            continue

        if len(current) >= target_words and duration >= min_duration:
            groups.append(current)
            current = []

    if current:
        start = getattr(current[0], "start", None)
        end = getattr(current[-1], "end", None)
        duration = (end - start) if start is not None and end is not None else 0
        if groups and duration < min_duration and len(current) <= 2:
            groups[-1].extend(current)
        else:
            groups.append(current)

    return groups


def generate_subtitles(audio_path: str, video_id: int, account: str) -> str:
    """Generate SRT subtitles from audio using faster-whisper.

    Returns path to the generated .srt file.
    """
    from faster_whisper import WhisperModel

    output_dir = Path(audio_path).parent
    srt_path = output_dir / "subtitles.srt"

    logger.info("Transcribing audio: %s (model: %s)", audio_path, settings.whisper_model)

    model = WhisperModel(
        settings.whisper_model,
        device="cpu",
        compute_type="int8",
    )

    segments, info = model.transcribe(
        audio_path,
        language=WHISPER_LANG,
        beam_size=5,
        word_timestamps=True,
        vad_filter=True,
    )

    logger.info("Detected language: %s (prob: %.2f)", info.language, info.language_probability)

    srt_entries = []
    index = 1

    for segment in segments:
        # Split long segments into readable chunks instead of 1-word flashes.
        if segment.words:
            words = [word for word in segment.words if _clean_word_text(word)]
            for group in _build_word_groups(words):
                start_time = group[0].start
                end_time = group[-1].end
                text = _format_cue_text(group)

                srt_entries.append(
                    f"{index}\n"
                    f"{_format_timestamp(start_time)} --> {_format_timestamp(end_time)}\n"
                    f"{text}\n"
                )
                index += 1
        else:
            srt_entries.append(
                f"{index}\n"
                f"{_format_timestamp(segment.start)} --> {_format_timestamp(segment.end)}\n"
                f"{segment.text.strip()}\n"
            )
            index += 1

    srt_content = "\n".join(srt_entries)
    srt_path.write_text(srt_content, encoding="utf-8")

    logger.info("Generated %d subtitle entries at %s", index - 1, srt_path)
    return str(srt_path)
