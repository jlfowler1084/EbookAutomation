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


def _make_pdf(
    path: Path,
    title: str,
    author: str,
    creator: str | None = None,
    producer: str | None = None,
    creation_date: str = "D:20110101000000",
) -> None:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    meta = {"/Title": title, "/Author": author, "/CreationDate": creation_date}
    if creator is not None:
        meta["/Creator"] = creator
    if producer is not None:
        meta["/Producer"] = producer
    writer.add_metadata(meta)
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


# --- EB-355 junk-metadata guard (mirrors pattern_db SCRUM-322 / SCRUM-323 / EB-351) ---

def test_pdf_literal_none_author_is_scrubbed(tmp_path):
    """SCRUM-322: Pdf995-class tools write the literal text 'None' into the author
    field. It must be scrubbed to None, not flow through to a planned key/filename."""
    pdf = tmp_path / "book.pdf"
    _make_pdf(pdf, "A Real Title", "None")
    meta = extract_metadata(pdf)
    assert meta.title == "A Real Title"
    assert meta.author is None


def test_pdf_literal_na_author_is_scrubbed(tmp_path):
    pdf = tmp_path / "book.pdf"
    _make_pdf(pdf, "A Real Title", "N/A")
    assert extract_metadata(pdf).author is None


def test_pdf995_creator_drops_whole_embedded_record(tmp_path):
    """SCRUM-323/EB-351: when the PDF's creator/producer is a known junk tool, the
    entire embedded record (title/author/year) is dropped so the filer falls back to
    the filename parser. Pdf995 injects the filename as title and the generation date
    as year."""
    pdf = tmp_path / "(Great Books) Ludwig Feuerbach - Essence.pdf"
    _make_pdf(pdf, "(Great Books) Ludwig Feuerbach - Essence", "None", creator="Pdf995")
    assert extract_metadata(pdf) == BookMetadata(None, None, None, None)


def test_acrobat_pdfwriter_producer_drops_record(tmp_path):
    """EB-351: Acrobat PDFWriter (distinct from the legitimate Acrobat Distiller)
    injects filenames as titles — drop its embedded record."""
    pdf = tmp_path / "book.pdf"
    _make_pdf(pdf, "joel", "joel", producer="Acrobat PDFWriter 5.0")
    assert extract_metadata(pdf) == BookMetadata(None, None, None, None)


def test_calibre_producer_metadata_is_preserved(tmp_path):
    """Calibre re-saves PDFs but preserves real metadata — must NOT trip the guard.
    Oil Kings is the canonical regression anchor."""
    pdf = tmp_path / "book.pdf"
    _make_pdf(
        pdf, "The Oil Kings", "Andrew Scott Cooper",
        creator="calibre 1.22.0", producer="calibre 1.22.0 [http://calibre-ebook.com]",
    )
    meta = extract_metadata(pdf)
    assert meta.title == "The Oil Kings"
    assert meta.author == "Andrew Scott Cooper"
    assert meta.year == 2011


def test_acrobat_distiller_is_not_dropped(tmp_path):
    """'Acrobat Distiller' is a legitimate prepress tool — a naive substring match on
    'acrobat' would wrongly drop it. Must be preserved."""
    pdf = tmp_path / "book.pdf"
    _make_pdf(pdf, "Real Title", "Real Author", producer="Acrobat Distiller 5.0.5 for Macintosh")
    meta = extract_metadata(pdf)
    assert meta.title == "Real Title"
    assert meta.author == "Real Author"


def test_epub_literal_none_creator_is_scrubbed(tmp_path):
    """SCRUM-322 applies to EPUB DC fields too: literal 'None' creator -> author None."""
    epub = tmp_path / "book.epub"
    _make_epub(epub, "A Real Title", "None", "2011-01-01")
    meta = extract_metadata(epub)
    assert meta.title == "A Real Title"
    assert meta.author is None


def test_epub_implausible_year_is_scrubbed(tmp_path):
    for raw_year in ("0101-01-01", "0000-01-01", "9999-01-01"):
        epub = tmp_path / f"book-{raw_year[:4]}.epub"
        _make_epub(epub, "A Real Title", "Andrew Scott Cooper", raw_year)
        meta = extract_metadata(epub)
        assert meta.title == "A Real Title"
        assert meta.author == "Andrew Scott Cooper"
        assert meta.year is None


def test_pdf_implausible_creation_year_is_scrubbed(tmp_path):
    pdf = tmp_path / "book.pdf"
    _make_pdf(
        pdf,
        "A Real Title",
        "Andrew Scott Cooper",
        creation_date="D:01010101000000",
    )
    meta = extract_metadata(pdf)
    assert meta.title == "A Real Title"
    assert meta.author == "Andrew Scott Cooper"
    assert meta.year is None


def test_fake_uploader_author_is_scrubbed(tmp_path):
    epub = tmp_path / "book.epub"
    _make_epub(epub, "A Real Title", "svejk, josef", "2011-01-01")
    meta = extract_metadata(epub)
    assert meta.title == "A Real Title"
    assert meta.author is None
    assert meta.year == 2011


def test_lowercase_real_author_is_preserved(tmp_path):
    epub = tmp_path / "book.epub"
    _make_epub(epub, "A Real Title", "bell hooks", "2011-01-01")
    meta = extract_metadata(epub)
    assert meta.author == "bell hooks"
