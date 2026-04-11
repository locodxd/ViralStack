"""
Smart model rotation with failure cache — Vertex AI edition.

Strategy:
- Single Vertex AI API key (configured in .env)
- Rotates across Gemini models in priority order
- A failure cache remembers which models failed recently
  so we don't waste time retrying until the cache expires.
- Cache auto-resets every CACHE_TTL_SECONDS to retry previously failed models.

For non-Gemini providers (elevenlabs): same round-robin key pool as before.
"""
import logging
import time
from datetime import datetime, timedelta
from contextlib import contextmanager
from typing import Optional
from sqlalchemy import and_
from core.db import get_session
from core.models import ApiKey
from core import discord_alerts
from config.settings import settings

logger = logging.getLogger(__name__)

COOLDOWN_SECONDS = 300          # 5 min cooldown on repeated failures
MAX_FAILURES_BEFORE_COOLDOWN = 3
CACHE_TTL_SECONDS = 900         # 15 min — then retry failed models


class NoKeysAvailableError(Exception):
    pass


# ============================================================
# Failure cache: tracks models that failed recently
# ============================================================
_failure_cache: dict[str, float] = {}   # model -> timestamp of failure
_cache_last_reset: float = time.time()


def _cache_is_failed(model: str) -> bool:
    """Check if a model is in the failure cache."""
    global _cache_last_reset

    now = time.time()
    if now - _cache_last_reset > CACHE_TTL_SECONDS:
        _failure_cache.clear()
        _cache_last_reset = now
        logger.info("Model failure cache reset (TTL %ds)", CACHE_TTL_SECONDS)
        return False

    ts = _failure_cache.get(model)
    if ts is None:
        return False

    if now - ts > CACHE_TTL_SECONDS:
        del _failure_cache[model]
        return False

    return True


def _cache_mark_failed(model: str):
    """Mark a model as failed."""
    _failure_cache[model] = time.time()


def _cache_mark_success(model: str):
    """Remove a model from failure cache on success."""
    _failure_cache.pop(model, None)


# ============================================================
# KeyPool — round-robin for non-Gemini providers
# ============================================================

class KeyPool:
    """Round-robin API key pool with cooldown and exhaustion tracking."""

    def __init__(self, provider: str):
        self.provider = provider

    def _get_available_key(self, session) -> ApiKey:
        now = datetime.utcnow()
        key = (
            session.query(ApiKey)
            .filter(
                and_(
                    ApiKey.provider == self.provider,
                    ApiKey.enabled == True,
                    (ApiKey.cooldown_until == None) | (ApiKey.cooldown_until <= now),
                )
            )
            .order_by(ApiKey.last_used_at.asc().nullsfirst())
            .first()
        )
        if not key:
            raise NoKeysAvailableError(f"No available keys for '{self.provider}'")
        return key

    @contextmanager
    def acquire(self):
        """Acquire a key. For non-gemini providers."""
        with get_session() as session:
            key = self._get_available_key(session)
            key.last_used_at = datetime.utcnow()
            key.usage_count += 1
            session.commit()
            key_id = key.id
            key_value = key.api_key
            key_label = key.label or f"key_{key.id}"

        logger.debug("Acquired key %s for %s", key_label, self.provider)
        try:
            yield key_value
            self._report_success(key_id)
        except Exception as e:
            self._report_failure(key_id, str(e))
            raise

    def _report_success(self, key_id: int):
        with get_session() as session:
            key = session.query(ApiKey).filter_by(id=key_id).first()
            if key:
                key.failure_count = 0

    def _report_failure(self, key_id: int, error: str = ""):
        with get_session() as session:
            key = session.query(ApiKey).filter_by(id=key_id).first()
            if not key:
                return
            key.failure_count += 1
            if key.failure_count >= MAX_FAILURES_BEFORE_COOLDOWN:
                key.cooldown_until = datetime.utcnow() + timedelta(seconds=COOLDOWN_SECONDS)
                logger.warning("Key %s (%s) in cooldown for %ds", key.label, self.provider, COOLDOWN_SECONDS)


# ============================================================
# GeminiRotator — model rotation with Vertex AI client
# ============================================================

class GeminiRotator:
    """
    Tries Gemini models in priority order via a single Vertex AI client:
    - Preferred models first, then remaining as fallback
    - Skips models that recently failed (cache)
    - Cache auto-resets every 15 min so we retry everything
    """

    def call(self, build_request, preferred_models: list[str] = None, **kwargs):
        """
        Execute a Gemini API call with automatic model rotation.

        Args:
            build_request: callable(client, model_name) -> response
                The caller provides a function that takes a genai.Client and model name,
                and makes the actual API call.
            preferred_models: optional list of model names to try FIRST, in order.
                If None, uses the default list from settings.

        Returns:
            (response, model_name) tuple — the successful response and which model worked.

        Raises:
            NoKeysAvailableError if all models exhausted.
        """
        from core.vertex_client import get_client

        client = get_client()

        all_models = settings.gemini_models_list
        if not all_models:
            raise NoKeysAvailableError("No Gemini models configured")

        # Build model order: preferred first, then remaining as fallback
        if preferred_models:
            models = list(preferred_models)
            for m in all_models:
                if m not in models:
                    models.append(m)
        else:
            models = all_models

        errors = []

        for model_name in models:
            # Skip cached failures
            if _cache_is_failed(model_name):
                continue

            try:
                response = build_request(client, model_name)

                # Success!
                _cache_mark_success(model_name)
                logger.info("Gemini OK: model=%s (Vertex AI)", model_name)
                return response, model_name

            except Exception as e:
                error_str = str(e)
                _cache_mark_failed(model_name)
                errors.append(f"{model_name}: {error_str[:120]}")
                logger.warning("Gemini fail: model=%s: %s", model_name, error_str[:150])

                # If it's a quota/rate error, mark and continue to next model
                lower = error_str.lower()
                if any(x in lower for x in ["quota", "rate limit", "429", "resource exhausted"]):
                    logger.info("Rate limit on model %s, trying next model", model_name)

        # All models failed
        summary = "\n".join(errors[-10:])
        msg = f"All Gemini models failed (Vertex AI):\n```\n{summary}\n```"
        logger.error(msg)
        discord_alerts.send_error(msg)
        raise NoKeysAvailableError(msg)


# Singleton
gemini_rotator = GeminiRotator()


# ============================================================
# Seed keys from .env into database
# ============================================================

def seed_keys_from_settings():
    """Populate API keys from settings if they don't exist yet.

    Note: Gemini now uses Vertex AI with a single API key configured
    in VERTEX_AI_API_KEY, so we no longer seed Gemini keys into the DB.
    Only non-Gemini providers (elevenlabs) are seeded here.
    """
    providers_keys = {
        "elevenlabs": settings.elevenlabs_keys_list,
    }

    with get_session() as session:
        for provider, keys in providers_keys.items():
            if not keys:
                continue

            existing = session.query(ApiKey).filter_by(provider=provider).count()
            if existing > 0:
                if existing != len(keys):
                    logger.info("Updating %s keys (had %d, now %d)", provider, existing, len(keys))
                    session.query(ApiKey).filter_by(provider=provider).delete()
                    session.commit()
                else:
                    continue

            for i, key_value in enumerate(keys):
                key = ApiKey(
                    provider=provider,
                    label=f"{provider}_{i+1}",
                    api_key=key_value,
                    enabled=True,
                )
                session.add(key)

            logger.info("Seeded %d keys for '%s'", len(keys), provider)
