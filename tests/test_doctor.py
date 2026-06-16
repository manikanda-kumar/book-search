from __future__ import annotations

from pathlib import Path

from book_search.doctor import doctor_has_failures, run_doctor
from book_search.pipeline import ingest_source
from helpers import make_minimal_epub


class TestDoctor:
    def test_doctor_reports_workspace(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        checks = run_doctor(tmp_path)
        ids = [check.id for check in checks]
        assert "workspace" in ids
        assert "python" in ids
        assert not doctor_has_failures(checks)

    def test_doctor_warns_without_books(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        checks = run_doctor(tmp_path)
        ingested = next(check for check in checks if check.id == "ingested_books")
        assert ingested.status == "warn"

    def test_doctor_sees_ingested_book(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        epub_path = tmp_path / "book.epub"
        epub_path.write_bytes(make_minimal_epub(title="Doctor Book"))
        ingest_source(epub_path, book_id="doctor-book", workspace=tmp_path)

        checks = run_doctor(tmp_path)
        ingested = next(check for check in checks if check.id == "ingested_books")
        assert ingested.status == "ok"

    def test_doctor_includes_config_checks(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        checks = run_doctor(tmp_path)
        ids = [check.id for check in checks]
        assert "workspace_config" in ids
        assert "chat_model_override" in ids