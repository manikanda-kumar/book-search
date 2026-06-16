from __future__ import annotations

from pathlib import Path

from ..chapters import chapter_by_index
from ..companion import answer_question, load_session, save_session
from ..config import describe_config
from ..doctor import run_doctor
from ..pipeline import list_books, load_book_record
from ..retrieval import search_chapters
from ..session_io import session_summary
from ..spoiler import resolve_spoiler_limits
from .markdown import render_markdown


class ApiError(Exception):
    def __init__(self, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def api_list_books(workspace: Path | None = None) -> list[dict]:
    return list_books(workspace)


def api_book_summary(book_id: str, workspace: Path | None = None) -> dict:
    record, paths = load_book_record(book_id, workspace)
    return {
        "book_id": record.get("book_id", book_id),
        "title": record.get("title"),
        "author": record.get("author"),
        "chapter_count": record.get("chapter_count", 0),
        "content_start_chapter": record.get("content_start_chapter"),
        "extraction_warnings": record.get("extraction_warnings") or [],
        "chapters": [
            {
                "index": int(chapter.get("index", 0)),
                "title": chapter.get("title"),
                "kind": chapter.get("kind", "body"),
                "word_count": chapter.get("word_count", 0),
            }
            for chapter in record.get("chapters", [])
            if isinstance(chapter, dict)
        ],
        "session": session_summary(paths, record),
        "book_dir": str(paths.book_dir),
    }


def api_chapter_content(book_id: str, chapter_index: int, workspace: Path | None = None) -> dict:
    record, paths = load_book_record(book_id, workspace)
    chapter = chapter_by_index(record.get("chapters", []), chapter_index)
    if chapter is None:
        raise ApiError(f"Chapter {chapter_index} not found.", status=404)

    path_value = str(chapter.get("path", ""))
    chapter_path = paths.root / path_value if path_value else None
    if chapter_path is None or not chapter_path.exists():
        raise ApiError(f"Chapter file missing for chapter {chapter_index}.", status=404)

    markdown = chapter_path.read_text(encoding="utf-8")
    return {
        "book_id": book_id,
        "index": chapter_index,
        "title": chapter.get("title"),
        "kind": chapter.get("kind", "body"),
        "word_count": chapter.get("word_count", 0),
        "markdown": markdown,
        "html": render_markdown(markdown),
    }


def api_ask(
    book_id: str,
    *,
    question: str,
    current_chapter: int | None = None,
    max_chapter: int | None = None,
    auto_spoiler: bool = True,
    model: str | None = None,
    workspace: Path | None = None,
) -> dict:
    if not question.strip():
        raise ApiError("Question is required.")
    record, paths = load_book_record(book_id, workspace)
    result = answer_question(
        record,
        paths,
        question,
        current_chapter=current_chapter,
        max_chapter=max_chapter,
        auto_spoiler=auto_spoiler,
        model=model,
    )
    payload = {key: value for key, value in result.items() if not key.startswith("_")}
    limits = resolve_spoiler_limits(
        current_chapter=current_chapter,
        max_chapter=max_chapter,
        auto_spoiler=auto_spoiler,
    )
    payload["spoiler_state"] = _spoiler_state(limits)
    return payload


def api_search(
    book_id: str,
    *,
    query: str,
    current_chapter: int | None = None,
    max_chapter: int | None = None,
    limit: int = 10,
    workspace: Path | None = None,
) -> dict:
    if not query.strip():
        raise ApiError("Query is required.")
    record, paths = load_book_record(book_id, workspace)
    chapters = record.get("chapters", [])
    snippets = search_chapters(
        paths.chapters_dir,
        query,
        chapters if isinstance(chapters, list) else [],
        book_id=str(record.get("book_id", book_id)),
        current_chapter=current_chapter,
        max_chapter=max_chapter,
        limit=limit,
    )
    return {
        "book_id": book_id,
        "query": query,
        "count": len(snippets),
        "results": snippets,
        "note": "Lexical text search over chapter excerpts (not semantic search).",
    }


def api_get_session(book_id: str, workspace: Path | None = None) -> dict:
    record, paths = load_book_record(book_id, workspace)
    session = load_session(paths)
    limits = resolve_spoiler_limits(
        current_chapter=session.get("current_chapter"),
        max_chapter=session.get("max_chapter"),
        auto_spoiler=True,
    )
    return {
        "book_id": book_id,
        "session": session_summary(paths, record),
        "spoiler_state": _spoiler_state(limits),
    }


def api_update_session(
    book_id: str,
    *,
    current_chapter: int | None = None,
    max_chapter: int | None = None,
    auto_spoiler: bool = True,
    workspace: Path | None = None,
) -> dict:
    record, paths = load_book_record(book_id, workspace)
    session = load_session(paths)
    if current_chapter is not None:
        session["current_chapter"] = current_chapter
    if auto_spoiler and current_chapter is not None:
        session["max_chapter"] = current_chapter
    elif max_chapter is not None:
        session["max_chapter"] = max_chapter
    else:
        session["max_chapter"] = None
    save_session(paths, session)
    limits = resolve_spoiler_limits(
        current_chapter=session.get("current_chapter"),
        max_chapter=session.get("max_chapter"),
        auto_spoiler=auto_spoiler,
    )
    return {
        "book_id": book_id,
        "session": session_summary(paths, record),
        "spoiler_state": _spoiler_state(limits),
    }


def api_config(workspace: Path | None = None) -> dict:
    return describe_config(workspace)


def api_doctor(workspace: Path | None = None) -> list[dict]:
    return [check.__dict__ for check in run_doctor(workspace)]


def _spoiler_state(limits) -> dict:
    if limits.max_chapter is None:
        return {
            "active": False,
            "label": "Spoiler guard off",
            "max_chapter": None,
            "auto_linked": False,
        }
    label = f"Using chapters 1–{limits.max_chapter}"
    if limits.auto_linked:
        label += " (auto-linked to current chapter)"
    return {
        "active": True,
        "label": label,
        "max_chapter": limits.max_chapter,
        "auto_linked": limits.auto_linked,
    }