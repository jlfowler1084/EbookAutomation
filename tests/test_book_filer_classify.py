import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer.taxonomy import load_taxonomy
from book_filer.classify import Classification, classify_name

TAX = load_taxonomy()


def test_classifies_clear_history_title():
    r = classify_name("The Stab-in-the-Back Myth and the Fall of the Weimar Republic.pdf", TAX)
    assert r.disposition == "shelf"
    assert r.section == "01 History"
    assert r.subcategory == "World Wars (WWI, WWII, Weimar)"
    assert r.confidence >= TAX.confidence_threshold


def test_flags_non_library_file():
    r = classify_name("Joseph_Fowler_Resume_Updated.pdf", TAX)
    assert r.disposition == "non_library"
    assert r.section is None


def test_unmatched_filename_routes_to_review():
    r = classify_name("-jd55w3j.pdf", TAX)
    assert r.disposition == "review"
    assert r.confidence == 0.0


def test_marxism_primary_source_goes_to_politics():
    r = classify_name("Kolakowski - Main Currents of Marxism.pdf", TAX)
    assert r.disposition == "shelf"
    assert r.section == "04 Politics & Society"
    assert r.subcategory == "Marxism & Socialist Theory"


def test_classification_is_deterministic():
    name = "Aleister Crowley - Book Of The Law.pdf"
    assert classify_name(name, TAX) == classify_name(name, TAX)
