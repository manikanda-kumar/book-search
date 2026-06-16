from __future__ import annotations

from pathlib import Path

from book_search.eval_fixtures import build_standard_eval_book
from book_search.ui.handlers import (
    api_book_summary,
    api_chapter_content,
    api_doctor,
    api_list_books,
    api_search,
)
from book_search.ui.markdown import render_markdown


class TestUiMarkdown:
    def test_render_markdown_headings_and_lists(self) -> None:
        html = render_markdown("# Title\n\nParagraph one.\n\n- item a\n- item b")
        assert "<h1>Title</h1>" in html
        assert "<p>Paragraph one.</p>" in html
        assert "<ul>" in html


class TestUiHandlers:
    def test_api_lists_and_loads_chapter(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        build_standard_eval_book(tmp_path)

        books = api_list_books(tmp_path)
        assert any(book["book_id"] == "eval-book" for book in books)

        summary = api_book_summary("eval-book", tmp_path)
        assert summary["title"] == "Eval Book"
        assert summary["chapters"]
        assert "extraction_warnings" in summary

        chapter = api_chapter_content("eval-book", 2, tmp_path)
        assert chapter["index"] == 2
        assert "Alice" in chapter["markdown"]
        assert "<" in chapter["html"]

    def test_api_search_is_lexical(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        build_standard_eval_book(tmp_path)
        payload = api_search("eval-book", query="Alice", workspace=tmp_path)
        assert payload["count"] >= 1
        assert "not semantic" in payload["note"]

    def test_api_doctor_returns_status_cards(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        build_standard_eval_book(tmp_path)
        checks = api_doctor(tmp_path)
        assert checks
        for check in checks:
            assert {"id", "status", "message"} <= check.keys()
            assert check["status"] in {"ok", "warn", "fail"}