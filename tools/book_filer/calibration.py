"""Calibration verdict (spec §6.2 + Plan-4 brainstorm decision).

GREEN requires ALL of: byte-identical determinism across two runs; ZERO files
auto-shelved into the wrong section in the spot-check; a human sign-off; and a
spot-check at least `min_spot_check` large. A 'review' disposition judged wrong
is NOT a failure — routing to review is always safe.
"""
from __future__ import annotations

import hashlib
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
    # EB-373 (R2): binds this verdict to an exact manifest (sha256 of canonical_projection).
    # Defaulting None keeps existing producers valid and makes an unbound verdict fail the
    # actuator's binding check *closed*. `stamp` records the run the verdict was signed for.
    manifest_digest: str | None = None
    stamp: str | None = None


@dataclass(frozen=True)
class BindingResult:
    ok: bool
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


def digest_projection(projection: str) -> str:
    """sha256 of a canonical manifest projection string — the manifest<->verdict binding anchor.

    The signer hashes the approved projection and records it on the verdict; the actuator
    re-derives the same digest from the manifest it is about to apply (see manifest.manifest_digest).
    """
    return hashlib.sha256(projection.encode("utf-8")).hexdigest()


def _gate_passes(verdict: dict, name: str) -> bool:
    """True iff `verdict["gates"][name]` is present AND records pass==True. Fail closed on any gap."""
    gates = verdict.get("gates")
    if not isinstance(gates, dict):
        return False
    gate = gates.get(name)
    return isinstance(gate, dict) and gate.get("pass") is True


def verify_binding(manifest_rows: list, verdict: dict) -> BindingResult:
    """R2: a manifest may be applied only behind a *fresh, fully-gated signed-GREEN* verdict whose
    recorded `manifest_digest` matches the manifest being applied.

    Returns ok=True only when ALL hold; otherwise ok=False with a reason naming the first failure
    (the actuator refuses + logs it). Asserts the floor and trash-safety machine gates rather than
    trusting a bare verdict: `evaluate_calibration` cannot encode them, so a bare verdict that merely
    says `green=True` (no `gates`) is rejected as gameable.
    """
    # Deferred sibling import avoids a manifest<->calibration cycle: manifest imports
    # digest_projection from this module at load time; this import only runs at call time.
    if __package__:
        from .manifest import manifest_digest
    else:  # imported with tools/ on sys.path but no package context (mirrors scan.py)
        from book_filer.manifest import manifest_digest

    if not isinstance(verdict, dict):
        return BindingResult(False, "verdict is not a mapping (fail closed)")

    recorded = verdict.get("manifest_digest")
    if not isinstance(recorded, str) or not recorded:
        return BindingResult(False, "verdict records no manifest_digest (unbound verdict, fail closed)")
    if recorded != manifest_digest(manifest_rows):
        return BindingResult(False, "manifest_digest mismatch: verdict does not bind this manifest")
    if verdict.get("green") is not True:
        return BindingResult(False, "verdict is not GREEN")
    if not _gate_passes(verdict, "auto_shelf_floor"):
        return BindingResult(False, "auto_shelf_floor gate missing or not passing")
    if not _gate_passes(verdict, "trash_safety"):
        return BindingResult(False, "trash_safety gate missing or not passing")
    return BindingResult(True, "bound: digest matches a signed, fully-gated GREEN verdict")
