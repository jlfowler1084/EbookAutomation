import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer.metadata import BookMetadata, extract_metadata


def _make_epub(path: Path, title: str, author: str, date: str, isbn: str | None = None) -> None:
    ident = f'<dc:identifier id="bookid">urn:isbn:{isbn}</dc:identifier>' if isbn else ""
    opf = (
        '<?xml version="1.0"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f"<dc:title>{title}</dc:title><dc:creator>{author}</dc:creator>"
        f"<dc:date>{date}</dc:date>{ident}"
        "</metadata><manifest/><spine/></package>"
    )
    container = (
        '<?xml version="1.0"?>'
        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">'
        '<rootfiles><rootfile full-path="content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("content.opf", opf)


def _make_pdf(path: Path, title: str, author: str) -> None:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.add_metadata({"/Title": title, "/Author": author, "/CreationDate": "D:20110101000000"})
    with open(path, "wb") as fh:
        writer.write(fh)


def test_extract_epub_metadata(tmp_path):
    epub = tmp_path / "book.epub"
    _make_epub(epub, "The Oil Kings", "Andrew Scott Cooper", "2011-09-08", isbn="9781416597865")
    meta = extract_metadata(epub)
    assert meta == BookMetadata(
        title="The Oil Kings", author="Andrew Scott Cooper", year=2011, isbn="9781416597865",
    )


def test_extract_pdf_metadata(tmp_path):
    pdf = tmp_path / "book.pdf"
    _make_pdf(pdf, "Designing Data-Intensive Applications", "Martin Kleppmann")
    meta = extract_metadata(pdf)
    assert meta.title == "Designing Data-Intensive Applications"
    assert meta.author == "Martin Kleppmann"
    assert meta.year == 2011
    assert meta.isbn is None


def test_unknown_extension_returns_empty(tmp_path):
    other = tmp_path / "book.txt"
    other.write_text("x", encoding="utf-8")
    assert extract_metadata(other) == BookMetadata(None, None, None, None)


def test_corrupt_epub_degrades_gracefully(tmp_path):
    bad = tmp_path / "bad.epub"
    bad.write_text("not a zip", encoding="utf-8")
    assert extract_metadata(bad) == BookMetadata(None, None, None, None)
