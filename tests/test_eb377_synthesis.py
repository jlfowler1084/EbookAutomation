import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import synthesize_batch_findings as syn  # noqa: E402


def test_synthesis_sections_and_artifact_separation():
    provenance = {
        "summary": {"total": 50, "complete": 47, "coverage_gap": 1,
                    "kfx_failed": 2, "weld_books": 0, "weld_total_sum": 0},
        "books": [{"source": "On First Principles.pdf", "weld_total": 0,
                   "status": "complete"}],
    }
    batch_qa_report = {
        "failure_clusters": [
            {"pattern_id": "FOOTNOTES_UNLINKED", "severity": "medium", "book_count": 9},
            {"pattern_id": "VQA_SCORE_LOW", "severity": "high", "book_count": 3},
        ],
        "observations": ["VQA scores correlate with ligature_splits"],
    }
    determinism = {"reproducible": False, "max_delta": 4}

    md = syn.synthesize(provenance, batch_qa_report, determinism)
    assert "Header-bleed verdict" in md
    assert "New patterns" in md
    assert "Measurement artifacts" in md
    # high-severity ranks above medium even with lower book_count
    assert md.index("VQA_SCORE_LOW") < md.index("FOOTNOTES_UNLINKED")
    # the REAL field (book_count) must render, not "?"
    assert "| VQA_SCORE_LOW | high | 3 |" in md
    # non-deterministic VQA is an artifact, not a finding
    assert "non-deterministic" in md.lower()
    assert "coverage_gap" in md or "coverage gap" in md.lower()


def test_critical_outranks_high():
    provenance = {"summary": {"total": 1, "complete": 1, "coverage_gap": 0,
                              "kfx_failed": 0, "weld_books": 0, "weld_total_sum": 0},
                  "books": []}
    batch_qa_report = {"failure_clusters": [
        {"pattern_id": "HIGH_ONE", "severity": "high", "book_count": 20},
        {"pattern_id": "CRIT_ONE", "severity": "critical", "book_count": 1},
    ], "observations": []}
    md = syn.synthesize(provenance, batch_qa_report, {"reproducible": True})
    assert md.index("CRIT_ONE") < md.index("HIGH_ONE")
