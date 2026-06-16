from __future__ import annotations

import html
import re


def render_markdown(text: str) -> str:
    lines = text.splitlines()
    blocks: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph:
            return
        body = " ".join(paragraph).strip()
        if body:
            blocks.append(f"<p>{html.escape(body)}</p>")
        paragraph.clear()

    def flush_list() -> None:
        if not list_items:
            return
        items = "".join(f"<li>{html.escape(item)}</li>" for item in list_items)
        blocks.append(f"<ul>{items}</ul>")
        list_items.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            flush_list()
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{html.escape(heading.group(2))}</h{level}>")
            continue

        if stripped.startswith("- "):
            flush_paragraph()
            list_items.append(stripped[2:].strip())
            continue

        flush_list()
        paragraph.append(stripped)

    flush_paragraph()
    flush_list()
    return "\n".join(blocks) if blocks else f"<p>{html.escape(text)}</p>"