"""
ViralStack v1.2 — Centralized configuration.

Everything in this file can be overridden via the .env file.
See `.env.example` for the full list of available knobs.
"""
from __future__ import annotations

import json
import os
import random
import re
import tempfile
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Any, List

BASE_DIR = Path(__file__).resolve().parent.parent
PLATFORMS_FILE = BASE_DIR / "config" / "platforms.json"
PLATFORM_REGISTRY_FILE = BASE_DIR / "config" / "platform_registry.json"
ACCOUNTS_FILE = BASE_DIR / "config" / "accounts.json"
BLACKOUT_FILE = BASE_DIR / "config" / "blackout_dates.json"

VERSION = "1.2.0"

DEFAULT_BUILTIN_ACCOUNTS = ["terror", "historias", "dinero"]

DEFAULT_PLATFORM_REGISTRY: dict[str, dict[str, Any]] = {
    "tiktok": {
        "display_name": "TikTok",
        "short_name": "TT",
        "enabled_by_default": True,
        "publisher": "builtin:tiktok",
        "hashtags_key": "hashtags_tiktok",
        "url_field": "tiktok_url",
        "published_field": "tiktok_published",
        "enabled_field": "tiktok_enabled",
        "supports_direct_publish": True,
    },
    "youtube": {
        "display_name": "YouTube Shorts",
        "short_name": "YT",
        "enabled_by_default": True,
        "publisher": "builtin:youtube",
        "hashtags_key": "hashtags_youtube",
        "url_field": "youtube_url",
        "published_field": "youtube_published",
        "enabled_field": "youtube_enabled",
        "supports_direct_publish": True,
    },
    "instagram": {
        "display_name": "Instagram Reels",
        "short_name": "IG",
        "enabled_by_default": False,
        "publisher": "webhook",
        "webhook_url_env": "INSTAGRAM_WEBHOOK_URL",
        "hashtags_key": "hashtags_instagram",
        "supports_direct_publish": False,
        "manual_url_template": "https://www.instagram.com/{account}/",
    },
}


def resolve_project_path(path: str | os.PathLike | None) -> str:
    """Resolve a user-configured path relative to the project root."""
    if not path:
        return ""
    candidate = Path(path)
    if candidate.is_absolute():
        return str(candidate)
    return str(BASE_DIR / candidate)


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

    # Generic / webhook platforms (v1.2)
    # Instagram can be connected through a webhook automation (Make/Zapier/custom API).
    instagram_webhook_url: str = ""
    platform_webhook_timeout_seconds: int = 120

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
        account_cfg = globals().get("ACCOUNTS", {}).get(account, {})
        per_account = account_cfg.get("quality_threshold")
        if per_account is None:
            per_account = getattr(self, f"quality_threshold_{account}", 0.0) or 0.0
        try:
            per_account = float(per_account)
        except (TypeError, ValueError):
            per_account = 0.0
        return per_account if per_account > 0 else self.quality_threshold

    def get_cookies_path(self, account: str) -> str:
        mapping = {
            "terror": self.tiktok_terror_cookies,
            "historias": self.tiktok_historias_cookies,
            "dinero": self.tiktok_dinero_cookies,
        }
        return resolve_project_path(
            mapping.get(account) or BASE_DIR / "storage" / "cookies" / f"{account}_cookies.txt"
        )

    def get_youtube_token_path(self, account: str) -> str:
        mapping = {
            "terror": self.youtube_terror_token,
            "historias": self.youtube_historias_token,
            "dinero": self.youtube_dinero_token,
        }
        return resolve_project_path(
            mapping.get(account) or BASE_DIR / "config" / f"youtube_{account}_token.json"
        )

    def get_gmail_token_path(self, account: str) -> str:
        mapping = {
            "terror": self.gmail_terror_token,
            "historias": self.gmail_historias_token,
            "dinero": self.gmail_dinero_token,
        }
        return resolve_project_path(
            mapping.get(account) or BASE_DIR / "config" / f"gmail_{account}_token.json"
        )

    class Config:
        env_file = str(BASE_DIR / ".env")
        env_file_encoding = "utf-8"


settings = Settings()


# ============================================================
# PLATFORM REGISTRY + TOGGLES — per account, per platform
# Editable via dashboard / Discord. New platforms can be added in
# config/platform_registry.json without changing the scheduler or pipeline.
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


def _normalize_platform_id(platform: str) -> str:
    """Normalize platform ids used in config files and API routes."""
    return re.sub(r"[^a-z0-9_]+", "_", (platform or "").strip().lower()).strip("_")


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "enabled"}


def _env_value(name: str | None) -> str:
    if not name:
        return ""
    return os.getenv(name, getattr(settings, name.lower(), "") or "")


def _normalize_platform_entry(platform: str, info: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(info or {})
    normalized["id"] = platform
    normalized.setdefault("display_name", platform.replace("_", " ").title())
    normalized.setdefault("short_name", platform[:2].upper())
    normalized["enabled_by_default"] = _coerce_bool(
        normalized.get("enabled_by_default"), False,
    )
    normalized.setdefault("publisher", "manual")
    normalized.setdefault("hashtags_key", f"hashtags_{platform}")
    normalized["supports_direct_publish"] = _coerce_bool(
        normalized.get("supports_direct_publish"),
        str(normalized.get("publisher", "")).startswith("builtin:"),
    )
    return normalized


def load_platform_registry() -> dict[str, dict[str, Any]]:
    """Load known platforms, merging defaults with config/platform_registry.json."""
    registry: dict[str, dict[str, Any]] = {
        key: dict(value) for key, value in DEFAULT_PLATFORM_REGISTRY.items()
    }

    if PLATFORM_REGISTRY_FILE.exists():
        try:
            data = json.loads(PLATFORM_REGISTRY_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                raw_platforms = data.get("platforms", data)
                if isinstance(raw_platforms, dict):
                    for raw_id, raw_info in raw_platforms.items():
                        platform = _normalize_platform_id(raw_id)
                        if not platform or not isinstance(raw_info, dict):
                            continue
                        merged = dict(registry.get(platform, {}))
                        merged.update(raw_info)
                        registry[platform] = merged
        except (json.JSONDecodeError, OSError):
            pass

    return {
        platform: _normalize_platform_entry(platform, info)
        for platform, info in registry.items()
    }


def list_platform_ids() -> List[str]:
    """All platforms known by the current registry."""
    return list(load_platform_registry().keys())


def get_platform_info(platform: str) -> dict[str, Any]:
    """Return registry metadata for a platform id, or an empty dict."""
    normalized = _normalize_platform_id(platform)
    return load_platform_registry().get(normalized, {})


def is_platform_supported(platform: str) -> bool:
    return bool(get_platform_info(platform))


def platform_display_name(platform: str) -> str:
    info = get_platform_info(platform)
    return info.get("display_name") or platform.replace("_", " ").title()


def platform_short_name(platform: str) -> str:
    info = get_platform_info(platform)
    return info.get("short_name") or platform[:2].upper()


def platform_hashtags_for(account: str, platform: str) -> list[str]:
    """Resolve account hashtags for a platform with sensible fallbacks."""
    cfg = ACCOUNTS.get(account, {}) if "ACCOUNTS" in globals() else {}
    info = get_platform_info(platform)
    keys = [
        info.get("hashtags_key"),
        f"hashtags_{_normalize_platform_id(platform)}",
        "hashtags",
        "hashtags_tiktok",
    ]
    for key in keys:
        if key and cfg.get(key):
            return list(cfg.get(key) or [])
    return []


def platform_webhook_url(platform: str) -> str:
    """Resolve a webhook URL configured for a platform, if any."""
    info = get_platform_info(platform)
    return (
        info.get("webhook_url")
        or _env_value(info.get("webhook_url_env"))
        or ""
    )


def load_platform_config() -> dict:
    """Load platform toggles from JSON file and normalize missing accounts/platforms."""
    data = {}
    if PLATFORMS_FILE.exists():
        try:
            loaded = json.loads(PLATFORMS_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except (json.JSONDecodeError, OSError):
            data = {}
    return _normalize_platform_config(data)


def save_platform_config(config: dict):
    """Save platform toggles to JSON file (atomic write)."""
    _atomic_write_json(PLATFORMS_FILE, _normalize_platform_config(config))


def _build_default_platforms() -> dict:
    """Build default platforms dict from registered accounts."""
    registry = load_platform_registry()
    return {
        acc: {
            platform: bool(info.get("enabled_by_default", False))
            for platform, info in registry.items()
        }
        for acc in _registered_accounts()
    }


def _registered_accounts() -> list:
    """List of account ids — ACCOUNTS dict if available, else built-in defaults."""
    try:
        return list(ACCOUNTS.keys())
    except NameError:
        return list(DEFAULT_BUILTIN_ACCOUNTS)


def _normalize_platform_config(data: dict | None) -> dict:
    """Ensure every account has every known platform toggle."""
    registry = load_platform_registry()
    defaults = {
        platform: bool(info.get("enabled_by_default", False))
        for platform, info in registry.items()
    }
    data = data if isinstance(data, dict) else {}
    account_ids = list(dict.fromkeys([*_registered_accounts(), *data.keys()]))
    normalized = {}

    for account in account_ids:
        account_cfg = dict(defaults)
        if "ACCOUNTS" in globals():
            account_meta = ACCOUNTS.get(account, {})
            declared = account_meta.get("platforms")
            if isinstance(declared, dict):
                for raw_platform, raw_enabled in declared.items():
                    platform = _normalize_platform_id(raw_platform)
                    if platform in registry:
                        account_cfg[platform] = _coerce_bool(raw_enabled, account_cfg.get(platform, False))

        raw_toggles = data.get(account, {})
        if isinstance(raw_toggles, dict):
            for raw_platform, raw_enabled in raw_toggles.items():
                platform = _normalize_platform_id(raw_platform)
                if not platform:
                    continue
                if platform not in registry:
                    continue
                account_cfg[platform] = _coerce_bool(raw_enabled, account_cfg.get(platform, False))

        normalized[account] = account_cfg

    return normalized


def ensure_platform_config() -> dict:
    """Create or refresh platforms.json when registry/accounts changed."""
    current = {}
    if PLATFORMS_FILE.exists():
        try:
            loaded = json.loads(PLATFORMS_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                current = loaded
        except (json.JSONDecodeError, OSError):
            current = {}
    normalized = _normalize_platform_config(current)
    if normalized != current:
        save_platform_config(normalized)
    return normalized


def is_platform_enabled(account: str, platform: str) -> bool:
    """Check if a platform is enabled for an account."""
    platform = _normalize_platform_id(platform)
    if not is_platform_supported(platform):
        return False
    config = load_platform_config()
    default = bool(get_platform_info(platform).get("enabled_by_default", False))
    return bool(config.get(account, {}).get(platform, default))


def enabled_platforms_for(account: str) -> list[str]:
    """Return platform ids enabled for an account, in registry order."""
    return [platform for platform in list_platform_ids() if is_platform_enabled(account, platform)]


def toggle_platform(account: str, platform: str, enabled: bool) -> dict:
    """Toggle a platform for an account. Returns updated config."""
    platform = _normalize_platform_id(platform)
    if not is_platform_supported(platform):
        raise ValueError(f"Unsupported platform: {platform}")
    config = load_platform_config()
    if account not in config:
        config[account] = _build_default_platforms().get(account, {})
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

_ACCOUNT_COMMON_DEFAULTS = {
    "min_words": 80,
    "max_words": 240,
    "duration_min_seconds": settings.min_video_seconds,
    "duration_max_seconds": settings.max_video_seconds,
    "hook_min_words": 5,
    "hook_max_words": 16,
    "quality_threshold": 0.0,
    "image_style": "Cinematic, photorealistic, detailed, vertical 9:16 composition",
    "image_style_fallback": "Photorealistic cinematic vertical scene",
    "emergency_color": "0x1C1C1C",
    "apply_horror_filter": False,
    "youtube_category_id": "24",
    "drive_folder_name": None,
    "platforms": {},
}

_ACCOUNT_V12_OVERRIDES = {
    "terror": {
        "min_words": 85,
        "max_words": 240,
        "hook_min_words": 5,
        "hook_max_words": 14,
        "image_style": (
            "Dark horror atmosphere, eerie shadows, dim cold lighting, "
            "desaturated colors with blue-green tint, fog, cinematic horror movie style, "
            "high contrast, photorealistic, 9:16 vertical composition"
        ),
        "image_style_fallback": (
            "Abandoned room, ominous silhouette, eerie shadows, cinematic horror, "
            "photorealistic, vertical 9:16"
        ),
        "emergency_color": "0x11171F",
        "apply_horror_filter": True,
        "youtube_category_id": "24",
    },
    "historias": {
        "min_words": 80,
        "max_words": 240,
        "hook_min_words": 6,
        "hook_max_words": 16,
        "image_style": (
            "Cinematic storytelling atmosphere, warm dramatic lighting, "
            "emotional and immersive, photorealistic, detailed textures, "
            "documentary style, 9:16 vertical composition"
        ),
        "image_style_fallback": (
            "Real-life dramatic moment, emotional storytelling, cinematic, "
            "photorealistic, vertical 9:16"
        ),
        "emergency_color": "0x2B211C",
        "youtube_category_id": "24",
    },
    "dinero": {
        "min_words": 80,
        "max_words": 250,
        "hook_min_words": 5,
        "hook_max_words": 15,
        "image_style": (
            "Modern professional aesthetic, clean composition, "
            "luxury and success imagery, bright motivational lighting, "
            "business and finance visuals, photorealistic, 9:16 vertical composition"
        ),
        "image_style_fallback": (
            "Modern finance success scene, clean composition, cinematic, "
            "photorealistic, vertical 9:16"
        ),
        "emergency_color": "0x182328",
        "youtube_category_id": "27",
    },
}


def _merge_account_defaults(account: str, config: dict) -> dict:
    """Apply v1.2 account defaults while preserving user-provided fields."""
    merged = dict(_ACCOUNT_COMMON_DEFAULTS)
    merged.update(_ACCOUNT_V12_OVERRIDES.get(account, {}))
    merged.update(config or {})
    if not merged.get("hashtags_instagram"):
        merged["hashtags_instagram"] = list(
            merged.get("hashtags_tiktok") or merged.get("hashtags") or ["#reels", "#viral"]
        )
    return merged

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
    _cfg = _merge_account_defaults(_acc, _ACCOUNT_BASE[_lang][_acc].copy())
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
        acc_id = re.sub(r"[^a-z0-9_]+", "_", (entry.get("id") or "").strip().lower()).strip("_")
        if not acc_id or acc_id in ACCOUNTS:
            continue
        try:
            vpd = max(0, min(6, int(entry.get("videos_per_day", 1))))
        except (TypeError, ValueError):
            vpd = 1

        cfg = _merge_account_defaults(acc_id, dict(entry))
        cfg.pop("id", None)
        cfg.setdefault("display_name", acc_id.title())
        cfg.setdefault("description", "")
        cfg.setdefault("voice", "kore")
        cfg.setdefault("voice_fallback", "en-US-GuyNeural" if settings.is_english else "es-MX-JorgeNeural")
        cfg.setdefault("music_mood", "motivational")
        cfg["hashtags_tiktok"] = list(cfg.get("hashtags_tiktok") or cfg.get("hashtags") or ["#fyp", "#viral"])
        cfg["hashtags_youtube"] = list(cfg.get("hashtags_youtube") or ["#shorts", "#viral"])
        cfg["hashtags_instagram"] = list(cfg.get("hashtags_instagram") or cfg["hashtags_tiktok"])
        cfg["videos_per_day"] = vpd
        cfg["schedule_windows"] = (
            cfg.get("schedule_windows")
            if isinstance(cfg.get("schedule_windows"), list)
            else _generate_schedule_windows(vpd)
        )
        cfg["is_custom"] = True
        cfg["hashtags"] = cfg["hashtags_tiktok"]
        ACCOUNTS[acc_id] = cfg


_load_custom_accounts()


def get_cookies_path_for(account: str) -> str:
    """Resolve TikTok cookies path for an account (built-in or custom)."""
    cfg = ACCOUNTS.get(account, {})
    custom = cfg.get("tiktok_cookies_path")
    if custom:
        return resolve_project_path(custom)
    return settings.get_cookies_path(account)


def get_youtube_token_path_for(account: str) -> str:
    cfg = ACCOUNTS.get(account, {})
    custom = cfg.get("youtube_token_path")
    if custom:
        return resolve_project_path(custom)
    return settings.get_youtube_token_path(account)


def get_gmail_token_path_for(account: str) -> str:
    cfg = ACCOUNTS.get(account, {})
    custom = cfg.get("gmail_token_path")
    if custom:
        return resolve_project_path(custom)
    return settings.get_gmail_token_path(account)


def list_account_ids() -> List[str]:
    """All account ids currently registered (built-in + custom)."""
    return list(ACCOUNTS.keys())


ensure_platform_config()

# Whisper language code
WHISPER_LANG = "en" if settings.is_english else "es"

# TTS language for gTTS fallback
GTTS_LANG = "en" if settings.is_english else "es"
