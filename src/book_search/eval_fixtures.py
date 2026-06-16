from __future__ import annotations

from pathlib import Path

from .extractors.epub import extract_epub
from .paths import BookPaths, book_paths
from .testdata import make_minimal_epub


STANDARD_EVAL_CHAPTERS = [
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
]


def build_standard_eval_book(workspace: Path) -> tuple[dict, BookPaths]:
    (workspace / "pyproject.toml").touch()
    epub_path = workspace / "eval-book.epub"
    epub_path.write_bytes(
        make_minimal_epub(
            title="Eval Book",
            author="Eval Author",
            chapters=STANDARD_EVAL_CHAPTERS,
        )
    )
    paths = book_paths("eval-book", workspace)
    record = extract_epub(epub_path, paths)
    return record, paths


def build_watermark_eval_book(workspace: Path) -> tuple[dict, BookPaths]:
    (workspace / "pyproject.toml").touch()
    chapters = [
        ("Cover", "<h1>Cover</h1><p>OceanofPDF.com</p>"),
        ("Title", "<h1>Title</h1><p>OceanofPDF.com</p>"),
        ("Introduction", "<h1>Introduction</h1><p>Real content begins here about platforms.</p>"),
    ]
    epub_path = workspace / "watermark-book.epub"
    epub_path.write_bytes(make_minimal_epub(title="Watermark Book", chapters=chapters))
    paths = book_paths("watermark-book", workspace)
    record = extract_epub(epub_path, paths)
    return record, paths