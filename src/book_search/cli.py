from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .citations import print_sources
from .companion import CompanionError, answer_question, chat_loop, set_reading_position
from .llm import RECOMMENDED_MODELS
from .pipeline import ingest_source, list_books, load_book_record
from .paths import WorkspaceDiscoveryError
from .eval import DEFAULT_JUDGE_MODEL, judge_eval_results, run_spoiler_eval
from .retrieval import search_chapters


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

    chapters = subparsers.add_parser("chapters", help="List chapters for an ingested book")
    chapters.add_argument("book_id", help="Previously ingested book id")

    search = subparsers.add_parser("search", help="Search chapter text without calling an LLM")
    search.add_argument("book_id", help="Previously ingested book id")
    search.add_argument("query", help="Search query")
    search.add_argument("--chapter", type=int, help="Bias retrieval toward this chapter")
    search.add_argument("--spoiler", type=int, help="Only use content up to this chapter")
    search.add_argument("--limit", type=int, default=10, help="Maximum chunks to return")

    position = subparsers.add_parser("position", help="Get or set persisted reading position")
    position.add_argument("book_id", help="Previously ingested book id")
    position_sub = position.add_subparsers(dest="position_command", required=False)

    position_show = position_sub.add_parser("show", help="Show saved reading position")
    position_show.set_defaults(position_command="show")

    position_set = position_sub.add_parser("set", help="Set saved reading position")
    position_set.add_argument("chapter", type=int, help="Current chapter number")
    position_set.add_argument("--spoiler", type=int, help="Spoiler guard chapter limit")
    position_set.set_defaults(position_command="set")

    ask = subparsers.add_parser("ask", help="Ask a one-shot question about an ingested book")
    ask.add_argument("book_id", help="Previously ingested book id")
    ask.add_argument("question", help="Question to ask")
    ask.add_argument("--chapter", type=int, help="Bias retrieval toward this chapter")
    ask.add_argument("--spoiler", type=int, help="Only use content up to this chapter")
    ask.add_argument("--model", help="Model slug (OpenRouter or OpenAI; see `book-search models`)")
    ask.add_argument("--show-sources", action="store_true", help="Print retrieved chunk excerpts")
    ask.add_argument(
        "--no-spoiler-auto",
        action="store_true",
        help="Do not auto-link spoiler guard to --chapter when --spoiler is omitted",
    )

    chat = subparsers.add_parser("chat", help="Interactive reading companion")
    chat.add_argument("book_id", help="Previously ingested book id")
    chat.add_argument("--chapter", type=int, help="Initial reading position")
    chat.add_argument("--spoiler", type=int, help="Only use content up to this chapter")
    chat.add_argument("--model", help="Model slug (OpenRouter or OpenAI; see `book-search models`)")
    chat.add_argument("--show-sources", action="store_true", help="Always print retrieved chunk excerpts")
    chat.add_argument(
        "--no-spoiler-auto",
        action="store_true",
        help="Do not auto-link spoiler guard to --chapter when --spoiler is omitted",
    )

    subparsers.add_parser("models", help="List recommended chat models")

    eval_cmd = subparsers.add_parser("eval", help="Run product eval suites")
    eval_sub = eval_cmd.add_subparsers(dest="eval_command", required=True)
    spoiler_eval = eval_sub.add_parser("spoiler", help="Run spoiler-guard eval suite")
    spoiler_eval.add_argument("--judge-model", default=None, help="Optional LLM judge model slug")
    spoiler_eval.add_argument("--json", action="store_true", help="Print machine-readable output")

    return parser


def _print_chapter_list(record: dict) -> None:
    chapters = record.get("chapters", [])
    if not isinstance(chapters, list) or not chapters:
        print("No chapters found.")
        return
    if record.get("content_start_chapter"):
        print(f"Content starts at chapter {record['content_start_chapter']}\n")
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        kind = str(chapter.get("kind", "body"))[:12]
        print(
            f"  {int(chapter.get('index', 0)):>3}  "
            f"{kind:12s}  "
            f"{str(chapter.get('title', '?'))[:50]:50s}  "
            f"{int(chapter.get('word_count', 0)):>6,} words"
        )


def _print_ask_sources(result: dict, *, show_sources: bool) -> None:
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

        if args.command == "chapters":
            record, _paths = load_book_record(args.book_id, workspace)
            print(f"{record.get('title', args.book_id)} — {record.get('chapter_count', 0)} chapters\n")
            _print_chapter_list(record)
            return 0

        if args.command == "search":
            record, paths = load_book_record(args.book_id, workspace)
            chapters = record.get("chapters", [])
            snippets = search_chapters(
                paths.chapters_dir,
                args.query,
                chapters if isinstance(chapters, list) else [],
                book_id=str(record.get("book_id", args.book_id)),
                current_chapter=args.chapter,
                max_chapter=args.spoiler,
                limit=args.limit,
            )
            if not snippets:
                print("No matching chunks found.")
                return 0
            print_sources(snippets, heading=f"Search results ({len(snippets)})")
            return 0

        if args.command == "position":
            _paths = load_book_record(args.book_id, workspace)[1]
            if args.position_command in (None, "show"):
                from .companion import load_session

                session = load_session(_paths)
                print(f"Current chapter: {session.get('current_chapter') or 'not set'}")
                print(f"Spoiler guard: {session.get('max_chapter') or 'off'}")
                return 0
            if args.position_command == "set":
                session = set_reading_position(
                    _paths,
                    current_chapter=args.chapter,
                    max_chapter=args.spoiler,
                )
                print(f"Saved current chapter: {session.get('current_chapter')}")
                if session.get("max_chapter") is not None:
                    print(f"Saved spoiler guard: chapters 1–{session['max_chapter']}")
                return 0
            parser.parse_args(["position", "--help"])
            return 0

        if args.command == "eval":
            if args.eval_command == "spoiler":
                results = run_spoiler_eval(workspace)
                passed = sum(1 for item in results if item.passed)
                report = {
                    "suite": "spoiler",
                    "passed": passed,
                    "total": len(results),
                    "results": [
                        {
                            "id": item.id,
                            "description": item.description,
                            "passed": item.passed,
                            "details": item.details,
                        }
                        for item in results
                    ],
                }
                judge = None
                if args.judge_model:
                    judge = judge_eval_results(
                        results,
                        suite="spoiler",
                        judge_model=args.judge_model,
                        implementation_notes=(
                            "Oracle #2: auto-link spoiler to current chapter, informed refusal, "
                            "front matter classification, retrieval exclusion."
                        ),
                    )
                    report["judge"] = judge
                if args.json:
                    print(json.dumps(report, indent=2, ensure_ascii=False))
                else:
                    print(f"Spoiler eval: {passed}/{len(results)} passed\n")
                    for item in results:
                        status = "PASS" if item.passed else "FAIL"
                        print(f"  [{status}] {item.id}: {item.description}")
                        if not item.passed:
                            print(f"         {item.details}")
                    if judge:
                        print("\nLLM judge:")
                        print(f"  model: {judge.get('judge_model', args.judge_model)}")
                        print(f"  overall_pass: {judge.get('overall_pass')}")
                        print(f"  score: {judge.get('score')}")
                        print(f"  summary: {judge.get('summary', '')}")
                        for finding in judge.get("findings", [])[:5]:
                            if isinstance(finding, dict):
                                print(
                                    f"  - [{finding.get('severity', '?')}] "
                                    f"{finding.get('issue', '')} -> {finding.get('recommendation', '')}"
                                )
                return 0 if passed == len(results) else 1
            return 1

        if args.command == "ask":
            record, paths = load_book_record(args.book_id, workspace)
            result = answer_question(
                record,
                paths,
                args.question,
                current_chapter=args.chapter,
                max_chapter=args.spoiler,
                auto_spoiler=not args.no_spoiler_auto,
                model=args.model,
            )
            print(result["answer"])
            _print_ask_sources(result, show_sources=args.show_sources)
            return 0

        if args.command == "chat":
            record, paths = load_book_record(args.book_id, workspace)
            chat_loop(
                record,
                paths,
                current_chapter=args.chapter,
                max_chapter=args.spoiler,
                auto_spoiler=not args.no_spoiler_auto,
                model=args.model,
                show_sources=args.show_sources,
            )
            return 0

    except (FileNotFoundError, FileExistsError, ValueError, WorkspaceDiscoveryError, CompanionError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    parser.print_help()
    return 1