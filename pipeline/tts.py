"""
Text-to-Speech using Google Gemini TTS via Vertex AI.

Strategy:
- Primary: Gemini TTS (gemini-2.5-flash-preview-tts) via Vertex AI
- Last resort: Edge TTS (free, unlimited, lower quality)
- Voice selection per account for maximum engagement

Voices (Spanish Latin America):
- Terror: charon — deep, gravelly, eerie
- Historias: orus — warm, engaging narrator
- Dinero: kore — clear, professional, authoritative
"""
import asyncio
import logging
import wave
from pathlib import Path
from config.settings import settings, ACCOUNTS

logger = logging.getLogger(__name__)

_TTS_MODEL = "gemini-2.5-flash-preview-tts"

# Voice mapping per account — optimized for Spanish narration engagement
_VOICES = {
    "terror": "charon",           # Deep, eerie — perfect for horror
    "historias": "orus",           # Warm narrator — engaging stories
    "dinero": "kore",             # Clear, authoritative — educational
}

# Fallback voices if primary fails
_FALLBACK_VOICES = {
    "terror": "fenrir",
    "historias": "zubenelgenubi",
    "dinero": "laomedeia",
}


async def _generate_gemini_tts(
    text: str,
    voice: str,
    output_path: Path,
) -> Path:
    """Generate TTS using Gemini TTS model via Vertex AI.

    Returns path to the generated WAV file.
    """
    from google.genai import types
    from core.vertex_client import get_client

    client = get_client()

    # Split long text into chunks for better quality (max ~4000 chars per call)
    chunks = _split_text_for_tts(text, max_chars=3500)
    all_audio_data = []

    for i, chunk in enumerate(chunks):
        logger.debug("TTS chunk %d/%d (%d chars)", i + 1, len(chunks), len(chunk))

        response = await asyncio.to_thread(
            client.models.generate_content,
            model=_TTS_MODEL,
            contents=chunk,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice,
                        )
                    )
                ),
            ),
        )

        # Extract audio data from response
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("audio/"):
                audio_bytes = part.inline_data.data
                all_audio_data.append(audio_bytes)
                break
        else:
            raise RuntimeError(f"No audio in TTS response for chunk {i+1}")

    # Combine all audio chunks into single valid WAV file
    _combine_audio_chunks(all_audio_data, output_path)

    logger.info("Gemini TTS generated: %s (voice=%s, %d chunks, Vertex AI)", output_path, voice, len(chunks))
    return output_path


def _split_text_for_tts(text: str, max_chars: int = 3500) -> list[str]:
    """Split text into chunks at sentence boundaries."""
    if len(text) <= max_chars:
        return [text]

    chunks = []
    current = ""

    # Split on sentence endings
    sentences = []
    temp = ""
    for char in text:
        temp += char
        if char in ".!?¿¡" and len(temp) > 10:
            sentences.append(temp.strip())
            temp = ""
    if temp.strip():
        sentences.append(temp.strip())

    for sentence in sentences:
        if len(current) + len(sentence) + 1 > max_chars and current:
            chunks.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence

    if current.strip():
        chunks.append(current.strip())

    return chunks if chunks else [text]


def _combine_audio_chunks(chunks: list[bytes], output_path: Path):
    """Combine multiple WAV/PCM audio chunks into a single valid WAV file.

    Gemini TTS returns WAV files — naive concatenation corrupts them because
    each chunk has its own WAV header. We must strip headers and recombine.
    """
    import io

    all_pcm_data = []
    sample_rate = 24000  # Gemini TTS default
    sample_width = 2     # 16-bit
    n_channels = 1       # mono

    for i, chunk_bytes in enumerate(chunks):
        try:
            bio = io.BytesIO(chunk_bytes)
            with wave.open(bio, "rb") as wf:
                if i == 0:
                    sample_rate = wf.getframerate()
                    sample_width = wf.getsampwidth()
                    n_channels = wf.getnchannels()
                all_pcm_data.append(wf.readframes(wf.getnframes()))
        except wave.Error:
            # Not a valid WAV — treat as raw PCM, skip header heuristic
            if len(chunk_bytes) > 44 and chunk_bytes[:4] == b"RIFF":
                # Has WAV header but wave module can't parse — skip 44-byte header
                all_pcm_data.append(chunk_bytes[44:])
            else:
                all_pcm_data.append(chunk_bytes)

    # Write combined PCM into a proper WAV file
    combined_pcm = b"".join(all_pcm_data)
    with wave.open(str(output_path), "wb") as wf_out:
        wf_out.setnchannels(n_channels)
        wf_out.setsampwidth(sample_width)
        wf_out.setframerate(sample_rate)
        wf_out.writeframes(combined_pcm)

    logger.info("Combined %d audio chunks -> %s (%.1f KB)",
                len(chunks), output_path, len(combined_pcm) / 1024)


async def _generate_edge_tts(text: str, voice: str, output_path: Path) -> Path:
    """Generate TTS using Edge TTS (last resort fallback)."""
    import edge_tts
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(output_path))
    logger.info("Edge TTS fallback generated: %s (%s)", output_path, voice)
    return output_path


async def generate_tts(script_text: str, account: str, video_id: int) -> str:
    """Generate TTS narration for a script.

    Priority:
    1. Gemini TTS via Vertex AI (primary voice)
    2. Gemini TTS via Vertex AI (fallback voice)
    3. Edge TTS (last resort, free unlimited)

    Returns path to the generated audio file.
    """
    output_dir = Path(settings.db_path).parent / "output" / account / str(video_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "narration.wav"

    account_cfg = ACCOUNTS.get(account, {})
    voice = account_cfg.get("voice") or _VOICES.get(account, "orus")
    fallback_voice = account_cfg.get("voice_fallback_gemini") or _FALLBACK_VOICES.get(account, "orus")

    # Try 1: Gemini TTS with primary voice
    try:
        await _generate_gemini_tts(script_text, voice, output_path)
        return str(output_path)
    except Exception as e:
        logger.warning("Gemini TTS primary voice failed: %s", e)

    # Try 2: Gemini TTS with fallback voice
    try:
        await _generate_gemini_tts(script_text, fallback_voice, output_path)
        return str(output_path)
    except Exception as e:
        logger.warning("Gemini TTS fallback voice failed: %s", e)

    # Try 3: Edge TTS (last resort)
    logger.warning("All Gemini TTS failed, falling back to Edge TTS")
    output_path = output_dir / "narration.mp3"
    edge_voice = account_cfg.get("voice_fallback") or ("es-MX-JorgeNeural" if not settings.is_english else "en-US-GuyNeural")
    await _generate_edge_tts(script_text, edge_voice, output_path)
    return str(output_path)
