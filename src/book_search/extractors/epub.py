from __future__ import annotations

import posixpath
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from zipfile import ZipFile, is_zipfile

from ..calibre import read_ebook_meta
from ..chapters import classify_chapter, content_start_chapter, enrich_book_chapters
from ..ingest_warnings import collect_extraction_warnings, source_fingerprint
from ..paths import BookPaths
from ..util import ensure_dir, excerpt, local_name, markdown_code_block, normalize_whitespace, slugify, utc_now, word_count, write_text


HTML_MEDIA_TYPES = {
    "application/xhtml+xml",
    "application/xml",
    "text/html",
}


def _invalid_epub_detail(source_path: Path) -> str | None:
    with source_path.open("rb") as handle:
        sample = handle.read(512).lstrip().lower()

    if sample.startswith(b"<!doctype html") or sample.startswith(b"<html"):
        return "the file appears to be an HTML document, not an EPUB archive"

    if sample.startswith(b"%pdf-"):
        return "the file appears to be a PDF, not an EPUB archive"

    return None


def _ensure_epub_archive(source_path: Path) -> None:
    if is_zipfile(source_path):
        return

    detail = _invalid_epub_detail(source_path)
    if detail:
        raise ValueError(f"Invalid EPUB: expected a ZIP-based EPUB archive, but {detail}.")

    raise ValueError("Invalid EPUB: expected a ZIP-based EPUB archive.")


def _read_opf_path(archive: ZipFile) -> str:
    container = ET.fromstring(archive.read("META-INF/container.xml"))
    rootfile = container.find(".//{*}rootfile")
    if rootfile is None:
        raise ValueError("EPUB container.xml does not declare a package document")
    full_path = rootfile.attrib.get("full-path")
    if not full_path:
        raise ValueError("EPUB package document path is missing")
    return full_path


def _resolve_href(base_file: str, href: str) -> str:
    base_dir = posixpath.dirname(base_file)
    return posixpath.normpath(posixpath.join(base_dir, href))


def _block_has_nested_blocks(elem: ET.Element) -> bool:
    block_tags = {
        "p",
        "div",
        "section",
        "article",
        "aside",
        "blockquote",
        "ul",
        "ol",
        "table",
        "pre",
        "figure",
        "dl",
    }
    for child in list(elem):
        if local_name(child.tag) in block_tags:
            return True
    return False


def _render_list(elem: ET.Element) -> list[str]:
    blocks: list[str] = []
    for child in list(elem):
        if local_name(child.tag) != "li":
            continue
        text = normalize_whitespace(" ".join(child.itertext()))
        if text:
            blocks.append(f"- {text}")
    return ["\n".join(blocks)] if blocks else []


def _render_table(elem: ET.Element) -> list[str]:
    rows: list[str] = []
    for row in elem.findall(".//{*}tr"):
        cells = [normalize_whitespace(" ".join(cell.itertext())) for cell in row if normalize_whitespace(" ".join(cell.itertext()))]
        if cells:
            rows.append(" | ".join(cells))
    if not rows:
        return []
    return ["\n".join(rows)]


def _element_to_blocks(elem: ET.Element) -> list[str]:
    tag = local_name(elem.tag)

    if tag in {"script", "style", "svg", "img", "image"}:
        return []

    if tag in {"section", "article", "aside", "body", "main", "nav", "figure", "dl"}:
        blocks: list[str] = []
        for child in list(elem):
            blocks.extend(_element_to_blocks(child))
        return blocks

    if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        text = normalize_whitespace(" ".join(elem.itertext()))
        if not text:
            return []
        level = min(int(tag[1]), 6)
        return [f"{'#' * level} {text}"]

    if tag == "pre":
        return [markdown_code_block("".join(elem.itertext()))] if "".join(elem.itertext()).strip() else []

    if tag in {"ul", "ol"}:
        return _render_list(elem)

    if tag == "table":
        return _render_table(elem)

    if tag in {"div", "blockquote"} and _block_has_nested_blocks(elem):
        blocks: list[str] = []
        for child in list(elem):
            blocks.extend(_element_to_blocks(child))
        return blocks

    if tag in {"p", "div", "span", "blockquote", "li"}:
        text = normalize_whitespace(" ".join(elem.itertext()))
        return [text] if text else []

    blocks: list[str] = []
    for child in list(elem):
        blocks.extend(_element_to_blocks(child))

    if not blocks:
        text = normalize_whitespace(" ".join(elem.itertext()))
        if text:
            blocks.append(text)

    return blocks


def _xhtml_to_markdown(raw: bytes) -> str:
    tree = ET.fromstring(raw)
    body = tree.find(".//{*}body")
    if body is None:
        body = tree

    blocks: list[str] = []
    for child in list(body):
        blocks.extend(_element_to_blocks(child))

    cleaned = [block.strip() for block in blocks if block and block.strip()]
    return "\n\n".join(cleaned).strip() + "\n"


def _chapter_title(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("#"):
            title = line.lstrip("#").strip()
            if title:
                return title
    return fallback


def extract_epub(source_path: Path, paths: BookPaths) -> dict:
    _ensure_epub_archive(source_path)
    ensure_dir(paths.extracted_dir)
    ensure_dir(paths.chapters_dir)
    calibre = read_ebook_meta(source_path, paths.extracted_dir)

    with ZipFile(source_path) as archive:
        opf_path = _read_opf_path(archive)
        package = ET.fromstring(archive.read(opf_path))

        metadata_elem = package.find(".//{*}metadata")
        if metadata_elem is not None:
            title = normalize_whitespace(" ".join((metadata_elem.findtext(".//{*}title") or source_path.stem).split()))
            author = normalize_whitespace(metadata_elem.findtext(".//{*}creator") or "Unknown author")
            language_text = normalize_whitespace(metadata_elem.findtext(".//{*}language") or "")
            identifier_text = normalize_whitespace(metadata_elem.findtext(".//{*}identifier") or "")
            language = language_text or None
            identifier = identifier_text or None
        else:
            title = source_path.stem
            author = "Unknown author"
            language = None
            identifier = None

        native_metadata = {
            "title": title,
            "author": author,
            "language": language,
            "identifier": identifier,
        }

        manifest: dict[str, dict[str, str]] = {}
        for item in package.findall(".//{*}manifest/{*}item"):
            item_id = item.attrib.get("id")
            href = item.attrib.get("href")
            media_type = item.attrib.get("media-type")
            if item_id and href and media_type:
                manifest[item_id] = {
                    "href": _resolve_href(opf_path, href),
                    "media_type": media_type,
                    "properties": item.attrib.get("properties", ""),
                }

        chapters: list[dict] = []
        combined_parts: list[str] = []
        chapter_index = 0

        for itemref in package.findall(".//{*}spine/{*}itemref"):
            idref = itemref.attrib.get("idref")
            if not idref or idref not in manifest:
                continue

            item = manifest[idref]
            if item["media_type"] not in HTML_MEDIA_TYPES:
                continue

            chapter_index += 1
            raw = archive.read(item["href"])
            markdown = _xhtml_to_markdown(raw)
            fallback = PurePosixPath(item["href"]).stem.replace("_", " ").replace("-", " ").strip() or f"Chapter {chapter_index}"
            chapter_title = _chapter_title(markdown, fallback.title())
            chapter_excerpt = excerpt(markdown)
            chapter_words = word_count(markdown)
            chapter_kind = classify_chapter(
                chapter_title,
                word_count=chapter_words,
                excerpt=chapter_excerpt,
            )

            chapter_slug = slugify(chapter_title, max_length=48)
            chapter_file = paths.chapters_dir / f"{chapter_index:03d}-{chapter_slug}.md"
            write_text(chapter_file, markdown)

            chapters.append(
                {
                    "index": chapter_index,
                    "title": chapter_title,
                    "kind": chapter_kind,
                    "source_href": item["href"],
                    "path": str(chapter_file.relative_to(paths.root)),
                    "word_count": chapter_words,
                    "excerpt": chapter_excerpt,
                }
            )
            combined_parts.append(f"# {chapter_title}\n\n{markdown.strip()}\n")

    combined_markdown = "\n\n".join(part.strip() for part in combined_parts if part.strip()) + "\n"
    combined_path = paths.extracted_dir / "book.md"
    write_text(combined_path, combined_markdown)

    calibre_metadata = calibre.get("normalized", {})
    authors = calibre_metadata.get("authors") or ([native_metadata["author"]] if native_metadata["author"] else [])
    resolved_title = calibre_metadata.get("title") or native_metadata["title"]
    resolved_author = " & ".join(authors) if authors else "Unknown author"
    languages = calibre_metadata.get("languages") or ([native_metadata["language"]] if native_metadata["language"] else [])
    resolved_language = languages[0] if languages else None
    resolved_identifier = calibre_metadata.get("primary_identifier") or native_metadata["identifier"]

    record = {
        "book_id": paths.book_dir.name,
        "title": resolved_title,
        "author": resolved_author,
        "authors": authors,
        "language": resolved_language,
        "languages": languages,
        "identifier": resolved_identifier,
        "publisher": calibre_metadata.get("publisher"),
        "published": calibre_metadata.get("published"),
        "series": calibre_metadata.get("series"),
        "series_index": calibre_metadata.get("series_index"),
        "tags": calibre_metadata.get("tags") or [],
        "source_format": "epub",
        "source_path": str(source_path.relative_to(paths.root)),
        "source_fingerprint": source_fingerprint(source_path),
        "extracted_at": utc_now(),
        "combined_markdown_path": str(combined_path.relative_to(paths.root)),
        "chapter_count": len(chapters),
        "content_start_chapter": content_start_chapter(chapters),
        "chapters": enrich_book_chapters(chapters),
        "metadata_sources": {
            "native_opf": native_metadata,
            "calibre_normalized": calibre_metadata,
        },
        "calibre": calibre,
    }
    record["extraction_warnings"] = collect_extraction_warnings(record)
    return record