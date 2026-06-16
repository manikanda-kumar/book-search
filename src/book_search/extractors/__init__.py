from __future__ import annotations

from pathlib import Path

from ..paths import BookPaths
from .epub import extract_epub


def extract_book(source_path: Path, paths: BookPaths) -> dict:
    suffix = source_path.suffix.lower()
    if suffix == ".epub":
        return extract_epub(source_path, paths)
    raise ValueError(f"Unsupported source format: {suffix}. EPUB only in v0.1.")