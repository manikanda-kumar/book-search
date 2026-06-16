from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .companion import CompanionError, answer_question, chat_loop
from .llm import RECOMMENDED_MODELS
from .pipeline import ingest_source, list_books, load_book_record
from .paths import WorkspaceDiscoveryError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="book-search",
        description="Reading companion — ingest books and discuss them while you read",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        help="Explicit workspace root (defaults to nearest pyproject.toml)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="Copy and extract an EPUB into the workspace")
    ingest.add_argument("source", help="Path to a local EPUB file")
    ingest.add_argument("--book-id", help="Override the generated book id")
    ingest.add_argument("--force", action="store_true", help="Overwrite an existing ingested book id")

    subparsers.add_parser("list", help="List ingested books")

    show = subparsers.add_parser("show", help="Show metadata and chapter list for an ingested book")
    show.add_argument("book_id", help="Previously ingested book id")

    ask = subparsers.add_parser("ask", help="Ask a one-shot question about an ingested book")
    ask.add_argument("book_id", help="Previously ingested book id")
    ask.add_argument("question", help="Question to ask")
    ask.add_argument("--chapter", type=int, help="Bias retrieval toward this chapter")
    ask.add_argument("--spoiler", type=int, help="Only use content up to this chapter")
    ask.add_argument("--model", help="Model slug (OpenRouter or OpenAI; see `book-search models`)")

    chat = subparsers.add_parser("chat", help="Interactive reading companion")
    chat.add_argument("book_id", help="Previously ingested book id")
    chat.add_argument("--chapter", type=int, help="Initial reading position")
    chat.add_argument("--spoiler", type=int, help="Only use content up to this chapter")
    chat.add_argument("--model", help="Model slug (OpenRouter or OpenAI; see `book-search models`)")

    subparsers.add_parser("models", help="List recommended chat models")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    workspace = getattr(args, "workspace", None)

    try:
        if args.command == "ingest":
            book_id, record, paths = ingest_source(
                Path(args.source),
                book_id=args.book_id,
                force=args.force,
                workspace=workspace,
            )
            print(f"Ingested {record['title']} as `{book_id}`")
            print(f"Author: {record['author']}")
            print(f"Chapters: {record['chapter_count']}")
            print(f"Data: {paths.book_dir}")
            return 0

        if args.command == "models":
            print("Recommended models for book-search companion:\n")
            for item in RECOMMENDED_MODELS:
                print(f"  {item['id']}")
                print(f"    {item['label']} — {item['notes']}")
                print(f"    tier: {item['tier']}\n")
            print("Set OPENROUTER_API_KEY, then optionally:")
            print("  export BOOK_SEARCH_CHAT_MODEL=moonshotai/kimi-k2.6")
            return 0

        if args.command == "list":
            books = list_books(workspace)
            if not books:
                print("No ingested books.")
                return 0
            for book in books:
                print(
                    f"  {book['book_id']:30s}  {book['title'][:40]:40s}  "
                    f"{book['chapter_count']:>3s} ch  {book['author']}"
                )
            return 0

        if args.command == "show":
            record, paths = load_book_record(args.book_id, workspace)
            print(json.dumps(record, indent=2, ensure_ascii=False))
            print(f"\nBook directory: {paths.book_dir}")
            return 0

        if args.command == "ask":
            record, paths = load_book_record(args.book_id, workspace)
            result = answer_question(
                record,
                paths,
                args.question,
                current_chapter=args.chapter,
                max_chapter=args.spoiler,
                model=args.model,
            )
            print(result["answer"])
            if result.get("sources"):
                print("\nSources:")
                for source in result["sources"]:
                    print(f"  • Ch {source['chapter_index']}: {source['chapter_title']}")
            return 0

        if args.command == "chat":
            record, paths = load_book_record(args.book_id, workspace)
            chat_loop(
                record,
                paths,
                current_chapter=args.chapter,
                max_chapter=args.spoiler,
                model=args.model,
            )
            return 0

    except (FileNotFoundError, FileExistsError, ValueError, WorkspaceDiscoveryError, CompanionError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    parser.print_help()
    return 1