"""
Central Vertex AI client factory.

All modules that need a Gemini client should use `get_client()` from here.
This ensures a single, consistent Vertex AI configuration across the project.
"""
import logging
from functools import lru_cache

from config.settings import settings

logger = logging.getLogger(__name__)

_client_instance = None


def get_client():
    """Return a cached Vertex AI genai.Client instance.

    Uses the Vertex AI API key from settings. The client is created once
    and reused for the lifetime of the process.
    """
    global _client_instance
    if _client_instance is not None:
        return _client_instance

    from google import genai

    api_key = settings.vertex_ai_api_key
    if not api_key:
        raise RuntimeError(
            "VERTEX_AI_API_KEY is not set. "
            "Add it to your .env file to use Vertex AI."
        )

    # Vertex AI API keys are self-contained (project is encoded in the key).
    # project/location and api_key are mutually exclusive in the SDK.
    _client_instance = genai.Client(vertexai=True, api_key=api_key)
    logger.info("Vertex AI client initialized with API key")
    return _client_instance


def reset_client():
    """Force re-creation of the client (useful after config changes)."""
    global _client_instance
    _client_instance = None
