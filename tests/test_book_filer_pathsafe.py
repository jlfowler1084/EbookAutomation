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
