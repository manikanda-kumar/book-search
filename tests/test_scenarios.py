from __future__ import annotations

from pathlib import Path

from book_search.extractors.epub import extract_epub
from book_search.paths import book_paths
from book_search.retrieval import retrieve_chapter_snippets, search_chapters
from helpers import make_minimal_epub


def _build_book(tmp_path: Path) -> tuple[dict, Path]:
    (tmp_path / "pyproject.toml").touch()
    epub_path = tmp_path / "scenario.epub"
    epub_path.write_bytes(
        make_minimal_epub(
            title="Scenario Book",
            chapters=[
                ("Introduction", "<h1>Introduction</h1><p>Alice founded the platform in 2010.</p>"),
                (
                    "Platforms",
                    "<h1>Platforms</h1><p>Platforms first serve users, then business customers, then only themselves.</p>",
                ),
                (
                    "Regulation",
                    "<h1>Regulation</h1><p>Antitrust and interoperability can reverse platform decay.</p>",
                ),
            ],
        )
    )
    paths = book_paths("scenario-book", tmp_path)
    record = extract_epub(epub_path, paths)
    return record, paths.chapters_dir


class TestRetrievalScenarios:
    def test_summarize_chapter_prefers_target_chapter(self, tmp_path: Path) -> None:
        record, chapters_dir = _build_book(tmp_path)
        snippets = retrieve_chapter_snippets(
            chapters_dir,
            "summarize platforms business customers users",
            record["chapters"],
            book_id="scenario-book",
            current_chapter=2,
            limit=3,
            min_word_count=5,
        )
        assert snippets
        assert int(snippets[0]["chapter_index"]) == 2

    def test_character_introduction_retrieves_introduction_chapter(self, tmp_path: Path) -> None:
        record, chapters_dir = _build_book(tmp_path)
        snippets = retrieve_chapter_snippets(
            chapters_dir,
            "Who is Alice?",
            record["chapters"],
            book_id="scenario-book",
            limit=3,
            min_word_count=5,
        )
        assert snippets
        assert int(snippets[0]["chapter_index"]) == 1
        assert "Alice" in str(snippets[0]["text"])

    def test_spoiler_guard_excludes_later_chapters(self, tmp_path: Path) -> None:
        record, chapters_dir = _build_book(tmp_path)
        snippets = retrieve_chapter_snippets(
            chapters_dir,
            "antitrust interoperability regulation",
            record["chapters"],
            book_id="scenario-book",
            max_chapter=2,
            limit=10,
            min_word_count=5,
        )
        assert snippets
        assert all(int(snippet["chapter_index"]) <= 2 for snippet in snippets)
        assert all("antitrust" not in str(snippet["text"]).lower() for snippet in snippets)

    def test_search_returns_chunk_ids(self, tmp_path: Path) -> None:
        record, chapters_dir = _build_book(tmp_path)
        snippets = search_chapters(
            chapters_dir,
            "platform decay",
            record["chapters"],
            book_id="scenario-book",
            limit=5,
        )
        assert snippets
        assert all("chunk_id" in snippet for snippet in snippets)
        assert snippets[0]["chunk_id"].startswith("scenario-book:ch")