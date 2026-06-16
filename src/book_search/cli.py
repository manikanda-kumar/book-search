from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .citations import print_sources
from .companion import CompanionError, answer_question, chat_loop, set_reading_position
from .llm import RECOMMENDED_MODELS
from .config import describe_config
from .doctor import doctor_has_failures, run_doctor
from .pipeline import delete_book, ingest_source, list_books, load_book_record
from .session_io import export_session, reset_session, session_summary
from .paths import WorkspaceDiscoveryError
from .eval import (
    DEFAULT_JUDGE_MODEL,
    EvalResult,
    judge_eval_results,
    run_all_evals,
    run_ingestion_eval,
    run_retrieval_eval,
    run_spoiler_eval,
    run_workflow_eval,
)
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

    config_cmd = subparsers.add_parser("config", help="Show resolved workspace and model configuration")
    config_cmd.add_argument("--json", action="store_true", help="Print machine-readable output")

    serve = subparsers.add_parser("serve", help="Start the constrained reading companion UI")
    serve.add_argument("--host", default="127.0.0.1", help="Bind host")
    serve.add_argument("--port", type=int, default=8765, help="Bind port")
    serve.add_argument("--book-id", help="Optional default book id")
    serve.add_argument("--open", action="store_true", help="Open the UI in a browser")

    subparsers.add_parser("doctor", help="Validate workspace, dependencies, and ingested books")

    session = subparsers.add_parser("session", help="Export or reset persisted companion sessions")
    session.add_argument("book_id", help="Previously ingested book id")
    session_sub = session.add_subparsers(dest="session_command", required=True)
    session_sub.add_parser("show", help="Show session summary")
    session_export = session_sub.add_parser("export", help="Export session history to JSON")
    session_export.add_argument("--output", type=Path, help="Destination file (default: companion dir)")
    session_reset = session_sub.add_parser("reset", help="Clear session history")
    session_reset.add_argument(
        "--keep-position",
        action="store_true",
        help="Keep current chapter and spoiler guard when clearing history",
    )

    delete = subparsers.add_parser("delete", help="Remove an ingested book from the workspace")
    delete.add_argument("book_id", help="Previously ingested book id")

    eval_cmd = subparsers.add_parser("eval", help="Run product eval suites")
    eval_sub = eval_cmd.add_subparsers(dest="eval_command", required=True)
    for suite_name, help_text in (
        ("spoiler", "Run spoiler-guard eval suite"),
        ("retrieval", "Run retrieval eval suite"),
        ("ingestion", "Run ingestion diagnostics eval suite"),
        ("workflow", "Run workflow polish eval suite"),
        ("all", "Run all eval suites"),
    ):
        suite_parser = eval_sub.add_parser(suite_name, help=help_text)
        suite_parser.add_argument(
            "--judge-model",
            default=DEFAULT_JUDGE_MODEL,
            help="LLM judge model slug (use --no-judge to skip)",
        )
        suite_parser.add_argument("--no-judge", action="store_true", help="Skip LLM judge review")
        suite_parser.add_argument("--json", action="store_true", help="Print machine-readable output")

    return parser


def _print_chapter_list(record: dict) -> None:
    chapters = record.get("chapters", [])
    if not isinstance(chapters, list) or not chapters:
        print("No chapters found.")
        return
    if record.get("content_start_chapter"):
        print(f"Content starts at chapter {record['content_start_chapter']}")
    warnings = record.get("extraction_warnings") or []
    if warnings:
        print(f"Extraction warnings: {len(warnings)}")
        for warning in warnings[:3]:
            print(f"  • {warning}")
    print()
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


def _build_eval_report(suite: str, results: list[EvalResult]) -> dict:
    passed = sum(1 for item in results if item.passed)
    return {
        "suite": suite,
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


def _print_eval_report(
    report: dict,
    *,
    json_output: bool,
    judge: dict | None,
    judge_model: str | None,
) -> None:
    if json_output:
        if judge:
            report["judge"] = judge
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    suite = report.get("suite", "eval")
    passed = report.get("passed", 0)
    total = report.get("total", 0)
    print(f"{suite.title()} eval: {passed}/{total} passed\n")
    for item in report.get("results", []):
        status = "PASS" if item.get("passed") else "FAIL"
        print(f"  [{status}] {item.get('id')}: {item.get('description')}")
        if not item.get("passed"):
            print(f"         {item.get('details')}")
    if judge:
        print("\nLLM judge:")
        print(f"  model: {judge.get('judge_model', judge_model)}")
        print(f"  overall_pass: {judge.get('overall_pass')}")
        print(f"  score: {judge.get('score')}")
        print(f"  summary: {judge.get('summary', '')}")
        for finding in judge.get("findings", [])[:5]:
            if isinstance(finding, dict):
                print(
                    f"  - [{finding.get('severity', '?')}] "
                    f"{finding.get('issue', '')} -> {finding.get('recommendation', '')}"
                )


def _run_eval_suite(
    suite: str,
    results: list[EvalResult],
    *,
    judge_model: str | None,
    no_judge: bool,
    json_output: bool,
    implementation_notes: str,
    extra_judge_payload: dict | None = None,
) -> int:
    report = _build_eval_report(suite, results)
    judge = None
    if not no_judge and judge_model:
        judge = judge_eval_results(
            results,
            suite=suite,
            judge_model=judge_model,
            implementation_notes=implementation_notes,
            extra_payload=extra_judge_payload,
        )
    _print_eval_report(report, json_output=json_output, judge=judge, judge_model=judge_model)
    return 0 if report["passed"] == report["total"] else 1


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
            warnings = record.get("extraction_warnings") or []
            if warnings:
                print(f"Warnings ({len(warnings)}):")
                for warning in warnings[:5]:
                    print(f"  • {warning}")
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

        if args.command == "config":
            payload = describe_config(workspace)
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                print(f"Workspace: {payload['workspace_root']}")
                print(f"Books dir: {payload['books_dir']}")
                print(f"Python: {payload['python_version']}")
                if payload.get("llm"):
                    llm = payload["llm"]
                    print(f"LLM: {llm['provider']} / {llm['model']}")
                    print(f"API key: {llm['api_key']}")
                else:
                    print(f"LLM: not configured ({payload.get('llm_error')})")
                chat_model = payload.get("env", {}).get("BOOK_SEARCH_CHAT_MODEL")
                if chat_model:
                    print(f"BOOK_SEARCH_CHAT_MODEL: {chat_model}")
            return 0

        if args.command == "session":
            record, paths = load_book_record(args.book_id, workspace)
            if args.session_command == "show":
                summary = session_summary(paths, record)
                if getattr(args, "json", False):
                    print(json.dumps(summary, indent=2, ensure_ascii=False))
                else:
                    print(f"Book: {summary.get('title')} ({summary.get('book_id')})")
                    print(f"Current chapter: {summary.get('current_chapter') or 'not set'}")
                    print(f"Spoiler guard: {summary.get('max_chapter') or 'off'}")
                    print(f"Show sources: {'on' if summary.get('show_sources') else 'off'}")
                    print(f"Turns: {summary.get('turn_count', 0)}")
                    if summary.get("updated_at"):
                        print(f"Updated: {summary['updated_at']}")
                return 0
            if args.session_command == "export":
                destination = export_session(paths, record, output_path=args.output)
                print(f"Exported session to {destination}")
                return 0
            if args.session_command == "reset":
                cleared = reset_session(paths, keep_position=args.keep_position)
                print("Session reset.")
                if args.keep_position:
                    print(f"Kept current chapter: {cleared.get('current_chapter') or 'not set'}")
                    print(f"Kept spoiler guard: {cleared.get('max_chapter') or 'off'}")
                else:
                    print("Cleared reading position and spoiler guard.")
                return 0
            return 1

        if args.command == "serve":
            from .ui import serve_ui

            serve_ui(
                host=args.host,
                port=args.port,
                workspace=workspace,
                book_id=args.book_id,
                open_browser=args.open,
            )
            return 0

        if args.command == "doctor":
            checks = run_doctor(workspace)
            for check in checks:
                label = check.status.upper()
                print(f"  [{label}] {check.id}: {check.message}")
            return 1 if doctor_has_failures(checks) else 0

        if args.command == "delete":
            paths = delete_book(args.book_id, workspace)
            print(f"Deleted book `{args.book_id}` from {paths.book_dir.parent}")
            return 0

        if args.command == "eval":
            eval_notes = {
                "spoiler": (
                    "Oracle #2: auto-link spoiler to current chapter, informed refusal, "
                    "front matter classification, retrieval exclusion."
                ),
                "retrieval": (
                    "Oracle #3: chapter bias, character intro, spoiler limits, themes-so-far, "
                    "chunk ids, later-answer refusal."
                ),
                "ingestion": (
                    "P1: extraction warnings, content start detection, duplicate identifier guard."
                ),
                "workflow": (
                    "P2: session export/reset, config diagnostics with masked secrets."
                ),
                "all": "Aggregated spoiler, retrieval, ingestion, and workflow suites.",
            }
            if args.eval_command == "spoiler":
                return _run_eval_suite(
                    "spoiler",
                    run_spoiler_eval(workspace),
                    judge_model=None if args.no_judge else args.judge_model,
                    no_judge=args.no_judge,
                    json_output=args.json,
                    implementation_notes=eval_notes["spoiler"],
                )
            if args.eval_command == "retrieval":
                return _run_eval_suite(
                    "retrieval",
                    run_retrieval_eval(workspace),
                    judge_model=None if args.no_judge else args.judge_model,
                    no_judge=args.no_judge,
                    json_output=args.json,
                    implementation_notes=eval_notes["retrieval"],
                )
            if args.eval_command == "ingestion":
                return _run_eval_suite(
                    "ingestion",
                    run_ingestion_eval(workspace),
                    judge_model=None if args.no_judge else args.judge_model,
                    no_judge=args.no_judge,
                    json_output=args.json,
                    implementation_notes=eval_notes["ingestion"],
                )
            if args.eval_command == "workflow":
                return _run_eval_suite(
                    "workflow",
                    run_workflow_eval(workspace),
                    judge_model=None if args.no_judge else args.judge_model,
                    no_judge=args.no_judge,
                    json_output=args.json,
                    implementation_notes=eval_notes["workflow"],
                )
            if args.eval_command == "all":
                suites = run_all_evals(workspace)
                all_results = [item for results in suites.values() for item in results]
                passed = sum(1 for item in all_results if item.passed)
                report = {
                    "suite": "all",
                    "passed": passed,
                    "total": len(all_results),
                    "suites": {name: _build_eval_report(name, results) for name, results in suites.items()},
                }
                judge = None
                if not args.no_judge and args.judge_model:
                    judge = judge_eval_results(
                        all_results,
                        suite="all",
                        judge_model=args.judge_model,
                        implementation_notes=eval_notes["all"],
                        extra_payload={"suites": report["suites"]},
                    )
                if args.json:
                    if judge:
                        report["judge"] = judge
                    print(json.dumps(report, indent=2, ensure_ascii=False))
                else:
                    print(f"All evals: {passed}/{len(all_results)} passed\n")
                    for name, results in suites.items():
                        suite_passed = sum(1 for item in results if item.passed)
                        print(f"{name.title()} ({suite_passed}/{len(results)})")
                        for item in results:
                            status = "PASS" if item.passed else "FAIL"
                            print(f"  [{status}] {item.id}")
                    if judge:
                        print("\nLLM judge:")
                        print(f"  model: {judge.get('judge_model', args.judge_model)}")
                        print(f"  overall_pass: {judge.get('overall_pass')}")
                        print(f"  score: {judge.get('score')}")
                        print(f"  summary: {judge.get('summary', '')}")
                return 0 if passed == len(all_results) else 1
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
            if result.get("trust_label"):
                print(f"[{result['trust_label']}]")
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