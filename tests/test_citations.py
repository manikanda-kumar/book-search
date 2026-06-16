from __future__ import annotations

from book_search.citations import (
    format_sources,
    make_chunk_id,
    validate_answer_citations,
)


class TestCitations:
    def test_make_chunk_id_is_stable(self) -> None:
        assert make_chunk_id("sample-book", 7, 2) == "sample-book:ch007:c002"

    def test_format_sources_is_chunk_granular(self) -> None:
        snippets = [
            {
                "chunk_id": "sample-book:ch007:c001",
                "chapter_index": 7,
                "chapter_title": "Introduction",
                "heading": "Introduction",
                "file": "007-introduction.md",
                "char_start": 0,
                "char_end": 120,
                "text": "Enshittification is a theory of platform decay.",
            },
            {
                "chunk_id": "sample-book:ch007:c002",
                "chapter_index": 7,
                "chapter_title": "Introduction",
                "heading": "Coining the term",
                "file": "007-introduction.md",
                "char_start": 121,
                "char_end": 240,
                "text": "The term spread because it named a shared experience.",
            },
        ]
        sources = format_sources(snippets)
        assert len(sources) == 2
        assert sources[0]["chunk_id"] == "sample-book:ch007:c001"
        assert "Enshittification" in sources[0]["excerpt"]

    def test_validate_answer_citations(self) -> None:
        snippets = [{"chunk_id": "book:ch007:c001"}]
        answer = "This is explained in [book:ch007:c001] and also [book:ch099:c001]."
        result = validate_answer_citations(answer, snippets)
        assert result["valid_chunk_ids"] == ["book:ch007:c001"]
        assert result["unknown_chunk_ids"] == ["book:ch099:c001"]