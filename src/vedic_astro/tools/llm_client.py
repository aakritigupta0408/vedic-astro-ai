"""
llm_client.py — LLM wrapper supporting Anthropic and Ollama backends.

Backend selection is controlled by ``settings.llm_backend``:
  - "anthropic"  → Anthropic Messages API (requires ANTHROPIC_API_KEY + credits)
  - "ollama"     → Local Ollama server (free, uses settings.ollama_model)

All responses are Redis-cached by prompt hash (7-day TTL).

Usage
-----
    client = get_llm_client()
    text = await client.complete(
        system="You are a Vedic astrology expert.",
        user="Interpret this chart: ...",
        model="claude-sonnet-4-6",   # ignored when backend=ollama
        max_tokens=1500,
    )
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class LLMClient:
    """Async LLM client — Anthropic or Ollama backend."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key = api_key
        self._anthropic_client: Optional[object] = None

    def _get_anthropic_client(self):
        if self._anthropic_client is None:
            try:
                import anthropic  # type: ignore[import]
                self._anthropic_client = anthropic.AsyncAnthropic(api_key=self._api_key)
            except ImportError as exc:
                raise RuntimeError(
                    "anthropic package not installed. Run: pip install anthropic"
                ) from exc
        return self._anthropic_client

    async def _complete_anthropic(
        self,
        system: str,
        user: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        client = self._get_anthropic_client()
        try:
            import anthropic  # type: ignore[import]
            response = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return response.content[0].text
        except Exception as exc:
            logger.error("Anthropic API error: %s", exc)
            raise RuntimeError(f"LLM call failed: {exc}") from exc

    async def _complete_ollama(
        self,
        system: str,
        user: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        from vedic_astro.settings import settings
        import httpx

        url = f"{settings.ollama_base_url}/api/chat"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as http:
                resp = await http.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["message"]["content"]
        except Exception as exc:
            logger.error("Ollama API error: %s", exc)
            raise RuntimeError(f"LLM call failed (ollama): {exc}") from exc

    async def complete(
        self,
        system: str,
        user: str,
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.3,
        use_cache: bool = True,
    ) -> str:
        """
        Send a completion request and return the assistant text.

        When ``settings.llm_backend == "ollama"``, the *model* parameter is
        ignored and ``settings.ollama_model`` is used instead.
        """
        from vedic_astro.tools.hasher import make_llm_key
        from vedic_astro.tools.cache import get_cache
        from vedic_astro.settings import settings

        backend = settings.llm_backend
        effective_model = settings.ollama_model if backend == "ollama" else model

        full_prompt = f"[backend={backend}][model={effective_model}][sys={system}][user={user}]"
        cache_key = make_llm_key(full_prompt)

        if use_cache:
            cache = get_cache()
            cached = await cache.get(cache_key)
            if cached:
                logger.debug("LLM cache HIT: %s", cache_key)
                return cached

        if backend == "ollama":
            text = await self._complete_ollama(system, user, effective_model, max_tokens, temperature)
        else:
            text = await self._complete_anthropic(system, user, effective_model, max_tokens, temperature)

        if use_cache:
            await get_cache().set(cache_key, text, ttl=settings.cache_llm_response_ttl)

        return text


# ─────────────────────────────────────────────────────────────────────────────
# Singleton factory
# ─────────────────────────────────────────────────────────────────────────────

_llm_instance: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Return the application-wide LLMClient singleton."""
    global _llm_instance
    if _llm_instance is None:
        from vedic_astro.settings import settings
        if settings.llm_backend == "anthropic" and not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set. Add it to .env or set LLM_BACKEND=ollama."
            )
        _llm_instance = LLMClient(api_key=settings.anthropic_api_key)
    return _llm_instance
