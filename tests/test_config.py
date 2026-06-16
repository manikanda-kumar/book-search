from __future__ import annotations

from pathlib import Path

from book_search.config import describe_config, mask_secret


class TestConfig:
    def test_mask_secret(self) -> None:
        assert mask_secret(None) is None
        assert mask_secret("short") == "***"
        masked = mask_secret("sk-abcdefghijklmnop")
        assert masked is not None
        assert "..." in masked
        assert "sk-a" in masked

    def test_describe_config_includes_workspace(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        config = describe_config(tmp_path)
        assert str(tmp_path) in config["workspace_root"]
        assert config["books_dir"].endswith("data/books")
        assert config["python_version"]
        assert config["recommended_models"]