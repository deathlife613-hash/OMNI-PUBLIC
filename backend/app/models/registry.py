"""Builds the configured provider. Adding a provider = one entry here.

Supported now: groq, openrouter (free models only). NOT yet implemented:
ollama (native API), huggingface (free credits too small to be useful).
"""
import httpx

from app.core.config import Settings
from app.models.base import Provider, ProviderError
from app.models.openai_compat import OpenAICompatProvider

PRESETS: dict[str, dict] = {
    "groq": {"base_url": "https://api.groq.com/openai/v1", "free_only": None},
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        # OpenRouter free models are the ones whose id ends in ":free".
        "free_only": lambda model_id: model_id.endswith(":free"),
    },
}


def build_provider(settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> Provider:
    preset = PRESETS.get(settings.ai_provider)
    if preset is None:
        raise ProviderError(
            "unsupported",
            f"Provider '{settings.ai_provider}' is not implemented. Available: {', '.join(PRESETS)}.",
        )
    if not settings.ai_api_key:
        raise ProviderError("not_configured", "No API key configured. Set OMNI_AI_API_KEY on the server.")
    return OpenAICompatProvider(
        name=settings.ai_provider,
        base_url=settings.ai_base_url or preset["base_url"],
        api_key=settings.ai_api_key,
        timeout=settings.ai_timeout_s,
        max_retries=settings.ai_max_retries,
        free_only=preset["free_only"],
        allow_paid=settings.allow_paid_providers,
        transport=transport,
    )
