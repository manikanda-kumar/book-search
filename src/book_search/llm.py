from __future__ import annotations

import os
from dataclasses import dataclass


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENAI_BASE_URL = "https://api.openai.com/v1"

# Tuned for grounded reading-companion Q&A (instruction following + clear prose).
RECOMMENDED_MODELS = [
    {
        "id": "moonshotai/kimi-k2.6",
        "label": "Kimi K2.6",
        "notes": "Default for companion chat. Strong instruction following and discussion quality.",
        "tier": "default",
    },
    {
        "id": "minimax/minimax-m2.5",
        "label": "MiniMax M2.5",
        "notes": "Faster/cheaper alternative for quick chapter Q&A while reading.",
        "tier": "fast",
    },
    {
        "id": "nvidia/nemotron-3-ultra-550b-a55b",
        "label": "Nemotron 3 Ultra",
        "notes": "Heavier reasoning for complex, multi-step book questions. Slower and pricier.",
        "tier": "deep",
    },
]

DEFAULT_OPENROUTER_MODEL = RECOMMENDED_MODELS[0]["id"]
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


@dataclass(frozen=True)
class LlmConfig:
    provider: str
    api_key: str
    base_url: str
    model: str
    default_headers: dict[str, str]


class LlmConfigError(RuntimeError):
    pass


def resolve_llm_config(model: str | None = None) -> LlmConfig:
    explicit_base = os.getenv("BOOK_SEARCH_API_BASE")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if explicit_base:
        api_key = openrouter_key or openai_key
        if not api_key:
            raise LlmConfigError(
                "BOOK_SEARCH_API_BASE is set but no API key was found. "
                "Set OPENROUTER_API_KEY or OPENAI_API_KEY."
            )
        provider = "custom"
        base_url = explicit_base.rstrip("/")
        resolved_model = model or os.getenv("BOOK_SEARCH_CHAT_MODEL") or DEFAULT_OPENROUTER_MODEL
        return LlmConfig(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=resolved_model,
            default_headers=_openrouter_headers(),
        )

    if openrouter_key:
        resolved_model = model or os.getenv("BOOK_SEARCH_CHAT_MODEL") or DEFAULT_OPENROUTER_MODEL
        return LlmConfig(
            provider="openrouter",
            api_key=openrouter_key,
            base_url=OPENROUTER_BASE_URL,
            model=resolved_model,
            default_headers=_openrouter_headers(),
        )

    if openai_key:
        resolved_model = model or os.getenv("BOOK_SEARCH_CHAT_MODEL") or DEFAULT_OPENAI_MODEL
        return LlmConfig(
            provider="openai",
            api_key=openai_key,
            base_url=OPENAI_BASE_URL,
            model=resolved_model,
            default_headers={},
        )

    raise LlmConfigError(
        "No API key found. Set OPENROUTER_API_KEY (recommended) or OPENAI_API_KEY."
    )


def create_client(config: LlmConfig):
    try:
        from openai import OpenAI
    except ImportError as error:
        raise LlmConfigError("openai package is not installed. Run: pip install -e '.[llm]'") from error

    return OpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        default_headers=config.default_headers or None,
    )


def complete_chat(
    *,
    system: str,
    user: str,
    model: str | None = None,
    max_tokens: int = 1200,
    timeout: int = 90,
) -> tuple[str, str]:
    config = resolve_llm_config(model=model)
    client = create_client(config)

    try:
        response = client.chat.completions.create(
            model=config.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=0.4,
            timeout=timeout,
        )
    except Exception as error:
        raise LlmConfigError(f"Chat request failed ({config.provider}/{config.model}): {error}") from error

    choice = response.choices[0].message.content if response.choices else None
    answer = (choice or "").strip()
    if not answer:
        raise LlmConfigError(f"Empty response from {config.provider}/{config.model}.")
    return answer, config.model


def _openrouter_headers() -> dict[str, str]:
    headers = {
        "HTTP-Referer": os.getenv("BOOK_SEARCH_HTTP_REFERER", "https://github.com/book-search"),
        "X-Title": os.getenv("BOOK_SEARCH_APP_TITLE", "book-search"),
    }
    return {key: value for key, value in headers.items() if value}