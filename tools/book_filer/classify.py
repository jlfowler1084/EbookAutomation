"""Deterministic filename classifier (spec §7 deterministic-first pass).

Disposition is one of:
- "non_library": a non-book file (resume, tax form, ...) — never shelved.
- "shelf": a confident (section, subcategory) match at/above the threshold.
- "review": no match or a low-confidence/tie — routed to _Needs_Review.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .taxonomy import Taxonomy


@dataclass(frozen=True)
class Classification:
    disposition: str                 # "shelf" | "review" | "non_library"
    section: str | None
    subcategory: str | None
    confidence: float
    source: str = "rule"


def classify_name(name: str, taxonomy: Taxonomy) -> Classification:
    text = name.lower()

    # 1. Non-library short-circuit.
    if any(kw in text for kw in taxonomy.non_library_keywords):
        return Classification("non_library", None, None, 1.0)

    # 2. Score every (section, subcategory) by distinct keyword hits.
    scores: Counter[tuple[str, str]] = Counter()
    for keyword, targets in taxonomy._index.items():
        if keyword in text:
            for target in targets:
                scores[target] += 1

    if not scores:
        return Classification("review", None, None, 0.0)

    ranked = scores.most_common()
    (best_section, best_sub), best_hits = ranked[0]
    runner_hits = ranked[1][1] if len(ranked) > 1 else 0

    total = sum(scores.values())
    confidence = best_hits / total  # share of hits the winner owns; 1.0 == unambiguous

    # 3. A genuine tie across different sections is ambiguous -> review.
    tie = runner_hits == best_hits and ranked[1][0][0] != best_section
    if tie or confidence < taxonomy.confidence_threshold:
        return Classification("review", best_section, best_sub, confidence)

    return Classification("shelf", best_section, best_sub, confidence)
