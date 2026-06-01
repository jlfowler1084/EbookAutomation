import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer.pathsafe import sanitize_component


def test_sanitize_replaces_middot_and_collapses_spaces():
    assert sanitize_component("World Wars (WWI · WWII · Weimar)") == "World Wars (WWI WWII Weimar)"


def test_sanitize_colon_becomes_dash():
    assert sanitize_component("Title: Subtitle") == "Title - Subtitle"


def test_sanitize_slash_becomes_dash():
    assert sanitize_component("Marx/Engels") == "Marx - Engels"


def test_sanitize_strips_other_illegal_chars():
    assert sanitize_component('a<b>c"d|e?f*g') == "abcdefg"


def test_sanitize_trims_trailing_dots_and_spaces():
    assert sanitize_component("name...  ") == "name"


def test_sanitize_guards_reserved_names():
    assert sanitize_component("CON") == "_CON"
    assert sanitize_component("com1") == "_com1"


def test_sanitize_empty_becomes_placeholder():
    assert sanitize_component("///") == "-"  # slashes -> ' - ', collapse, trim -> '-'
    assert sanitize_component("") == "_"


from book_filer.pathsafe import build_base_name


def test_build_base_name_simple():
    assert build_base_name("Cooper, Andrew Scott", "The Oil Kings", 2011) == \
        "Cooper, Andrew Scott - The Oil Kings (2011)"


def test_build_base_name_no_year():
    assert build_base_name("Spencer, Herbert", "The Man Versus the State", None) == \
        "Spencer, Herbert - The Man Versus the State"


def test_build_base_name_with_series():
    assert build_base_name(
        "Spengler, Oswald", "Form and Actuality", 1918,
        series="Decline of the West", series_index="01",
    ) == "Spengler, Oswald - [Decline of the West 01] Form and Actuality (1918)"


def test_build_base_name_with_disambiguator():
    assert build_base_name(
        "Coogan, Michael", "The New Oxford Annotated Bible", 2010, disambiguator="NRSV",
    ) == "Coogan, Michael - The New Oxford Annotated Bible (2010) [NRSV]"


from book_filer.pathsafe import compute_shelf_path


def test_compute_shelf_path_layout():
    p = compute_shelf_path(
        library_root=Path("F:\\Books"),
        section="01 History",
        subcategory="World Wars (WWI, WWII, Weimar)",
        author_sort="Cooper, Andrew Scott",
        title="The Oil Kings",
        ext=".pdf",
        year=2011,
        max_path_length=240,
    )
    assert p == Path(
        "F:\\Books\\01 History\\World Wars (WWI, WWII, Weimar)\\"
        "Cooper, Andrew Scott\\Cooper, Andrew Scott - The Oil Kings (2011).pdf"
    )


def test_compute_shelf_path_truncates_title_only_when_too_long():
    long_title = "A " * 200  # 400 chars
    p = compute_shelf_path(
        library_root=Path("F:\\Books"),
        section="02 Philosophy",
        subcategory="Ethics & Political Philosophy",
        author_sort="Author, Test",
        title=long_title,
        ext=".epub",
        year=1999,
        max_path_length=160,
    )
    assert len(str(p)) <= 160
    assert "…" in p.name
    assert p.name.endswith("(1999).epub")
    assert p.parent == Path(
        "F:\\Books\\02 Philosophy\\Ethics & Political Philosophy\\Author, Test"
    )


from book_filer.pathsafe import unique_path


def test_unique_path_returns_input_when_free(tmp_path):
    target = tmp_path / "Book.epub"
    assert unique_path(target) == target


def test_unique_path_suffixes_on_collision(tmp_path):
    (tmp_path / "Book.epub").write_text("x", encoding="utf-8")
    assert unique_path(tmp_path / "Book.epub") == tmp_path / "Book (2).epub"


def test_unique_path_increments_until_free(tmp_path):
    (tmp_path / "Book.epub").write_text("x", encoding="utf-8")
    (tmp_path / "Book (2).epub").write_text("x", encoding="utf-8")
    assert unique_path(tmp_path / "Book.epub") == tmp_path / "Book (3).epub"


def test_build_base_name_sanitizes_series_index():
    # An illegal char in the series index must not slip into the "safe" stem.
    assert build_base_name(
        "Author, Test", "Title", 2000, series="Series", series_index="2/3",
    ) == "Author, Test - [Series 2 - 3] Title (2000)"
