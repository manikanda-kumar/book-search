from __future__ import annotations

from pathlib import Path

import pytest

from book_search.extractors.epub import extract_epub
from book_search.paths import book_paths
from book_search.pipeline import ingest_source, list_books, load_book_record
from helpers import make_minimal_epub


class TestEpubExtraction:
    def test_extracts_chapters_and_metadata(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        epub_path = tmp_path / "sample-book.epub"
        epub_path.write_bytes(make_minimal_epub())

        paths = book_paths("sample-book", tmp_path)
        record = extract_epub(epub_path, paths)

        assert record["title"] == "Sample Book"
        assert record["author"] == "Jane Author"
        assert record["chapter_count"] == 2
        assert record["chapters"][0]["title"] == "Introduction"
        assert record["chapters"][1]["title"] == "Chapter One"
        assert (paths.chapters_dir / "001-introduction.md").exists()
        assert (paths.chapters_dir / "002-chapter-one.md").exists()
        assert (paths.extracted_dir / "book.md").exists()

    def test_rejects_non_epub(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        bad_path = tmp_path / "not-a-book.epub"
        bad_path.write_text("<html>not an epub</html>", encoding="utf-8")
        paths = book_paths("bad", tmp_path)

        with pytest.raises(ValueError, match="Invalid EPUB"):
            extract_epub(bad_path, paths)


class TestIngestPipeline:
    def test_ingest_end_to_end(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        epub_path = tmp_path / "my-book.epub"
        epub_path.write_bytes(make_minimal_epub(title="Pipeline Book"))

        book_id, record, paths = ingest_source(epub_path, workspace=tmp_path)

        assert book_id == "my-book"
        assert record["title"] == "Pipeline Book"
        assert paths.book_record_path.exists()
        assert (paths.source_dir / "source.epub").exists()

    def test_list_and_show(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        epub_path = tmp_path / "listed.epub"
        epub_path.write_bytes(make_minimal_epub(title="Listed Book", author="Test Author"))
        ingest_source(epub_path, book_id="listed-book", workspace=tmp_path)

        books = list_books(tmp_path)
        assert len(books) == 1
        assert books[0]["book_id"] == "listed-book"
        assert books[0]["title"] == "Listed Book"

        record, _paths = load_book_record("listed-book", tmp_path)
        assert record["author"] == "Test Author"

    def test_refuses_reingest_without_force(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        epub_path = tmp_path / "dup.epub"
        epub_path.write_bytes(make_minimal_epub())
        ingest_source(epub_path, book_id="dup", workspace=tmp_path)

        with pytest.raises(FileExistsError):
            ingest_source(epub_path, book_id="dup", workspace=tmp_path)