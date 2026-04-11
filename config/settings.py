import json
import os
import random
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import List

BASE_DIR = Path(__file__).resolve().parent.parent
PLATFORMS_FILE = BASE_DIR / "config" / "platforms.json"


class Settings(BaseSettings):
    # === Language: "en" or "es" — controls prompts, TTS voice, hashtags, everything ===
    language: str = "es"

    # Discord Bot
    discord_bot_token: str = ""
    discord_guild_id: int = 0
    discord_owner_id: int = 0
    discord_alerts_channel_id: int = 0
    discord_stats_channel_id: int = 0

    # Discord Webhook (legacy fallback)
    discord_webhook_url: str = ""
    discord_user_id: str = ""

    # Vertex AI
    vertex_ai_api_key: str = ""
    vertex_ai_project: str = ""
    vertex_ai_location: str = "us-central1"

    # Gemini models (same models, now served through Vertex AI)
    gemini_models: str = "gemini-3-flash-preview,gemini-3.1-flash-lite-preview,gemini-2.5-flash,gemini-3.1-pro-preview,gemini-2.5-pro"

    # Google AI (for quality check — free at https://aistudio.google.com/apikey)
    google_ai_api_key: str = ""

    # ElevenLabs (optional fallback)
    elevenlabs_api_keys: str = ""  # comma-separated

    # Image generation daily limit for Imagen 4.0
    imagen_daily_limit: int = 70

    # Google Drive
    google_service_account_file: str = str(BASE_DIR / "config" / "service_account.json")

    # YouTube OAuth (per account)
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_terror_token: str = str(BASE_DIR / "config" / "youtube_terror_token.json")
    youtube_historias_token: str = str(BASE_DIR / "config" / "youtube_historias_token.json")
    youtube_dinero_token: str = str(BASE_DIR / "config" / "youtube_dinero_token.json")

    # Gmail OAuth (per account)
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_terror_token: str = str(BASE_DIR / "config" / "gmail_terror_token.json")
    gmail_historias_token: str = str(BASE_DIR / "config" / "gmail_historias_token.json")
    gmail_dinero_token: str = str(BASE_DIR / "config" / "gmail_dinero_token.json")

    # Videos per day per account (0=disabled, max 6)
    videos_per_day_terror: int = 2
    videos_per_day_historias: int = 2
    videos_per_day_dinero: int = 2

    # TikTok cookies
    tiktok_terror_cookies: str = str(BASE_DIR / "storage" / "cookies" / "terror_cookies.txt")
    tiktok_historias_cookies: str = str(BASE_DIR / "storage" / "cookies" / "historias_cookies.txt")
    tiktok_dinero_cookies: str = str(BASE_DIR / "storage" / "cookies" / "dinero_cookies.txt")

    # General
    db_path: str = str(BASE_DIR / "storage" / "viralstack.db")
    log_level: str = "INFO"
    quality_threshold: float = 6.0
    max_retries_per_video: int = 3
    whisper_model: str = "base"

    # FFmpeg — on Linux VPS use "ffmpeg" (system), on Windows use local binary
    ffmpeg_path: str = "ffmpeg"

    # Short-form video pacing
    min_video_seconds: int = 30
    max_video_seconds: int = 90
    image_display_seconds: float = 5.5

    # Subtitle styling / grouping
    subtitle_font_name: str = "Arial"
    subtitle_font_size: int = 58
    subtitle_font_scale: float = 0.034
    subtitle_outline: int = 4
    subtitle_outline_scale: float = 0.08
    subtitle_shadow: int = 1
    subtitle_margin_v: int = 190
    subtitle_margin_v_ratio: float = 0.10
    subtitle_margin_h: int = 72
    subtitle_margin_h_ratio: float = 0.067
    subtitle_words_per_cue: int = 3
    subtitle_min_cue_seconds: float = 1.0
    subtitle_max_words_per_cue: int = 5

    # Optional platform extras
    enable_drive_upload: bool = False

    # Video quality preset
    video_crf: int = 20
    video_preset: str = "medium"
    video_bitrate_audio: str = "192k"
    video_width: int = 1080
    video_height: int = 1920

    # Dashboard
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8000

    # Timezone for scheduler (use your TikTok audience timezone)
    timezone: str = "America/New_York"

    @property
    def is_english(self) -> bool:
        return self.language.lower().startswith("en")

    @property
    def gemini_models_list(self) -> List[str]:
        return [m.strip() for m in self.gemini_models.split(",") if m.strip()]

    @property
    def elevenlabs_keys_list(self) -> List[str]:
        return [k.strip() for k in self.elevenlabs_api_keys.split(",") if k.strip()]

    def get_cookies_path(self, account: str) -> str:
        mapping = {
            "terror": self.tiktok_terror_cookies,
            "historias": self.tiktok_historias_cookies,
            "dinero": self.tiktok_dinero_cookies,
        }
        return mapping.get(account, "")

    def get_youtube_token_path(self, account: str) -> str:
        mapping = {
            "terror": self.youtube_terror_token,
            "historias": self.youtube_historias_token,
            "dinero": self.youtube_dinero_token,
        }
        return mapping.get(account, "")

    def get_gmail_token_path(self, account: str) -> str:
        mapping = {
            "terror": self.gmail_terror_token,
            "historias": self.gmail_historias_token,
            "dinero": self.gmail_dinero_token,
        }
        return mapping.get(account, "")

    class Config:
        env_file = str(BASE_DIR / ".env")
        env_file_encoding = "utf-8"


settings = Settings()


# ============================================================
# PLATFORM TOGGLES — per account, per platform
# Editable via Discord bot commands
# ============================================================

_DEFAULT_PLATFORMS = {
    "terror": {"tiktok": True, "youtube": True},
    "historias": {"tiktok": True, "youtube": True},
    "dinero": {"tiktok": True, "youtube": True},
}


def load_platform_config() -> dict:
    """Load platform toggles from JSON file."""
    if PLATFORMS_FILE.exists():
        try:
            return json.loads(PLATFORMS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return _DEFAULT_PLATFORMS.copy()


def save_platform_config(config: dict):
    """Save platform toggles to JSON file."""
    PLATFORMS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PLATFORMS_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")


def is_platform_enabled(account: str, platform: str) -> bool:
    """Check if a platform is enabled for an account."""
    config = load_platform_config()
    return config.get(account, {}).get(platform, True)


def toggle_platform(account: str, platform: str, enabled: bool) -> dict:
    """Toggle a platform for an account. Returns updated config."""
    config = load_platform_config()
    if account not in config:
        config[account] = {"tiktok": True, "youtube": True}
    config[account][platform] = enabled
    save_platform_config(config)
    return config


# Initialize platforms.json if it doesn't exist
if not PLATFORMS_FILE.exists():
    save_platform_config(_DEFAULT_PLATFORMS)


# ============================================================
# LANGUAGE-AWARE CONFIGURATIONS
# ============================================================

PRICING = {
    "mencion_15s": 15,      # USD
    "video_dedicado": 25,
    "link_bio_1mes": 40,
}


def _rand_minute() -> int:
    """Generate a random non-round minute (avoids :00, :15, :30, :45)."""
    blocked = {0, 15, 30, 45}
    return random.choice([x for x in range(1, 60) if x not in blocked])


def _generate_schedule_windows(n: int, hour_ranges: list[tuple[int, int]]) -> list[dict]:
    """Generate N random schedule windows spread across hour ranges."""
    if n <= 0:
        return []

    n = min(n, 6)  # Hard cap

    all_hours = list(range(8, 23))  # 8am to 10pm
    slot_size = max(1, len(all_hours) // n)

    windows = []
    used_hours = set()

    for i in range(n):
        start_idx = i * slot_size
        end_idx = min(start_idx + slot_size, len(all_hours))
        if start_idx >= len(all_hours):
            start_idx = 0
            end_idx = len(all_hours)

        candidates = [h for h in all_hours[start_idx:end_idx] if h not in used_hours]
        if not candidates:
            candidates = [h for h in all_hours if h not in used_hours]
        if not candidates:
            candidates = all_hours

        hour = random.choice(candidates)
        used_hours.add(hour)
        windows.append({"hour": hour, "minute": _rand_minute()})

    windows.sort(key=lambda w: (w["hour"], w["minute"]))
    return windows


# Account base configs per language
_ACCOUNT_BASE = {
    "en": {
        "terror": {
            "display_name": "Terror",
            "description": "Horror stories, scary tales, creepypastas, paranormal encounters",
            "voice": "charon",
            "voice_fallback": "en-US-GuyNeural",
            "music_mood": "dark_ambient",
            "hashtags_tiktok": ["#horror", "#scary", "#creepypasta", "#paranormal", "#scarystories",
                                "#horrorstories", "#creepy", "#haunted", "#fyp", "#viral"],
            "hashtags_youtube": ["#horror", "#scary", "#creepypasta", "#paranormal", "#scarystories",
                                 "#horrorstories", "#shorts", "#creepy", "#haunted", "#viral"],
        },
        "historias": {
            "display_name": "Stories",
            "description": "True stories, fiction, interesting tales, real-life anecdotes",
            "voice": "orus",
            "voice_fallback": "en-US-GuyNeural",
            "music_mood": "emotional_ambient",
            "hashtags_tiktok": ["#stories", "#truecrime", "#truestory", "#storytime", "#realstories",
                                "#fiction", "#tales", "#mindblowing", "#fyp", "#viral"],
            "hashtags_youtube": ["#stories", "#truecrime", "#truestory", "#storytime", "#realstories",
                                 "#fiction", "#shorts", "#mindblowing", "#viral"],
        },
        "dinero": {
            "display_name": "Money & Investing",
            "description": "Money tips, investing, personal finance, financial education",
            "voice": "kore",
            "voice_fallback": "en-US-GuyNeural",
            "music_mood": "motivational",
            "hashtags_tiktok": ["#money", "#investing", "#finance", "#personalfinance",
                                "#passiveincome", "#stocks", "#crypto", "#financialfreedom",
                                "#fyp", "#viral"],
            "hashtags_youtube": ["#money", "#investing", "#finance", "#personalfinance",
                                 "#passiveincome", "#stocks", "#shorts", "#financialfreedom",
                                 "#viral"],
        },
    },
    "es": {
        "terror": {
            "display_name": "Terror",
            "description": "Videos de terror, historias de miedo, creepypastas",
            "voice": "charon",       # Gemini TTS — deep, eerie
            "voice_fallback": "es-MX-JorgeNeural",  # Edge TTS fallback
            "music_mood": "dark_ambient",
            "hashtags_tiktok": ["#terror", "#miedo", "#historiasdeterror", "#creepypasta", "#paranormal",
                                "#historiademiedo", "#terrorreal", "#miedoreal", "#fyp", "#viral"],
            "hashtags_youtube": ["#terror", "#miedo", "#historiasdeterror", "#creepypasta", "#paranormal",
                                 "#historiademiedo", "#shorts", "#terrorreal", "#viral"],
        },
        "historias": {
            "display_name": "Historias",
            "description": "Historias reales y ficticias, relatos interesantes, anécdotas",
            "voice": "orus",                      # Gemini TTS — warm narrator
            "voice_fallback": "es-MX-JorgeNeural",
            "music_mood": "emotional_ambient",
            "hashtags_tiktok": ["#historias", "#historiasreales", "#relatos", "#historia", "#anecdotas",
                                "#historiasdeficcion", "#cuentos", "#relatoscortos", "#fyp", "#viral"],
            "hashtags_youtube": ["#historias", "#historiasreales", "#relatos", "#historia", "#anecdotas",
                                 "#historiasdeficcion", "#shorts", "#relatoscortos", "#viral"],
        },
        "dinero": {
            "display_name": "Dinero e Inversiones",
            "description": "Tips de dinero, inversiones, finanzas personales, educación financiera",
            "voice": "kore",            # Gemini TTS — authoritative
            "voice_fallback": "es-MX-JorgeNeural",
            "music_mood": "motivational",
            "hashtags_tiktok": ["#dinero", "#inversiones", "#finanzas", "#educacionfinanciera",
                                "#dineroextra", "#invertir", "#finanzaspersonales", "#ahorrar",
                                "#fyp", "#viral"],
            "hashtags_youtube": ["#dinero", "#inversiones", "#finanzas", "#educacionfinanciera",
                                 "#dineroextra", "#invertir", "#shorts", "#finanzaspersonales",
                                 "#viral"],
        },
    },
}

# Videos per day per account from .env
_VPD = {
    "terror": max(0, min(6, settings.videos_per_day_terror)),
    "historias": max(0, min(6, settings.videos_per_day_historias)),
    "dinero": max(0, min(6, settings.videos_per_day_dinero)),
}

# Build final ACCOUNTS dict with dynamic schedule windows
_lang = "en" if settings.is_english else "es"
ACCOUNTS = {}
for _acc, _vpd in _VPD.items():
    _cfg = _ACCOUNT_BASE[_lang][_acc].copy()
    _cfg["videos_per_day"] = _vpd
    _cfg["schedule_windows"] = _generate_schedule_windows(_vpd, [(8, 23)])
    # Backwards-compatible "hashtags" key (uses tiktok hashtags by default)
    _cfg["hashtags"] = _cfg["hashtags_tiktok"]
    ACCOUNTS[_acc] = _cfg

# Whisper language code
WHISPER_LANG = "en" if settings.is_english else "es"

# TTS language for gTTS fallback
GTTS_LANG = "en" if settings.is_english else "es"
