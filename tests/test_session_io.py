from __future__ import annotations

import json
from pathlib import Path

from book_search.companion import load_session, save_session
from book_search.eval_fixtures import build_standard_eval_book
from book_search.session_io import export_session, reset_session, session_summary


class TestSessionIo:
    def test_session_summary_counts_turns(self, tmp_path: Path) -> None:
        record, paths = build_standard_eval_book(tmp_path)
        save_session(
            paths,
            {
                "current_chapter": 2,
                "max_chapter": 2,
                "history": [
                    {"role": "user", "content": "one"},
                    {"role": "assistant", "content": "two"},
                    {"role": "user", "content": "three"},
                ],
            },
        )

        summary = session_summary(paths, record)
        assert summary["turn_count"] == 2
        assert summary["current_chapter"] == 2

    def test_export_session_writes_json(self, tmp_path: Path) -> None:
        record, paths = build_standard_eval_book(tmp_path)
        save_session(
            paths,
            {
                "current_chapter": 3,
                "history": [{"role": "user", "content": "hello"}],
            },
        )

        export_path = export_session(paths, record)
        payload = json.loads(export_path.read_text(encoding="utf-8"))
        assert payload["book_id"] == "eval-book"
        assert payload["reading_position"]["current_chapter"] == 3
        assert payload["history"]

    def test_reset_session_clears_or_keeps_position(self, tmp_path: Path) -> None:
        record, paths = build_standard_eval_book(tmp_path)
        save_session(
            paths,
            {
                "current_chapter": 5,
                "max_chapter": 5,
                "show_sources": True,
                "history": [{"role": "user", "content": "x"}],
            },
        )

        reset_session(paths, keep_position=True)
        kept = load_session(paths)
        assert kept["current_chapter"] == 5
        assert kept["history"] == []
        assert kept["show_sources"] is False

        save_session(paths, {"current_chapter": 1, "max_chapter": 1, "history": [{"role": "user", "content": "y"}]})
        reset_session(paths, keep_position=False)
        cleared = load_session(paths)
        assert cleared["current_chapter"] is None
        assert cleared["max_chapter"] is None
        assert cleared["history"] == []