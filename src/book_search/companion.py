from __future__ import annotations

import json
import logging

from .citations import (
    enrich_result_trust,
    format_retrieved_context,
    format_sources,
    print_sources,
    validate_answer_citations,
)
from .llm import LlmConfigError, complete_chat, resolve_llm_config
from .paths import BookPaths
from .retrieval import retrieve_chapter_snippets
from .spoiler import build_spoiler_blocked_response, resolve_spoiler_limits
from .util import excerpt, normalize_whitespace, read_json, utc_now, write_json


class CompanionError(RuntimeError):
    pass


def build_instructions(record: dict, *, max_chapter: int | None = None) -> str:
    title = record.get("title", "this book")
    author = record.get("author", "the author")
    if max_chapter is not None:
        spoiler_line = (
            f"- Spoiler guard is ON: only use content from chapters 1 through {max_chapter}.\n"
            f"- If the question needs later chapters, respond exactly: "
            f"\"I can only use chapters 1–{max_chapter}, and the provided excerpts do not answer that yet without spoilers.\""
        )
    else:
        spoiler_line = "- No spoiler guard is active; you may draw on any supplied excerpt."

    return f"""You are a reading companion for "{title}" by {author}.

Your job is to help the reader understand, discuss, and think with the book — in the spirit of {author}'s perspective, without claiming to literally be them.

Rules:
- Ground every answer in the supplied source chunks only.
- Each excerpt is tagged with a stable chunk id like `book-id:ch007:c001`.
- When citing, include the exact chunk id in square brackets, e.g. [book-id:ch007:c001].
- If the excerpts do not support an answer, say so directly.
- Be conversational and clarifying, not encyclopedic.
- When useful, connect ideas to earlier themes in the provided excerpts.
- Do not invent quotes, chapter names, chunk ids, or facts.
{spoiler_line}
"""


def answer_question(
    record: dict,
    paths: BookPaths,
    question: str,
    *,
    history: list[dict[str, str]] | None = None,
    current_chapter: int | None = None,
    max_chapter: int | None = None,
    auto_spoiler: bool = True,
    model: str | None = None,
    logger: logging.Logger | None = None,
) -> dict:
    clean_question = normalize_whitespace(question)
    if not clean_question:
        raise CompanionError("Question is required.")

    chapters = record.get("chapters", [])
    if not isinstance(chapters, list):
        chapters = []

    book_id = str(record.get("book_id", paths.book_dir.name))
    limits = resolve_spoiler_limits(
        current_chapter=current_chapter,
        max_chapter=max_chapter,
        auto_spoiler=auto_spoiler,
    )

    blocked = build_spoiler_blocked_response(
        clean_question,
        paths.chapters_dir,
        chapters,
        book_id=book_id,
        limits=limits,
    )
    if blocked is not None:
        return enrich_result_trust(blocked)

    snippets = retrieve_chapter_snippets(
        paths.chapters_dir,
        clean_question,
        chapters,
        book_id=book_id,
        current_chapter=limits.current_chapter,
        max_chapter=limits.max_chapter,
        allow_fallback=False,
    )
    if not snippets:
        snippets = retrieve_chapter_snippets(
            paths.chapters_dir,
            clean_question,
            chapters,
            book_id=book_id,
            current_chapter=limits.current_chapter,
            max_chapter=limits.max_chapter,
            allow_fallback=True,
        )
    if not snippets:
        raise CompanionError("No chapter context was available for this book.")

    if logger:
        logger.info(
            "companion.retrieve question=%r snippets=%d chunk_ids=%s",
            clean_question,
            len(snippets),
            [snippet.get("chunk_id") for snippet in snippets],
        )

    instructions = build_instructions(record, max_chapter=limits.max_chapter)
    prior_turns = _format_history(history or [])
    context = format_retrieved_context(snippets)
    reading_position = _format_reading_position(limits)
    input_text = (
        f"Book metadata:\n{json.dumps(_book_context(record), ensure_ascii=False, indent=2)}\n\n"
        f"Reading position:\n{reading_position}\n\n"
        f"Conversation so far:\n{prior_turns}\n\n"
        f"Question:\n{clean_question}\n\n"
        f"Retrieved chapter excerpts:\n{context}\n"
    )

    try:
        answer, resolved_model = complete_chat(system=instructions, user=input_text, model=model)
    except LlmConfigError as error:
        if logger:
            logger.exception("companion.llm_error question=%r", clean_question)
        raise CompanionError(str(error)) from error

    sources = format_sources(snippets)
    citation_check = validate_answer_citations(answer, snippets)
    return enrich_result_trust(
        {
            "answer": answer,
            "model": resolved_model,
            "sources": sources,
            "chunks": snippets,
            "citation_check": citation_check,
            "current_chapter": limits.current_chapter,
            "max_chapter": limits.max_chapter,
            "spoiler_auto_linked": limits.auto_linked,
            "spoiler_blocked": False,
            "_trace": {
                "retrieved_snippets": snippets,
                "retrieved_sources": sources,
                "citation_check": citation_check,
            },
        }
    )


def load_session(paths: BookPaths) -> dict:
    session_path = paths.companion_dir / "session.json"
    if not session_path.exists():
        return _empty_session()
    payload = read_json(session_path)
    if not isinstance(payload, dict):
        return _empty_session()
    return {
        "current_chapter": payload.get("current_chapter"),
        "max_chapter": payload.get("max_chapter"),
        "show_sources": bool(payload.get("show_sources", False)),
        "history": payload.get("history", []) if isinstance(payload.get("history"), list) else [],
        "updated_at": payload.get("updated_at"),
    }


def save_session(paths: BookPaths, session: dict) -> None:
    write_json(
        paths.companion_dir / "session.json",
        {
            "current_chapter": session.get("current_chapter"),
            "max_chapter": session.get("max_chapter"),
            "show_sources": bool(session.get("show_sources", False)),
            "history": session.get("history", [])[-20:],
            "updated_at": session.get("updated_at") or utc_now(),
        },
    )


def _empty_session() -> dict:
    return {
        "current_chapter": None,
        "max_chapter": None,
        "show_sources": False,
        "history": [],
        "updated_at": None,
    }


def set_reading_position(paths: BookPaths, *, current_chapter: int | None = None, max_chapter: int | None = None) -> dict:
    session = load_session(paths)
    if current_chapter is not None:
        session["current_chapter"] = current_chapter
    if max_chapter is not None:
        session["max_chapter"] = max_chapter
    save_session(paths, session)
    return session


def chat_loop(
    record: dict,
    paths: BookPaths,
    *,
    current_chapter: int | None = None,
    max_chapter: int | None = None,
    auto_spoiler: bool = True,
    model: str | None = None,
    show_sources: bool = False,
) -> None:
    session = load_session(paths)
    if current_chapter is not None:
        session["current_chapter"] = current_chapter
    if max_chapter is not None:
        session["max_chapter"] = max_chapter
    if show_sources:
        session["show_sources"] = True

    title = record.get("title", paths.book_dir.name)
    author = record.get("author", "Unknown")
    try:
        llm = resolve_llm_config(model=model)
        model_label = f"{llm.provider} / {llm.model}"
    except LlmConfigError as error:
        raise CompanionError(str(error)) from error

    print(f"\n📖 {title} by {author}")
    print(f"   {record.get('chapter_count', 0)} chapters")
    print(f"   Model: {model_label}")
    print(f"   Current chapter: {session.get('current_chapter') or 'not set'}")
    limits = resolve_spoiler_limits(
        current_chapter=session.get("current_chapter"),
        max_chapter=session.get("max_chapter"),
        auto_spoiler=auto_spoiler,
    )
    spoiler_label = "off"
    if limits.max_chapter is not None:
        spoiler_label = f"chapters 1–{limits.max_chapter}"
        if limits.auto_linked:
            spoiler_label += " (auto-linked to current chapter)"
    print(f"   Spoiler guard: {spoiler_label}")
    if record.get("content_start_chapter"):
        print(f"   Content starts: chapter {record['content_start_chapter']}")
    print(f"   Show sources: {'on' if session.get('show_sources') else 'off'}")
    print()
    print("Commands:")
    print("  /chapter N     — set reading position")
    print("  /spoiler N     — only use content up to chapter N")
    print("  /spoiler off   — disable spoiler guard")
    print("  /sources       — toggle retrieved source display")
    print("  /chapters      — list chapters")
    print("  /clear         — clear conversation")
    print("  /quit          — exit")
    print()

    history: list[dict[str, str]] = list(session.get("history", []))

    while True:
        try:
            question = input("❓ ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not question:
            continue

        lowered = question.lower()
        if lowered in {"/quit", "/q", "/exit"}:
            save_session(paths, {**session, "history": history})
            print("Bye!")
            break

        if lowered == "/clear":
            history = []
            save_session(paths, {**session, "history": history})
            print("Conversation cleared.")
            continue

        if lowered == "/sources":
            session["show_sources"] = not bool(session.get("show_sources"))
            save_session(paths, {**session, "history": history})
            print(f"Show sources: {'on' if session['show_sources'] else 'off'}")
            continue

        if lowered == "/chapters":
            _print_chapters(record)
            continue

        if lowered.startswith("/chapter"):
            value = question.split(maxsplit=1)[1].strip() if " " in question else ""
            if not value.isdigit():
                print("Usage: /chapter N")
                continue
            session["current_chapter"] = int(value)
            if auto_spoiler:
                session["max_chapter"] = int(value)
            save_session(paths, {**session, "history": history})
            chapter = _find_chapter(record, int(value))
            if chapter:
                print(f"Now reading: {chapter['index']}. {chapter['title']}")
            else:
                print(f"Set current chapter to {value}.")
            continue

        if lowered.startswith("/spoiler"):
            value = question.split(maxsplit=1)[1].strip() if " " in question else ""
            if not value or value.lower() == "off":
                session["max_chapter"] = None
                print("Spoiler guard off.")
            elif value.isdigit():
                session["max_chapter"] = int(value)
                print(f"Spoiler guard on: chapters 1–{value} only.")
            else:
                print("Usage: /spoiler N  or  /spoiler off")
                continue
            save_session(paths, {**session, "history": history})
            continue

        print("Thinking...")
        try:
            result = answer_question(
                record,
                paths,
                question,
                history=history,
                current_chapter=session.get("current_chapter"),
                max_chapter=session.get("max_chapter"),
                auto_spoiler=auto_spoiler,
                model=model,
            )
        except CompanionError as error:
            print(f"Error: {error}")
            continue

        answer = result["answer"]
        print(f"\n{'=' * 60}")
        print(answer)
        _print_result_sources(result, show_sources=bool(session.get("show_sources")))
        print(f"{'=' * 60}\n")

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})
        save_session(paths, {**session, "history": history})


def _print_result_sources(result: dict, *, show_sources: bool) -> None:
    if show_sources:
        print_sources(result.get("chunks", []))
    elif result.get("sources"):
        print("\nSources:")
        for source in result["sources"]:
            print(f"  • {source['chunk_id']} — Ch {source['chapter_index']}: {source['chapter_title']}")

    citation_check = result.get("citation_check", {})
    unknown = citation_check.get("unknown_chunk_ids") or []
    if unknown:
        print("\nCitation check:")
        print(f"  ⚠ Model cited chunk ids not in retrieval: {', '.join(unknown)}")


def _book_context(record: dict) -> dict:
    return {
        "book_id": record.get("book_id"),
        "title": record.get("title"),
        "author": record.get("author"),
        "chapter_count": record.get("chapter_count"),
        "language": record.get("language"),
    }


def _format_reading_position(limits) -> str:
    lines = []
    if limits.current_chapter is not None:
        lines.append(f"The reader is currently on chapter {limits.current_chapter}.")
    else:
        lines.append("The reader has not set a current chapter.")
    if limits.max_chapter is not None:
        lines.append(f"Do not use content from chapters after {limits.max_chapter}.")
        if limits.auto_linked:
            lines.append("Spoiler guard is auto-linked to the current chapter.")
    return "\n".join(lines)


def _format_history(history: list[dict[str, str]]) -> str:
    formatted: list[str] = []
    for item in history[-8:]:
        role = normalize_whitespace(item.get("role", "user")).lower()
        content = normalize_whitespace(item.get("content", ""))
        if role not in {"user", "assistant"} or not content:
            continue
        formatted.append(f"{role}: {excerpt(content, 400)}")
    return "\n".join(formatted) or "No prior conversation."


def _print_chapters(record: dict) -> None:
    chapters = record.get("chapters", [])
    if not isinstance(chapters, list):
        return
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        print(f"  {chapter.get('index', '?'):>3}  {chapter.get('title', '?')} ({chapter.get('word_count', 0)} words)")


def _find_chapter(record: dict, index: int) -> dict | None:
    chapters = record.get("chapters", [])
    if not isinstance(chapters, list):
        return None
    for chapter in chapters:
        if isinstance(chapter, dict) and chapter.get("index") == index:
            return chapter
    return None