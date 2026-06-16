from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .chapters import format_chapter_label
from .retrieval import retrieve_chapter_snippets


@dataclass(frozen=True)
class SpoilerLimits:
    current_chapter: int | None
    max_chapter: int | None
    auto_linked: bool = False


def resolve_spoiler_limits(
    *,
    current_chapter: int | None,
    max_chapter: int | None,
    auto_spoiler: bool = True,
) -> SpoilerLimits:
    if max_chapter is not None:
        return SpoilerLimits(current_chapter=current_chapter, max_chapter=max_chapter, auto_linked=False)
    if auto_spoiler and current_chapter is not None:
        return SpoilerLimits(current_chapter=current_chapter, max_chapter=current_chapter, auto_linked=True)
    return SpoilerLimits(current_chapter=current_chapter, max_chapter=None, auto_linked=False)


def spoiler_refusal_message(
    max_chapter: int,
    *,
    chapters: list[dict] | None = None,
    later_match: bool = False,
) -> str:
    label = format_chapter_label(chapters or [], max_chapter)
    if later_match:
        return (
            f"I can only use chapters 1–{max_chapter} ({label}), "
            "and the provided excerpts do not answer that yet without spoilers."
        )
    return (
        f"I can only use chapters 1–{max_chapter} ({label}), "
        "and the provided excerpts do not answer that."
    )


def check_later_chapter_matches(
    chapters_dir: Path,
    question: str,
    chapters: list[dict],
    *,
    book_id: str,
    max_chapter: int,
    current_chapter: int | None = None,
) -> bool:
    later = retrieve_chapter_snippets(
        chapters_dir,
        question,
        chapters,
        book_id=book_id,
        current_chapter=current_chapter,
        max_chapter=None,
        limit=3,
        min_word_count=0,
        allow_fallback=False,
    )
    return any(int(snippet.get("chapter_index", 0)) > max_chapter for snippet in later)


def build_spoiler_blocked_response(
    question: str,
    chapters_dir: Path,
    chapters: list[dict],
    *,
    book_id: str,
    limits: SpoilerLimits,
) -> dict | None:
    if limits.max_chapter is None:
        return None

    snippets = retrieve_chapter_snippets(
        chapters_dir,
        question,
        chapters,
        book_id=book_id,
        current_chapter=limits.current_chapter,
        max_chapter=limits.max_chapter,
        allow_fallback=False,
    )
    if snippets:
        return None

    later_match = check_later_chapter_matches(
        chapters_dir,
        question,
        chapters,
        book_id=book_id,
        max_chapter=limits.max_chapter,
        current_chapter=limits.current_chapter,
    )
    answer = spoiler_refusal_message(
        limits.max_chapter,
        chapters=chapters,
        later_match=later_match,
    )
    response = {
        "answer": answer,
        "model": None,
        "sources": [],
        "chunks": [],
        "citation_check": {"referenced_chunk_ids": [], "valid_chunk_ids": [], "unknown_chunk_ids": []},
        "current_chapter": limits.current_chapter,
        "max_chapter": limits.max_chapter,
        "spoiler_blocked": True,
        "later_match": later_match,
        "auto_linked": limits.auto_linked,
    }
    _assert_refusal_has_no_retrieved_sources(response)
    return response


def _assert_refusal_has_no_retrieved_sources(response: dict) -> None:
    if response.get("sources") or response.get("chunks"):
        raise ValueError("Spoiler refusal must not include retrieved sources or chunks.")