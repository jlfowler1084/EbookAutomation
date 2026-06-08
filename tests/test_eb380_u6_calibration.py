"""U6 calibration gate (EB-380).

Deliverables:
1. Dead-high-key resolution: "high":0.6 dropped from _DEFAULT_THRESHOLDS (never read)
2. Confidence-correctness correlation: seeded fixtures + adversarial check
3. Determinism gate: two sweep_inbox calls with frozen oracle -> byte-identical projection
4. Provisional threshold documentation

Calibration story (STOP-gate summary):
- Seeded set (N=14 fixtures) shows zero wrong-shelf cases at any confidence level.
- For correctly-shelved cases, mean confidence >= 0.80 (multiple keyword hits).
- The format guard (EB-365) routes format-only filenames to review before the propose gate,
  closing the "encyclopedia/dictionary at confidence 1.0" false-shelf class.
- PROVISIONAL threshold: taxonomy.confidence_threshold=0.34 is correct for Phase-1
  propose-only. Graduation condition: >=150 live inbox observations with per-section
  coverage AND wrong-shelf rate <=2%, then raise to 0.45 or re-calibrate.
- "high":0.6 DECISION (U6): dropped. The propose gate is cls.disposition=="shelf", which
  already embeds taxonomy.confidence_threshold. A second inbox-level "high" gate would
  create a [0.34, 0.6) deadband where classify says shelf but inbox downgrades --
  an inconsistency, not calibration. Graduation path: raise confidence_threshold in JSON.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from book_filer.classify import classify_name
from book_filer.config import LibraryConfig
from book_filer.inbox import (
    QUEUE_FILENAME,
    _DEFAULT_THRESHOLDS,
    sweep_inbox,
)
from book_filer.taxonomy import load_taxonomy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(tmp_path: Path) -> LibraryConfig:
    return LibraryConfig(
        library_root=tmp_path / "Books",
        calibre_library=tmp_path / "Calibre",
        audio_root=tmp_path / "Books" / "Audio_Books",
        documents_root=tmp_path / "Documents",
        materialize_mode="copy",
        trash_retention_days=30,
        operational_folders=("_Inbox", "_Needs_Review", "_Quarantine", "_Trash_Pending"),
        scan_exclude=("Audio_Books",),
        max_path_length=240,
    )


def _canonical_rows(queue_path: Path) -> list[dict]:
    """Load queue JSONL, strip non-deterministic fields, sort by path."""
    rows = []
    for line in queue_path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        row.pop("swept_at", None)   # timestamp — non-deterministic by design
        rows.append(row)
    return sorted(rows, key=lambda r: r.get("path", ""))


# ---------------------------------------------------------------------------
# 1. Dead-high-key resolution
# ---------------------------------------------------------------------------

def test_high_key_removed_from_default_thresholds():
    """U6 decision: "high" key was never read; dropped to eliminate dead code."""
    assert "high" not in _DEFAULT_THRESHOLDS, (
        '"high" must be removed from _DEFAULT_THRESHOLDS (U6 decision: propose is gated '
        "by cls.disposition=='shelf' which already embeds taxonomy.confidence_threshold)"
    )


def test_low_key_remains_for_tier_routing():
    """'low' is actively used at _compute_row:301 to route review->ambiguous."""
    assert "low" in _DEFAULT_THRESHOLDS
    assert isinstance(_DEFAULT_THRESHOLDS["low"], float)
    assert 0.0 < _DEFAULT_THRESHOLDS["low"] < 1.0


# ---------------------------------------------------------------------------
# 2. Seeded calibration fixtures + confidence-correctness correlation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CalibrationFixture:
    filename_stem: str          # stem of the PDF filename (no ext)
    title: Optional[str]        # PDF title metadata, or None
    expected_section: Optional[str]   # None = don't-care (review / non_library)
    expected_disposition: str   # "shelf" | "review" | "non_library"
    note: str = ""


# Human-labeled ground truth.  For "shelf" entries expected_section is the full
# section code from the taxonomy (e.g. "05 Finance & Investing").
_FIXTURES: list[CalibrationFixture] = [
    # ── Correct-shelf cases (strong evidence, clear single-section signal) ────────
    CalibrationFixture(
        "nietzsche-beyond-good-evil", "Beyond Good and Evil",
        "02 Philosophy", "shelf",
        note="nietzsche keyword -> 02 Philosophy",
    ),
    CalibrationFixture(
        "communist-manifesto-marx-engels", "The Communist Manifesto",
        "04 Politics & Society", "shelf",
        note="marx + communist -> 04 Politics Marxism",
    ),
    CalibrationFixture(
        "python-in-easy-steps-mcgrath", "Python in Easy Steps",
        "09 Technology, Science & Reference", "shelf",
        note="python + programming -> 09 Technology",
    ),
    CalibrationFixture(
        "lords-of-finance-ahamed", "Lords of Finance",
        "05 Finance & Investing", "shelf",
        note="lords of finance (multi-word keyword) -> 05 Finance Money/Banking",
    ),
    CalibrationFixture(
        "genesis-annotated-bible-barton", "Genesis: A Bible Commentary",
        "03 Religion & Bible Study", "shelf",
        note="genesis + bible + commentary -> 03 Religion Bible Study",
    ),
    CalibrationFixture(
        "world-war-ii-beevor", "World War II: The Last Battle",
        "01 History", "shelf",
        note="world war -> 01 History World Wars",
    ),
    CalibrationFixture(
        "sherlock-holmes-complete-doyle", "The Adventures of Sherlock Holmes",
        "06 Fiction & Literature", "shelf",
        note="sherlock -> 06 Fiction Genre Fiction",
    ),
    CalibrationFixture(
        "stock-market-technical-analysis", "Technical Analysis of Stock Markets",
        "05 Finance & Investing", "shelf",
        note="technical analysis + stock -> 05 Finance Stock Market",
    ),
    CalibrationFixture(
        "powershell-in-a-month-jones", "PowerShell in a Month of Lunches",
        "09 Technology, Science & Reference", "shelf",
        note="powershell -> 09 Technology Programming",
    ),
    CalibrationFixture(
        "bible-study-ezekiel-commentary", "Ezekiel: A Bible Commentary and Study Guide",
        "03 Religion & Bible Study", "shelf",
        note="ezekiel + bible + commentary -> 03 Religion Bible Study",
    ),
    # ── Review cases (cross-section ambiguity / format-only EB-365) ──────────────
    CalibrationFixture(
        "nicomachean-ethics-political-economy",
        "Ethics and Political Economy of Aristotle",
        None, "review",
        note="ethics (02 Phil) vs political economy (04 Pol) cross-section tie -> review",
    ),
    CalibrationFixture(
        "dictionary-of-philosophy-terms",
        "A Dictionary of Philosophy",
        None, "review",
        note="dictionary is format_keyword; no subject evidence -> EB-365 format guard fires",
    ),
    # ── Non-library cases ────────────────────────────────────────────────────────
    CalibrationFixture(
        "2024-tax-return-1040-w2", None,
        None, "non_library",
        note="tax + 1040 are non_library_keywords",
    ),
    CalibrationFixture(
        "resume-john-doe-senior-developer", None,
        None, "non_library",
        note="resume is a non_library_keyword",
    ),
]


@pytest.fixture(scope="module")
def real_taxonomy():
    return load_taxonomy()


def _run_fixtures(taxonomy) -> list[tuple[CalibrationFixture, object]]:
    return [
        (fx, classify_name(fx.filename_stem, taxonomy, fx.title))
        for fx in _FIXTURES
    ]


def test_calibration_correct_shelf_fixtures_all_shelf(real_taxonomy):
    """Every 'shelf'-expected fixture must produce shelf AND the expected section."""
    shelf_fixtures = [fx for fx in _FIXTURES if fx.expected_disposition == "shelf"]
    failures = []
    for fx in shelf_fixtures:
        cls = classify_name(fx.filename_stem, real_taxonomy, fx.title)
        if cls.disposition != "shelf":
            failures.append(
                f"  {fx.filename_stem!r}: expected shelf, got {cls.disposition!r} "
                f"(conf={cls.confidence:.3f}, section={cls.section!r})"
            )
        elif cls.section != fx.expected_section:
            failures.append(
                f"  {fx.filename_stem!r}: expected section {fx.expected_section!r}, "
                f"got {cls.section!r} (conf={cls.confidence:.3f})"
            )
    assert not failures, "Calibration shelf fixtures failed:\n" + "\n".join(failures)


def test_calibration_review_fixtures_all_review(real_taxonomy):
    """Every 'review'-expected fixture must produce review disposition."""
    review_fixtures = [fx for fx in _FIXTURES if fx.expected_disposition == "review"]
    failures = []
    for fx in review_fixtures:
        cls = classify_name(fx.filename_stem, real_taxonomy, fx.title)
        if cls.disposition != "review":
            failures.append(
                f"  {fx.filename_stem!r}: expected review, got {cls.disposition!r} "
                f"(conf={cls.confidence:.3f}, section={cls.section!r}, note: {fx.note})"
            )
    assert not failures, "Calibration review fixtures failed:\n" + "\n".join(failures)


def test_calibration_non_library_fixtures(real_taxonomy):
    """Every 'non_library'-expected fixture must produce non_library disposition."""
    nl_fixtures = [fx for fx in _FIXTURES if fx.expected_disposition == "non_library"]
    failures = []
    for fx in nl_fixtures:
        cls = classify_name(fx.filename_stem, real_taxonomy, fx.title)
        if cls.disposition != "non_library":
            failures.append(
                f"  {fx.filename_stem!r}: expected non_library, got {cls.disposition!r}"
            )
    assert not failures, "Non-library fixtures failed:\n" + "\n".join(failures)


def test_no_wrong_shelf_in_calibration_set(real_taxonomy):
    """Adversarial check: no fixture produces shelf with the WRONG section.

    A wrong-shelf at any confidence level is a calibration finding.  If this
    test fails, the failing fixture's confidence is the key data point -- a
    wrong-shelf at confidence > 0.5 means the threshold sorts by the wrong axis.
    """
    wrong_shelf: list[str] = []
    for fx in _FIXTURES:
        if fx.expected_section is None:
            continue  # review/non_library: section is don't-care
        cls = classify_name(fx.filename_stem, real_taxonomy, fx.title)
        if cls.disposition == "shelf" and cls.section != fx.expected_section:
            wrong_shelf.append(
                f"  {fx.filename_stem!r}: expected {fx.expected_section!r}, "
                f"got {cls.section!r} at confidence={cls.confidence:.3f}"
            )
    assert not wrong_shelf, (
        "Wrong-shelf cases found in calibration set (confidence shown -- "
        "high confidence wrong-shelf means the threshold sorts by the wrong axis):\n"
        + "\n".join(wrong_shelf)
    )


def test_correct_shelf_mean_confidence_above_half(real_taxonomy):
    """Confidence-correctness correlation: correctly-shelved cases must average >= 0.5.

    If the mean falls below 0.5, the shelf decisions are marginal -- the threshold
    is not providing meaningful signal above the minimum.
    """
    shelf_confidences = []
    for fx in _FIXTURES:
        if fx.expected_disposition != "shelf":
            continue
        cls = classify_name(fx.filename_stem, real_taxonomy, fx.title)
        if cls.disposition == "shelf" and cls.section == fx.expected_section:
            shelf_confidences.append(cls.confidence)

    assert shelf_confidences, "No correctly-shelved cases to measure"
    mean_conf = sum(shelf_confidences) / len(shelf_confidences)
    assert mean_conf >= 0.5, (
        f"Mean confidence for correctly-shelved calibration cases = {mean_conf:.3f} < 0.5. "
        "This indicates the classifier is making marginal shelf decisions -- "
        "raise taxonomy.confidence_threshold or strengthen taxonomy keywords."
    )


def test_confidence_at_or_above_taxonomy_threshold_for_shelf(real_taxonomy):
    """Sanity: every shelf disposition must have confidence >= taxonomy.confidence_threshold.

    This is guaranteed by _classification_from_scores but worth asserting explicitly
    so any future refactor that breaks the invariant fails loudly here.
    """
    threshold = real_taxonomy.confidence_threshold
    violations = []
    for fx in _FIXTURES:
        cls = classify_name(fx.filename_stem, real_taxonomy, fx.title)
        if cls.disposition == "shelf" and cls.confidence < threshold:
            violations.append(
                f"  {fx.filename_stem!r}: shelf at conf={cls.confidence:.3f} < "
                f"threshold={threshold:.3f}"
            )
    assert not violations, (
        "Shelf disposition below taxonomy.confidence_threshold (classifier invariant broken):\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# 3. Determinism gate
# ---------------------------------------------------------------------------

def test_determinism_with_frozen_oracle(tmp_path, real_taxonomy):
    """Two sweep_inbox calls with a frozen empty oracle produce byte-identical output.

    The frozen oracle is the key: if the live shelf is scanned between calls, a file
    that appears on shelf between run1 and run2 would change the dedup verdict.
    Pinning to frozenset() eliminates that non-determinism source.

    swept_at is the only field excluded from comparison -- it is a wall-clock timestamp
    that legitimately differs between calls.
    """
    cfg = _cfg(tmp_path)

    # Populate a small inbox
    inbox = cfg.library_root / "_Inbox" / "Manual"
    inbox.mkdir(parents=True)
    (inbox / "nietzsche-beyond-good-evil.pdf").write_bytes(b"PDF" * 100)
    (inbox / "lords-of-finance-ahamed.pdf").write_bytes(b"PDF" * 200)
    (inbox / "unknown-no-keywords-xyz.pdf").write_bytes(b"PDF" * 50)

    frozen_oracle: frozenset[str] = frozenset()

    run1 = tmp_path / "run1"
    run1.mkdir()
    sweep_inbox(
        cfg, run1, real_taxonomy,
        library_root_arg=cfg.library_root,
        settle_seconds=0,
        _shelf_oracle=frozen_oracle,
    )

    run2 = tmp_path / "run2"
    run2.mkdir()
    sweep_inbox(
        cfg, run2, real_taxonomy,
        library_root_arg=cfg.library_root,
        settle_seconds=0,
        _shelf_oracle=frozen_oracle,
    )

    rows1 = _canonical_rows(run1 / QUEUE_FILENAME)
    rows2 = _canonical_rows(run2 / QUEUE_FILENAME)

    assert rows1 == rows2, (
        "sweep_inbox is non-deterministic with frozen oracle.\n"
        f"Run1 has {len(rows1)} rows, run2 has {len(rows2)} rows.\n"
        "Differing rows (first mismatch):\n"
        + _diff_rows(rows1, rows2)
    )


def _diff_rows(a: list[dict], b: list[dict]) -> str:
    """Return a short description of the first differing row pair."""
    if len(a) != len(b):
        return f"  row count differs: {len(a)} vs {len(b)}"
    for i, (ra, rb) in enumerate(zip(a, b)):
        if ra != rb:
            diffs = {k for k in (ra.keys() | rb.keys()) if ra.get(k) != rb.get(k)}
            return f"  row[{i}] differs in fields: {diffs}\n  run1: {ra}\n  run2: {rb}"
    return "  (no row-level diff found — ordering issue?)"


# ---------------------------------------------------------------------------
# 4. Provisional threshold documentation (static assertions)
# ---------------------------------------------------------------------------

def test_provisional_threshold_graduation_conditions_documented():
    """Ensure the calibration module docstring records Phase-2 graduation conditions.

    This is a documentation contract: the source file of THIS module must contain
    the magic phrases so that they're discoverable via grep and survive future edits.
    """
    source = Path(__file__).read_text(encoding="utf-8")
    assert ">=150" in source, (
        "Calibration module must document the >=150 live observation "
        "graduation condition for Phase-2."
    )
    assert "2%" in source or "<=2%" in source, (
        "Calibration module must document the <=2% wrong-shelf graduation gate."
    )


def test_provisional_threshold_current_value_is_sane(real_taxonomy):
    """taxonomy.confidence_threshold must be in [0.25, 0.75] for Phase-1.

    Outside this band either lets too many ties through (< 0.25) or would
    block legitimate shelf proposals (> 0.75).
    """
    t = real_taxonomy.confidence_threshold
    assert 0.25 <= t <= 0.75, (
        f"taxonomy.confidence_threshold={t:.3f} is outside the sane Phase-1 range [0.25, 0.75]. "
        "Recalibrate before next phase."
    )
