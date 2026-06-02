#!/usr/bin/env python3
"""Prompt-contract regression tests for EB-353.

The local VQA grader (Qwen3-VL) emitted false-positive `major`/`critical`
"garbled OCR / extraction failure" findings on legible code, syntax-template
text, AND clean prose (e.g. Python-in-Easy-Steps p62's
`statements-to-execute-when-test-...` placeholders; ML-for-Asset-Managers p58's
legible `def formBlockMatrix(...)` snippet; and even hallucinated `cid:3`/`x2SX`
corruption on clean exercise pages scored 0). Root cause: the grader prompt's
Text Integrity rubric conflated *text legibility* (character correctness) with
*lost line/format structure* (line breaks / indentation / monospace), never
exempted code/template tokens, and never defined what genuine corruption is.

These tests cannot exercise the live VLM, so instead they assert the prompt
*contract* — the specific guardrail clauses must be present so a future edit
cannot silently delete the fix and let the false-positive mode regress. Each
assertion is anchored to a distinctive phrase (not a bare keyword that could
appear incidentally), and the load-bearing clauses (severity cap, legibility
score-band, per-region scoring, the concrete corruption literals) are pinned.

Two artifacts are checked for parity:
  * agents/qa-evaluation/system-prompt.md  (preferred, used by visual_qa.py)
  * tools/visual_qa_rubric.md              (legacy fallback)

Usage:
    python -m pytest tests/test_vqa_grader_prompt_contract.py -v
"""

from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENT_PROMPT = REPO_ROOT / "agents" / "qa-evaluation" / "system-prompt.md"
LEGACY_RUBRIC = REPO_ROOT / "tools" / "visual_qa_rubric.md"

# Codepoints referenced via chr() so this test source stays pure-ASCII (the
# EB-353 bug itself was an encoding round-trip mangling literal glyphs; we do not
# repeat that mistake in the test file).
U_FFFD = chr(0xFFFD)  # replacement character
U_LAMBDA = chr(0x03BB)  # math glyph-soup example
U_QUARTER = chr(0x00BC)  # fraction glyph example


def _load(path: Path) -> str:
    assert path.exists(), f"grader prompt artifact missing: {path}"
    return path.read_text(encoding="utf-8").lower()


def _load_raw(path: Path) -> str:
    """UTF-8 content WITHOUT lowercasing — for case/codepoint-sensitive checks."""
    assert path.exists(), f"grader prompt artifact missing: {path}"
    return path.read_text(encoding="utf-8")


class TestAgentPromptCodeFalsePositiveGuardrails(unittest.TestCase):
    """The primary grader prompt must distinguish legible text from corruption."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = _load(AGENT_PROMPT)
        cls.raw = _load_raw(AGENT_PROMPT)

    def test_defines_genuine_corruption_with_character_level_evidence(self):
        """Genuine corruption is anchored to the DEFINITION clause + concrete
        markers — not bare keywords that also appear in exemption prose."""
        self.assertIn("genuine corruption requires", self.text,
                      "Prompt must contain the positive corruption-definition clause")
        self.assertIn("character-level evidence", self.text,
                      "Definition must demand character-level evidence")
        self.assertIn("cid:", self.text,
                      "Prompt must cite (cid:N) glyph artifacts as genuine corruption evidence")
        self.assertIn("mojibake", self.text,
                      "Prompt must cite mojibake as genuine corruption evidence")
        self.assertIn("replacement character", self.text,
                      "Prompt must cite replacement characters as genuine corruption evidence")
        self.assertIn("u+fffd", self.text,
                      "Prompt must cite the U+FFFD codepoint (guards against an empty or "
                      "encoding-normalized example)")

    def test_concrete_corruption_literals_present_raw(self):
        """The actual example glyphs must survive (an ANSI/cp1252 editor save could
        silently mangle them while the ASCII labels stay green — the exact
        encoding-robustness failure mode the fix's own history warns about)."""
        self.assertIn(U_FFFD, self.raw,
                      "Prompt must contain the literal U+FFFD glyph as a concrete example")
        self.assertIn(U_LAMBDA, self.raw,
                      "Prompt must contain a literal math glyph-soup example (lambda)")
        self.assertIn(U_QUARTER, self.raw,
                      "Prompt must contain a literal fraction glyph example")

    def test_exempts_legible_code_and_template_tokens(self):
        """Legible code, identifiers, operators, and hyphenated placeholder/template
        tokens must be explicitly named as legitimate content, not OCR debris."""
        self.assertIn("source code", self.text,
                      "Prompt must exempt source code from text_integrity garble findings")
        self.assertIn("placeholder", self.text,
                      "Prompt must exempt placeholder/template tokens")
        self.assertIn("camelcase", self.text,
                      "Prompt must name code identifier styles (camelCase) as legitimate")

    def test_routes_lost_formatting_to_layout_categories_for_all_legible_text(self):
        """Lost line breaks / indentation / monospace on legible text — code,
        template, OR prose — belongs in paragraph_flow/page_layout, not
        text_integrity (the prose sub-mode: Python p180/189/192/195/198)."""
        self.assertIn("monospace", self.text,
                      "Prompt must reference lost monospace/code formatting")
        self.assertIn("paragraph_flow", self.text,
                      "Prompt must route lost formatting to paragraph_flow")
        self.assertIn("ordinary prose", self.text,
                      "Routing must cover legible PROSE that lost line structure, not only code")

    def test_severity_cap_on_legible_text(self):
        """The single most load-bearing clause: legible-but-unformatted text is
        capped at moderate and may NEVER be major/critical (this is what prevents
        the original text_integrity-MAJOR-at-score-23 failure)."""
        self.assertIn("at most **moderate**", self.text,
                      "Prompt must cap legible-but-unformatted text at moderate severity")
        self.assertIn("`major` or `critical`", self.text,
                      "Prompt must forbid major/critical severity on legible-but-unformatted text")
        self.assertIn("legible-but-unformatted text", self.text,
                      "The cap must be scoped to legible-but-unformatted TEXT (code/template/prose)")

    def test_legibility_score_band_floor(self):
        """Legible text must score in the 70-100 Text Integrity band — the
        quantitative guarantee that contradicts the BEFORE score-23 failures.
        (Anchored on the ASCII clause, not the en-dash, for robustness.)"""
        self.assertIn("legible text scores in the", self.text,
                      "Prompt must pin the legibility score-band floor")

    def test_guards_ocr_extraction_failure_assertion_on_legible_text(self):
        """The grader must not assert OCR/extraction failure when the page text is
        legible — that drives false paid-OCR (Gemini) escalation."""
        self.assertIn("legible", self.text,
                      "Prompt must use legibility as the discriminant")
        self.assertTrue(
            ("extraction failure" in self.text) or ("ocr failure" in self.text),
            "Prompt must explicitly address the OCR/extraction-failure claim",
        )
        self.assertTrue(
            ("can read" in self.text) or ("can transcribe" in self.text),
            "Prompt must instruct: if you can read/transcribe it, it is not garbled",
        )

    def test_split_words_remain_text_integrity(self):
        """Recall guard: the legibility carve-out must NOT swallow genuine
        intra-word corruption (split words / orphaned fragments stay text_integrity)."""
        self.assertIn("split words", self.text,
                      "Prompt must keep split words as a genuine Text Integrity defect")

    def test_mixed_page_independent_region_scoring(self):
        """A page may hold BOTH real corruption (math) and legible code; the
        no-bleed rule (abp06 p51) must be pinned, not just the word 'region'."""
        self.assertIn("score each region independently", self.text,
                      "Prompt must require independent per-region scoring")
        self.assertIn("must not be called", self.text,
                      "Prompt must carry the no-bleed clause (legible region not called illegible)")

    def test_pagination_guard_forbids_inventing_missing_content(self):
        """A page-break truncation must not be flagged as missing/incomplete
        content (the Python p186 'missing table description' false positive)."""
        self.assertIn("pagination", self.text)
        self.assertIn("do not invent missing", self.text,
                      "Prompt must forbid inventing missing/incomplete content from pagination")

    def test_recall_genuine_garble_remains_scoreable(self):
        """Recall guard: genuine garble must remain a low-band, high-severity
        defect — the severity vocabulary and the garbled score-band must survive."""
        self.assertIn("garbled passages", self.text,
                      "Prompt must keep the low score-band for genuine garbled text")
        self.assertIn("critical", self.text)
        self.assertIn("major", self.text)


class TestLegacyRubricParityGuardrails(unittest.TestCase):
    """The legacy fallback rubric carries the SAME guardrails (parity)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = _load(LEGACY_RUBRIC)

    def test_legacy_exempts_code_and_cites_corruption_markers(self):
        self.assertIn("source code", self.text,
                      "Legacy rubric must exempt source code from garble findings")
        self.assertIn("cid:", self.text,
                      "Legacy rubric must cite (cid:N) as genuine corruption evidence")
        self.assertIn("u+fffd", self.text,
                      "Legacy rubric must cite the U+FFFD codepoint (parity with primary)")
        self.assertIn("replacement character", self.text,
                      "Legacy rubric must cite the replacement character")
        self.assertIn("legible", self.text,
                      "Legacy rubric must use legibility as the discriminant")

    def test_legacy_routing_and_prose(self):
        self.assertIn("paragraph_flow", self.text,
                      "Legacy rubric must route lost formatting to paragraph_flow")
        self.assertIn("ordinary prose", self.text,
                      "Legacy routing must cover prose, not only code")
        self.assertIn("placeholder", self.text,
                      "Legacy rubric must exempt placeholder/template tokens")

    def test_legacy_severity_cap(self):
        """Legacy parity for the severity cap. The legacy severity scale has no
        'major' tier, so a misfile would reach for 'critical' (worse) — the
        explicit 'never critical' hard cap must be present."""
        self.assertIn("at most moderate", self.text,
                      "Legacy rubric must cap legible-text findings at moderate")
        self.assertIn("never `critical`", self.text,
                      "Legacy rubric must explicitly forbid critical severity on legible content")

    def test_legacy_pagination_guard(self):
        self.assertIn("pagination", self.text)
        self.assertIn("is not missing content", self.text,
                      "Legacy rubric must forbid treating pagination as missing content")


if __name__ == "__main__":
    unittest.main(verbosity=2)
