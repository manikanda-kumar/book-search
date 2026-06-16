from __future__ import annotations

from .util import excerpt, normalize_whitespace


def make_chunk_id(book_id: str, chapter_index: int, chunk_index: int) -> str:
    return f"{book_id}:ch{chapter_index:03d}:c{chunk_index:03d}"


def format_chunk_label(snippet: dict) -> str:
    chapter_index = int(snippet.get("chapter_index", 0))
    chapter_title = str(snippet.get("chapter_title", "Unknown"))
    chunk_id = str(snippet.get("chunk_id", ""))
    if chunk_id:
        return f"[{chunk_id}] Ch {chapter_index}: {chapter_title}"
    return f"Ch {chapter_index}: {chapter_title}"


def format_sources(snippets: list[dict]) -> list[dict]:
    sources: list[dict] = []
    seen: set[str] = set()
    for snippet in snippets:
        chunk_id = str(snippet.get("chunk_id", ""))
        if not chunk_id or chunk_id in seen:
            continue
        seen.add(chunk_id)
        sources.append(
            {
                "chunk_id": chunk_id,
                "chapter_index": int(snippet.get("chapter_index", 0)),
                "chapter_title": str(snippet.get("chapter_title", "")),
                "heading": str(snippet.get("heading", "")),
                "file": str(snippet.get("file", "")),
                "char_start": int(snippet.get("char_start", 0)),
                "char_end": int(snippet.get("char_end", 0)),
                "excerpt": excerpt(str(snippet.get("text", "")), limit=220),
            }
        )
    return sources


def format_retrieved_context(snippets: list[dict]) -> str:
    blocks: list[str] = []
    for snippet in snippets:
        chunk_id = str(snippet.get("chunk_id", ""))
        blocks.append(
            "\n".join(
                [
                    f"Source chunk: {chunk_id}",
                    f"Chapter {snippet.get('chapter_index')}: {snippet.get('chapter_title')}",
                    f"File: {snippet.get('file')}",
                    f"Heading: {snippet.get('heading')}",
                    f"Offsets: {snippet.get('char_start')}-{snippet.get('char_end')}",
                    f"Excerpt:\n{snippet.get('text')}",
                ]
            )
        )
    return "\n\n".join(blocks)


def print_sources(snippets: list[dict], *, heading: str = "Retrieved sources") -> None:
    sources = format_sources(snippets)
    if not sources:
        return
    print(f"\n{heading}:")
    for index, source in enumerate(sources, start=1):
        print(f"  [{index}] {source['chunk_id']}")
        print(f"      Ch {source['chapter_index']}: {source['chapter_title']}")
        if source.get("heading"):
            print(f"      Heading: {source['heading']}")
        if source.get("char_end", 0) > 0:
            print(f"      Span: {source['char_start']}-{source['char_end']} in chapter file")
        print(f"      \"{source['excerpt']}\"")


def validate_answer_citations(answer: str, snippets: list[dict]) -> dict:
    allowed_ids = {str(snippet.get("chunk_id", "")) for snippet in snippets if snippet.get("chunk_id")}
    referenced = _extract_chunk_ids(answer)
    valid = sorted(chunk_id for chunk_id in referenced if chunk_id in allowed_ids)
    unknown = sorted(chunk_id for chunk_id in referenced if chunk_id not in allowed_ids)
    return {
        "referenced_chunk_ids": referenced,
        "valid_chunk_ids": valid,
        "unknown_chunk_ids": unknown,
    }


def _extract_chunk_ids(answer: str) -> list[str]:
    import re

    pattern = re.compile(r"\b[\w-]+:ch\d{3}:c\d{3}\b")
    seen: set[str] = set()
    ordered: list[str] = []
    for match in pattern.finditer(answer):
        chunk_id = match.group(0)
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        ordered.append(chunk_id)
    return ordered