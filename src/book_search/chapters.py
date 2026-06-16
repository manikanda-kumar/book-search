from __future__ import annotations

import re

from .util import normalize_whitespace


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
    "half title",
    "series page",
    "about the author",
}

BACK_MATTER_TITLES = {
    "appendix",
    "appendices",
    "notes",
    "endnotes",
    "bibliography",
    "references",
    "index",
    "acknowledgments",
    "acknowledgements",
    "afterword",
    "colophon",
}

LOW_VALUE_MARKERS = (
    "oceanofpdf.com",
    "downloaded from",
    "all rights reserved",
)


def normalize_chapter_title(title: str) -> str:
    cleaned = normalize_whitespace(title).lower()
    cleaned = re.sub(r"[^a-z0-9\s]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def classify_chapter(title: str, *, word_count: int, excerpt: str = "") -> str:
    normalized = normalize_chapter_title(title)
    if normalized in FRONT_MATTER_TITLES:
        return "front_matter"
    if normalized in BACK_MATTER_TITLES:
        return "back_matter"
    if _looks_like_front_matter(normalized, word_count=word_count, excerpt=excerpt):
        return "front_matter"
    return "body"


def enrich_chapter_record(chapter: dict) -> dict:
    enriched = dict(chapter)
    enriched["kind"] = classify_chapter(
        str(chapter.get("title", "")),
        word_count=int(chapter.get("word_count", 0)),
        excerpt=str(chapter.get("excerpt", "")),
    )
    return enriched


def enrich_book_chapters(chapters: list[dict]) -> list[dict]:
    return [enrich_chapter_record(chapter) for chapter in chapters if isinstance(chapter, dict)]


def content_start_chapter(chapters: list[dict]) -> int | None:
    for chapter in enrich_book_chapters(chapters):
        if chapter.get("kind") == "body":
            return int(chapter.get("index", 0)) or None
    return None


def chapter_by_index(chapters: list[dict], index: int) -> dict | None:
    for chapter in chapters:
        if isinstance(chapter, dict) and int(chapter.get("index", -1)) == index:
            return enrich_chapter_record(chapter)
    return None


def format_chapter_label(chapters: list[dict], index: int) -> str:
    chapter = chapter_by_index(chapters, index)
    if not chapter:
        return f"chapter {index}"
    title = str(chapter.get("title", "")).strip()
    return f"chapter {index} ({title})" if title else f"chapter {index}"


def _looks_like_front_matter(normalized_title: str, *, word_count: int, excerpt: str) -> bool:
    if word_count <= 15 and any(marker in normalized_title for marker in ("cover", "title", "copyright")):
        return True
    excerpt_lower = normalize_whitespace(excerpt).lower()
    if word_count <= 30 and excerpt_lower in LOW_VALUE_MARKERS:
        return True
    if word_count <= 20 and all(marker in excerpt_lower for marker in ("oceanofpdf",)):
        return True
    return False