from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .chapters import content_start_chapter, enrich_book_chapters
from .citations import answer_trust_status, enrich_result_trust
from .companion import load_session, save_session
from .config import describe_config, mask_secret
from .eval_fixtures import build_standard_eval_book, build_watermark_eval_book
from .llm import LlmConfigError, complete_chat
from .pipeline import ingest_source
from .session_io import export_session, reset_session
from .retrieval import retrieve_chapter_snippets, search_chapters
from .spoiler import build_spoiler_blocked_response, resolve_spoiler_limits
from .testdata import make_minimal_epub


DEFAULT_JUDGE_MODEL = "minimax/minimax-m2.5"

JUDGE_PROMPTS: dict[str, str] = {
    "spoiler": """You are a strict QA judge for a book-reading companion product.
Review deterministic eval results for spoiler-guard semantics.
Return JSON only with keys:
- overall_pass: boolean
- score: number from 0 to 100
- findings: array of {severity: "high"|"medium"|"low", issue: string, recommendation: string}
- summary: string
Be concrete. Fail the review if spoiler refusal behavior is weak or ambiguous.""",
    "retrieval": """You are a strict QA judge for a book-reading companion product.
Review deterministic eval results for chapter-aware lexical retrieval.
Return JSON only with keys:
- overall_pass: boolean
- score: number from 0 to 100
- findings: array of {severity: "high"|"medium"|"low", issue: string, recommendation: string}
- summary: string
Be concrete. Fail the review if retrieval does not respect chapter bias, spoiler limits, or chunk id stability.""",
    "ingestion": """You are a strict QA judge for a book-reading companion product.
Review deterministic eval results for EPUB ingestion diagnostics and duplicate detection.
Return JSON only with keys:
- overall_pass: boolean
- score: number from 0 to 100
- findings: array of {severity: "high"|"medium"|"low", issue: string, recommendation: string}
- summary: string
Be concrete. Fail the review if extraction warnings or duplicate guards are missing or weak.""",
    "workflow": """You are a strict QA judge for a book-reading companion product.
Review deterministic eval results for user workflow polish (session export/reset, config diagnostics).
Return JSON only with keys:
- overall_pass: boolean
- score: number from 0 to 100
- findings: array of {severity: "high"|"medium"|"low", issue: string, recommendation: string}
- summary: string
Be concrete. Fail the review if session export/reset or config diagnostics are incomplete.""",
    "all": """You are a strict QA judge for a book-reading companion product.
Review aggregated eval results across spoiler, retrieval, ingestion, and workflow suites.
Return JSON only with keys:
- overall_pass: boolean
- score: number from 0 to 100
- findings: array of {severity: "high"|"medium"|"low", issue: string, recommendation: string}
- summary: string
Be concrete. Fail if any suite has critical gaps for a trustworthy reading companion.""",
}

JUDGE_USER_TEMPLATES: dict[str, str] = {
    "spoiler": "Review this eval report for Oracle recommendation #2 (spoiler guard semantics).\n\n{payload}",
    "retrieval": "Review this eval report for Oracle recommendation #3 (product-level retrieval evals).\n\n{payload}",
    "ingestion": "Review this eval report for P1 ingestion reliability (warnings and duplicate detection).\n\n{payload}",
    "workflow": "Review this eval report for P2 workflow polish (session export/reset, config diagnostics).\n\n{payload}",
    "all": "Review this aggregated eval report across all product suites.\n\n{payload}",
}


@dataclass(frozen=True)
class EvalCase:
    id: str
    description: str
    check: str


@dataclass
class EvalResult:
    id: str
    description: str
    passed: bool
    details: str
    evidence: dict


def run_spoiler_eval(workspace: Path | None = None) -> list[EvalResult]:
    tmp_root = _eval_workspace(workspace)
    record, paths = build_standard_eval_book(tmp_root)

    results: list[EvalResult] = []
    results.append(_eval_auto_link_spoiler(record, paths))
    results.append(_eval_refusal_with_later_match(record, paths))
    results.append(_eval_refusal_without_later_match(record, paths))
    results.append(_eval_front_matter_classification(record))
    results.append(_eval_spoiler_excludes_later_retrieval(record, paths))
    return results


def run_retrieval_eval(workspace: Path | None = None) -> list[EvalResult]:
    tmp_root = _eval_workspace(workspace)
    record, paths = build_standard_eval_book(tmp_root)
    chapters = record["chapters"]
    chapters_dir = paths.chapters_dir
    book_id = "eval-book"

    results: list[EvalResult] = []
    results.append(_eval_summarize_chapter_prefers_target(record, chapters_dir, chapters, book_id))
    results.append(_eval_character_introduction(record, chapters_dir, chapters, book_id))
    results.append(_eval_spoiler_retrieval_excludes_later(record, chapters_dir, chapters, book_id))
    results.append(_eval_themes_respect_spoiler(record, chapters_dir, chapters, book_id))
    results.append(_eval_chapter_boost_predictable(record, chapters_dir, chapters, book_id))
    results.append(_eval_search_returns_chunk_ids(record, chapters_dir, chapters, book_id))
    results.append(_eval_later_answer_blocked(record, paths))
    return results


def run_ingestion_eval(workspace: Path | None = None) -> list[EvalResult]:
    tmp_root = _eval_workspace(workspace)

    results: list[EvalResult] = []
    results.append(_eval_watermark_warnings(tmp_root))
    results.append(_eval_warnings_stored_on_record(tmp_root))
    results.append(_eval_content_start_detected(tmp_root))
    results.append(_eval_duplicate_identifier_guard(tmp_root))
    return results


def run_workflow_eval(workspace: Path | None = None) -> list[EvalResult]:
    tmp_root = _eval_workspace(workspace)

    results: list[EvalResult] = []
    results.append(_eval_session_export_includes_metadata(tmp_root))
    results.append(_eval_session_reset_clears_history(tmp_root))
    results.append(_eval_session_reset_keep_position(tmp_root))
    results.append(_eval_config_describe_includes_workspace(tmp_root))
    results.append(_eval_config_masks_api_keys())
    results.append(_eval_trust_status_spoiler_blocked(tmp_root))
    results.append(_eval_trust_status_sources_available(tmp_root))
    results.append(_eval_trust_status_citation_warning())
    return results


def run_all_evals(workspace: Path | None = None) -> dict[str, list[EvalResult]]:
    return {
        "spoiler": run_spoiler_eval(workspace),
        "retrieval": run_retrieval_eval(workspace),
        "ingestion": run_ingestion_eval(workspace),
        "workflow": run_workflow_eval(workspace),
    }


def judge_eval_results(
    results: list[EvalResult],
    *,
    suite: str,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    implementation_notes: str = "",
    extra_payload: dict | None = None,
) -> dict:
    payload = {
        "suite": suite,
        "results": [asdict(result) for result in results],
        "implementation_notes": implementation_notes,
    }
    if extra_payload:
        payload.update(extra_payload)

    system = JUDGE_PROMPTS.get(suite, JUDGE_PROMPTS["all"])
    user_template = JUDGE_USER_TEMPLATES.get(suite, JUDGE_USER_TEMPLATES["all"])
    user = user_template.format(payload=json.dumps(payload, indent=2, ensure_ascii=False))

    try:
        raw, model = complete_chat(system=system, user=user, model=judge_model, max_tokens=1200)
    except LlmConfigError as error:
        return {
            "overall_pass": None,
            "score": None,
            "findings": [],
            "summary": f"Judge unavailable: {error}",
            "judge_model": judge_model,
            "parse_error": str(error),
        }

    parsed = _parse_judge_json(raw)
    parsed["judge_model"] = model
    parsed["raw"] = raw
    return parsed


def _eval_summarize_chapter_prefers_target(
    record: dict,
    chapters_dir: Path,
    chapters: list[dict],
    book_id: str,
) -> EvalResult:
    snippets = retrieve_chapter_snippets(
        chapters_dir,
        "summarize platforms business customers users",
        chapters,
        book_id=book_id,
        current_chapter=3,
        limit=3,
        min_word_count=5,
    )
    top_chapter = int(snippets[0]["chapter_index"]) if snippets else None
    passed = bool(snippets) and top_chapter == 3
    return EvalResult(
        id="summarize_chapter_prefers_target",
        description="Summarize-style query with current chapter bias prefers that chapter",
        passed=passed,
        details=f"top_chapter={top_chapter} indexes={[item['chapter_index'] for item in snippets]}",
        evidence={"top_chapter": top_chapter, "chapter_indexes": [item["chapter_index"] for item in snippets]},
    )


def _eval_character_introduction(
    record: dict,
    chapters_dir: Path,
    chapters: list[dict],
    book_id: str,
) -> EvalResult:
    snippets = retrieve_chapter_snippets(
        chapters_dir,
        "Who is Alice?",
        chapters,
        book_id=book_id,
        limit=3,
        min_word_count=5,
    )
    top_chapter = int(snippets[0]["chapter_index"]) if snippets else None
    has_alice = bool(snippets) and "Alice" in str(snippets[0]["text"])
    passed = top_chapter == 2 and has_alice
    return EvalResult(
        id="character_introduction",
        description="Character introduction query retrieves the introduction chapter",
        passed=passed,
        details=f"top_chapter={top_chapter} has_alice={has_alice}",
        evidence={"top_chapter": top_chapter, "text": snippets[0]["text"] if snippets else ""},
    )


def _eval_spoiler_retrieval_excludes_later(
    record: dict,
    chapters_dir: Path,
    chapters: list[dict],
    book_id: str,
) -> EvalResult:
    snippets = retrieve_chapter_snippets(
        chapters_dir,
        "antitrust interoperability regulation",
        chapters,
        book_id=book_id,
        max_chapter=3,
        limit=10,
        min_word_count=5,
    )
    indexes = [int(item["chapter_index"]) for item in snippets]
    passed = bool(snippets) and all(index <= 3 for index in indexes)
    passed = passed and all("antitrust" not in str(item["text"]).lower() for item in snippets)
    return EvalResult(
        id="spoiler_retrieval_excludes_later",
        description="Retrieval under spoiler guard excludes later chapters",
        passed=passed,
        details=f"chapter_indexes={indexes}",
        evidence={"chapter_indexes": indexes},
    )


def _eval_themes_respect_spoiler(
    record: dict,
    chapters_dir: Path,
    chapters: list[dict],
    book_id: str,
) -> EvalResult:
    snippets = retrieve_chapter_snippets(
        chapters_dir,
        "recurring themes platform decay regulation antitrust",
        chapters,
        book_id=book_id,
        max_chapter=3,
        limit=6,
        min_word_count=5,
    )
    indexes = [int(item["chapter_index"]) for item in snippets]
    passed = bool(snippets) and all(index <= 3 for index in indexes)
    return EvalResult(
        id="themes_respect_spoiler",
        description="Themes-so-far query respects spoiler chapter limit",
        passed=passed,
        details=f"chapter_indexes={indexes}",
        evidence={"chapter_indexes": indexes},
    )


def _eval_chapter_boost_predictable(
    record: dict,
    chapters_dir: Path,
    chapters: list[dict],
    book_id: str,
) -> EvalResult:
    snippets = retrieve_chapter_snippets(
        chapters_dir,
        "platforms business customers users",
        chapters,
        book_id=book_id,
        current_chapter=3,
        limit=3,
        min_word_count=5,
    )
    top_chapter = int(snippets[0]["chapter_index"]) if snippets else None
    passed = top_chapter == 3
    return EvalResult(
        id="chapter_boost_predictable",
        description="Current-chapter retrieval boost ranks the active chapter first",
        passed=passed,
        details=f"top_chapter={top_chapter}",
        evidence={"top_chapter": top_chapter},
    )


def _eval_search_returns_chunk_ids(
    record: dict,
    chapters_dir: Path,
    chapters: list[dict],
    book_id: str,
) -> EvalResult:
    snippets = search_chapters(
        chapters_dir,
        "platform decay",
        chapters,
        book_id=book_id,
        limit=5,
    )
    passed = bool(snippets) and all("chunk_id" in item for item in snippets)
    passed = passed and snippets[0]["chunk_id"].startswith(f"{book_id}:ch")
    return EvalResult(
        id="search_returns_chunk_ids",
        description="Search results include stable chunk ids",
        passed=passed,
        details=f"chunk_ids={[item.get('chunk_id') for item in snippets]}",
        evidence={"chunk_ids": [item.get("chunk_id") for item in snippets]},
    )


def _eval_later_answer_blocked(record: dict, paths) -> EvalResult:
    limits = resolve_spoiler_limits(current_chapter=3, max_chapter=3, auto_spoiler=False)
    response = build_spoiler_blocked_response(
        "antitrust interoperability regulation",
        paths.chapters_dir,
        record["chapters"],
        book_id="eval-book",
        limits=limits,
    )
    passed = (
        response is not None
        and response.get("spoiler_blocked") is True
        and response.get("later_match") is True
        and "yet without spoilers" in response.get("answer", "")
    )
    return EvalResult(
        id="later_answer_blocked",
        description="Question answerable only in later chapters triggers spoiler refusal",
        passed=passed,
        details=response.get("answer", "") if response else "no response",
        evidence=response or {},
    )


def _eval_watermark_warnings(workspace: Path) -> EvalResult:
    record, _paths = build_watermark_eval_book(workspace)
    warnings = record.get("extraction_warnings", [])
    passed = isinstance(warnings, list) and any("watermark" in warning.lower() for warning in warnings)
    return EvalResult(
        id="watermark_warnings",
        description="Watermark-like text triggers extraction warnings",
        passed=passed,
        details=str(warnings),
        evidence={"warnings": warnings},
    )


def _eval_warnings_stored_on_record(workspace: Path) -> EvalResult:
    record, _paths = build_standard_eval_book(workspace)
    warnings = record.get("extraction_warnings")
    passed = isinstance(warnings, list)
    return EvalResult(
        id="warnings_stored_on_record",
        description="Extraction warnings are stored on the book record",
        passed=passed,
        details=str(warnings),
        evidence={"warnings": warnings},
    )


def _eval_content_start_detected(workspace: Path) -> EvalResult:
    record, _paths = build_watermark_eval_book(workspace)
    start = record.get("content_start_chapter")
    passed = start == 3
    return EvalResult(
        id="content_start_detected",
        description="Content start chapter is detected after front matter",
        passed=passed,
        details=f"content_start_chapter={start}",
        evidence={"content_start_chapter": start},
    )


def _eval_session_export_includes_metadata(workspace: Path) -> EvalResult:
    (workspace / "pyproject.toml").touch()
    record, paths = build_standard_eval_book(workspace)
    save_session(
        paths,
        {
            "current_chapter": 3,
            "max_chapter": 3,
            "show_sources": True,
            "history": [
                {"role": "user", "content": "What are platforms?"},
                {"role": "assistant", "content": "Platforms serve users first."},
            ],
        },
    )
    export_path = export_session(paths, record)
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    passed = (
        payload.get("book_id") == "eval-book"
        and payload.get("title")
        and payload.get("exported_at")
        and payload.get("reading_position", {}).get("current_chapter") == 3
        and payload.get("turn_count") == 1
        and len(payload.get("history", [])) == 2
    )
    return EvalResult(
        id="session_export_includes_metadata",
        description="Session export writes book metadata, position, and conversation history",
        passed=passed,
        details=f"keys={sorted(payload.keys())}",
        evidence={"export_path": str(export_path), "turn_count": payload.get("turn_count")},
    )


def _eval_session_reset_clears_history(workspace: Path) -> EvalResult:
    record, paths = build_standard_eval_book(workspace)
    save_session(
        paths,
        {
            "current_chapter": 2,
            "max_chapter": 2,
            "show_sources": True,
            "history": [{"role": "user", "content": "hello"}],
        },
    )
    cleared = reset_session(paths, keep_position=False)
    session = load_session(paths)
    passed = (
        cleared.get("history") == []
        and session.get("history") == []
        and session.get("current_chapter") is None
        and session.get("max_chapter") is None
        and session.get("show_sources") is False
    )
    return EvalResult(
        id="session_reset_clears_history",
        description="Session reset clears conversation and reading position",
        passed=passed,
        details=f"session={session}",
        evidence={"session": session},
    )


def _eval_session_reset_keep_position(workspace: Path) -> EvalResult:
    record, paths = build_standard_eval_book(workspace)
    save_session(
        paths,
        {
            "current_chapter": 4,
            "max_chapter": 4,
            "history": [{"role": "user", "content": "keep me"}],
        },
    )
    reset_session(paths, keep_position=True)
    session = load_session(paths)
    passed = (
        session.get("current_chapter") == 4
        and session.get("max_chapter") == 4
        and session.get("history") == []
    )
    return EvalResult(
        id="session_reset_keep_position",
        description="Session reset can preserve reading position while clearing history",
        passed=passed,
        details=f"session={session}",
        evidence={"session": session},
    )


def _eval_config_describe_includes_workspace(workspace: Path) -> EvalResult:
    (workspace / "pyproject.toml").touch()
    config = describe_config(workspace)
    passed = (
        config.get("workspace_root")
        and config.get("books_dir")
        and config.get("python_version")
        and isinstance(config.get("recommended_models"), list)
    )
    return EvalResult(
        id="config_describe_includes_workspace",
        description="Config diagnostics include workspace paths and runtime info",
        passed=bool(passed),
        details=f"workspace_root={config.get('workspace_root')}",
        evidence={"keys": sorted(config.keys())},
    )


def _eval_trust_status_spoiler_blocked(workspace: Path) -> EvalResult:
    record, paths = build_standard_eval_book(workspace)
    limits = resolve_spoiler_limits(current_chapter=3, max_chapter=3, auto_spoiler=False)
    response = build_spoiler_blocked_response(
        "antitrust interoperability",
        paths.chapters_dir,
        record["chapters"],
        book_id="eval-book",
        limits=limits,
    )
    enriched = enrich_result_trust(response or {})
    passed = answer_trust_status(enriched) == "spoiler_blocked" and enriched.get("trust_label") == "Spoiler blocked"
    return EvalResult(
        id="trust_status_spoiler_blocked",
        description="Spoiler-blocked answers expose spoiler_blocked trust status",
        passed=passed,
        details=f"trust_status={enriched.get('trust_status')}",
        evidence={"trust_status": enriched.get("trust_status"), "trust_label": enriched.get("trust_label")},
    )


def _eval_trust_status_sources_available(workspace: Path) -> EvalResult:
    enriched = enrich_result_trust(
        {
            "sources": [{"chunk_id": "eval-book:ch003:c001"}],
            "citation_check": {"valid_chunk_ids": [], "unknown_chunk_ids": []},
        }
    )
    passed = answer_trust_status(enriched) == "sources_available_no_inline_citations"
    return EvalResult(
        id="trust_status_sources_available",
        description="Answers with backend sources but no inline citations badge as sources available",
        passed=passed,
        details=f"trust_status={enriched.get('trust_status')}",
        evidence={"trust_status": enriched.get("trust_status")},
    )


def _eval_trust_status_citation_warning() -> EvalResult:
    enriched = enrich_result_trust(
        {
            "citation_check": {"valid_chunk_ids": [], "unknown_chunk_ids": ["eval-book:ch099:c001"]},
        }
    )
    passed = answer_trust_status(enriched) == "citation_warning"
    return EvalResult(
        id="trust_status_citation_warning",
        description="Unknown inline citations badge as citation warning",
        passed=passed,
        details=f"trust_status={enriched.get('trust_status')}",
        evidence={"trust_status": enriched.get("trust_status")},
    )


def _eval_config_masks_api_keys() -> EvalResult:
    masked = mask_secret("sk-abcdefghijklmnop")
    passed = masked is not None and "..." in masked and "sk-a" in masked and "mnop" in masked
    passed = passed and mask_secret(None) is None
    return EvalResult(
        id="config_masks_api_keys",
        description="Config diagnostics mask API key secrets",
        passed=passed,
        details=f"masked={masked}",
        evidence={"masked": masked},
    )


def _eval_duplicate_identifier_guard(workspace: Path) -> EvalResult:
    (workspace / "pyproject.toml").touch()
    first_epub = workspace / "dup-a.epub"
    second_epub = workspace / "dup-b.epub"
    shared_identifier = "shared-eval-identifier"
    first_epub.write_bytes(make_minimal_epub(title="Dup A", identifier=shared_identifier))
    second_epub.write_bytes(make_minimal_epub(title="Dup B", identifier=shared_identifier))

    ingest_source(first_epub, book_id="dup-a", workspace=workspace)
    conflict_raised = False
    message = ""
    try:
        ingest_source(second_epub, book_id="dup-b", workspace=workspace)
    except ValueError as error:
        conflict_raised = True
        message = str(error)

    passed = conflict_raised and "dup-a" in message
    return EvalResult(
        id="duplicate_identifier_guard",
        description="Ingest refuses a second book with the same identifier",
        passed=passed,
        details=message or "no conflict raised",
        evidence={"conflict_raised": conflict_raised, "message": message},
    )


def _eval_auto_link_spoiler(record: dict, paths) -> EvalResult:
    limits = resolve_spoiler_limits(current_chapter=2, max_chapter=None, auto_spoiler=True)
    passed = limits.max_chapter == 2 and limits.auto_linked is True
    return EvalResult(
        id="auto_link_spoiler",
        description="Setting current chapter without explicit spoiler auto-links max chapter",
        passed=passed,
        details=f"limits={limits}",
        evidence={"limits": asdict(limits)},
    )


def _eval_refusal_with_later_match(record: dict, paths) -> EvalResult:
    limits = resolve_spoiler_limits(current_chapter=2, max_chapter=2, auto_spoiler=False)
    response = build_spoiler_blocked_response(
        "antitrust interoperability regulation",
        paths.chapters_dir,
        record["chapters"],
        book_id="eval-book",
        limits=limits,
    )
    passed = (
        response is not None
        and response.get("spoiler_blocked") is True
        and response.get("later_match") is True
        and "yet without spoilers" in response.get("answer", "")
        and not response.get("sources")
        and not response.get("chunks")
    )
    return EvalResult(
        id="refusal_with_later_match",
        description="Blocked spoiler question mentions later material may exist",
        passed=passed,
        details=response.get("answer", "") if response else "no response",
        evidence=response or {},
    )


def _eval_refusal_without_later_match(record: dict, paths) -> EvalResult:
    limits = resolve_spoiler_limits(current_chapter=2, max_chapter=2, auto_spoiler=False)
    response = build_spoiler_blocked_response(
        "xyzzy nonexistent gibberish term",
        paths.chapters_dir,
        record["chapters"],
        book_id="eval-book",
        limits=limits,
    )
    passed = (
        response is not None
        and response.get("spoiler_blocked") is True
        and response.get("later_match") is False
        and "yet without spoilers" not in response.get("answer", "")
        and not response.get("sources")
        and not response.get("chunks")
    )
    return EvalResult(
        id="refusal_without_later_match",
        description="Blocked unknown question does not claim later spoilers",
        passed=passed,
        details=response.get("answer", "") if response else "no response",
        evidence=response or {},
    )


def _eval_front_matter_classification(record: dict) -> EvalResult:
    chapters = enrich_book_chapters(record["chapters"])
    cover = next(ch for ch in chapters if ch["title"] == "Cover")
    intro = next(ch for ch in chapters if ch["title"] == "Introduction")
    start = content_start_chapter(chapters)
    passed = cover["kind"] == "front_matter" and intro["kind"] == "body" and start == 2
    return EvalResult(
        id="front_matter_classification",
        description="Front matter is classified and content start chapter is detected",
        passed=passed,
        details=f"cover={cover['kind']} intro={intro['kind']} start={start}",
        evidence={"content_start_chapter": start, "kinds": [(c["index"], c["kind"]) for c in chapters]},
    )


def _eval_spoiler_excludes_later_retrieval(record: dict, paths) -> EvalResult:
    snippets = retrieve_chapter_snippets(
        paths.chapters_dir,
        "antitrust interoperability",
        record["chapters"],
        book_id="eval-book",
        max_chapter=2,
        limit=10,
        min_word_count=0,
    )
    passed = bool(snippets) and all(int(item["chapter_index"]) <= 2 for item in snippets)
    return EvalResult(
        id="spoiler_excludes_later_retrieval",
        description="Retrieval under spoiler guard never returns later chapters",
        passed=passed,
        details=f"chapter_indexes={[item['chapter_index'] for item in snippets]}",
        evidence={"chapter_indexes": [item["chapter_index"] for item in snippets]},
    )


def _eval_workspace(workspace: Path | None) -> Path:
    if workspace is not None:
        return workspace
    import tempfile

    return Path(tempfile.mkdtemp(prefix="book-search-eval-"))


def _parse_judge_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    return {
        "overall_pass": None,
        "score": None,
        "findings": [{"severity": "medium", "issue": "Judge returned non-JSON", "recommendation": raw[:500]}],
        "summary": "Could not parse judge JSON",
        "parse_error": True,
    }