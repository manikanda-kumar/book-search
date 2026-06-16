from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


WORD_RE = re.compile(r"\b[\w'-]+\b")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def slugify(value: str, max_length: int = 64) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    if not slug:
        return "book"
    return slug[:max_length].strip("-") or "book"


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: object) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")


def word_count(text: str) -> int:
    return len(WORD_RE.findall(text))


def excerpt(text: str, limit: int = 180) -> str:
    cleaned = normalize_whitespace(text)
    if len(cleaned) <= limit:
        return cleaned
    truncated = cleaned[:limit]
    last_period = max(truncated.rfind("."), truncated.rfind("!"), truncated.rfind("?"))
    if last_period > limit // 2:
        return cleaned[: last_period + 1].rstrip()
    return cleaned[: limit - 1].rstrip() + "…"


def dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        cleaned = normalize_whitespace(item)
        if not cleaned or cleaned in seen:
            continue
        output.append(cleaned)
        seen.add(cleaned)
    return output


def local_name(tag: str) -> str:
    return tag.split("}", 1)[-1].lower()


def escape_html(text: str) -> str:
    return html.escape(text, quote=True)


def markdown_code_block(text: str) -> str:
    stripped = text.strip("\n")
    if not stripped:
        return ""
    return f"```\n{stripped}\n```"


def split_markdown_paragraphs(markdown: str) -> list[str]:
    paragraphs: list[str] = []
    buffer: list[str] = []
    in_code = False

    for line in markdown.splitlines():
        if line.startswith("```"):
            in_code = not in_code
            if buffer:
                paragraphs.append("\n".join(buffer).strip())
                buffer = []
            continue

        if in_code:
            continue

        if not line.strip():
            if buffer:
                paragraphs.append("\n".join(buffer).strip())
                buffer = []
            continue

        buffer.append(line)

    if buffer:
        paragraphs.append("\n".join(buffer).strip())

    return [paragraph for paragraph in paragraphs if paragraph]