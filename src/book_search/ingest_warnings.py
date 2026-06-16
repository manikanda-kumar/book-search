from __future__ import annotations

import hashlib
from pathlib import Path


def collect_extraction_warnings(record: dict) -> list[str]:
    warnings: list[str] = []
    chapters = record.get("chapters", [])
    if not isinstance(chapters, list):
        return warnings

    start = record.get("content_start_chapter")
    if isinstance(start, int) and start > 5:
        warnings.append(
            f"Content appears to start at chapter {start}; unusually large front matter block."
        )

    watermark_hits = 0
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        excerpt = str(chapter.get("excerpt", "")).lower()
        if "oceanofpdf.com" in excerpt or "downloaded from" in excerpt:
            watermark_hits += 1
    if watermark_hits >= 2:
        warnings.append(f"Detected watermark-like text in {watermark_hits} chapters.")

    tiny_non_front = sum(
        1
        for chapter in chapters
        if isinstance(chapter, dict)
        and int(chapter.get("word_count", 0)) < 20
        and chapter.get("kind") != "front_matter"
    )
    if tiny_non_front >= 2:
        warnings.append(f"Found {tiny_non_front} very short non-front-matter chapters.")

    chapter_count = int(record.get("chapter_count", len(chapters)))
    if chapter_count > 50:
        warnings.append(f"Large chapter count ({chapter_count}); verify spine segmentation.")

    body_count = sum(1 for chapter in chapters if isinstance(chapter, dict) and chapter.get("kind") == "body")
    if body_count == 0:
        warnings.append("No body chapters detected after classification.")

    return warnings


def source_fingerprint(source_path: Path) -> str:
    digest = hashlib.sha256()
    with source_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_identifier_conflict(
    identifier: str | None,
    *,
    exclude_book_id: str,
    books: list[dict],
) -> str | None:
    if not identifier:
        return None
    for book in books:
        if book.get("book_id") == exclude_book_id:
            continue
        if book.get("identifier") == identifier:
            return str(book.get("book_id"))
    return None