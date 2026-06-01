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
