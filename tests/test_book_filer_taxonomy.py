import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer.taxonomy import Taxonomy, load_taxonomy


def test_load_taxonomy_real_file():
    tax = load_taxonomy()
    assert isinstance(tax, Taxonomy)
    assert len(tax.sections) == 12
    assert "01 History" in tax.sections
    assert 0.0 < tax.confidence_threshold < 1.0
    assert "passport" in tax.non_library_keywords


def test_keyword_index_maps_to_section_subcategory():
    tax = load_taxonomy()
    hits = tax.lookup("weimar")
    assert ("01 History", "World Wars (WWI, WWII, Weimar)") in hits


def test_lookup_is_case_insensitive_and_empty_for_unknown():
    tax = load_taxonomy()
    assert tax.lookup("WEIMAR") == tax.lookup("weimar")
    assert tax.lookup("zzz-nonsense") == set()


def test_load_taxonomy_rejects_duplicate_section_codes(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(
        '{"version":1,"confidence_threshold":0.3,"non_library_keywords":[],'
        '"sections":[{"code":"X","subcategories":[]},{"code":"X","subcategories":[]}]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate section"):
        load_taxonomy(bad)
