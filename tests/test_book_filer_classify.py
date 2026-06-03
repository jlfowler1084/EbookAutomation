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


def test_keyword_matching_requires_word_boundaries():
    assert classify_name("the second recovering copy.epub", TAX).disposition == "review"
    assert classify_name("Unacknowledged.pdf", TAX).disposition == "review"


def test_word_boundary_matching_preserves_real_word_and_phrase_hits():
    knowledge = classify_name("A Theory of Knowledge.pdf", TAX)
    assert knowledge.disposition == "shelf"
    assert knowledge.section == "02 Philosophy"

    federal_reserve = classify_name("A Second Look at the Federal Reserve.epub", TAX)
    assert federal_reserve.disposition == "shelf"
    assert federal_reserve.section == "05 Finance & Investing"


def test_metadata_title_classifies_cryptic_filename():
    without_title = classify_name("x19a3.epub", TAX)
    assert without_title.disposition == "review"

    with_title = classify_name("x19a3.epub", TAX, title="A Second Look at the Federal Reserve")
    assert with_title.disposition == "shelf"
    assert with_title.section == "05 Finance & Investing"
    assert with_title.source == "metadata"


def test_title_filename_cross_section_conflict_routes_to_review():
    r = classify_name("a literary novel.epub", TAX, title="A Second Look at the Federal Reserve")
    assert r.disposition == "review"
    assert r.section == "05 Finance & Investing"
    assert r.source == "metadata"


# ---------------------------------------------------------------------------
# EB-355 Plan 5 — permanent correct-or-review regressions for the 4 RED-run
# mis-shelves (data/batch_reports/book_filer_whatif/20260602-182319). Each must
# NOT auto-shelf to its known-wrong section: land in the correct section OR route
# to review (review is always safe). All RED now (currently shelf->wrong at conf
# 1.0); #2/#3/#4 flip GREEN with word-boundary matching (Unit 2), #1 with
# title-primary source-aware scoring + publisher-boilerplate handling (Unit 3).
# Mechanisms captured by the Unit 1 characterization harness.
# ---------------------------------------------------------------------------

def test_when_genius_failed_not_misshelved_to_publishing():
    # Offending token: "publishing" (WHOLE WORD) from "Random House Publishing
    # Group" publisher boilerplate -> 11 Writing & Children's Books. Word-boundary
    # alone will NOT fix this; needs title-primary scoring + boilerplate handling.
    r = classify_name(
        "Lowenstein, Roger - When genius failed_ the rise and fall of "
        "Long-Term Capital Management (2011_2000, Random House Publishing Group) "
        "- libgen.li.epub",
        TAX,
    )
    assert r.disposition == "review" or r.section == "05 Finance & Investing", (
        f"finance book must not auto-shelf to Publishing; got {r.disposition}/{r.section}"
    )


def test_creature_from_jekyll_island_not_misshelved_to_fiction():
    # Offending token: "eco" (SUBSTRING) inside "second" -> 06 Fiction. Word-boundary fixes it.
    r = classify_name("the creature from jekyll island a second look at t.epub", TAX)
    assert r.disposition == "review" or r.section in (
        "05 Finance & Investing",
        "07 Conspiracy, Esoterica & Fringe",
    ), f"Federal-Reserve book must not auto-shelf to Fiction; got {r.disposition}/{r.section}"


def test_unacknowledged_not_misshelved_to_philosophy():
    # Offending token: "knowledge" (SUBSTRING) inside "unacknowledged" -> 02 Philosophy.
    r = classify_name(
        "Steven M. Greer - Unacknowledged_ An Expose of the World's Greatest "
        "Secret (2017) - libgen.li.pdf",
        TAX,
    )
    assert r.disposition == "review" or r.section == "07 Conspiracy, Esoterica & Fringe", (
        f"UFO-disclosure book must not auto-shelf to Philosophy; got {r.disposition}/{r.section}"
    )


def test_unseen_realm_not_misshelved_to_fiction():
    # Offending token: "eco" (SUBSTRING) inside "recovering" -> 06 Fiction. Word-boundary fixes it.
    r = classify_name("the unseen realm recovering the supernatural world.epub", TAX)
    assert r.disposition == "review" or r.section == "03 Religion & Bible Study", (
        f"biblical book must not auto-shelf to Fiction; got {r.disposition}/{r.section}"
    )


# ---------------------------------------------------------------------------
# EB-365 Unit 2 — format-tier demotion guard. A file whose entire keyword
# evidence is form-tier (dictionary/encyclopedia/...) + boilerplate
# (publishing), with NO subject-tier hit, routes to review instead of being
# auto-shelved to the Reference subcategory. Pinned #32 leads.
# ---------------------------------------------------------------------------

def test_theological_dictionary_32_demoted_to_review():
    # Pinned spot-check #32: "Theological Dictionary of the New Testament".
    # Only matches: `dictionary` (form word, title+name) + `publishing`
    # (filename boilerplate, e.g. "Eerdmans Publishing"). theology != theological
    # on a word boundary; "testament" is not a keyword. Lone form word wins
    # uncontested today -> Reference shelf. The guard must demote to review.
    r = classify_name(
        "Kittel - Theological Dictionary of the New Testament (Eerdmans Publishing).pdf",
        TAX,
        title="Theological Dictionary of the New Testament",
    )
    assert r.disposition == "review"
    assert r.reason == "format-only: no subject evidence"
    # Would-be target retained for audit.
    assert r.section == "09 Technology, Science & Reference"
    assert r.subcategory == "Reference & Encyclopedic"


def test_encyclopedia_of_unknown_subject_demoted_to_review():
    r = classify_name("The Encyclopedia of Ancient Giants in North America.pdf", TAX)
    assert r.disposition == "review"
    assert r.reason == "format-only: no subject evidence"


def test_atlas_of_unknown_subject_demoted_to_review():
    r = classify_name("Atlas of Remote Islands.epub", TAX)
    assert r.disposition == "review"
    assert r.reason == "format-only: no subject evidence"


def test_form_word_plus_subject_keyword_still_shelves():
    # R2 co-occurrence: a real subject (`python`) alongside the form word
    # (`handbook`) -> subject_evidence non-empty -> classify as today (shelf).
    r = classify_name("The Python Handbook.pdf", TAX)
    assert r.disposition == "shelf"
    assert r.section == "09 Technology, Science & Reference"
    assert r.reason is None


def test_publishing_only_is_not_demoted_precondition_guard():
    # R3 / §4.1 dual-use: `publishing` with NO form word -> M ∩ format == ∅ ->
    # guard does not fire; `publishing` stays a valid classifier keyword.
    r = classify_name("The Art of Publishing.pdf", TAX)
    assert r.disposition == "shelf"
    assert r.section == "11 Writing & Children's Books"
    assert r.reason is None


def test_form_word_plus_only_boilerplate_demoted():
    # Locks the exact #32 correction: a form word that WINS (present in title and
    # name) whose only other evidence is `publishing` boilerplate (name-only).
    # `publishing` is excluded from subject_evidence -> review. Without the
    # exclusion this would auto-shelf to Reference.
    r = classify_name(
        "Atlas of Cartography (Penguin Publishing).pdf",
        TAX,
        title="Atlas of Cartography",
    )
    assert r.disposition == "review"
    assert r.reason == "format-only: no subject evidence"


def test_pure_subject_titles_unchanged_no_reason():
    # R2: pure-subject titles classify exactly as before, with reason None.
    weimar = classify_name(
        "The Stab-in-the-Back Myth and the Fall of the Weimar Republic.pdf", TAX
    )
    assert weimar.disposition == "shelf"
    assert weimar.section == "01 History"
    assert weimar.reason is None


def test_demotion_is_deterministic():
    name = "Kittel - Theological Dictionary of the New Testament (Eerdmans Publishing).pdf"
    title = "Theological Dictionary of the New Testament"
    assert classify_name(name, TAX, title=title) == classify_name(name, TAX, title=title)
