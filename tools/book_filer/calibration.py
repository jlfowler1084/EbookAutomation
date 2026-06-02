"""Calibration verdict (spec §6.2 + Plan-4 brainstorm decision).

GREEN requires ALL of: byte-identical determinism across two runs; ZERO files
auto-shelved into the wrong section in the spot-check; a human sign-off; and a
spot-check at least `min_spot_check` large. A 'review' disposition judged wrong
is NOT a failure — routing to review is always safe.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpotCheck:
    path: str
    disposition: str   # "shelf" | "review" | "non_library"
    correct: bool      # human judgement of whether the disposition was right


@dataclass(frozen=True)
class CalibrationVerdict:
    deterministic: bool
    wrong_shelf_count: int
    spot_check_size: int
    signed_off_by: str | None
    green: bool
    reason: str


def evaluate_calibration(
    projection_a: str,
    projection_b: str,
    spot_check: list[SpotCheck],
    signed_off_by: str | None,
    min_spot_check: int = 20,
) -> CalibrationVerdict:
    deterministic = projection_a == projection_b
    wrong_shelf = sum(1 for c in spot_check if c.disposition == "shelf" and not c.correct)
    big_enough = len(spot_check) >= min_spot_check
    signed = bool(signed_off_by and signed_off_by.strip())

    green = deterministic and wrong_shelf == 0 and big_enough and signed
    if green:
        reason = "GREEN: deterministic, zero wrong-shelf, signed off."
    else:
        fails = []
        if not deterministic:
            fails.append("non-deterministic")
        if wrong_shelf:
            fails.append(f"{wrong_shelf} wrong-shelf")
        if not big_enough:
            fails.append(f"spot-check {len(spot_check)} < {min_spot_check}")
        if not signed:
            fails.append("not signed off")
        reason = "RED: " + ", ".join(fails)

    return CalibrationVerdict(deterministic, wrong_shelf, len(spot_check), signed_off_by, green, reason)
