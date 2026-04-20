"""Fallback fingerprint detector for cloud-primary VQA.

SCRUM-281 Unit 1 — identifies parsed VQA pages where the primary provider
emitted a detectable default response instead of real findings. Flagged pages
are routed to Claude for re-evaluation in a single batched call.

Three matcher categories (OR-combined):
  1. empty issues + score >= threshold per page (hardest signal)
  2. known-fallback substring in issues[i].description (case-insensitive)
  3. report-level category_scores collapse (all pages empty-issues + any >= threshold)

Operates on parsed pages (post-schema-validation list[dict]) — not raw text.
Detection is a response-layer concern; the VisionProvider Protocol is untouched.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path


logger = logging.getLogger("visual_qa.fingerprint_detector")


@dataclass(frozen=True)
class FingerprintSettings:
    """Tuning knobs for the fallback detector.

    empty_issues_score_threshold: pages with issues==[] AND score >= this
        value trigger Matcher 1. Default 80 (validated against SCRUM-283 artifacts).
    substring_corpus: case-insensitive substrings to match in issue descriptions.
        Loaded from the corpus JSON; passed in as a tuple for hashability.
    match_category_scores_collapse: when True, Matcher 3 fires — if ALL pages
        have issues==[] and any page hits the score threshold, every page is
        flagged regardless of individual score.
    """

    empty_issues_score_threshold: int
    substring_corpus: tuple[str, ...]
    match_category_scores_collapse: bool


class FallbackFingerprintDetector:
    """Detects VQA pages that match known cloud-provider fallback patterns.

    Usage::

        detector = FallbackFingerprintDetector.from_corpus("tools/visual_qa_fallback_fingerprints.json")
        settings = FingerprintSettings(
            empty_issues_score_threshold=80,
            substring_corpus=tuple(corpus["substring_fingerprints"]),
            match_category_scores_collapse=True,
        )
        flagged_page_numbers = detector.detect(all_pages_results, settings)
    """

    def __init__(self, substring_fingerprints: list[str]) -> None:
        # Store lowercased for case-insensitive matching in detect()
        self._fingerprints: tuple[str, ...] = tuple(
            s.lower() for s in substring_fingerprints
        )

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_corpus(cls, corpus_path: str | Path) -> FallbackFingerprintDetector:
        """Load the detector from a versioned corpus JSON file.

        Raises FileNotFoundError if the file is absent (misconfiguration).
        Raises ValueError if the file is not valid JSON (corpus corruption).
        """
        corpus_path = Path(corpus_path)
        if not corpus_path.exists():
            raise FileNotFoundError(
                f"Fingerprint corpus not found: {corpus_path}. "
                "Check visual_qa.fallback.corpus_path in config/settings.json."
            )
        try:
            data = json.loads(corpus_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Malformed JSON in fingerprint corpus {corpus_path}: {exc}"
            ) from exc

        fingerprints = data.get("substring_fingerprints", [])
        logger.debug(
            "Loaded fingerprint corpus v%s with %d substring entries from %s",
            data.get("version", "?"),
            len(fingerprints),
            corpus_path,
        )
        return cls(fingerprints)

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect(
        self,
        parsed_pages: list[dict],
        settings: FingerprintSettings,
    ) -> set[int]:
        """Return page numbers that match a known-fallback fingerprint.

        parsed_pages is the all_pages_results list from run_visual_qa's
        batch loop — dicts with keys: page_number, page_type, score, pass,
        issues (list of issue dicts with description, category, severity).

        Returns an empty set when no fallback is detected or the list is empty.
        Non-dict entries and pages without page_number are silently skipped.
        """
        if not parsed_pages:
            return set()

        valid_pages = [p for p in parsed_pages if isinstance(p, dict)]
        if not valid_pages:
            return set()

        flagged: set[int] = set()

        # Matcher 3 (report-level): if ALL pages have issues==[], this whole
        # batch looks like a collapse — flag every page above the threshold.
        # This catches the Python-class pattern where Qwen emits structurally
        # uniform empty responses across all pages.
        if settings.match_category_scores_collapse:
            pages_with_issues = [p for p in valid_pages if p.get("issues", [])]
            if not pages_with_issues:
                # No page has real findings — check for the high-score signal
                any_high = any(
                    p.get("score", 0) >= settings.empty_issues_score_threshold
                    for p in valid_pages
                )
                if any_high:
                    for page in valid_pages:
                        pn = page.get("page_number")
                        if pn is not None:
                            flagged.add(pn)
                    logger.debug(
                        "Matcher 3 fired: all %d pages have issues==[] with at least one score >= %d",
                        len(valid_pages),
                        settings.empty_issues_score_threshold,
                    )
                    return flagged
            # Mixed-page case: Matcher 3 does not fire; fall through to 1+2

        # Matcher 1 (per-page): empty issues + high score
        for page in valid_pages:
            if (
                not page.get("issues", [])
                and page.get("score", 0) >= settings.empty_issues_score_threshold
            ):
                pn = page.get("page_number")
                if pn is not None:
                    flagged.add(pn)

        # Matcher 2 (per-issue): substring match on description
        if self._fingerprints:
            for page in valid_pages:
                pn = page.get("page_number")
                if pn is None or pn in flagged:
                    continue
                for issue in page.get("issues", []):
                    desc = issue.get("description", "").lower()
                    if any(fp in desc for fp in self._fingerprints):
                        flagged.add(pn)
                        break

        if flagged:
            logger.debug(
                "Fingerprint detector flagged %d page(s): %s",
                len(flagged),
                sorted(flagged),
            )

        return flagged
