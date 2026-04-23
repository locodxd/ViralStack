"""
ViralStack v1.1 — Unified multi-LLM text generation.

Supported providers (all optional, only those with credentials are activated):
- gemini      → Google Generative AI (gemini-* via google-genai client over Vertex/keys)
- vertex      → same client, but explicit project/location route
- openai      → OpenAI Chat Completions API (gpt-4o, gpt-4o-mini, o1-mini, gpt-4-turbo, ...)
- anthropic   → Anthropic Messages API (claude-3-5-sonnet-*, claude-3-haiku-*, claude-3-opus-*)
- groq        → Groq API (llama-3.3-70b-versatile, mixtral-8x7b-32768, ...)
- openrouter  → OpenRouter unified API (any model id `vendor/model`)
- mistral     → Mistral La Plateforme (mistral-large-latest, ...)
- deepseek    → DeepSeek API (deepseek-chat, deepseek-reasoner)
- together    → Together AI
- ollama      → Local Ollama daemon (no key needed) — ideal for self-hosters

Each provider is selected from `settings.script_provider_chain` (e.g. "gemini,openai,anthropic").

Public API:
    `generate_text(prompt, *, system=None, temperature=0.7, max_tokens=4000,
                   preferred_chain=None, account=None) -> LLMResult`
    Tries providers in order; on transient failure (rate-limit, 5xx) moves to the next.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result + error types
# ---------------------------------------------------------------------------

@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    usage: dict = field(default_factory=dict)
    raw: object = None

    def __bool__(self) -> bool:
        return bool(self.text)


class ProviderUnavailable(Exception):
    """No credentials / SDK for this provider."""


class ProviderTransientError(Exception):
    """Rate-limit, 5xx, network blip — try the next provider."""


class ProviderHardError(Exception):
    """Auth / 4xx — don't retry the same provider."""


# ---------------------------------------------------------------------------
# Provider base
# ---------------------------------------------------------------------------

class BaseProvider:
    name: str = "base"
    default_model: str = ""

    def is_available(self) -> bool:  # pragma: no cover - trivial
        return False

    def models(self) -> List[str]:
        return [self.default_model] if self.default_model else []

    def generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4000,
        timeout: float = 120.0,
    ) -> LLMResult:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _csv(value: str) -> List[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _httpx_post(url: str, headers: dict, payload: dict, timeout: float) -> httpx.Response:
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(url, headers=headers, json=payload)
        if r.status_code in (429,) or 500 <= r.status_code < 600:
            raise ProviderTransientError(f"{r.status_code}: {r.text[:200]}")
        if r.status_code >= 400:
            raise ProviderHardError(f"{r.status_code}: {r.text[:200]}")
        return r
    except httpx.TimeoutException as e:
        raise ProviderTransientError(f"timeout: {e}")
    except httpx.NetworkError as e:
        raise ProviderTransientError(f"network: {e}")


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

class GeminiProvider(BaseProvider):
    """Routes through the existing GeminiRotator — already handles key+model rotation."""

    name = "gemini"

    def __init__(self):
        self._rotator = None

    def _get_rotator(self):
        if self._rotator is None:
            from core.key_rotation import gemini_rotator
            self._rotator = gemini_rotator
        return self._rotator

    def is_available(self) -> bool:
        try:
            rot = self._get_rotator()
            # consider available if at least one key OR vertex is configured
            return bool(getattr(rot, "key_pool", None) and rot.key_pool.available_keys()) or \
                bool(settings.vertex_ai_project)
        except Exception:
            return False

    def models(self) -> List[str]:
        return settings.gemini_models_list or [settings.gemini_models.split(",")[0]]

    def generate(self, prompt, *, system=None, model=None, temperature=0.7,
                 max_tokens=4000, timeout=120.0) -> LLMResult:
        from google.genai import types  # local import → only if SDK installed
        rot = self._get_rotator()
        preferred = [model] if model else (settings.gemini_models_list or None)

        def build(client, model_name):
            return client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                ),
            )

        try:
            response, model_used = rot.call(build, preferred_models=preferred)
        except Exception as e:
            # Distinguish: if all keys exhausted → transient (try next provider);
            # otherwise hard.
            msg = str(e).lower()
            if "no" in msg and ("key" in msg or "available" in msg):
                raise ProviderTransientError(str(e))
            raise ProviderTransientError(str(e))
        return LLMResult(
            text=response.text or "",
            provider=self.name,
            model=model_used,
            raw=response,
        )


class OpenAIProvider(BaseProvider):
    name = "openai"
    default_model = "gpt-4o-mini"
    base_url = "https://api.openai.com/v1"

    def __init__(self, api_keys: str = "", base_url: str = "", default_model: str = ""):
        self.api_keys = _csv(api_keys or settings.openai_api_keys)
        if base_url:
            self.base_url = base_url.rstrip("/")
        if default_model:
            self.default_model = default_model

    def is_available(self) -> bool:
        return bool(self.api_keys)

    def models(self) -> List[str]:
        return _csv(settings.openai_models) or [self.default_model]

    def generate(self, prompt, *, system=None, model=None, temperature=0.7,
                 max_tokens=4000, timeout=120.0) -> LLMResult:
        if not self.api_keys:
            raise ProviderUnavailable("openai: no API keys")
        model = model or self.models()[0]
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})

        last_exc: Optional[Exception] = None
        for key in self.api_keys:
            try:
                r = _httpx_post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {key}",
                             "Content-Type": "application/json"},
                    payload={
                        "model": model,
                        "messages": msgs,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                    timeout=timeout,
                )
                data = r.json()
                text = data["choices"][0]["message"]["content"] or ""
                return LLMResult(
                    text=text, provider=self.name, model=model,
                    usage=data.get("usage", {}), raw=data,
                )
            except ProviderTransientError as e:
                last_exc = e
                continue
            except Exception as e:
                last_exc = e
                continue
        raise ProviderTransientError(f"openai exhausted all keys: {last_exc}")


class AnthropicProvider(BaseProvider):
    name = "anthropic"
    default_model = "claude-3-5-haiku-latest"
    base_url = "https://api.anthropic.com/v1"
    api_version = "2023-06-01"

    def is_available(self) -> bool:
        return bool(_csv(settings.anthropic_api_keys))

    def models(self) -> List[str]:
        return _csv(settings.anthropic_models) or [self.default_model]

    def generate(self, prompt, *, system=None, model=None, temperature=0.7,
                 max_tokens=4000, timeout=120.0) -> LLMResult:
        keys = _csv(settings.anthropic_api_keys)
        if not keys:
            raise ProviderUnavailable("anthropic: no API keys")
        model = model or self.models()[0]
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system

        last_exc: Optional[Exception] = None
        for key in keys:
            try:
                r = _httpx_post(
                    f"{self.base_url}/messages",
                    headers={"x-api-key": key,
                             "anthropic-version": self.api_version,
                             "Content-Type": "application/json"},
                    payload=payload,
                    timeout=timeout,
                )
                data = r.json()
                # Anthropic returns content blocks
                blocks = data.get("content", [])
                text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
                return LLMResult(
                    text=text, provider=self.name, model=model,
                    usage=data.get("usage", {}), raw=data,
                )
            except ProviderTransientError as e:
                last_exc = e
                continue
            except Exception as e:
                last_exc = e
                continue
        raise ProviderTransientError(f"anthropic exhausted all keys: {last_exc}")


class OpenRouterProvider(OpenAIProvider):
    """OpenRouter speaks OpenAI's protocol, so we just rebase the URL."""
    name = "openrouter"
    default_model = "openai/gpt-4o-mini"

    def __init__(self):
        super().__init__(
            api_keys=settings.openrouter_api_keys,
            base_url="https://openrouter.ai/api/v1",
            default_model=self.default_model,
        )

    def models(self) -> List[str]:
        return _csv(settings.openrouter_models) or [self.default_model]

    def is_available(self) -> bool:
        return bool(self.api_keys)


class GroqProvider(OpenAIProvider):
    name = "groq"
    default_model = "llama-3.3-70b-versatile"

    def __init__(self):
        super().__init__(
            api_keys=settings.groq_api_keys,
            base_url="https://api.groq.com/openai/v1",
            default_model=self.default_model,
        )

    def models(self) -> List[str]:
        return _csv(settings.groq_models) or [self.default_model]

    def is_available(self) -> bool:
        return bool(self.api_keys)


class DeepSeekProvider(OpenAIProvider):
    name = "deepseek"
    default_model = "deepseek-chat"

    def __init__(self):
        super().__init__(
            api_keys=settings.deepseek_api_keys,
            base_url="https://api.deepseek.com/v1",
            default_model=self.default_model,
        )

    def models(self) -> List[str]:
        return _csv(settings.deepseek_models) or [self.default_model]

    def is_available(self) -> bool:
        return bool(self.api_keys)


class TogetherProvider(OpenAIProvider):
    name = "together"
    default_model = "meta-llama/Llama-3.3-70B-Instruct-Turbo"

    def __init__(self):
        super().__init__(
            api_keys=settings.together_api_keys,
            base_url="https://api.together.xyz/v1",
            default_model=self.default_model,
        )

    def models(self) -> List[str]:
        return _csv(settings.together_models) or [self.default_model]

    def is_available(self) -> bool:
        return bool(self.api_keys)


class MistralProvider(OpenAIProvider):
    name = "mistral"
    default_model = "mistral-large-latest"

    def __init__(self):
        super().__init__(
            api_keys=settings.mistral_api_keys,
            base_url="https://api.mistral.ai/v1",
            default_model=self.default_model,
        )

    def models(self) -> List[str]:
        return _csv(settings.mistral_models) or [self.default_model]

    def is_available(self) -> bool:
        return bool(self.api_keys)


class OllamaProvider(BaseProvider):
    """Local Ollama daemon — no API key required, only a base URL."""
    name = "ollama"
    default_model = "llama3.2"

    def __init__(self):
        self.base_url = (settings.ollama_base_url or "http://localhost:11434").rstrip("/")

    def is_available(self) -> bool:
        return bool(settings.ollama_enabled)

    def models(self) -> List[str]:
        return _csv(settings.ollama_models) or [self.default_model]

    def generate(self, prompt, *, system=None, model=None, temperature=0.7,
                 max_tokens=4000, timeout=120.0) -> LLMResult:
        model = model or self.models()[0]
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if system:
            payload["system"] = system
        try:
            r = _httpx_post(f"{self.base_url}/api/generate", headers={}, payload=payload, timeout=timeout)
        except ProviderHardError as e:
            raise ProviderTransientError(str(e))
        data = r.json()
        return LLMResult(
            text=data.get("response", "") or "",
            provider=self.name,
            model=model,
            raw=data,
        )


# ---------------------------------------------------------------------------
# Registry + chain
# ---------------------------------------------------------------------------

_PROVIDERS: dict[str, BaseProvider] = {}


def _registry() -> dict[str, BaseProvider]:
    if _PROVIDERS:
        return _PROVIDERS
    for cls in (GeminiProvider, OpenAIProvider, AnthropicProvider, OpenRouterProvider,
                GroqProvider, DeepSeekProvider, TogetherProvider, MistralProvider, OllamaProvider):
        try:
            inst = cls()
            _PROVIDERS[inst.name] = inst
        except Exception as e:  # pragma: no cover
            logger.debug("Provider %s init failed: %s", cls.__name__, e)
    return _PROVIDERS


def get_provider(name: str) -> Optional[BaseProvider]:
    return _registry().get(name.lower())


def list_available_providers() -> List[str]:
    """Return names of providers that have credentials/SDK available."""
    return [name for name, p in _registry().items() if p.is_available()]


def resolve_chain(preferred: Optional[List[str]] = None) -> List[BaseProvider]:
    """Resolve the provider chain: explicit list → settings → all available."""
    if preferred:
        names = preferred
    else:
        names = _csv(settings.script_provider_chain) or list_available_providers()
    chain = []
    for n in names:
        p = get_provider(n)
        if p and p.is_available():
            chain.append(p)
    if not chain:
        # Last resort: anything that responds
        for p in _registry().values():
            if p.is_available():
                chain.append(p)
    return chain


def generate_text(
    prompt: str,
    *,
    system: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 4000,
    preferred_chain: Optional[List[str]] = None,
    timeout: float = 120.0,
) -> LLMResult:
    """Try providers in order; return first non-empty result."""
    chain = resolve_chain(preferred_chain)
    if not chain:
        raise ProviderUnavailable(
            "No LLM provider configured. Add at least one of: "
            "GEMINI_API_KEYS, OPENAI_API_KEYS, ANTHROPIC_API_KEYS, OPENROUTER_API_KEYS, "
            "GROQ_API_KEYS, DEEPSEEK_API_KEYS, TOGETHER_API_KEYS, MISTRAL_API_KEYS, "
            "or set OLLAMA_ENABLED=true."
        )

    last_error: Optional[Exception] = None
    for provider in chain:
        try:
            logger.info("LLM: trying provider=%s", provider.name)
            result = provider.generate(
                prompt, system=system, temperature=temperature,
                max_tokens=max_tokens, timeout=timeout,
            )
            if result.text:
                logger.info("LLM: success provider=%s model=%s chars=%d",
                            result.provider, result.model, len(result.text))
                return result
            last_error = ProviderTransientError(f"{provider.name} returned empty")
        except ProviderUnavailable as e:
            logger.debug("LLM: provider=%s unavailable: %s", provider.name, e)
            last_error = e
            continue
        except (ProviderTransientError, ProviderHardError) as e:
            logger.warning("LLM: provider=%s failed: %s", provider.name, e)
            last_error = e
            continue
        except Exception as e:  # pragma: no cover
            logger.exception("LLM: provider=%s unexpected error", provider.name)
            last_error = e
            continue

    raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")
