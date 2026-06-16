from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from .chapters import content_start_chapter, enrich_book_chapters
from .companion import answer_question
from .llm import LlmConfigError, complete_chat
from .paths import book_paths
from .pipeline import load_book_record
from .retrieval import retrieve_chapter_snippets
from .spoiler import build_spoiler_blocked_response, resolve_spoiler_limits, spoiler_refusal_message


DEFAULT_JUDGE_MODEL = "minimax/minimax-m2.5"


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
    from .extractors.epub import extract_epub
    from .testdata import make_minimal_epub

    tmp_root = _eval_workspace(workspace)
    (tmp_root / "pyproject.toml").touch()
    epub_path = tmp_root / "eval-book.epub"
    epub_path.write_bytes(
        make_minimal_epub(
            title="Eval Book",
            chapters=[
                ("Cover", "<h1>Cover</h1><p>OceanofPDF.com</p>"),
                ("Introduction", "<h1>Introduction</h1><p>Alice founded the platform in 2010.</p>"),
                (
                    "Platforms",
                    "<h1>Platforms</h1><p>Platforms first serve users, then business customers, then only themselves.</p>",
                ),
                (
                    "Regulation",
                    "<h1>Regulation</h1><p>Antitrust and interoperability can reverse platform decay.</p>",
                ),
            ],
        )
    )
    paths = book_paths("eval-book", tmp_root)
    record = extract_epub(epub_path, paths)

    results: list[EvalResult] = []
    results.append(_eval_auto_link_spoiler(record, paths))
    results.append(_eval_refusal_with_later_match(record, paths))
    results.append(_eval_refusal_without_later_match(record, paths))
    results.append(_eval_front_matter_classification(record))
    results.append(_eval_spoiler_excludes_later_retrieval(record, paths))
    return results


def judge_eval_results(
    results: list[EvalResult],
    *,
    suite: str,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    implementation_notes: str = "",
) -> dict:
    payload = {
        "suite": suite,
        "results": [asdict(result) for result in results],
        "implementation_notes": implementation_notes,
    }
    system = """You are a strict QA judge for a book-reading companion product.
Review deterministic eval results for spoiler-guard semantics.
Return JSON only with keys:
- overall_pass: boolean
- score: number from 0 to 100
- findings: array of {severity: "high"|"medium"|"low", issue: string, recommendation: string}
- summary: string
Be concrete. Fail the review if spoiler refusal behavior is weak or ambiguous."""
    user = (
        "Review this eval report for Oracle recommendation #2 (spoiler guard semantics).\n\n"
        f"{json.dumps(payload, indent=2, ensure_ascii=False)}"
    )
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