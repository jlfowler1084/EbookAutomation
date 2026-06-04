import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer.calibration import (
    CalibrationVerdict,
    SpotCheck,
    evaluate_calibration,
    verify_binding,
)
from book_filer.manifest import ManifestRow, manifest_digest

_OK_SAMPLE = [SpotCheck(path=f"f{i}", disposition="shelf", correct=True) for i in range(20)]


def test_green_requires_determinism_zero_wrongshelf_and_signoff():
    v = evaluate_calibration("PROJ", "PROJ", _OK_SAMPLE, signed_off_by="joe", min_spot_check=20)
    assert v.green is True
    assert v.deterministic and v.wrong_shelf_count == 0


def test_non_deterministic_is_red():
    v = evaluate_calibration("PROJ_A", "PROJ_B", _OK_SAMPLE, signed_off_by="joe", min_spot_check=20)
    assert v.green is False and v.deterministic is False


def test_any_wrong_shelf_is_red():
    sample = _OK_SAMPLE[:-1] + [SpotCheck(path="bad", disposition="shelf", correct=False)]
    v = evaluate_calibration("PROJ", "PROJ", sample, signed_off_by="joe", min_spot_check=20)
    assert v.green is False and v.wrong_shelf_count == 1


def test_wrong_review_item_does_not_fail_green():
    # A 'review' item judged incorrect is NOT a wrong-shelf; review is always safe.
    sample = _OK_SAMPLE + [SpotCheck(path="r", disposition="review", correct=False)]
    v = evaluate_calibration("PROJ", "PROJ", sample, signed_off_by="joe", min_spot_check=20)
    assert v.green is True


def test_missing_signoff_or_small_sample_is_red():
    assert evaluate_calibration("P", "P", _OK_SAMPLE, signed_off_by=None, min_spot_check=20).green is False
    assert evaluate_calibration("P", "P", _OK_SAMPLE[:5], signed_off_by="joe", min_spot_check=20).green is False


def test_empty_or_whitespace_signoff_is_red():
    # A gate must not treat an empty / whitespace-only signer as a real sign-off.
    assert evaluate_calibration("P", "P", _OK_SAMPLE, signed_off_by="", min_spot_check=20).green is False
    assert evaluate_calibration("P", "P", _OK_SAMPLE, signed_off_by="   ", min_spot_check=20).green is False


# --------------------------------------------------------------------------- #
# Unit 1 (EB-373): manifest <-> signed-GREEN binding (R2)
# --------------------------------------------------------------------------- #

def _row(**kw) -> ManifestRow:
    base = dict(
        original_path=r"F:\Books\_Inbox\x.epub", destination_path=r"F:\Books\01 History\a.epub",
        sha256="abc123", size=10, planned_calibre_key="isbn:9780", calibre_id=None, isbn="9780",
        format="epub", section="01 History", subcategory="Modern & 20th-Century General",
        author_sort="A, B", title="T", year=2000, duplicate_group_id=None, canonical_reason=None,
        classification_confidence=0.9, classification_source="rule", taxonomy_version=1,
        tool_version="0.4.0", action="copy", undo_action="Remove-Item -LiteralPath dest", review_required=False,
    )
    base.update(kw)
    return ManifestRow(**base)


def _signed_verdict(rows, **overrides) -> dict:
    """A fully-gated signed-GREEN sidecar bound to `rows` (shape mirrors
    data/batch_reports/.../calibration-verdict-signed.json + the new manifest_digest)."""
    verdict = {
        "green": True,
        "manifest_digest": manifest_digest(rows),
        "gates": {
            "auto_shelf_floor": {"pass": True, "auto_shelf_count": 225, "floor": 224},
            "trash_safety": {"pass": True, "trash_rows": 44, "violations": 0},
        },
    }
    verdict.update(overrides)
    return verdict


def test_calibration_verdict_carries_optional_binding_fields_defaulting_none():
    # Back-compat: existing producers construct a bare verdict; binding fields default None.
    v = evaluate_calibration("PROJ", "PROJ", _OK_SAMPLE, signed_off_by="joe", min_spot_check=20)
    assert v.manifest_digest is None and v.stamp is None
    bound = CalibrationVerdict(
        deterministic=True, wrong_shelf_count=0, spot_check_size=20, signed_off_by="joe",
        green=True, reason="GREEN", manifest_digest="deadbeef", stamp="20260604-000000",
    )
    assert bound.manifest_digest == "deadbeef" and bound.stamp == "20260604-000000"


def test_manifest_digest_is_order_and_calibre_id_invariant():
    # Built on the already-sorted, calibre_id-dropped projection -> order/volatile invariant.
    a = [_row(original_path="b", calibre_id=None), _row(original_path="a", calibre_id="x")]
    b = [_row(original_path="a", calibre_id="y"), _row(original_path="b", calibre_id=None)]
    assert manifest_digest(a) == manifest_digest(b)


def test_manifest_digest_detects_real_drift():
    a = [_row(original_path="a", section="01 History")]
    b = [_row(original_path="a", section="04 Politics & Society")]
    assert manifest_digest(a) != manifest_digest(b)


def test_verify_binding_accepts_matching_fully_gated_green():
    rows = [_row(original_path="a"), _row(original_path="b")]
    result = verify_binding(rows, _signed_verdict(rows))
    assert result.ok is True


def test_verify_binding_rejects_digest_mismatch():
    rows = [_row(original_path="a")]
    other = [_row(original_path="a", section="99 Different")]
    # Verdict bound to `other`, applied against `rows` -> refuse (fail closed).
    result = verify_binding(rows, _signed_verdict(other))
    assert result.ok is False and "digest" in result.reason.lower()


def test_verify_binding_rejects_unbound_verdict():
    rows = [_row(original_path="a")]
    no_digest = _signed_verdict(rows)
    no_digest["manifest_digest"] = None  # an unbound (bare) verdict
    assert verify_binding(rows, no_digest).ok is False
    del no_digest["manifest_digest"]
    assert verify_binding(rows, no_digest).ok is False


def test_verify_binding_rejects_non_green():
    rows = [_row(original_path="a")]
    assert verify_binding(rows, _signed_verdict(rows, green=False)).ok is False


def test_verify_binding_rejects_missing_floor_gate():
    rows = [_row(original_path="a")]
    v = _signed_verdict(rows)
    del v["gates"]["auto_shelf_floor"]
    result = verify_binding(rows, v)
    assert result.ok is False and "floor" in result.reason.lower()


def test_verify_binding_rejects_missing_trash_safety_gate():
    rows = [_row(original_path="a")]
    v = _signed_verdict(rows)
    del v["gates"]["trash_safety"]
    result = verify_binding(rows, v)
    assert result.ok is False and "trash" in result.reason.lower()


def test_verify_binding_rejects_failing_gate():
    # Present but not passing -> reject (assert pass, don't trust mere presence).
    rows = [_row(original_path="a")]
    v = _signed_verdict(rows)
    v["gates"]["auto_shelf_floor"] = {"pass": False, "auto_shelf_count": 10, "floor": 224}
    assert verify_binding(rows, v).ok is False


def test_verify_binding_rejects_bare_calibration_verdict():
    # A bare evaluate_calibration-style verdict (green True, NO machine gates) is "gameable" -> reject.
    rows = [_row(original_path="a")]
    bare = {"green": True, "manifest_digest": manifest_digest(rows)}  # no "gates"
    assert verify_binding(rows, bare).ok is False
