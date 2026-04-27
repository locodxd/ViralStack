import logging
import math
import re
from pathlib import Path
import yaml
from google.genai import types
from core.key_rotation import gemini_rotator
from core.db import get_session
from core.models import IdeaHistory
from core import llm_providers
from config.settings import ACCOUNTS, resolve_project_path, settings

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "config" / "prompts"

# Seconds per image — each visual prompt covers this duration.
# User preference: slower scene pacing with fewer generated images.
SECONDS_PER_IMAGE = settings.image_display_seconds
_SCRIPT_MAX_OUTPUT_TOKENS = 6000
_MAX_SCRIPT_ATTEMPTS = 3
_WORDS_PER_SECOND = 2.6

_MIN_WORDS_BY_ACCOUNT = {
    "terror": 85,
    "historias": 80,
    "dinero": 80,
}

_MAX_WORDS_BY_ACCOUNT = {
    "terror": 240,
    "historias": 240,
    "dinero": 250,
}

_DURATION_LIMITS = {
    "terror": (settings.min_video_seconds, settings.max_video_seconds),
    "historias": (settings.min_video_seconds, settings.max_video_seconds),
    "dinero": (settings.min_video_seconds, settings.max_video_seconds),
}

_HOOK_WORD_LIMITS = {
    "terror": (5, 14),
    "historias": (6, 16),
    "dinero": (5, 15),
}

_WEAK_HOOK_STARTERS = {
    "en": (
        "today i want",
        "in this video",
        "let me tell you",
        "this is the story",
        "have you ever",
        "i'm going to tell you",
    ),
    "es": (
        "hoy te voy a contar",
        "en este video",
        "te voy a contar",
        "esta es la historia",
        "quiero contarte",
        "alguna vez",
    ),
}

_HOOK_TRIGGER_TOKENS = {
    "terror": (
        # Times / timestamps
        "3 am", "3am", "2 am", "4 am", "medianoche", "midnight", "last night", "anoche",
        "madrugada",
        # Devices / evidence
        "grabacion", "grabación", "camara", "cámara", "camera", "ring", "monitor",
        "audio", "foto", "video", "captura", "screenshot", "notificacion", "notificación",
        "notification", "alert", "alerta", "mensaje", "message", "llamada", "call",
        "telefono", "teléfono", "phone", "app",
        # Places / objects
        "puerta", "door", "pasillo", "hallway", "pared", "wall", "ventana", "window",
        "espejo", "mirror", "sotano", "sótano", "basement", "atico", "ático", "attic",
        "closet", "armario", "escalera", "stairs", "cama", "bed", "baño", "bathroom",
        "cocina", "kitchen", "garage", "cuarto", "room", "casa", "house",
        # Horror elements
        "sombra", "shadow", "respirar", "respiracion", "respiración", "breathing",
        "pasos", "footsteps", "steps", "golpe", "golpes", "knock", "knocking",
        "timbre", "doorbell", "grito", "scream", "susurro", "whisper",
        "sangre", "blood", "mancha", "stain", "marca", "mark", "huella", "print",
        "ruido", "noise", "sound", "sonido", "voz", "voice", "voces", "voices",
        # People / creatures
        "muñeca", "doll", "niño", "niña", "child", "kid", "figura", "figure",
        "silueta", "silhouette", "alguien", "someone", "nadie", "nobody", "vecino",
        "neighbor", "desconocido", "stranger", "muerto", "dead",
        # Actions / states
        "solo", "alone", "sola", "desperté", "despertar", "woke", "wake",
        "corre", "run", "escondí", "hide", "desapareció", "disappeared", "vanished",
        "movió", "moved", "abrió", "opened", "cerró", "closed",
        # Evidence words
        "prueba", "pruebas", "proof", "evidence", "debajo", "underneath", "behind",
        "detrás", "inside", "dentro", "never", "nunca", "jamas", "jamás",
    ),
    "historias": (
        # Numbers / dates
        "1", "2", "3", "4", "5", "6", "7", "8", "9", "0",
        "año", "años", "year", "years", "siglo", "century", "guerra", "war",
        # People / roles
        "nadie", "nobody", "doctor", "capitan", "capitán", "captain", "presidente",
        "president", "soldado", "soldier", "piloto", "pilot", "ingeniero", "engineer",
        "astronauta", "astronaut", "cientifico", "científico", "scientist",
        "hombre", "man", "mujer", "woman", "rey", "king",
        # Events / objects
        "submarino", "submarine", "avion", "avión", "plane", "barco", "ship",
        "puente", "bridge", "bomba", "bomb", "cohete", "rocket", "tren", "train",
        "accidente", "accident", "error", "mistake", "falla", "failure",
        "desastre", "disaster", "colapso", "collapse",
        # Discovery / revelation
        "secreto", "secret", "descubri", "descubrió", "discovered", "found",
        "prueba", "proof", "verdad", "truth", "carta", "letter",
        "mensaje", "message", "foto", "photo", "mapa", "map",
        "sobrevivi", "sobrevivió", "survived", "perdió", "lost",
        "desaparecio", "desapareció", "disappeared", "volvio", "volvió", "returned",
        # Cause / effect
        "porque", "because", "culpa", "fault", "hormiga", "ant", "tornillo", "screw",
        "inodoro", "toilet", "centavo", "cent", "dolar", "dollar",
        "imposible", "impossible", "increible", "increíble", "unbelievable",
        "real", "verdadero", "true", "absurdo", "absurd",
    ),
    "dinero": (
        "$", "%", "banco", "bank", "error", "mistake",
        "rico", "rich", "pobre", "poor", "millonario", "millionaire",
        "ahorras", "ahorrar", "save", "saving",
        "inversion", "inversión", "invest", "investing",
        "tarjeta", "card", "deuda", "debt",
        "interes", "interés", "interest",
        "este año", "this year", "hoy", "today", "mañana", "tomorrow",
        "3 pasos", "steps", "dinero", "money", "cash",
        "salario", "salary", "sueldo", "income", "ingreso",
        "pierde", "pierdes", "losing", "lose", "ganas", "earn",
        "costo", "cost", "precio", "price", "gratis", "free",
        "crypto", "bitcoin", "s&p", "bolsa", "stock",
        "impuesto", "tax", "irs", "sat", "deduccion", "deducción",
        "ahorro", "cuenta", "account", "credito", "crédito", "credit",
        "inflacion", "inflación", "inflation", "rendimiento", "return",
    ),
}

# Field labels per language for parsing Gemini's response
_FIELD_MAP = {
    "en": {
        "title": ["TITLE:"],
        "hook": ["HOOK:"],
        "script_text": ["SCRIPT:"],
        "visual_prompts_raw": ["VISUAL:"],
        "estimated_duration_raw": ["DURATION:"],
    },
    "es": {
        "title": ["TITULO:", "TÍTULO:"],
        "hook": ["GANCHO:"],
        "script_text": ["GUION:", "GUIÓN:"],
        "visual_prompts_raw": ["VISUAL:"],
        "estimated_duration_raw": ["DURACION:", "DURACIÓN:"],
    },
}


def _account_config(account: str) -> dict:
    return ACCOUNTS.get(account, {})


def _account_int(account: str, key: str, default: int) -> int:
    try:
        return int(_account_config(account).get(key, default))
    except (TypeError, ValueError):
        return default


def _word_limits_for(account: str) -> tuple[int, int]:
    min_words = _account_int(account, "min_words", _MIN_WORDS_BY_ACCOUNT.get(account, 80))
    max_words = _account_int(account, "max_words", _MAX_WORDS_BY_ACCOUNT.get(account, 240))
    return max(1, min_words), max(max_words, min_words)


def _duration_limits_for(account: str) -> tuple[int, int]:
    min_default, max_default = _DURATION_LIMITS.get(
        account,
        (settings.min_video_seconds, settings.max_video_seconds),
    )
    min_duration = _account_int(account, "duration_min_seconds", min_default)
    max_duration = _account_int(account, "duration_max_seconds", max_default)
    return max(1, min_duration), max(max_duration, min_duration)


def _hook_word_limits_for(account: str) -> tuple[int, int]:
    min_default, max_default = _HOOK_WORD_LIMITS.get(account, (5, 16))
    min_words = _account_int(account, "hook_min_words", min_default)
    max_words = _account_int(account, "hook_max_words", max_default)
    return max(1, min_words), max(max_words, min_words)


def _load_prompt_config(account: str) -> dict:
    """Load the prompt YAML config for an account, language-aware."""
    account_cfg = _account_config(account)
    path = Path(resolve_project_path(account_cfg.get("prompt_file"))) if account_cfg.get("prompt_file") else PROMPTS_DIR / f"{account}.yaml"
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    lang = "en" if settings.is_english else "es"
    if isinstance(data, dict) and lang in data:
        return data[lang]
    if isinstance(data, dict) and {"system_prompt", "script_prompt"}.issubset(data.keys()):
        return data
    raise RuntimeError(f"Prompt file {path} must contain '{lang}' or system_prompt/script_prompt")


def _get_previous_ideas_compact(account: str, limit: int = 50) -> str:
    """Build a rich dedup context so Gemini truly avoids repeating topics.

    Sends full titles + hooks (not just keywords) so the model can
    distinguish between superficially similar but actually different ideas.
    """
    with get_session() as session:
        ideas = (
            session.query(IdeaHistory.title, IdeaHistory.keywords)
            .filter_by(account=account)
            .order_by(IdeaHistory.created_at.desc())
            .limit(limit)
            .all()
        )
        if not ideas:
            return "None" if settings.is_english else "Ninguna"

        entries = []
        for title, keywords in ideas:
            title = (title or "").strip()
            keywords = (keywords or "").strip()
            if title and keywords:
                entries.append(f'"{title}" ({keywords})')
            elif title:
                entries.append(f'"{title}"')
            elif keywords:
                entries.append(keywords)
        if not entries:
            return "None" if settings.is_english else "Ninguna"

        return "\n".join(f"- {e}" for e in entries)


def _extract_keywords(title: str, hook: str, script: str) -> str:
    """Extract a descriptive fingerprint from title + hook + script opening.

    Stores enough context (8-12 meaningful words) so that the dedup prompt
    can distinguish between similar-sounding but different ideas.
    """
    _STOPWORDS = {
        "the", "a", "an", "is", "was", "it", "in", "on", "at", "to", "for",
        "of", "and", "or", "but", "not", "this", "that", "with", "from", "by",
        "el", "la", "los", "las", "un", "una", "de", "en", "que", "es", "y",
        "del", "por", "con", "se", "su", "al", "lo", "como", "mas", "pero",
        "si", "te", "tu", "no", "ya", "hay", "eso", "esta", "este", "son",
        "tiene", "hace", "cada", "todo", "esa", "ese", "una", "uno",
    }
    text = f"{title} {hook} {script[:300]}".lower()
    words = [w.strip(".,!?\"'()¿¡:;") for w in text.split() if len(w) > 2]
    unique = []
    for w in words:
        if w in _STOPWORDS or w in unique:
            continue
        unique.append(w)
        if len(unique) >= 10:
            break

    return " ".join(unique) if unique else title[:60]


def _normalize_script_pacing(script_text: str) -> str:
    """Clean punctuation that causes slow/robotic narration pacing."""
    text = (script_text or "").strip()
    if not text:
        return text

    # Collapse long dot runs and keep at most one dramatic ellipsis.
    text = re.sub(r"\.{4,}", "...", text)
    parts = [p.strip() for p in re.split(r"\s*\.\.\.\s*", text) if p.strip()]
    if len(parts) > 1:
        text = f"{parts[0]}... {' '.join(parts[1:])}"
    elif parts:
        text = parts[0]

    # Remove repeated punctuation bursts like "!!" or "??".
    text = re.sub(r"([!?.,])\1+", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _trim_to_last_sentence(script_text: str) -> str:
    """Trim dangling partial tail when model output is cut mid-sentence."""
    text = (script_text or "").strip()
    if not text:
        return text

    if text[-1] in ".!?":
        return text

    matches = list(re.finditer(r"[.!?]", text))
    if not matches:
        return text

    last_idx = matches[-1].end()
    trimmed = text[:last_idx].strip()
    return trimmed or text


def _normalize_hook_text(hook_text: str) -> str:
    """Clean hook text so validation and script-prefix checks are stable."""
    text = (hook_text or "").strip().strip("\"'")
    if not text:
        return text

    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"([!?.,])\1+", r"\1", text)
    if text[-1] not in ".!?":
        text = f"{text}."
    return text


def _normalized_words(text: str) -> list[str]:
    """Tokenize text for fuzzy comparisons without relying on punctuation."""
    return re.findall(r"\b\w+\b", (text or "").casefold())


def _shared_prefix_ratio(left: str, right: str) -> float:
    """Measure how much the start of one phrase overlaps the start of another."""
    left_words = _normalized_words(left)
    right_words = _normalized_words(right)
    if not left_words or not right_words:
        return 0.0

    max_compare = min(len(left_words), len(right_words), 18)
    shared = 0
    for idx in range(max_compare):
        if left_words[idx] != right_words[idx]:
            break
        shared += 1

    return shared / max(1, min(len(left_words), 12))


def _ensure_hook_leads_script(hook_text: str, script_text: str) -> str:
    """Force the narration to open with the hook if the model drifted away from it."""
    hook = _normalize_hook_text(hook_text)
    script = (script_text or "").strip()
    if not hook:
        return script
    if not script:
        return hook

    if _shared_prefix_ratio(hook, script) >= 0.55:
        return script

    normalized_hook = " ".join(_normalized_words(hook))
    normalized_script = " ".join(_normalized_words(script[: max(len(hook) * 2, 120)]))
    if normalized_hook and normalized_hook in normalized_script:
        return script

    return f"{hook} {script}".strip()


def _trim_script_to_max_words(script_text: str, max_words: int) -> str:
    """Trim oversized scripts at sentence boundaries to stay within runtime target."""
    text = (script_text or "").strip()
    if not text:
        return text

    words = re.findall(r"\b\w+\b", text)
    if len(words) <= max_words:
        return text

    sentences = [
        s.strip() for s in re.split(r"(?<=[.!?])\s+|(?<=\.\.\.)\s*", text) if s.strip()
    ]
    kept: list[str] = []

    for sentence in sentences:
        candidate = " ".join(kept + [sentence]).strip()
        if len(re.findall(r"\b\w+\b", candidate)) > max_words:
            break
        kept.append(sentence)

    trimmed = " ".join(kept).strip()
    return _trim_to_last_sentence(trimmed or text)


def _enforce_script_bounds(script_text: str, account: str) -> str:
    """Normalize pacing and clamp overly long scripts before TTS."""
    text = _trim_to_last_sentence(_normalize_script_pacing(script_text))
    _, max_words = _word_limits_for(account)
    return _trim_script_to_max_words(text, max_words)


def _hook_validation_reasons(hook_text: str, script_text: str, account: str) -> list[str]:
    """Reject generic or weak hooks before accepting the script."""
    hook = _normalize_hook_text(hook_text)
    if not hook:
        return ["missing hook"]

    lang = "en" if settings.is_english else "es"
    lower = hook.casefold()
    hook_words = _normalized_words(hook)
    min_words, max_words = _hook_word_limits_for(account)
    reasons = []

    if len(hook_words) < min_words:
        reasons.append(f"hook too short ({len(hook_words)} words < {min_words})")
    if len(hook_words) > max_words:
        reasons.append(f"hook too long ({len(hook_words)} words > {max_words})")

    if any(lower.startswith(prefix) for prefix in _WEAK_HOOK_STARTERS[lang]):
        reasons.append("hook starts generically")

    triggers = _HOOK_TRIGGER_TOKENS.get(account, ())
    if triggers and not any(token in lower for token in triggers):
        reasons.append("hook lacks a concrete trigger")

    if script_text and _shared_prefix_ratio(hook, script_text) < 0.55:
        reasons.append("script does not open with the hook")

    return reasons


def _missing_response_sections(raw_text: str) -> list[str]:
    """Detect missing top-level labeled sections in the model response."""
    lang = "en" if settings.is_english else "es"
    field_map = _FIELD_MAP[lang]
    upper = (raw_text or "").upper()
    missing = []
    required_keys = {"title", "hook", "script_text"}

    for field_key, prefixes in field_map.items():
        if field_key not in required_keys:
            continue
        if not any(prefix in upper for prefix in prefixes):
            missing.append(field_key)

    return missing


def _script_validation_reasons(parsed: dict, account: str, raw_text: str) -> list[str]:
    """Explain why a script response should be rejected and retried."""
    title = (parsed.get("title") or "").strip()
    hook = _normalize_hook_text(parsed.get("hook", ""))
    script_text = (parsed.get("script_text") or "").strip()
    visuals = parsed.get("visual_prompts") or []
    estimated_duration = int(parsed.get("estimated_duration") or 0)
    min_d, max_d = _duration_limits_for(account)
    min_words, max_words = _word_limits_for(account)
    words = re.findall(r"\b\w+\b", script_text)
    reasons = []

    missing_sections = _missing_response_sections(raw_text)
    if missing_sections:
        reasons.append(f"missing sections: {', '.join(missing_sections)}")

    if not title:
        reasons.append("missing title")
    if not script_text:
        reasons.append("missing script")

    reasons.extend(_hook_validation_reasons(hook, script_text, account))

    if script_text:
        if len(words) < min_words:
            reasons.append(f"script too short ({len(words)} words < {min_words})")
        if len(words) > max_words:
            reasons.append(f"script too long ({len(words)} words > {max_words})")
        if script_text[-1] not in ".!?":
            reasons.append("script does not end with punctuation")

    if not (min_d <= estimated_duration <= max_d):
        reasons.append(
            f"duration out of range ({estimated_duration}s not in {min_d}-{max_d}s)"
        )

    # Visuals: no minimum, max 18 — Gemini decides how many fit the script
    if len(visuals) == 0 and script_text:
        reasons.append("no visual prompts provided")

    return reasons


def _is_incomplete_script(parsed: dict, account: str, raw_text: str) -> bool:
    """Validate script payload completeness before accepting it."""
    return bool(_script_validation_reasons(parsed, account, raw_text))


def _estimate_duration_from_words(script_text: str) -> int:
    """Estimate narration duration using rough words-per-second."""
    words = re.findall(r"\b\w+\b", script_text or "")
    if not words:
        return max(settings.min_video_seconds, 45)
    return int(round(len(words) / _WORDS_PER_SECOND))


def _normalize_duration(account: str, model_duration: int, script_text: str) -> int:
    """Blend model estimate with text-based estimate and clamp by account."""
    min_d, max_d = _duration_limits_for(account)
    text_duration = _estimate_duration_from_words(script_text)
    blended = int(round((model_duration * 0.35) + (text_duration * 0.65)))
    return max(min_d, min(max_d, blended))


def _parse_script_response(text: str) -> dict:
    """Parse Gemini's response into structured data."""
    lang = "en" if settings.is_english else "es"
    field_map = _FIELD_MAP[lang]

    result = {
        "title": "",
        "hook": "",
        "script_text": "",
        "visual_prompts": [],
        "estimated_duration": 60,
    }

    lines = text.strip().split("\n")
    current_key = None
    current_value = []

    for line in lines:
        line_stripped = line.strip()
        upper = line_stripped.upper()

        matched = False
        for field_key, prefixes in field_map.items():
            for prefix in prefixes:
                if upper.startswith(prefix):
                    if current_key:
                        result[current_key] = "\n".join(current_value).strip()
                    current_key = field_key
                    current_value = [line_stripped.split(":", 1)[1].strip()]
                    matched = True
                    break
            if matched:
                break

        if not matched:
            current_value.append(line_stripped)

    if current_key:
        result[current_key] = "\n".join(current_value).strip()

    # Parse visual prompts
    if "visual_prompts_raw" in result:
        result["visual_prompts"] = [
            v.strip() for v in result.pop("visual_prompts_raw").split("|") if v.strip()
        ]

    # Parse duration
    if "estimated_duration_raw" in result:
        raw = result.pop("estimated_duration_raw")
        numbers = re.findall(r"\d+", raw)
        if numbers:
            result["estimated_duration"] = int(numbers[0])

    return result


def _split_script_into_segments(script_text: str, num_segments: int) -> list[str]:
    """Split script text into N roughly equal segments at sentence boundaries.

    Each segment represents what is being narrated during one image.
    Returns list of text segments.
    """
    # Split into sentences
    raw_sentences = re.split(r'(?<=[.!?])\s+|(?<=\.\.\.)\s*', script_text)
    sentences = [s.strip() for s in raw_sentences if s.strip() and len(s.strip()) > 5]

    if not sentences:
        return [script_text]

    if len(sentences) <= num_segments:
        return sentences

    # Distribute sentences into segments as evenly as possible
    chunk_size = max(1, len(sentences) / num_segments)
    segments = []
    current = []
    target_idx = chunk_size

    for i, sentence in enumerate(sentences):
        current.append(sentence)
        if i + 1 >= target_idx and len(segments) < num_segments - 1:
            segments.append(" ".join(current))
            current = []
            target_idx += chunk_size

    # Last segment gets remaining sentences
    if current:
        segments.append(" ".join(current))

    return segments


def _sample_visuals_evenly(visual_prompts: list[str], target_count: int) -> list[str]:
    """Trim oversized visual lists while preserving beginning, middle, and ending beats."""
    if target_count <= 0 or len(visual_prompts) <= target_count:
        return list(visual_prompts)
    if target_count == 1:
        return [visual_prompts[-1]]

    last_index = len(visual_prompts) - 1
    indices = [
        round(i * last_index / (target_count - 1))
        for i in range(target_count)
    ]
    return [visual_prompts[idx] for idx in indices]


def _align_visuals_to_script(
    visual_prompts: list[str],
    script_text: str,
    estimated_duration: int,
    account: str,
) -> list[str]:
    """Ensure we have exactly the right number of visual prompts for the duration.

    Target: 1 image per SECONDS_PER_IMAGE seconds.
    If Gemini returned too few, we generate more by splitting the script into
    chronological segments and creating a visual for each.
    If too many, we trim to the target count.
    """
    _MAX_VISUALS = 18
    target_count = min(_MAX_VISUALS, math.ceil(estimated_duration / SECONDS_PER_IMAGE))

    # If Gemini gave us enough (within 20% tolerance), use them directly
    if len(visual_prompts) >= target_count * 0.8:
        logger.info(
            "Visual prompts OK: %d provided, %d target (duration=%ds)",
            len(visual_prompts), target_count, estimated_duration,
        )
        # Trim if too many
        if len(visual_prompts) > target_count:
            return _sample_visuals_evenly(visual_prompts, target_count)
        return visual_prompts

    # Not enough — split script into segments and generate visual prompts
    logger.info(
        "Expanding visual prompts: %d provided but %d needed (duration=%ds)",
        len(visual_prompts), target_count, estimated_duration,
    )

    segments = _split_script_into_segments(script_text, target_count)

    # Style hints per account for better prompt generation
    style = _account_config(account).get("image_style") or "Cinematic, photorealistic"

    # If we already have some visual prompts from Gemini, interleave them
    # with generated ones to maintain quality
    existing = list(visual_prompts)
    result = []

    for i, segment in enumerate(segments):
        if i < len(existing):
            # Use Gemini's original prompt for this slot
            result.append(existing[i])
        else:
            # Generate from script segment
            # Truncate the segment to keep the visual prompt focused
            snippet = segment[:120].strip()
            result.append(f"{style} scene depicting: {snippet}")

    logger.info("Expanded to %d visual prompts from %d", len(result), len(visual_prompts))
    return result


def _build_retry_prompt(base_prompt: str, account: str, reasons: list[str], attempt: int) -> str:
    """Tighten instructions when Gemini returns a malformed or truncated script."""
    min_d, max_d = _duration_limits_for(account)
    max_visuals = min(18, math.ceil(max_d / SECONDS_PER_IMAGE))
    hook_min_words, hook_max_words = _hook_word_limits_for(account)
    reason_text = "; ".join(reasons) if reasons else "response incomplete"

    return (
        f"{base_prompt}\n\n"
        "CRITICAL REGENERATION INSTRUCTIONS:\n"
        f"- Previous attempt #{attempt} was invalid: {reason_text}.\n"
        "- Regenerate the FULL answer from scratch.\n"
        "- Return exactly the labeled sections TITLE/HOOK/SCRIPT/VISUAL/DURATION (or TITULO/GANCHO/GUION/VISUAL/DURACION in Spanish).\n"
        f"- Keep narration between {min_d} and {max_d} seconds.\n"
        f"- Make HOOK/GANCHO {hook_min_words}-{hook_max_words} words, concrete, and impossible to scroll past.\n"
        "- SCRIPT/GUION must open with the same HOOK/GANCHO almost word-for-word.\n"
        f"- Provide up to {max_visuals} visual prompts, one every ~{SECONDS_PER_IMAGE:.1f} seconds.\n"
        "- End SCRIPT/GUION with a complete final sentence and punctuation.\n"
        "- Do not add explanations before or after the labeled fields.\n"
    )


async def generate_script(account: str) -> dict:
    """Generate a video script using Gemini with key+model rotation."""
    prompt_config = _load_prompt_config(account)
    previous_ideas = _get_previous_ideas_compact(account)
    min_duration, max_duration = _duration_limits_for(account)
    max_visuals = min(18, math.ceil(max_duration / SECONDS_PER_IMAGE))
    hook_min_words, hook_max_words = _hook_word_limits_for(account)

    system_prompt = prompt_config["system_prompt"]
    script_prompt = prompt_config["script_prompt"].format(
        previous_ideas=previous_ideas,
        min_duration=min_duration,
        max_duration=max_duration,
        image_seconds=f"{SECONDS_PER_IMAGE:.1f}",
        max_visuals=max_visuals,
        hook_min_words=hook_min_words,
        hook_max_words=hook_max_words,
    )

    def build_request(client, model_name, prompt_text: str, temperature: float):
        return client.models.generate_content(
            model=model_name,
            contents=prompt_text,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=temperature,
                max_output_tokens=_SCRIPT_MAX_OUTPUT_TOKENS,
            ),
        )

    def _generate_once(prompt_text: str, temperature: float) -> tuple[dict, str, str]:
        """Generate one script via the multi-LLM chain.

        First provider in `settings.script_provider_chain` wins; on failure
        we transparently fall through to the next provider (OpenAI, Claude,
        OpenRouter, Groq, ...). Gemini stays the default at the front of the
        chain so existing setups behave identically.
        """
        try:
            result = llm_providers.generate_text(
                prompt_text,
                system=system_prompt,
                temperature=temperature,
                max_tokens=_SCRIPT_MAX_OUTPUT_TOKENS,
            )
            raw_text = result.text or ""
            model_used = f"{result.provider}:{result.model}"
        except Exception as exc:
            # Hard fall-back to legacy direct rotator path if the abstraction
            # blew up — keeps the system alive even if a provider import fails.
            logger.warning("Multi-LLM chain failed (%s) — falling back to gemini_rotator.", exc)
            response, model_used = gemini_rotator.call(
                lambda client, model_name: build_request(
                    client, model_name, prompt_text, temperature
                ),
                preferred_models=settings.gemini_models_list or None,
            )
            raw_text = response.text or ""
        logger.info("Script generated for %s using %s: %d chars", account, model_used, len(raw_text))

        parsed_local = _parse_script_response(raw_text)
        parsed_local["hook"] = _normalize_hook_text(parsed_local.get("hook", ""))
        parsed_local["script_text"] = _enforce_script_bounds(
            _ensure_hook_leads_script(
                parsed_local.get("hook", ""),
                parsed_local.get("script_text", ""),
            ),
            account,
        )
        parsed_local["estimated_duration"] = _normalize_duration(
            account,
            parsed_local.get("estimated_duration", 60),
            parsed_local.get("script_text", ""),
        )
        return parsed_local, raw_text, model_used

    parsed = {}
    raw_text = ""
    model_used = ""
    validation_reasons: list[str] = []

    for attempt in range(1, _MAX_SCRIPT_ATTEMPTS + 1):
        prompt_text = (
            script_prompt
            if attempt == 1
            else _build_retry_prompt(script_prompt, account, validation_reasons, attempt - 1)
        )
        temperature = 0.72 if attempt == 1 else 0.58

        parsed, raw_text, model_used = _generate_once(prompt_text, temperature)
        validation_reasons = _script_validation_reasons(parsed, account, raw_text)

        if not validation_reasons:
            break

        logger.warning(
            "Script attempt %d/%d rejected for %s: %s",
            attempt,
            _MAX_SCRIPT_ATTEMPTS,
            account,
            "; ".join(validation_reasons),
        )

    if validation_reasons:
        raise RuntimeError(
            f"Could not generate a complete script for {account}: {'; '.join(validation_reasons)}"
        )

    # Fallback: if no visual prompts at all, generate from scratch
    if not parsed["visual_prompts"] and parsed["script_text"]:
        logger.warning("No VISUAL section in response, generating all visual prompts from script")

    # Align visuals to script: ensure 1 image per 5.5 seconds, chronologically
    parsed["visual_prompts"] = _align_visuals_to_script(
        parsed.get("visual_prompts", []),
        parsed["script_text"],
        parsed["estimated_duration"],
        account,
    )

    # Extract descriptive keywords for dedup
    keywords = _extract_keywords(parsed["title"], parsed.get("hook", ""), parsed["script_text"])

    # Save to idea history with compact keywords
    with get_session() as session:
        idea = IdeaHistory(
            account=account,
            summary=parsed["title"][:200] if parsed["title"] else raw_text[:200],
            title=parsed["title"],
            keywords=keywords,
        )
        session.add(idea)

    logger.info(
        "Script for %s: '%s' (~%ds, %d visuals) [keywords: %s]",
        account, parsed["title"], parsed["estimated_duration"],
        len(parsed["visual_prompts"]), keywords
    )

    return parsed
