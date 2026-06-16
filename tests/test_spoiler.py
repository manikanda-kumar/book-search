from __future__ import annotations

from pathlib import Path

from book_search.chapters import classify_chapter, content_start_chapter, enrich_book_chapters
from book_search.extractors.epub import extract_epub
from book_search.paths import book_paths
from book_search.spoiler import build_spoiler_blocked_response, resolve_spoiler_limits
from book_search.testdata import make_minimal_epub


def _book(tmp_path: Path):
    (tmp_path / "pyproject.toml").touch()
    epub_path = tmp_path / "spoiler.epub"
    epub_path.write_bytes(
        make_minimal_epub(
            chapters=[
                ("Cover", "<h1>Cover</h1><p>OceanofPDF.com</p>"),
                ("Introduction", "<h1>Introduction</h1><p>Alice founded the platform.</p>"),
                ("Platforms", "<h1>Platforms</h1><p>Platforms serve users first.</p>"),
                ("Regulation", "<h1>Regulation</h1><p>Antitrust can reverse decay.</p>"),
            ]
        )
    )
    paths = book_paths("spoiler-book", tmp_path)
    record = extract_epub(epub_path, paths)
    return record, paths


class TestSpoilerSemantics:
    def test_auto_link_current_to_max(self) -> None:
        limits = resolve_spoiler_limits(current_chapter=3, max_chapter=None, auto_spoiler=True)
        assert limits.max_chapter == 3
        assert limits.auto_linked is True

    def test_explicit_spoiler_not_auto_linked(self) -> None:
        limits = resolve_spoiler_limits(current_chapter=3, max_chapter=5, auto_spoiler=True)
        assert limits.max_chapter == 5
        assert limits.auto_linked is False

    def test_classifies_cover_as_front_matter(self, tmp_path: Path) -> None:
        record, _paths = _book(tmp_path)
        chapters = enrich_book_chapters(record["chapters"])
        assert chapters[0]["kind"] == "front_matter"
        assert content_start_chapter(chapters) == 2

    def test_informed_refusal_when_answer_is_later(self, tmp_path: Path) -> None:
        record, paths = _book(tmp_path)
        limits = resolve_spoiler_limits(current_chapter=2, max_chapter=2, auto_spoiler=False)
        response = build_spoiler_blocked_response(
            "antitrust regulation interoperability",
            paths.chapters_dir,
            record["chapters"],
            book_id="spoiler-book",
            limits=limits,
        )
        assert response is not None
        assert response["later_match"] is True
        assert "yet without spoilers" in response["answer"]

    def test_refusal_without_claiming_later_spoilers(self, tmp_path: Path) -> None:
        record, paths = _book(tmp_path)
        limits = resolve_spoiler_limits(current_chapter=2, max_chapter=2, auto_spoiler=False)
        response = build_spoiler_blocked_response(
            "xyzzyplugh nonsense term",
            paths.chapters_dir,
            record["chapters"],
            book_id="spoiler-book",
            limits=limits,
        )
        assert response is not None
        assert response["later_match"] is False
        assert "yet without spoilers" not in response["answer"]