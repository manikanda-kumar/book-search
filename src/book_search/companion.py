from __future__ import annotations

import json
import logging
from pathlib import Path

from .llm import LlmConfigError, complete_chat, resolve_llm_config
from .paths import BookPaths
from .retrieval import format_sources, retrieve_chapter_snippets
from .util import excerpt, normalize_whitespace, read_json, write_json


class CompanionError(RuntimeError):
    pass


def build_instructions(record: dict, *, max_chapter: int | None = None) -> str:
    title = record.get("title", "this book")
    author = record.get("author", "the author")
    spoiler_line = (
        f"- Spoiler guard is ON: only discuss content from chapters 1 through {max_chapter}. "
        "If the question requires later material, say you have not read that far yet."
        if max_chapter is not None
        else "- No spoiler guard is active; you may draw on any supplied excerpt."
    )
    return f"""You are a reading companion for "{title}" by {author}.

Your job is to help the reader understand, discuss, and think with the book — in the spirit of {author}'s perspective, without claiming to literally be them.

Rules:
- Ground every answer in the supplied chapter excerpts only.
- If the excerpts do not support an answer, say so directly.
- Cite sources inline as [Chapter N: Title].
- Be conversational and clarifying, not encyclopedic.
- When useful, connect ideas to earlier themes in the provided excerpts.
- Do not invent quotes, chapter names, or facts.
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
    model: str | None = None,
    logger: logging.Logger | None = None,
) -> dict:
    clean_question = normalize_whitespace(question)
    if not clean_question:
        raise CompanionError("Question is required.")

    chapters = record.get("chapters", [])
    if not isinstance(chapters, list):
        chapters = []

    snippets = retrieve_chapter_snippets(
        paths.chapters_dir,
        clean_question,
        chapters,
        current_chapter=current_chapter,
        max_chapter=max_chapter,
    )
    if not snippets:
        raise CompanionError("No chapter context was available for this book.")

    if logger:
        logger.info(
            "companion.retrieve question=%r snippets=%d chapters=%s",
            clean_question,
            len(snippets),
            [snippet.get("chapter_index") for snippet in snippets],
        )

    instructions = build_instructions(record, max_chapter=max_chapter)
    prior_turns = _format_history(history or [])
    context = "\n\n".join(_format_snippet(snippet) for snippet in snippets)
    reading_position = _format_reading_position(current_chapter, max_chapter)
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
    return {
        "answer": answer,
        "model": resolved_model,
        "sources": sources,
        "current_chapter": current_chapter,
        "max_chapter": max_chapter,
        "_trace": {
            "retrieved_snippets": snippets,
            "retrieved_sources": sources,
        },
    }


def load_session(paths: BookPaths) -> dict:
    session_path = paths.companion_dir / "session.json"
    if not session_path.exists():
        return {"current_chapter": None, "max_chapter": None, "history": []}
    payload = read_json(session_path)
    if not isinstance(payload, dict):
        return {"current_chapter": None, "max_chapter": None, "history": []}
    return {
        "current_chapter": payload.get("current_chapter"),
        "max_chapter": payload.get("max_chapter"),
        "history": payload.get("history", []) if isinstance(payload.get("history"), list) else [],
    }


def save_session(paths: BookPaths, session: dict) -> None:
    write_json(
        paths.companion_dir / "session.json",
        {
            "current_chapter": session.get("current_chapter"),
            "max_chapter": session.get("max_chapter"),
            "history": session.get("history", [])[-20:],
        },
    )


def chat_loop(
    record: dict,
    paths: BookPaths,
    *,
    current_chapter: int | None = None,
    max_chapter: int | None = None,
    model: str | None = None,
) -> None:
    session = load_session(paths)
    if current_chapter is not None:
        session["current_chapter"] = current_chapter
    if max_chapter is not None:
        session["max_chapter"] = max_chapter

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
    print(f"   Spoiler guard: {session.get('max_chapter') or 'off'}")
    print()
    print("Commands:")
    print("  /chapter N     — set reading position")
    print("  /spoiler N     — only use content up to chapter N")
    print("  /spoiler off   — disable spoiler guard")
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

        if lowered == "/chapters":
            _print_chapters(record)
            continue

        if lowered.startswith("/chapter"):
            value = question.split(maxsplit=1)[1].strip() if " " in question else ""
            if not value.isdigit():
                print("Usage: /chapter N")
                continue
            session["current_chapter"] = int(value)
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
                model=model,
            )
        except CompanionError as error:
            print(f"Error: {error}")
            continue

        answer = result["answer"]
        print(f"\n{'=' * 60}")
        print(answer)
        if result.get("sources"):
            print("\nSources:")
            for source in result["sources"]:
                print(f"  • Ch {source['chapter_index']}: {source['chapter_title']}")
        print(f"{'=' * 60}\n")

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})
        save_session(paths, {**session, "history": history})


def _book_context(record: dict) -> dict:
    return {
        "title": record.get("title"),
        "author": record.get("author"),
        "chapter_count": record.get("chapter_count"),
        "language": record.get("language"),
    }


def _format_snippet(snippet: dict[str, str | int]) -> str:
    return (
        f"Chapter {snippet.get('chapter_index')}: {snippet.get('chapter_title')}\n"
        f"File: {snippet.get('file')}\n"
        f"Heading: {snippet.get('heading')}\n"
        f"Excerpt:\n{snippet.get('text')}"
    )


def _format_reading_position(current_chapter: int | None, max_chapter: int | None) -> str:
    lines = []
    if current_chapter is not None:
        lines.append(f"The reader is currently on chapter {current_chapter}.")
    else:
        lines.append("The reader has not set a current chapter.")
    if max_chapter is not None:
        lines.append(f"Do not use content from chapters after {max_chapter}.")
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