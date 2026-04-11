import logging
import asyncio
from typing import Callable, List, Any
from core import discord_alerts

logger = logging.getLogger(__name__)


class FallbackExhaustedError(Exception):
    """All providers in the fallback chain have failed."""
    pass


class FallbackChain:
    """Execute a list of provider functions in order, falling back on failure."""

    def __init__(self, providers: List[Callable], max_retries_per_provider: int = 2):
        if not providers:
            raise ValueError("FallbackChain requires at least one provider")
        self.providers = providers
        self.max_retries = max_retries_per_provider

    async def execute(self, *args, **kwargs) -> Any:
        """Try each provider in order. Returns the first successful result."""
        errors = []

        for i, provider in enumerate(self.providers):
            provider_name = getattr(provider, '__name__', f'provider_{i}')

            for attempt in range(1, self.max_retries + 1):
                try:
                    logger.info(
                        "FallbackChain: trying %s (attempt %d/%d)",
                        provider_name, attempt, self.max_retries
                    )

                    if asyncio.iscoroutinefunction(provider):
                        result = await provider(*args, **kwargs)
                    else:
                        result = provider(*args, **kwargs)

                    logger.info("FallbackChain: %s succeeded", provider_name)
                    return result

                except Exception as e:
                    wait_time = min(2 ** attempt, 16)
                    logger.warning(
                        "FallbackChain: %s attempt %d failed: %s (waiting %ds)",
                        provider_name, attempt, str(e), wait_time
                    )
                    errors.append((provider_name, attempt, str(e)))

                    if attempt < self.max_retries:
                        await asyncio.sleep(wait_time)

            logger.warning("FallbackChain: %s exhausted all retries", provider_name)

        error_summary = "\n".join(
            f"  [{name}] attempt {att}: {err}" for name, att, err in errors
        )
        msg = f"All providers failed:\n{error_summary}"
        logger.error("FallbackChain: %s", msg)

        discord_alerts.send_error(f"FallbackChain exhausted:\n```\n{error_summary[:1500]}\n```")

        raise FallbackExhaustedError(msg)
