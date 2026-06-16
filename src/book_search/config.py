from __future__ import annotations

import os
import sys
from pathlib import Path

from .llm import RECOMMENDED_MODELS, resolve_llm_config, LlmConfigError
from .paths import books_root, workspace_root


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def describe_config(workspace: Path | None = None) -> dict:
    root = workspace_root(workspace)
    books_dir = books_root(workspace)

    env_vars = {
        "OPENROUTER_API_KEY": mask_secret(os.getenv("OPENROUTER_API_KEY")),
        "OPENAI_API_KEY": mask_secret(os.getenv("OPENAI_API_KEY")),
        "BOOK_SEARCH_CHAT_MODEL": os.getenv("BOOK_SEARCH_CHAT_MODEL"),
        "BOOK_SEARCH_API_BASE": os.getenv("BOOK_SEARCH_API_BASE"),
        "BOOK_SEARCH_HTTP_REFERER": os.getenv("BOOK_SEARCH_HTTP_REFERER"),
        "BOOK_SEARCH_APP_TITLE": os.getenv("BOOK_SEARCH_APP_TITLE"),
    }

    llm: dict | None = None
    llm_error: str | None = None
    try:
        resolved = resolve_llm_config()
        llm = {
            "provider": resolved.provider,
            "model": resolved.model,
            "base_url": resolved.base_url,
            "api_key": mask_secret(resolved.api_key),
        }
    except LlmConfigError as error:
        llm_error = str(error)

    return {
        "workspace_root": str(root),
        "books_dir": str(books_dir),
        "python_version": sys.version.split()[0],
        "env": env_vars,
        "llm": llm,
        "llm_error": llm_error,
        "recommended_models": [item["id"] for item in RECOMMENDED_MODELS],
    }