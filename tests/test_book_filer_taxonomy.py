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


# ---------------------------------------------------------------------------
# EB-365 Unit 1 — format-tier / boilerplate overlay + version bump.
# Form words describe a book's *form*, not its subject; the overlay tags them
# so the Unit 2 demotion guard can route "form-word of <no-subject>" to review.
# ---------------------------------------------------------------------------

def test_v2_taxonomy_loads_format_and_boilerplate_overlays():
    tax = load_taxonomy()
    assert tax.format_keywords == frozenset(
        {"encyclopedia", "dictionary", "handbook", "atlas"}
    )
    assert tax.boilerplate_keywords == frozenset({"publishing"})


def test_taxonomy_version_reads_as_two():
    tax = load_taxonomy()
    assert tax.version == 2


def test_format_words_remain_in_reference_index_overlay_not_removal():
    # The overlay tags form words; it must NOT remove them from their
    # Reference & Encyclopedic subcategory, so a co-occurring subject can
    # still reach the Reference shelf.
    tax = load_taxonomy()
    assert ("09 Technology, Science & Reference", "Reference & Encyclopedic") in tax.lookup(
        "dictionary"
    )


def test_v1_file_without_overlay_keys_loads_with_empty_frozensets(tmp_path):
    v1 = tmp_path / "v1.json"
    v1.write_text(
        '{"version":1,"confidence_threshold":0.34,"non_library_keywords":[],'
        '"sections":[{"code":"01 X","subcategories":['
        '{"name":"Sub","keywords":["alpha"]}]}]}',
        encoding="utf-8",
    )
    tax = load_taxonomy(v1)
    assert tax.version == 1
    assert tax.format_keywords == frozenset()
    assert tax.boilerplate_keywords == frozenset()
