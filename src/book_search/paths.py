from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BookPaths:
    root: Path
    book_dir: Path
    source_dir: Path
    extracted_dir: Path
    chapters_dir: Path
    companion_dir: Path
    book_record_path: Path


class WorkspaceDiscoveryError(RuntimeError):
    pass


def workspace_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise WorkspaceDiscoveryError(
        f"Cannot find workspace root. Expected 'pyproject.toml' in "
        f"{current} or a parent directory. Use --workspace to set an explicit path."
    )


def books_root(start: Path | None = None) -> Path:
    return workspace_root(start) / "data" / "books"


def book_paths(book_id: str, start: Path | None = None) -> BookPaths:
    root = workspace_root(start)
    book_dir = books_root(start) / book_id
    return BookPaths(
        root=root,
        book_dir=book_dir,
        source_dir=book_dir / "source",
        extracted_dir=book_dir / "extracted",
        chapters_dir=book_dir / "chapters",
        companion_dir=book_dir / "companion",
        book_record_path=book_dir / "book.json",
    )