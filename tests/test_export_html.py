from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from book_search.export_html import (
    export_chapter_html,
    parse_spine_range,
    parse_toc_chapter_starts,
    validate_export_selector,
)
from book_search.pipeline import ingest_source
from helpers import make_minimal_epub


def make_epub_with_image_and_toc() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>""",
        )
        archive.writestr("OEBPS/images/figure.png", b"fake-png-bytes")
        archive.writestr(
            "OEBPS/toc.xhtml",
            """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <body>
    <p><a href="chapter1.xhtml">Chapter 1: Alpha</a></p>
    <p><a href="chapter2.xhtml">Chapter 2: Beta</a></p>
  </body>
</html>""",
        )
        archive.writestr(
            "OEBPS/chapter1.xhtml",
            """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <body><h1>Alpha</h1><p>First chapter text.</p></body>
</html>""",
        )
        archive.writestr(
            "OEBPS/chapter2.xhtml",
            """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <body>
    <h1>Beta</h1>
    <p><img src="images/figure.png" alt="diagram"/></p>
    <p>Second chapter text.</p>
    <p><a href="javascript:alert(1)">unsafe</a></p>
  </body>
</html>""",
        )
        archive.writestr(
            "OEBPS/content.opf",
            """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Image Book</dc:title>
    <dc:creator>Test Author</dc:creator>
    <dc:language>en</dc:language>
    <dc:identifier id="uid">image-book</dc:identifier>
  </metadata>
  <manifest>
    <item id="toc" href="toc.xhtml" media-type="application/xhtml+xml"/>
    <item id="ch1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
    <item id="ch2" href="chapter2.xhtml" media-type="application/xhtml+xml"/>
    <item id="img" href="images/figure.png" media-type="image/png"/>
  </manifest>
  <spine>
    <itemref idref="toc"/>
    <itemref idref="ch1"/>
    <itemref idref="ch2"/>
  </spine>
</package>""",
        )
    return buffer.getvalue()


class TestExportHtml:
    def test_parse_toc_chapter_starts(self) -> None:
        with zipfile.ZipFile(io.BytesIO(make_epub_with_image_and_toc())) as archive:
            starts = parse_toc_chapter_starts(archive)
        assert starts == {1: "chapter1.xhtml", 2: "chapter2.xhtml"}

    def test_exports_chapter_with_image(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        epub_path = tmp_path / "image-book.epub"
        epub_path.write_bytes(make_epub_with_image_and_toc())
        _book_id, record, paths = ingest_source(epub_path, book_id="image-book", workspace=tmp_path)

        destination, image_count, recovered_images, missing_images = export_chapter_html(record, paths, chapter_number=2)

        html = destination.read_text(encoding="utf-8")
        assert image_count == 1
        assert recovered_images == []
        assert missing_images == []
        assert "<img" in html
        assert f'src="{destination.stem}-images/figure.png"' in html
        assert "Second chapter text." in html
        assert (destination.parent / f"{destination.stem}-images" / "figure.png").exists()

    def test_escapes_unsafe_html(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        epub_path = tmp_path / "image-book.epub"
        epub_path.write_bytes(make_epub_with_image_and_toc())
        _book_id, record, paths = ingest_source(epub_path, book_id="image-book", workspace=tmp_path)

        destination, _image_count, _recovered, _missing = export_chapter_html(record, paths, chapter_number=2)
        html = destination.read_text(encoding="utf-8")
        assert 'href="javascript:alert(1)"' not in html
        assert 'href="#"' in html

    def test_exports_by_spine_range(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        epub_path = tmp_path / "sample.epub"
        epub_path.write_bytes(make_minimal_epub())
        _book_id, record, paths = ingest_source(epub_path, book_id="sample", workspace=tmp_path)

        destination, _image_count, _recovered, _missing = export_chapter_html(record, paths, spine_from=2, spine_to=2)
        html = destination.read_text(encoding="utf-8")
        assert "Chapter One" in html
        assert "main idea" in html

    def test_requires_selector(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        epub_path = tmp_path / "sample.epub"
        epub_path.write_bytes(make_minimal_epub())
        _book_id, record, paths = ingest_source(epub_path, book_id="sample", workspace=tmp_path)

        with pytest.raises(ValueError, match="exactly one"):
            export_chapter_html(record, paths)

    def test_validate_export_selector(self) -> None:
        validate_export_selector(chapter_number=1, title=None, spine=None)
        with pytest.raises(ValueError, match="exactly one"):
            validate_export_selector(chapter_number=1, title="Alpha", spine=None)
        with pytest.raises(ValueError, match="exactly one"):
            validate_export_selector(chapter_number=None, title=None, spine=None)

    def test_parse_spine_range(self) -> None:
        assert parse_spine_range("43-48") == (43, 48)
        assert parse_spine_range("5") == (5, 5)
        with pytest.raises(ValueError, match="Invalid --spine"):
            parse_spine_range("abc")

    def test_watermark_does_not_strip_chapter_body(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            archive.writestr(
                "META-INF/container.xml",
                """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>""",
            )
            archive.writestr(
                "OEBPS/toc.xhtml",
                """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><body>
<p><a href="chapter1.xhtml">Chapter 1: Alpha</a></p>
</body></html>""",
            )
            archive.writestr(
                "OEBPS/chapter1.xhtml",
                """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <body>
    <h2>Section</h2>
    <div class="calibre3"> </div>
    <p>Important chapter body that must survive watermark removal.</p>
    <div style="float: none; margin: 10px 0px 10px 0px; text-align: center;">
      <p><a href="https://oceanofpdf.com"><i>OceanofPDF.com</i></a></p>
    </div>
  </body>
</html>""",
            )
            archive.writestr(
                "OEBPS/content.opf",
                """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Watermark Book</dc:title>
    <dc:creator>Test Author</dc:creator>
    <dc:language>en</dc:language>
    <dc:identifier id="uid">watermark-book</dc:identifier>
  </metadata>
  <manifest>
    <item id="toc" href="toc.xhtml" media-type="application/xhtml+xml"/>
    <item id="ch1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="toc"/>
    <itemref idref="ch1"/>
  </spine>
</package>""",
            )
        epub_path = tmp_path / "watermark-book.epub"
        epub_path.write_bytes(buffer.getvalue())
        _book_id, record, paths = ingest_source(epub_path, book_id="watermark-book", workspace=tmp_path)

        destination, _image_count, _recovered, _missing = export_chapter_html(record, paths, chapter_number=1)
        html = destination.read_text(encoding="utf-8")
        assert "Important chapter body that must survive watermark removal." in html
        assert "oceanofpdf.com" not in html.casefold()

    def test_recovers_missing_image_from_fallback(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (tmp_path / "pyproject.toml").touch()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            archive.writestr(
                "META-INF/container.xml",
                """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>""",
            )
            archive.writestr(
                "OEBPS/toc.xhtml",
                """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><body>
<p><a href="chapter1.xhtml">Chapter 1: Alpha</a></p>
</body></html>""",
            )
            archive.writestr(
                "OEBPS/chapter1.xhtml",
                """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <body><p><img src="images/00016.jpg"/></p></body>
</html>""",
            )
            archive.writestr(
                "OEBPS/content.opf",
                """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Fallback Book</dc:title>
    <dc:creator>Test Author</dc:creator>
    <dc:language>en</dc:language>
    <dc:identifier id="uid">fallback-book</dc:identifier>
  </metadata>
  <manifest>
    <item id="toc" href="toc.xhtml" media-type="application/xhtml+xml"/>
    <item id="ch1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="toc"/>
    <itemref idref="ch1"/>
  </spine>
</package>""",
            )
        epub_path = tmp_path / "fallback-book.epub"
        epub_path.write_bytes(buffer.getvalue())
        _book_id, record, paths = ingest_source(epub_path, book_id="fallback-book", workspace=tmp_path)

        from book_search import export_html as export_html_module

        monkeypatch.setattr(
            export_html_module,
            "_fetch_image_bytes",
            lambda _url: b"fallback-jpeg-bytes",
        )

        destination, image_count, recovered_images, missing_images = export_chapter_html(record, paths, chapter_number=1)
        html = destination.read_text(encoding="utf-8")
        assert image_count == 1
        assert recovered_images == ["00016.jpg"]
        assert missing_images == []
        assert "Recovered 1 image(s) from public-domain fallback: 00016.jpg" in html
        assert (destination.parent / f"{destination.stem}-images" / "00016.jpg").read_bytes() == b"fallback-jpeg-bytes"