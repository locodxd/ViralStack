"""
ViralStack v1.1 — Centralized configuration.

Everything in this file can be overridden via the .env file.
See `.env.example` for the full list of available knobs.
"""
import json
import os
import random
import tempfile
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
PLATFORMS_FILE = BASE_DIR / "config" / "platforms.json"
ACCOUNTS_FILE = BASE_DIR / "config" / "accounts.json"
BLACKOUT_FILE = BASE_DIR / "config" / "blackout_dates.json"

VERSION = "1.1.0"


class Settings(BaseSettings):
    # === Version ===
    version: str = VERSION

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
    gemini_models: str = "gemini-3.1-pro-preview,gemini-3-flash-preview,gemini-3.1-flash-lite-preview,gemini-2.5-pro,gemini-2.5-flash"

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
    log_format: str = "text"  # "text" or "json" (structured logging)
    log_mask_secrets: bool = True
    quality_threshold: float = 6.0
    quality_threshold_terror: float = 0.0   # 0 = use global
    quality_threshold_historias: float = 0.0
    quality_threshold_dinero: float = 0.0
    max_retries_per_video: int = 3
    pipeline_timeout_seconds: int = 1800     # 30 min hard timeout per video
    publish_inter_platform_delay: float = 4.0  # seconds between platform uploads to avoid IP-block patterns
    whisper_model: str = "base"              # tiny | base | small | medium | large-v3
    whisper_device: str = "cpu"              # cpu | cuda | auto
    whisper_compute_type: str = "int8"       # int8 | float16 | float32

    # FFmpeg — on Linux VPS use "ffmpeg" (system), on Windows use local binary
    ffmpeg_path: str = "ffmpeg"
    ffmpeg_threads: int = 0                  # 0 = auto

    # Short-form video pacing
    min_video_seconds: int = 30
    max_video_seconds: int = 90
    image_display_seconds: float = 5.5
    crossfade_duration: float = 0.3
    music_volume_percent: float = 5.0        # 0-100
    narration_volume_boost: float = 1.3
    ken_burns_max_zoom: float = 1.15
    ken_burns_max_pan_pixels: int = 40
    video_fps: int = 30

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
    subtitle_primary_color: str = "&H00FFFFFF"   # ASS BGR
    subtitle_outline_color: str = "&H00000000"

    # Optional platform extras
    enable_drive_upload: bool = False
    drive_root_folder: str = "ViralStack Videos"
    drive_dedupe: bool = True

    # Video quality preset
    video_crf: int = 20
    video_preset: str = "medium"
    video_bitrate_audio: str = "192k"
    video_width: int = 1080
    video_height: int = 1920

    # Dashboard
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8000
    dashboard_api_key: str = ""              # if set, ALL /api/* endpoints require X-API-Key header
    dashboard_enable_cors: bool = False
    dashboard_cors_origins: str = "*"        # comma-separated
    dashboard_default_page_size: int = 50
    dashboard_max_page_size: int = 500
    dashboard_auto_refresh_seconds: int = 60

    # Timezone for scheduler (use your TikTok audience timezone)
    timezone: str = "America/New_York"

    # === SCHEDULER (NEW in v1.1) ===
    schedule_hour_start: int = 8             # earliest possible publish hour
    schedule_hour_end: int = 22              # latest possible publish hour
    schedule_jitter_seconds: int = 600       # ± random jitter from APScheduler
    schedule_skip_weekends: bool = False
    schedule_misfire_grace_seconds: int = 3600
    email_poll_interval_minutes: int = 30
    daily_stats_hour: int = 23
    daily_stats_minute: int = 55
    morning_stats_hour: int = 8
    morning_stats_minute: int = 0

    # === ROTATION & RESILIENCE (NEW in v1.1) ===
    key_cooldown_seconds: int = 300
    key_max_failures_before_cooldown: int = 3
    model_failure_cache_ttl: int = 900
    fallback_chain_max_retries: int = 2
    fallback_chain_base_backoff: float = 2.0
    fallback_chain_max_backoff: float = 16.0

    # === SCRIPT GEN (NEW in v1.1) ===
    script_max_retries: int = 3
    script_dedup_history_size: int = 50
    script_words_per_second: float = 2.6
    script_max_visual_prompts: int = 18
    script_max_hashtags: int = 15

    # === BACKUPS (NEW in v1.1) ===
    enable_db_backup: bool = True
    db_backup_hour: int = 3
    db_backup_keep_days: int = 14
    db_backup_dir: str = str(BASE_DIR / "storage" / "backups")

    # === MULTI-CHANNEL NOTIFICATIONS (NEW in v1.1) ===
    slack_webhook_url: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    generic_webhook_url: str = ""            # POSTs JSON {level,title,description,account,ts}
    notification_min_level: str = "info"     # info | warning | error | urgent
    notification_rate_limit_per_minute: int = 30

    # === EMAIL AGENT (NEW in v1.1) ===
    email_pricing_mention_15s: int = 15
    email_pricing_video_dedicado: int = 25
    email_pricing_link_bio_1mes: int = 40
    email_signature: str = ""                # appended to all auto-replies

    # === DISCORD (NEW in v1.1) ===
    discord_status_message: str = "ViralStack"
    discord_send_tracebacks: bool = False    # if False, only message goes; full traceback to logs

    # === HEALTH (NEW in v1.1) ===
    health_max_failed_streak: int = 5        # alert if N pipeline failures in a row

    # === MULTI-LLM SCRIPT GENERATION (NEW in v1.1) ===
    # Comma-separated chain of providers to try, in order, until one returns a usable script.
    # Available: gemini, openai, anthropic, openrouter, groq, deepseek, together, mistral, ollama
    script_provider_chain: str = "gemini,openai,anthropic,openrouter,groq,deepseek,together,mistral,ollama"

    # OpenAI
    openai_api_keys: str = ""
    openai_models: str = "gpt-5.4,gpt-5.4-mini,gpt-5.4-nano"

    # Anthropic Claude
    anthropic_api_keys: str = ""
    anthropic_models: str = "claude-opus-4-7,claude-sonnet-4-6,claude-haiku-4-5"

    # OpenRouter (any model id `vendor/model`)
    openrouter_api_keys: str = ""
    openrouter_models: str = "openai/gpt-5.4,anthropic/claude-opus-4.7,anthropic/claude-sonnet-4.6,google/gemini-3.1-pro-preview,google/gemini-3-flash-preview,deepseek/deepseek-chat"

    # Groq (super fast inference)
    groq_api_keys: str = ""
    groq_models: str = "openai/gpt-oss-120b,openai/gpt-oss-20b,llama-3.3-70b-versatile,llama-3.1-8b-instant,groq/compound-mini"

    # DeepSeek
    deepseek_api_keys: str = ""
    deepseek_models: str = "deepseek-chat,deepseek-reasoner"

    # Together AI
    together_api_keys: str = ""
    together_models: str = "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8,meta-llama/Llama-4-Scout-17B-16E-Instruct,deepseek-ai/DeepSeek-V3.1,Qwen/Qwen3-Next-80B-A3B-Instruct,moonshotai/Kimi-K2-Instruct"

    # Mistral La Plateforme
    mistral_api_keys: str = ""
    mistral_models: str = "mistral-medium-2508,mistral-large-latest,mistral-small-latest,devstral-medium-latest,codestral-latest"

    # Ollama (local — no API key needed)
    ollama_enabled: bool = False
    ollama_base_url: str = "http://localhost:11434"
    ollama_models: str = "qwen3:latest,qwen3:30b,qwen3:235b,qwen3-vl:8b,qwen3-coder-next,llama3.3,gpt-oss:20b"

    @property
    def is_english(self) -> bool:
        return self.language.lower().startswith("en")

    @property
    def gemini_models_list(self) -> List[str]:
        return [m.strip() for m in self.gemini_models.split(",") if m.strip()]

    @property
    def elevenlabs_keys_list(self) -> List[str]:
        return [k.strip() for k in self.elevenlabs_api_keys.split(",") if k.strip()]

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.dashboard_cors_origins.split(",") if o.strip()]

    def quality_threshold_for(self, account: str) -> float:
        """Return per-account quality threshold or fall back to global."""
        per_account = getattr(self, f"quality_threshold_{account}", 0.0) or 0.0
        return per_account if per_account > 0 else self.quality_threshold

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


def _atomic_write_json(path: Path, data) -> None:
    """Write JSON atomically (tmp file + rename) so concurrent reads never see a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_platform_config() -> dict:
    """Load platform toggles from JSON file."""
    if PLATFORMS_FILE.exists():
        try:
            data = json.loads(PLATFORMS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return _build_default_platforms()


def save_platform_config(config: dict):
    """Save platform toggles to JSON file (atomic write)."""
    _atomic_write_json(PLATFORMS_FILE, config)


def _build_default_platforms() -> dict:
    """Build default platforms dict from registered accounts."""
    return {acc: {"tiktok": True, "youtube": True} for acc in _registered_accounts()}


def _registered_accounts() -> list:
    """List of account ids — ACCOUNTS dict if available, else built-in defaults."""
    try:
        return list(ACCOUNTS.keys())
    except NameError:
        return ["terror", "historias", "dinero"]


def is_platform_enabled(account: str, platform: str) -> bool:
    """Check if a platform is enabled for an account."""
    config = load_platform_config()
    return config.get(account, {}).get(platform, True)


def toggle_platform(account: str, platform: str, enabled: bool) -> dict:
    """Toggle a platform for an account. Returns updated config."""
    config = load_platform_config()
    if account not in config:
        config[account] = {"tiktok": True, "youtube": True}
    config[account][platform] = bool(enabled)
    save_platform_config(config)
    return config


def load_blackout_dates() -> list:
    """Load list of dates (YYYY-MM-DD) where production should NOT run."""
    if BLACKOUT_FILE.exists():
        try:
            data = json.loads(BLACKOUT_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [str(d) for d in data]
        except (json.JSONDecodeError, OSError):
            pass
    return []


def save_blackout_dates(dates: list) -> None:
    _atomic_write_json(BLACKOUT_FILE, sorted(set(str(d) for d in dates)))


# Initialize platforms.json if it doesn't exist
if not PLATFORMS_FILE.exists():
    save_platform_config(_build_default_platforms())


# ============================================================
# LANGUAGE-AWARE CONFIGURATIONS
# ============================================================

PRICING = {
    "mencion_15s": settings.email_pricing_mention_15s,      # USD
    "video_dedicado": settings.email_pricing_video_dedicado,
    "link_bio_1mes": settings.email_pricing_link_bio_1mes,
}


def _rand_minute() -> int:
    """Generate a random non-round minute (avoids :00, :15, :30, :45)."""
    blocked = {0, 15, 30, 45}
    return random.choice([x for x in range(1, 60) if x not in blocked])


def _generate_schedule_windows(n: int, hour_ranges: list[tuple[int, int]] = None) -> list[dict]:
    """Generate N random schedule windows spread across configured hours."""
    if n <= 0:
        return []

    n = min(n, 6)  # Hard cap

    # Use settings, with safe fallbacks
    h_start = max(0, min(23, settings.schedule_hour_start))
    h_end = max(h_start + 1, min(24, settings.schedule_hour_end + 1))
    all_hours = list(range(h_start, h_end))
    if not all_hours:
        all_hours = list(range(8, 23))

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
    _cfg["schedule_windows"] = _generate_schedule_windows(_vpd)
    # Backwards-compatible "hashtags" key (uses tiktok hashtags by default)
    _cfg["hashtags"] = _cfg["hashtags_tiktok"]
    ACCOUNTS[_acc] = _cfg


# ============================================================
# CUSTOM ACCOUNTS — load any extra accounts the user defines in
# config/accounts.json. This lets users add a 4th, 5th, ... niche
# without editing source code.
#
# accounts.json schema (list of objects):
# [
#   {
#     "id": "tech",
#     "display_name": "Tech News",
#     "description": "Daily tech news shorts",
#     "voice": "kore",
#     "voice_fallback": "en-US-GuyNeural",
#     "music_mood": "motivational",
#     "videos_per_day": 2,
#     "hashtags_tiktok": ["#tech", "#fyp"],
#     "hashtags_youtube": ["#tech", "#shorts"],
#     "youtube_token_path": "config/youtube_tech_token.json",
#     "tiktok_cookies_path": "storage/cookies/tech_cookies.txt",
#     "gmail_token_path": "config/gmail_tech_token.json",
#     "prompt_file": "config/prompts/tech.yaml"
#   }
# ]
# ============================================================

def _load_custom_accounts() -> None:
    if not ACCOUNTS_FILE.exists():
        return
    try:
        data = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    if not isinstance(data, list):
        return

    for entry in data:
        if not isinstance(entry, dict):
            continue
        acc_id = (entry.get("id") or "").strip().lower()
        if not acc_id or acc_id in ACCOUNTS:
            continue
        vpd = max(0, min(6, int(entry.get("videos_per_day", 1))))
        cfg = {
            "display_name": entry.get("display_name", acc_id.title()),
            "description": entry.get("description", ""),
            "voice": entry.get("voice", "kore"),
            "voice_fallback": entry.get("voice_fallback", "es-MX-JorgeNeural"),
            "music_mood": entry.get("music_mood", "motivational"),
            "hashtags_tiktok": entry.get("hashtags_tiktok") or ["#fyp", "#viral"],
            "hashtags_youtube": entry.get("hashtags_youtube") or ["#shorts", "#viral"],
            "videos_per_day": vpd,
            "schedule_windows": _generate_schedule_windows(vpd),
            "youtube_token_path": entry.get("youtube_token_path"),
            "tiktok_cookies_path": entry.get("tiktok_cookies_path"),
            "gmail_token_path": entry.get("gmail_token_path"),
            "prompt_file": entry.get("prompt_file"),
            "is_custom": True,
        }
        cfg["hashtags"] = cfg["hashtags_tiktok"]
        ACCOUNTS[acc_id] = cfg


_load_custom_accounts()


def get_cookies_path_for(account: str) -> str:
    """Resolve TikTok cookies path for an account (built-in or custom)."""
    cfg = ACCOUNTS.get(account, {})
    custom = cfg.get("tiktok_cookies_path")
    if custom:
        return str(custom)
    return settings.get_cookies_path(account)


def get_youtube_token_path_for(account: str) -> str:
    cfg = ACCOUNTS.get(account, {})
    custom = cfg.get("youtube_token_path")
    if custom:
        return str(custom)
    return settings.get_youtube_token_path(account)


def get_gmail_token_path_for(account: str) -> str:
    cfg = ACCOUNTS.get(account, {})
    custom = cfg.get("gmail_token_path")
    if custom:
        return str(custom)
    return settings.get_gmail_token_path(account)


def list_account_ids() -> List[str]:
    """All account ids currently registered (built-in + custom)."""
    return list(ACCOUNTS.keys())

# Whisper language code
WHISPER_LANG = "en" if settings.is_english else "es"

# TTS language for gTTS fallback
GTTS_LANG = "en" if settings.is_english else "es"
