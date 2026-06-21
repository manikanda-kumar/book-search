from __future__ import annotations

import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from .extractors.epub import _read_opf_path, _resolve_href
from .paths import BookPaths
from .pipeline import load_book_record
from .util import ensure_dir, escape_html, local_name, slugify, write_text

TOC_CHAPTER_RE = re.compile(
    r'href="([^"#]+)(?:#[^"]*)?"[^>]*>\s*Chapter\s+(\d+)\s*:\s*([^<]+)\s*<',
    re.IGNORECASE,
)
IMG_SRC_RE = re.compile(r"""<img\b[^>]*\bsrc=["']([^"']+)["']""", re.IGNORECASE)
UNSAFE_HREF_PREFIXES = ("javascript:", "data:", "vbscript:")
VOID_ELEMENTS = {"br", "hr", "img"}
# Public-domain fallbacks for images referenced in EPUB HTML but stripped from pirated archives.
KNOWN_IMAGE_FALLBACKS: dict[str, str] = {
    "00016.jpg": "https://upload.wikimedia.org/wikipedia/commons/4/42/Robida_vingtieme_siecle_p68_1.jpg",
}
BLOCK_ELEMENTS = {
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "div",
    "blockquote",
    "span",
    "li",
    "td",
    "th",
    "tr",
    "table",
    "ul",
    "ol",
    "sup",
    "i",
    "b",
    "strong",
    "em",
    "a",
}

READER_CSS = """
html {
  font-size: 18px;
}
body {
  color: #1a1a1a;
  background: #faf9f7;
  margin: 0;
  padding: 2rem 1.25rem 4rem;
  line-height: 1.65;
  font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
}
article {
  max-width: 42rem;
  margin: 0 auto;
}
article h1, article h2 {
  line-height: 1.25;
  margin: 2rem 0 1rem;
}
article p, article li, article blockquote {
  display: block;
  margin: 0.85em 0;
}
article blockquote {
  margin-left: 1.25rem;
  padding-left: 1rem;
  border-left: 3px solid #d8d3c8;
  font-style: italic;
}
article img {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 1.5rem auto;
}
article .book-search-missing-image {
  color: #5c574f;
  font-size: 0.9rem;
  font-style: italic;
  margin: 1rem 0;
  padding: 0.75rem 1rem;
  border: 1px dashed #d8d3c8;
  background: #f5f2eb;
}
article ul {
  margin: 0.85em 0 0.85em 1.25rem;
}
article .calibre11 {
  text-indent: 1.5em;
}
article sup {
  font-size: 0.75em;
  vertical-align: super;
}
.book-search-export-meta {
  color: #5c574f;
  font-size: 0.9rem;
  border-bottom: 1px solid #e2ddd3;
  margin-bottom: 2rem;
  padding-bottom: 1rem;
}
.book-search-export-meta p {
  margin: 0.25rem 0;
}
"""


def _chapter_spine(record: dict) -> list[dict]:
    chapters = record.get("chapters", [])
    if not isinstance(chapters, list):
        return []
    return [chapter for chapter in chapters if isinstance(chapter, dict) and chapter.get("source_href")]


def _spine_index(chapter: dict) -> int | None:
    raw = chapter.get("index")
    if raw is None:
        return None
    return int(raw)


def parse_toc_chapter_starts(archive: ZipFile) -> dict[int, str]:
    starts: dict[int, str] = {}
    for name in archive.namelist():
        if not name.lower().endswith((".html", ".xhtml", ".htm")):
            continue
        try:
            raw = archive.read(name).decode("utf-8", errors="replace")
        except KeyError:
            continue
        for match in TOC_CHAPTER_RE.finditer(raw):
            href, number, _title = match.groups()
            chapter_num = int(number)
            starts.setdefault(chapter_num, PurePosixPath(href).name)
    return starts


def _index_for_source_href(spine: list[dict], source_name: str) -> int | None:
    for chapter in spine:
        href = str(chapter.get("source_href", ""))
        if PurePosixPath(href).name == source_name or href == source_name:
            return _spine_index(chapter)
    return None


def _last_spine_index(spine: list[dict]) -> int:
    indices = [index for chapter in spine if (index := _spine_index(chapter)) is not None]
    if not indices:
        raise ValueError("Book record has no valid spine indices.")
    return max(indices)


def resolve_spine_range(
    record: dict,
    archive: ZipFile,
    *,
    chapter_number: int | None = None,
    title: str | None = None,
    spine_from: int | None = None,
    spine_to: int | None = None,
) -> tuple[int, int, str]:
    spine = _chapter_spine(record)
    if not spine:
        raise ValueError("Book record has no chapter spine entries.")

    if spine_from is not None or spine_to is not None:
        start = spine_from or 1
        end = spine_to or start
        if start > end:
            raise ValueError(f"Invalid spine range: {start}-{end}")
        label = f"spine {start}-{end}"
        return start, end, label

    if chapter_number is not None:
        toc = parse_toc_chapter_starts(archive)
        start_href = toc.get(chapter_number)
        if not start_href:
            raise ValueError(f"Could not find Chapter {chapter_number} in the EPUB table of contents.")
        start_index = _index_for_source_href(spine, start_href)
        if start_index is None:
            raise ValueError(f"Could not map Chapter {chapter_number} ({start_href}) to spine index.")
        next_href = toc.get(chapter_number + 1)
        if next_href:
            end_index = _index_for_source_href(spine, next_href)
            if end_index is not None:
                return start_index, end_index - 1, f"Chapter {chapter_number}"
        return start_index, _last_spine_index(spine), f"Chapter {chapter_number}"

    if title:
        normalized = title.casefold().strip()
        matches = [
            chapter
            for chapter in spine
            if normalized in str(chapter.get("title", "")).casefold()
        ]
        if not matches:
            raise ValueError(f"No spine chapter title matches `{title}`.")
        start_chapter = matches[0]
        start_index = _spine_index(start_chapter)
        if start_index is None:
            raise ValueError(f"Matched chapter `{title}` has no spine index.")
        start_href = PurePosixPath(str(start_chapter.get("source_href", ""))).name
        toc = parse_toc_chapter_starts(archive)
        matched_chapter_number = next((num for num, href in toc.items() if href == start_href), None)
        if matched_chapter_number is not None:
            next_href = toc.get(matched_chapter_number + 1)
            if next_href:
                end_index = _index_for_source_href(spine, next_href)
                if end_index is not None:
                    return start_index, end_index - 1, str(start_chapter.get("title", title))
        end_index = start_index
        for chapter in spine:
            index = _spine_index(chapter)
            if index is None or index <= start_index:
                continue
            next_href_name = PurePosixPath(str(chapter.get("source_href", ""))).name
            if next_href_name in toc.values():
                break
            end_index = index
        return start_index, end_index, str(start_chapter.get("title", title))

    raise ValueError("Specify exactly one of --chapter, --title, or --spine.")


def _safe_attribute_value(name: str, value: str) -> str:
    if name == "href" and value.strip().lower().startswith(UNSAFE_HREF_PREFIXES):
        return "#"
    return escape_html(value)


def _is_watermark_element(elem: ET.Element) -> bool:
    joined = "".join(elem.itertext()).casefold()
    if "oceanofpdf.com" in joined:
        return True
    for value in elem.attrib.values():
        if "oceanofpdf.com" in value.casefold():
            return True
    return False


def _is_layout_noise_element(elem: ET.Element) -> bool:
    tag = local_name(elem.tag)
    if tag != "div":
        return False
    class_name = elem.attrib.get("class", "")
    if class_name == "mbppagebreak":
        return True
    style = elem.attrib.get("style", "").replace(" ", "").casefold()
    if style == "height:0pt":
        return True
    return False


def _render_html_element(elem: ET.Element) -> str:
    tag = local_name(elem.tag)
    if tag in {"script", "style"}:
        return ""

    if tag == "img":
        src = escape_html(elem.attrib.get("src", ""))
        alt = elem.attrib.get("alt", "")
        alt_attr = f' alt="{escape_html(alt)}"' if alt else ""
        return f'<img src="{src}"{alt_attr}/>'

    if tag in VOID_ELEMENTS:
        return f"<{tag}/>"

    attribs = " ".join(
        f'{name}="{_safe_attribute_value(name, value)}"'
        for name, value in sorted(elem.attrib.items())
        if name != "xmlns"
    )
    open_tag = f"<{tag} {attribs}>" if attribs else f"<{tag}>"

    inner_parts: list[str] = []
    if elem.text:
        inner_parts.append(escape_html(elem.text))
    for child in list(elem):
        rendered = _render_html_element(child)
        if rendered:
            inner_parts.append(rendered)
        if child.tail:
            inner_parts.append(escape_html(child.tail))

    if tag in BLOCK_ELEMENTS:
        return f"{open_tag}{''.join(inner_parts)}</{tag}>"

    return "".join(inner_parts)


def _body_inner_html(raw: bytes) -> str:
    try:
        tree = ET.fromstring(raw)
    except ET.ParseError as error:
        raise ValueError("EPUB chapter HTML is not well-formed.") from error
    body = tree.find(".//{*}body")
    if body is None:
        return ""
    parts: list[str] = []
    if body.text and body.text.strip():
        parts.append(escape_html(body.text.strip()))
    for child in list(body):
        if _is_watermark_element(child) or _is_layout_noise_element(child):
            continue
        rendered = _render_html_element(child)
        if rendered:
            parts.append(rendered)
        if child.tail and child.tail.strip():
            parts.append(escape_html(child.tail.strip()))
    return "\n".join(part for part in parts if part)


def _find_archive_image_path(archive: ZipFile, source_href: str, src: str) -> str | None:
    resolved = _resolve_href(source_href, src)
    if resolved in archive.namelist():
        return resolved
    filename = PurePosixPath(resolved).name
    candidates = [name for name in archive.namelist() if PurePosixPath(name).name == filename]
    if len(candidates) == 1:
        return candidates[0]
    for name in candidates:
        if name.endswith(f"/{filename}") or name.endswith(filename):
            return name
    return None


def _fetch_image_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "book-search/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def _load_image_bytes(archive: ZipFile, source_href: str, src: str) -> tuple[bytes | None, str, str]:
    filename = PurePosixPath(_resolve_href(source_href, src)).name
    archive_path = _find_archive_image_path(archive, source_href, src)
    if archive_path is not None:
        return archive.read(archive_path), filename, "archive"
    fallback_url = KNOWN_IMAGE_FALLBACKS.get(filename)
    if fallback_url:
        try:
            return _fetch_image_bytes(fallback_url), filename, "fallback"
        except (OSError, urllib.error.URLError):
            return None, filename, "missing"
    return None, filename, "missing"


def _copy_referenced_images(
    fragment: str,
    *,
    archive: ZipFile,
    source_href: str,
    images_dir: Path,
    images_href_prefix: str,
) -> tuple[str, int, list[str], list[str]]:
    copied = 0
    recovered: list[str] = []
    missing: list[str] = []

    def replace(match: re.Match[str]) -> str:
        nonlocal copied
        original = match.group(0)
        src = match.group(1)
        if src.startswith(("http://", "https://", "data:")):
            return original
        payload, filename, source = _load_image_bytes(archive, source_href, src)
        rewritten_src = f"{images_href_prefix}/{filename}"
        rewritten = original.replace(src, rewritten_src)
        if payload is None:
            missing.append(filename)
            return (
                f'<p class="book-search-missing-image">Image unavailable in source EPUB: {escape_html(filename)}</p>'
                f"{rewritten}"
            )
        ensure_dir(images_dir)
        (images_dir / filename).write_bytes(payload)
        copied += 1
        if source == "fallback":
            recovered.append(filename)
        return rewritten

    return IMG_SRC_RE.sub(replace, fragment), copied, recovered, missing


def _load_stylesheet(archive: ZipFile) -> str | None:
    for name in ("stylesheet.css", "Styles/stylesheet.css", "OEBPS/stylesheet.css"):
        try:
            return _sanitize_epub_css(archive.read(name).decode("utf-8", errors="replace"))
        except KeyError:
            continue
    for name in archive.namelist():
        if name.lower().endswith(".css"):
            try:
                return _sanitize_epub_css(archive.read(name).decode("utf-8", errors="replace"))
            except KeyError:
                continue
    return None


def _sanitize_epub_css(css: str) -> str:
    cleaned = re.sub(r"@namespace[^;]+;", "", css)
    return cleaned.strip()


def _plain_text_word_count(html_fragment: str) -> int:
    text = re.sub(r"<[^>]+>", " ", html_fragment)
    text = re.sub(r"\s+", " ", text).strip()
    return len(re.findall(r"\b[\w'-]+\b", text))


def export_chapter_html(
    record: dict,
    paths: BookPaths,
    *,
    chapter_number: int | None = None,
    title: str | None = None,
    spine_from: int | None = None,
    spine_to: int | None = None,
    output_path: Path | None = None,
) -> tuple[Path, int, list[str], list[str]]:
    source_epub = paths.source_dir / "source.epub"
    if not source_epub.exists():
        raise FileNotFoundError(f"Source EPUB not found: {source_epub}")

    with ZipFile(source_epub) as archive:
        _read_opf_path(archive)
        start_index, end_index, label = resolve_spine_range(
            record,
            archive,
            chapter_number=chapter_number,
            title=title,
            spine_from=spine_from,
            spine_to=spine_to,
        )

        spine = _chapter_spine(record)
        selected = [
            chapter
            for chapter in spine
            if (index := _spine_index(chapter)) is not None and start_index <= index <= end_index
        ]
        if not selected:
            raise ValueError(f"No spine chapters found for range {start_index}-{end_index}.")

        export_dir = paths.book_dir / "exported"
        slug = slugify(label, max_length=64)
        html_path = output_path or (export_dir / f"{slug}.html")
        images_href_prefix = f"{html_path.stem}-images"
        images_dir = html_path.parent / images_href_prefix
        if images_dir.exists():
            for child in images_dir.iterdir():
                child.unlink()
        else:
            ensure_dir(images_dir)

        body_parts: list[str] = []
        image_count = 0
        recovered_images: list[str] = []
        missing_images: list[str] = []
        for chapter in selected:
            source_href = str(chapter["source_href"])
            chapter_index = _spine_index(chapter)
            raw = archive.read(source_href)
            fragment = _body_inner_html(raw)
            if not fragment:
                continue
            fragment, copied, recovered, missing = _copy_referenced_images(
                fragment,
                archive=archive,
                source_href=source_href,
                images_dir=images_dir,
                images_href_prefix=images_href_prefix,
            )
            image_count += copied
            recovered_images.extend(recovered)
            missing_images.extend(missing)
            body_parts.append(
                f'<section class="book-search-spine" data-spine-index="{chapter_index}">\n{fragment}\n</section>'
            )

        combined_body = "\n".join(body_parts)
        word_count = _plain_text_word_count(combined_body)
        expected_words = sum(int(chapter.get("word_count", 0)) for chapter in selected)
        if expected_words >= 200 and word_count < max(200, int(expected_words * 0.5)):
            raise ValueError(
                f"Exported chapter looks incomplete ({word_count} of ~{expected_words} expected words). "
                f"Try an explicit spine range instead, e.g. --spine {start_index}-{end_index}."
            )

        stylesheet = _load_stylesheet(archive)
        css_parts = [READER_CSS.strip()]
        if stylesheet:
            css_parts.append(stylesheet)
        css_block = f"<style>\n{chr(10).join(css_parts)}\n</style>"
        book_title = escape_html(str(record.get("title", "Book")))
        safe_label = escape_html(label)
        meta_lines = [
            f"<p><strong>{book_title}</strong> — {safe_label}</p>",
            f"<p>Spine {start_index}–{end_index} · {word_count:,} words · {len(selected)} sections · {image_count} image(s)</p>",
        ]
        if recovered_images:
            recovered_label = ", ".join(escape_html(name) for name in sorted(set(recovered_images)))
            meta_lines.append(
                f"<p>Recovered {len(set(recovered_images))} image(s) from public-domain fallback: {recovered_label}</p>"
            )
        if missing_images:
            missing_label = ", ".join(escape_html(name) for name in sorted(set(missing_images)))
            meta_lines.append(f"<p>Missing image(s) in source EPUB: {missing_label}</p>")
        meta_block = "\n      ".join(meta_lines)
        document = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{book_title} — {safe_label}</title>
  {css_block}
</head>
<body class="calibre">
  <article data-spine-range="{start_index}-{end_index}" data-word-count="{word_count}" data-image-count="{image_count}">
    <header class="book-search-export-meta">
      {meta_block}
    </header>
{combined_body}
  </article>
</body>
</html>
"""
        write_text(html_path, document)

    return html_path, image_count, recovered_images, missing_images


def export_chapter_html_for_book(
    book_id: str,
    *,
    workspace: Path | None = None,
    chapter_number: int | None = None,
    title: str | None = None,
    spine_from: int | None = None,
    spine_to: int | None = None,
    output_path: Path | None = None,
) -> tuple[Path, int, list[str], list[str]]:
    record, paths = load_book_record(book_id, workspace)
    return export_chapter_html(
        record,
        paths,
        chapter_number=chapter_number,
        title=title,
        spine_from=spine_from,
        spine_to=spine_to,
        output_path=output_path,
    )


def parse_spine_range(value: str) -> tuple[int, int]:
    try:
        if "-" in value:
            start_text, end_text = value.split("-", 1)
            spine_from = int(start_text.strip())
            spine_to = int(end_text.strip())
        else:
            spine_from = spine_to = int(value.strip())
    except ValueError as error:
        raise ValueError(f"Invalid --spine value `{value}`. Expected a number or range like 43-48.") from error
    return spine_from, spine_to


def validate_export_selector(
    *,
    chapter_number: int | None,
    title: str | None,
    spine: str | None,
) -> None:
    selectors = [name for name, value in (("chapter", chapter_number), ("title", title), ("spine", spine)) if value is not None]
    if len(selectors) != 1:
        joined = ", ".join(f"--{name}" for name in selectors) or "none"
        raise ValueError(f"Specify exactly one of --chapter, --title, or --spine (got {joined}).")