from __future__ import annotations

from pathlib import Path

import pytest

from book_search.eval_fixtures import build_watermark_eval_book
from book_search.extractors.epub import extract_epub
from book_search.ingest_warnings import collect_extraction_warnings, find_identifier_conflict
from book_search.paths import book_paths
from book_search.pipeline import delete_book, ingest_source
from helpers import make_minimal_epub


class TestIngestWarnings:
    def test_collects_watermark_warning(self, tmp_path: Path) -> None:
        record, _paths = build_watermark_eval_book(tmp_path)
        warnings = collect_extraction_warnings(record)
        assert any("watermark" in warning.lower() for warning in warnings)
        assert record["extraction_warnings"]

    def test_source_fingerprint_on_record(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        epub_path = tmp_path / "fp.epub"
        epub_path.write_bytes(make_minimal_epub())
        paths = book_paths("fp-book", tmp_path)
        record = extract_epub(epub_path, paths)
        assert record.get("source_fingerprint")
        assert isinstance(record.get("extraction_warnings"), list)

    def test_find_identifier_conflict(self) -> None:
        books = [
            {"book_id": "a", "identifier": "same-id"},
            {"book_id": "b", "identifier": "other-id"},
        ]
        assert find_identifier_conflict("same-id", exclude_book_id="b", books=books) == "a"
        assert find_identifier_conflict("same-id", exclude_book_id="a", books=books) is None

    def test_ingest_refuses_duplicate_identifier(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        shared = "duplicate-test-id"
        first = tmp_path / "first.epub"
        second = tmp_path / "second.epub"
        first.write_bytes(make_minimal_epub(title="First", identifier=shared))
        second.write_bytes(make_minimal_epub(title="Second", identifier=shared))

        ingest_source(first, book_id="first-book", workspace=tmp_path)
        with pytest.raises(ValueError, match="first-book"):
            ingest_source(second, book_id="second-book", workspace=tmp_path)

    def test_delete_book_removes_directory(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        epub_path = tmp_path / "del.epub"
        epub_path.write_bytes(make_minimal_epub())
        ingest_source(epub_path, book_id="del-book", workspace=tmp_path)
        paths = delete_book("del-book", tmp_path)
        assert not paths.book_dir.exists()