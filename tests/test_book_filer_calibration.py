import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer.calibration import SpotCheck, evaluate_calibration

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
