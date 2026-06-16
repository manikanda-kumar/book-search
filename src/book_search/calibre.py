from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from .util import normalize_whitespace, write_text


def detect_calibre_tools() -> dict[str, str | None]:
    return {
        "ebook_convert": shutil.which("ebook-convert"),
        "ebook_meta": shutil.which("ebook-meta"),
        "calibre_debug": shutil.which("calibre-debug"),
    }


def _field_key(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


def _parse_ebook_meta_output(raw: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    current_key: str | None = None

    for line in raw.splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            label, value = line.split(":", 1)
            current_key = _field_key(label)
            fields[current_key] = value.strip()
            continue

        if current_key is None:
            continue

        continuation = line.strip()
        if not continuation:
            continue
        existing = fields[current_key]
        fields[current_key] = f"{existing}\n{continuation}" if existing else continuation

    return fields


def _parse_identifiers(raw: str) -> dict[str, str]:
    identifiers: dict[str, str] = {}
    for part in raw.split(","):
        item = part.strip()
        if not item or ":" not in item:
            continue
        key, value = item.split(":", 1)
        key = normalize_whitespace(key).lower()
        value = normalize_whitespace(value)
        if key and value:
            identifiers[key] = value
    return identifiers


def _parse_authors(raw: str) -> list[str]:
    authors: list[str] = []
    seen: set[str] = set()

    for group in raw.split(";"):
        cleaned_group = normalize_whitespace(group).strip()
        if cleaned_group.startswith("[") and cleaned_group.endswith("]"):
            cleaned_group = cleaned_group[1:-1].strip()
        if not cleaned_group:
            continue

        for author in re.split(r"\s*&\s*", cleaned_group):
            cleaned_author = normalize_whitespace(author)
            bracketed_suffix = re.sub(r"\s*\[[^\]]+\]\s*$", "", cleaned_author).strip()
            if bracketed_suffix:
                cleaned_author = bracketed_suffix
            if not cleaned_author:
                continue
            dedupe_key = cleaned_author.casefold()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            authors.append(cleaned_author)

    return authors


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def read_ebook_meta(source_path: Path, output_dir: Path) -> dict:
    tools = detect_calibre_tools()
    result: dict = {
        "tools": tools,
        "available": bool(tools["ebook_meta"]),
        "normalized": {},
    }

    ebook_meta = tools["ebook_meta"]
    if not ebook_meta:
        return result

    output_dir.mkdir(parents=True, exist_ok=True)

    metadata_run = _run([ebook_meta, str(source_path)])
    if metadata_run.returncode != 0:
        result["error"] = metadata_run.stderr.strip() or metadata_run.stdout.strip() or "ebook-meta failed"
        return result

    raw_output_path = output_dir / "calibre-metadata.txt"
    write_text(raw_output_path, metadata_run.stdout)
    fields = _parse_ebook_meta_output(metadata_run.stdout)
    identifiers = _parse_identifiers(fields.get("identifiers", ""))

    authors = _parse_authors(fields.get("author_s", ""))
    languages = [normalize_whitespace(language) for language in re.split(r"\s*,\s*", fields.get("languages", "")) if normalize_whitespace(language)]
    tags = [normalize_whitespace(tag) for tag in re.split(r"\s*,\s*", fields.get("tags", "")) if normalize_whitespace(tag)]

    normalized = {
        "title": normalize_whitespace(fields.get("title", "")) or None,
        "authors": authors,
        "languages": languages,
        "publisher": normalize_whitespace(fields.get("publisher", "")) or None,
        "published": normalize_whitespace(fields.get("published", "")) or None,
        "series": normalize_whitespace(fields.get("series", "")) or None,
        "series_index": normalize_whitespace(fields.get("series_index", "")) or None,
        "tags": tags,
        "identifiers": identifiers,
        "comments": fields.get("comments") or None,
    }
    primary_identifier = identifiers.get("isbn") or identifiers.get("uuid") or next(iter(identifiers.values()), None)
    normalized["primary_identifier"] = primary_identifier

    result.update(
        {
            "raw_output_path": str(raw_output_path),
            "fields": fields,
            "normalized": normalized,
        }
    )

    opf_path = output_dir / "calibre-metadata.opf"
    opf_run = _run([ebook_meta, str(source_path), f"--to-opf={opf_path}"])
    if opf_run.returncode == 0 and opf_path.exists():
        result["opf_path"] = str(opf_path)

    cover_path = output_dir / "cover.jpg"
    cover_run = _run([ebook_meta, str(source_path), f"--get-cover={cover_path}"])
    if cover_run.returncode == 0 and cover_path.exists() and cover_path.stat().st_size > 0:
        result["cover_path"] = str(cover_path)

    return result