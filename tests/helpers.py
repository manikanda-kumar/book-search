from __future__ import annotations

import io
import zipfile


def make_minimal_epub(
    title: str = "Sample Book",
    author: str = "Jane Author",
    chapters: list[tuple[str, str]] | None = None,
) -> bytes:
    """Build a minimal valid EPUB archive in memory."""
    if chapters is None:
        chapters = [
            ("Introduction", "<h1>Introduction</h1><p>Welcome to the book.</p>"),
            ("Chapter One", "<h1>Chapter One</h1><p>The main idea appears here.</p>"),
        ]

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

        manifest_items = []
        spine_items = []
        for index, (chapter_title, body_html) in enumerate(chapters, start=1):
            item_id = f"ch{index}"
            href = f"chapter{index}.xhtml"
            manifest_items.append(
                f'<item id="{item_id}" href="{href}" media-type="application/xhtml+xml"/>'
            )
            spine_items.append(f'<itemref idref="{item_id}"/>')
            archive.writestr(
                f"OEBPS/{href}",
                f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>{chapter_title}</title></head>
  <body>{body_html}</body>
</html>""",
            )

        archive.writestr(
            "OEBPS/content.opf",
            f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{title}</dc:title>
    <dc:creator>{author}</dc:creator>
    <dc:language>en</dc:language>
    <dc:identifier id="uid">sample-book-uid</dc:identifier>
  </metadata>
  <manifest>
    {''.join(manifest_items)}
  </manifest>
  <spine>
    {''.join(spine_items)}
  </spine>
</package>""",
        )

    return buffer.getvalue()