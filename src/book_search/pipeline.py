from __future__ import annotations

import shutil
from pathlib import Path

from .extractors import extract_book
from .paths import BookPaths, book_paths, books_root
from .util import ensure_dir, read_json, slugify, write_json


def ingest_source(
    source_path: Path,
    book_id: str | None = None,
    force: bool = False,
    workspace: Path | None = None,
) -> tuple[str, dict, BookPaths]:
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    resolved = source_path.resolve()
    suffix = resolved.suffix.lower()
    if suffix != ".epub":
        raise ValueError(f"Unsupported format: {suffix}. Only EPUB is supported in v0.1.")

    inferred_id = book_id or slugify(resolved.stem)
    paths = book_paths(inferred_id, workspace)
    book_dir_existed = paths.book_dir.exists()

    if paths.book_dir.exists() and not force and paths.book_record_path.exists():
        raise FileExistsError(f"Book `{inferred_id}` already exists. Use --force to re-ingest.")

    ensure_dir(paths.source_dir)
    ensure_dir(paths.companion_dir)
    destination = paths.source_dir / f"source{suffix}"

    try:
        if destination.resolve() != resolved:
            shutil.copy2(resolved, destination)

        record = extract_book(destination, paths)
        write_json(paths.book_record_path, record)
        return inferred_id, record, paths
    except Exception:
        if not book_dir_existed and paths.book_dir.exists():
            shutil.rmtree(paths.book_dir, ignore_errors=True)
        raise


def load_book_record(book_id: str, workspace: Path | None = None) -> tuple[dict, BookPaths]:
    paths = book_paths(book_id, workspace)
    if not paths.book_record_path.exists():
        raise FileNotFoundError(f"Book `{book_id}` has not been ingested yet.")
    record = read_json(paths.book_record_path)
    if not isinstance(record, dict):
        raise ValueError(f"Invalid book record for `{book_id}`.")
    return record, paths


def list_books(workspace: Path | None = None) -> list[dict[str, str]]:
    root = books_root(workspace)
    if not root.exists():
        return []

    items: list[dict[str, str]] = []
    for book_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        record_path = book_dir / "book.json"
        if not record_path.exists():
            continue
        record = read_json(record_path)
        if not isinstance(record, dict):
            continue
        items.append(
            {
                "book_id": book_dir.name,
                "title": str(record.get("title", book_dir.name)),
                "author": str(record.get("author", "Unknown")),
                "chapter_count": str(record.get("chapter_count", 0)),
                "source_format": str(record.get("source_format", "")),
            }
        )
    return items