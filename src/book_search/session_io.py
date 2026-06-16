from __future__ import annotations

from pathlib import Path

from .companion import load_session, save_session
from .paths import BookPaths
from .util import utc_now, write_json


def session_summary(paths: BookPaths, record: dict) -> dict:
    session = load_session(paths)
    history = session.get("history", [])
    turn_count = len([item for item in history if isinstance(item, dict) and item.get("role") == "user"])
    return {
        "book_id": record.get("book_id", paths.book_dir.name),
        "title": record.get("title"),
        "author": record.get("author"),
        "current_chapter": session.get("current_chapter"),
        "max_chapter": session.get("max_chapter"),
        "show_sources": bool(session.get("show_sources", False)),
        "turn_count": turn_count,
        "message_count": len(history) if isinstance(history, list) else 0,
        "updated_at": session.get("updated_at"),
    }


def build_session_export(paths: BookPaths, record: dict) -> dict:
    session = load_session(paths)
    history = session.get("history", [])
    if not isinstance(history, list):
        history = []
    return {
        "book_id": record.get("book_id", paths.book_dir.name),
        "title": record.get("title"),
        "author": record.get("author"),
        "exported_at": utc_now(),
        "reading_position": {
            "current_chapter": session.get("current_chapter"),
            "max_chapter": session.get("max_chapter"),
        },
        "show_sources": bool(session.get("show_sources", False)),
        "turn_count": len([item for item in history if isinstance(item, dict) and item.get("role") == "user"]),
        "history": history,
    }


def export_session(
    paths: BookPaths,
    record: dict,
    *,
    output_path: Path | None = None,
) -> Path:
    payload = build_session_export(paths, record)
    destination = output_path or (paths.companion_dir / f"session-export-{payload['exported_at'][:10]}.json")
    write_json(destination, payload)
    return destination


def reset_session(paths: BookPaths, *, keep_position: bool = False) -> dict:
    session = load_session(paths)
    current_chapter = session.get("current_chapter") if keep_position else None
    max_chapter = session.get("max_chapter") if keep_position else None
    cleared = {
        "current_chapter": current_chapter,
        "max_chapter": max_chapter,
        "show_sources": False,
        "history": [],
        "updated_at": utc_now(),
    }
    save_session(paths, cleared)
    return cleared