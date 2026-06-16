from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from .calibre import detect_calibre_tools
from .config import describe_config

from .paths import books_root, workspace_root
from .pipeline import list_books, load_book_record


@dataclass
class DoctorCheck:
    id: str
    status: str
    message: str


def run_doctor(workspace: Path | None = None) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []

    try:
        root = workspace_root(workspace)
        checks.append(DoctorCheck("workspace", "ok", f"Workspace root: {root}"))
    except Exception as error:
        checks.append(DoctorCheck("workspace", "fail", str(error)))
        return checks

    if sys.version_info < (3, 11):
        checks.append(DoctorCheck("python", "fail", f"Python 3.11+ required, found {sys.version.split()[0]}"))
    else:
        checks.append(DoctorCheck("python", "ok", f"Python {sys.version.split()[0]}"))

    books_dir = books_root(workspace)
    if books_dir.exists():
        checks.append(DoctorCheck("books_dir", "ok", f"Books directory: {books_dir}"))
    else:
        checks.append(DoctorCheck("books_dir", "warn", "No data/books directory yet."))

    config = describe_config(workspace)
    checks.append(DoctorCheck("workspace_config", "ok", f"Books dir: {config['books_dir']}"))

    if config.get("llm"):
        llm = config["llm"]
        checks.append(
            DoctorCheck(
                "llm_api",
                "ok",
                f"LLM provider configured: {llm['provider']} / {llm['model']} (key {llm['api_key']})",
            )
        )
    else:
        checks.append(DoctorCheck("llm_api", "warn", config.get("llm_error", "LLM not configured")))

    chat_model = config.get("env", {}).get("BOOK_SEARCH_CHAT_MODEL")
    if chat_model:
        checks.append(DoctorCheck("chat_model_override", "ok", f"BOOK_SEARCH_CHAT_MODEL={chat_model}"))
    else:
        checks.append(
            DoctorCheck(
                "chat_model_override",
                "ok",
                "Using default chat model (set BOOK_SEARCH_CHAT_MODEL to override).",
            )
        )

    if importlib.util.find_spec("openai") is None:
        checks.append(DoctorCheck("openai_package", "warn", "openai package not installed. Run: pip install -e '.[llm]'"))
    else:
        checks.append(DoctorCheck("openai_package", "ok", "openai package available"))

    calibre = detect_calibre_tools()
    if calibre.get("ebook_meta"):
        checks.append(DoctorCheck("calibre", "ok", "Calibre ebook-meta available"))
    else:
        checks.append(DoctorCheck("calibre", "warn", "Calibre not found; metadata enrichment disabled."))

    books = _load_book_summaries(workspace)
    if not books:
        checks.append(DoctorCheck("ingested_books", "warn", "No ingested books found."))
    else:
        checks.append(DoctorCheck("ingested_books", "ok", f"{len(books)} ingested book(s)."))
        warning_count = sum(len(book.get("extraction_warnings", [])) for book in books)
        if warning_count:
            checks.append(
                DoctorCheck(
                    "extraction_warnings",
                    "warn",
                    f"{warning_count} extraction warning(s) across ingested books.",
                )
            )
        else:
            checks.append(DoctorCheck("extraction_warnings", "ok", "No extraction warnings on ingested books."))

    return checks


def doctor_has_failures(checks: list[DoctorCheck]) -> bool:
    return any(check.status == "fail" for check in checks)


def _load_book_summaries(workspace: Path | None) -> list[dict]:
    summaries: list[dict] = []
    for item in list_books(workspace):
        try:
            record, _paths = load_book_record(item["book_id"], workspace)
        except Exception:
            continue
        summaries.append(record)
    return summaries