from __future__ import annotations

import re
from pathlib import Path

from .citations import format_sources, make_chunk_id
from .util import normalize_whitespace, split_markdown_paragraphs


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "book",
    "by",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}

FRONT_MATTER_TITLES = {
    "cover",
    "title",
    "mini toc",
    "copyrightnotice",
    "copyright",
    "dedication",
    "epigraph",
    "also by",
    "praise",
    "advance praise",
    "contents",
    "table of contents",
}


def retrieve_chapter_snippets(
    chapters_dir: Path,
    question: str,
    chapters: list[dict] | None = None,
    *,
    book_id: str | None = None,
    current_chapter: int | None = None,
    max_chapter: int | None = None,
    limit: int = 6,
    min_word_count: int = 30,
) -> list[dict]:
    query_tokens = _tokenize(question)
    chapter_meta = _chapter_meta_by_file(chapters or [])
    resolved_book_id = book_id or "book"
    chunks = _iter_chapter_chunks(
        chapters_dir,
        chapter_meta,
        book_id=resolved_book_id,
        max_chapter=max_chapter,
    )

    scored: list[tuple[int, dict]] = []
    for chunk in chunks:
        if int(chunk.get("word_count", 0)) < min_word_count and _is_front_matter(chunk):
            continue
        score = _score_chunk(chunk, question, query_tokens, current_chapter=current_chapter)
        if score <= 0:
            continue
        chunk["retrieval_score"] = score
        scored.append((score, chunk))

    scored.sort(
        key=lambda item: (
            -item[0],
            int(item[1]["chapter_index"]),
            str(item[1]["file"]),
            int(item[1]["chunk_index"]),
        )
    )

    if not scored:
        fallbacks = [
            chunk
            for chunk in chunks
            if int(chunk.get("word_count", 0)) >= min_word_count and not _is_front_matter(chunk)
        ]
        if current_chapter is not None:
            fallbacks.sort(
                key=lambda chunk: (
                    abs(int(chunk["chapter_index"]) - current_chapter),
                    int(chunk["chapter_index"]),
                    int(chunk["chunk_index"]),
                )
            )
        return fallbacks[:limit]

    snippets: list[dict] = []
    seen: set[str] = set()
    for _score, chunk in scored:
        chunk_id = str(chunk["chunk_id"])
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        snippets.append(chunk)
        if len(snippets) >= limit:
            break
    return snippets


def search_chapters(
    chapters_dir: Path,
    query: str,
    chapters: list[dict] | None = None,
    *,
    book_id: str | None = None,
    current_chapter: int | None = None,
    max_chapter: int | None = None,
    limit: int = 10,
) -> list[dict]:
    return retrieve_chapter_snippets(
        chapters_dir,
        query,
        chapters,
        book_id=book_id,
        current_chapter=current_chapter,
        max_chapter=max_chapter,
        limit=limit,
        min_word_count=0,
    )


def _chapter_meta_by_file(chapters: list[dict]) -> dict[str, dict]:
    mapping: dict[str, dict] = {}
    for chapter in chapters:
        path_value = str(chapter.get("path", ""))
        file_name = Path(path_value).name
        if file_name:
            mapping[file_name] = chapter
    return mapping


def _iter_chapter_chunks(
    chapters_dir: Path,
    chapter_meta: dict[str, dict],
    *,
    book_id: str,
    max_chapter: int | None,
) -> list[dict]:
    chunks: list[dict] = []
    for path in sorted(chapters_dir.glob("*.md")):
        meta = chapter_meta.get(path.name, {})
        chapter_index = int(meta.get("index", _index_from_filename(path.name)))
        if max_chapter is not None and chapter_index > max_chapter:
            continue

        text = path.read_text(encoding="utf-8")
        chapter_title = str(meta.get("title", path.stem))
        word_count = int(meta.get("word_count", len(text.split())))
        for chunk_index, chunk in enumerate(_split_markdown_file(path, text), start=1):
            chunk.update(
                {
                    "chapter_index": chapter_index,
                    "chapter_title": chapter_title,
                    "word_count": word_count,
                    "chunk_index": chunk_index,
                    "chunk_id": make_chunk_id(book_id, chapter_index, chunk_index),
                }
            )
            chunks.append(chunk)
    return chunks


def _index_from_filename(file_name: str) -> int:
    match = re.match(r"^(\d+)-", file_name)
    if match:
        return int(match.group(1))
    return 0


def _is_front_matter(chunk: dict) -> bool:
    title = str(chunk.get("chapter_title", "")).strip().lower()
    return title in FRONT_MATTER_TITLES


def _split_markdown_file(path: Path, text: str) -> list[dict]:
    sections: list[tuple[str, str]] = []
    current_heading = path.name
    buffer: list[str] = []

    for line in text.splitlines():
        if line.startswith("#"):
            if buffer:
                sections.append((current_heading, "\n".join(buffer).strip()))
                buffer = []
            current_heading = re.sub(r"^#+\s*", "", line).strip() or path.name
            continue
        buffer.append(line)

    if buffer:
        sections.append((current_heading, "\n".join(buffer).strip()))

    if not sections:
        sections.append((path.name, text.strip()))

    chunks: list[dict] = []
    for heading, section_text in sections:
        paragraphs = split_markdown_paragraphs(section_text) or [section_text]
        current_parts: list[str] = []
        current_length = 0
        section_cursor = 0

        def flush_chunk(parts: list[str], start: int, end: int) -> None:
            if not parts:
                return
            chunk_text = "\n\n".join(parts).strip()
            chunks.append(
                {
                    "file": path.name,
                    "heading": heading,
                    "text": chunk_text,
                    "char_start": start,
                    "char_end": end,
                }
            )

        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue

            paragraph_start = section_text.find(paragraph, section_cursor)
            if paragraph_start < 0:
                paragraph_start = section_cursor
            paragraph_end = paragraph_start + len(paragraph)

            projected = current_length + len(paragraph)
            if current_parts and projected > 1200:
                flush_chunk(current_parts, section_cursor, paragraph_start)
                current_parts = []
                current_length = 0
                section_cursor = paragraph_start

            if not current_parts:
                section_cursor = paragraph_start

            current_parts.append(paragraph)
            current_length += len(paragraph)
            section_cursor = paragraph_end

        if current_parts:
            flush_chunk(current_parts, section_cursor - current_length, section_cursor)

    return [chunk for chunk in chunks if chunk["text"]]


def _score_chunk(
    chunk: dict,
    question: str,
    query_tokens: set[str],
    *,
    current_chapter: int | None,
) -> int:
    haystack = f"{chunk['file']} {chunk['heading']} {chunk['text']}".lower()
    heading_haystack = f"{chunk['file']} {chunk['heading']} {chunk.get('chapter_title', '')}".lower()
    chunk_tokens = _tokenize(haystack)
    heading_tokens = _tokenize(heading_haystack)
    overlap = query_tokens & chunk_tokens
    score = len(overlap) * 4
    score += len(query_tokens & heading_tokens) * 6

    chapter_index = int(chunk.get("chapter_index", 0))
    if current_chapter is not None:
        distance = abs(chapter_index - current_chapter)
        if distance == 0:
            score += 24
        elif distance == 1:
            score += 12
        elif distance == 2:
            score += 6

    if _is_front_matter(chunk):
        score -= 8

    if question.lower() in haystack:
        score += 8
    if question.lower() in heading_haystack:
        score += 12

    important_phrases = [phrase for phrase in re.findall(r'"([^"]+)"', question) if phrase]
    important_phrases.extend(part for part in re.split(r"[?.!,;:]", question) if len(part.split()) >= 3)
    for phrase in important_phrases:
        normalized_phrase = normalize_whitespace(phrase).lower()
        if normalized_phrase and normalized_phrase in haystack:
            score += 5
        if normalized_phrase and normalized_phrase in heading_haystack:
            score += 10

    return score


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9-]+", text.lower())
        if token not in STOPWORDS and len(token) > 2
    }


__all__ = ["retrieve_chapter_snippets", "search_chapters", "format_sources", "FRONT_MATTER_TITLES"]