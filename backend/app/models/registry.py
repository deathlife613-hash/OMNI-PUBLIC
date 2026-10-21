"""Builds the configured provider. Adding a provider = one entry here.

Supported: groq, openrouter (free models only), ollama (Ollama Cloud free plan, or a local server),
huggingface (Inference Providers; NOT free for free accounts - see docs/FREE_SERVICES_RESEARCH.md).
All four speak the OpenAI-compatible chat API, so one adapter serves them.
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
    # Ollama Cloud (free plan = small starter allowance, 1 concurrent request). Key from ollama.com/settings/keys.
    # Local Ollama: set OMNI_AI_BASE_URL=http://localhost:11434/v1 - no key needed.
    "ollama": {"base_url": "https://ollama.com/v1", "free_only": None, "keyless_with_custom_url": True},
    # Hugging Face router. Per HF's pricing page free accounts get no included credits, so requests
    # will fail with a "payment required" error until credits are bought. OMNI never enables that itself.
    "huggingface": {"base_url": "https://router.huggingface.co/v1", "free_only": None},
}


def build_provider(settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> Provider:
    preset = PRESETS.get(settings.ai_provider)
    if preset is None:
        raise ProviderError(
            "unsupported",
            f"Provider '{settings.ai_provider}' is not implemented. Available: {', '.join(PRESETS)}.",
        )
    api_key = settings.ai_api_key
    if not api_key:
        if preset.get("keyless_with_custom_url") and settings.ai_base_url:
            api_key = "ollama"  # local servers ignore the key; the header just needs a value
        else:
            raise ProviderError("not_configured", "No API key configured. Set OMNI_AI_API_KEY on the server.")
    return OpenAICompatProvider(
        name=settings.ai_provider,
        base_url=settings.ai_base_url or preset["base_url"],
        api_key=api_key,
        timeout=settings.ai_timeout_s,
        max_retries=settings.ai_max_retries,
        free_only=preset["free_only"],
        allow_paid=settings.allow_paid_providers,
        transport=transport,
    )
