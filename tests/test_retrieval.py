from __future__ import annotations

from pathlib import Path

from book_search.extractors.epub import extract_epub
from book_search.paths import book_paths
from book_search.retrieval import retrieve_chapter_snippets
from helpers import make_minimal_epub


def _ingest_sample(tmp_path: Path) -> tuple[dict, Path]:
    (tmp_path / "pyproject.toml").touch()
    epub_path = tmp_path / "sample.epub"
    epub_path.write_bytes(
        make_minimal_epub(
            chapters=[
                ("Introduction", "<h1>Introduction</h1><p>Welcome to enshittification theory.</p>"),
                (
                    "Platforms",
                    "<h1>Platforms</h1><p>Platforms first serve users, then business customers, then only themselves.</p>",
                ),
                (
                    "Regulation",
                    "<h1>Regulation</h1><p>Antitrust and interoperability can reverse platform decay.</p>",
                ),
            ]
        )
    )
    paths = book_paths("sample", tmp_path)
    record = extract_epub(epub_path, paths)
    return record, paths.chapters_dir


class TestChapterRetrieval:
    def test_prefers_current_chapter(self, tmp_path: Path) -> None:
        record, chapters_dir = _ingest_sample(tmp_path)
        snippets = retrieve_chapter_snippets(
            chapters_dir,
            "What do platforms do over time?",
            record["chapters"],
            book_id="sample",
            current_chapter=2,
            limit=3,
            min_word_count=5,
        )
        assert snippets
        assert int(snippets[0]["chapter_index"]) == 2
        assert str(snippets[0]["chunk_id"]).startswith("sample:ch")

    def test_spoiler_guard_excludes_later_chapters(self, tmp_path: Path) -> None:
        record, chapters_dir = _ingest_sample(tmp_path)
        snippets = retrieve_chapter_snippets(
            chapters_dir,
            "regulation antitrust interoperability",
            record["chapters"],
            book_id="sample",
            max_chapter=2,
            limit=6,
            min_word_count=5,
        )
        assert snippets
        assert all(int(snippet["chapter_index"]) <= 2 for snippet in snippets)

    def test_skips_front_matter_when_possible(self, tmp_path: Path) -> None:
        record, chapters_dir = _ingest_sample(tmp_path)
        snippets = retrieve_chapter_snippets(
            chapters_dir,
            "welcome introduction",
            record["chapters"],
            book_id="sample",
            limit=2,
            min_word_count=5,
        )
        assert snippets
        assert int(snippets[0]["chapter_index"]) == 1