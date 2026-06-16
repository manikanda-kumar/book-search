from __future__ import annotations

from book_search.eval import run_ingestion_eval, run_retrieval_eval, run_spoiler_eval, run_workflow_eval


class TestEvalSuites:
    def test_spoiler_eval_passes(self, tmp_path) -> None:
        results = run_spoiler_eval(tmp_path)
        assert len(results) == 5
        assert all(result.passed for result in results)

    def test_retrieval_eval_passes(self, tmp_path) -> None:
        results = run_retrieval_eval(tmp_path)
        assert len(results) == 7
        assert all(result.passed for result in results)

    def test_ingestion_eval_passes(self, tmp_path) -> None:
        results = run_ingestion_eval(tmp_path)
        assert len(results) == 4
        assert all(result.passed for result in results)

    def test_workflow_eval_passes(self, tmp_path) -> None:
        results = run_workflow_eval(tmp_path)
        assert len(results) == 8
        assert all(result.passed for result in results)