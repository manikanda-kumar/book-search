from __future__ import annotations

import pytest

from book_search.llm import (
    DEFAULT_OPENROUTER_MODEL,
    LlmConfigError,
    resolve_llm_config,
)


class TestLlmConfig:
    def test_prefers_openrouter_when_key_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BOOK_SEARCH_API_BASE", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("BOOK_SEARCH_CHAT_MODEL", raising=False)

        config = resolve_llm_config()
        assert config.provider == "openrouter"
        assert config.model == DEFAULT_OPENROUTER_MODEL
        assert config.base_url.endswith("/api/v1")

    def test_honors_explicit_model_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-test")
        config = resolve_llm_config(model="minimax/minimax-m2.5")
        assert config.model == "minimax/minimax-m2.5"

    def test_falls_back_to_openai(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "oa-test")
        config = resolve_llm_config()
        assert config.provider == "openai"
        assert config.model == "gpt-4o-mini"

    def test_raises_without_keys(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("BOOK_SEARCH_API_BASE", raising=False)
        with pytest.raises(LlmConfigError):
            resolve_llm_config()