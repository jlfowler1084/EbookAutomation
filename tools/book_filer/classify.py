"""Deterministic filename classifier (spec §7 deterministic-first pass).

Disposition is one of:
- "non_library": a non-book file (resume, tax form, ...) — never shelved.
- "shelf": a confident (section, subcategory) match at/above the threshold.
- "review": no match or a low-confidence/tie — routed to _Needs_Review.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
import re

from .taxonomy import Taxonomy


@dataclass(frozen=True)
class Classification:
    disposition: str                 # "shelf" | "review" | "non_library"
    section: str | None
    subcategory: str | None
    confidence: float
    source: str = "rule"
    reason: str | None = None        # audit note when a rule routes to review


_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_SOURCE_BOILERPLATE_PHRASES = (
    "random house publishing group",
)


def _normalize_match_text(text: str) -> str:
    """Lowercase and collapse punctuation/separators for boundary-aware matching."""
    return " ".join(_NON_ALNUM_RE.sub(" ", text.lower()).split())


@lru_cache(maxsize=None)
def _keyword_pattern(keyword: str) -> re.Pattern[str] | None:
    normalized = _normalize_match_text(keyword)
    if not normalized:
        return None
    parts = [re.escape(part) for part in normalized.split()]
    phrase = r"\s+".join(parts)
    return re.compile(rf"(?<![a-z0-9]){phrase}(?![a-z0-9])")


def _keyword_matches(keyword: str, normalized_text: str) -> bool:
    pattern = _keyword_pattern(keyword)
    return bool(pattern and pattern.search(normalized_text))


def _strip_source_boilerplate(normalized_text: str) -> str:
    text = normalized_text
    for phrase in _SOURCE_BOILERPLATE_PHRASES:
        pattern = _keyword_pattern(phrase)
        if pattern:
            text = pattern.sub(" ", text)
    return " ".join(text.split())


def _score_text(normalized_text: str, taxonomy: Taxonomy) -> Counter[tuple[str, str]]:
    scores: Counter[tuple[str, str]] = Counter()
    for keyword, targets in taxonomy._index.items():
        if _keyword_matches(keyword, normalized_text):
            for target in sorted(targets):
                scores[target] += 1
    return scores


def _collect_matches(normalized_text: str, taxonomy: Taxonomy) -> set[str]:
    """Return the set of indexed keywords that match the text (identities, not counts)."""
    if not normalized_text:
        return set()
    return {kw for kw in taxonomy._index if _keyword_matches(kw, normalized_text)}


_FORMAT_ONLY_REASON = "format-only: no subject evidence"


def _apply_format_guard(
    result: Classification,
    name_text: str,
    title_text: str,
    taxonomy: Taxonomy,
) -> Classification:
    """EB-365: demote a would-be shelf whose only evidence is form-tier + boilerplate.

    Fires only when at least one *form* word matched (precondition) and nothing
    that matched is subject evidence. Keeps the would-be section/subcategory on
    the row for audit. Any subject-tier hit — or no form-word hit — is untouched.
    """
    if result.disposition != "shelf":
        return result

    matched = _collect_matches(name_text, taxonomy) | _collect_matches(title_text, taxonomy)
    if not (matched & taxonomy.format_keywords):
        return result  # no form word -> classify as today (R2/R3 precondition)

    subject_evidence = matched - taxonomy.format_keywords - taxonomy.boilerplate_keywords
    if subject_evidence:
        return result  # a real subject co-occurs -> classify as today (R2)

    return Classification(
        "review",
        result.section,
        result.subcategory,
        result.confidence,
        result.source,
        reason=_FORMAT_ONLY_REASON,
    )


def _rank_scores(scores: Counter[tuple[str, str]]) -> list[tuple[tuple[str, str], int]]:
    return sorted(scores.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))


def _classification_from_scores(
    scores: Counter[tuple[str, str]],
    taxonomy: Taxonomy,
    source: str,
) -> Classification:
    if not scores:
        return Classification("review", None, None, 0.0, source)

    ranked = _rank_scores(scores)
    (best_section, best_sub), best_hits = ranked[0]
    runner_hits = ranked[1][1] if len(ranked) > 1 else 0

    total = sum(scores.values())
    confidence = best_hits / total  # share of hits the winner owns; 1.0 == unambiguous

    # 3. A genuine tie across different sections is ambiguous -> review.
    tie = runner_hits == best_hits and ranked[1][0][0] != best_section
    if tie or confidence < taxonomy.confidence_threshold:
        return Classification("review", best_section, best_sub, confidence, source)

    return Classification("shelf", best_section, best_sub, confidence, source)


def _classify_core(name_text: str, title_text: str, taxonomy: Taxonomy) -> Classification:
    # 1. Non-library short-circuit.
    if any(
        _keyword_matches(kw, name_text) or (title_text and _keyword_matches(kw, title_text))
        for kw in taxonomy.non_library_keywords
    ):
        return Classification("non_library", None, None, 1.0)

    # 2. Score title as primary evidence; filename remains fallback/secondary.
    title_scores = _score_text(title_text, taxonomy) if title_text else Counter()
    name_scores = _score_text(name_text, taxonomy)

    if title_scores:
        if name_scores:
            title_section = _rank_scores(title_scores)[0][0][0]
            name_section = _rank_scores(name_scores)[0][0][0]
            if title_section != name_section:
                title_cls = _classification_from_scores(title_scores, taxonomy, "metadata")
                return Classification(
                    "review",
                    title_cls.section,
                    title_cls.subcategory,
                    title_cls.confidence,
                    "metadata",
                )
            return _classification_from_scores(title_scores + name_scores, taxonomy, "metadata")
        return _classification_from_scores(title_scores, taxonomy, "metadata")

    return _classification_from_scores(name_scores, taxonomy, "rule")


def classify_name(name: str, taxonomy: Taxonomy, title: str | None = None) -> Classification:
    name_text = _strip_source_boilerplate(_normalize_match_text(name))
    title_text = _normalize_match_text(title) if title else ""

    result = _classify_core(name_text, title_text, taxonomy)
    # 3. EB-365 format-tier demotion: final check before any shelf is honored.
    return _apply_format_guard(result, name_text, title_text, taxonomy)
