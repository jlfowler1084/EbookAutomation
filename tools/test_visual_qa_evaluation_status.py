# tools/test_visual_qa_evaluation_status.py
"""Unit tests for VQA report evaluation_status field (SCRUM-318).

Verifies that build_report() correctly sets evaluation_status, and that
overall_score / overall_pass are None when the API failed instead of 0 / False.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from visual_qa import build_report


class FakeProvider:
    """Minimal provider stub that satisfies build_report's estimate_cost call."""

    def estimate_cost(self, model, input_tokens, output_tokens):
        return 0.0


class TestBuildReportEvaluationStatus(unittest.TestCase):
    """Tests for SCRUM-318: evaluation_status field in VQA reports."""

    def _minimal_report(self, qa_data):
        """Call build_report with minimal required args and return the result."""
        return build_report(
            book_path="/fake/path/book.kfx",
            qa_data=qa_data,
            total_pages=100,
            pages_sampled=8,
            dpi=150,
            model="test-model",
            input_tokens=0,
            output_tokens=0,
            provider=FakeProvider(),
        )

    # ------------------------------------------------------------------
    # AC1 / AC2: api_failure path
    # ------------------------------------------------------------------

    def test_api_failure_sets_evaluation_status(self):
        """When qa_data has evaluation_status=api_failure, report must reflect it."""
        qa_data = {
            "evaluation_status": "api_failure",
            "overall_score": None,
            "overall_pass": None,
            "pages": [],
            "category_scores": {},
            "summary": "All API batches failed — no pages were evaluated.",
            "top_issues": [],
        }
        report = self._minimal_report(qa_data)
        self.assertEqual(report["evaluation_status"], "api_failure")

    def test_api_failure_overall_score_is_none(self):
        """When evaluation_status=api_failure, overall_score must be None (not 0)."""
        qa_data = {
            "evaluation_status": "api_failure",
            "overall_score": None,
            "overall_pass": None,
            "pages": [],
            "category_scores": {},
            "summary": "All API batches failed — no pages were evaluated.",
            "top_issues": [],
        }
        report = self._minimal_report(qa_data)
        self.assertIsNone(report["overall_score"])

    def test_api_failure_overall_pass_is_none(self):
        """When evaluation_status=api_failure, overall_pass must be None (not False)."""
        qa_data = {
            "evaluation_status": "api_failure",
            "overall_score": None,
            "overall_pass": None,
            "pages": [],
            "category_scores": {},
            "summary": "All API batches failed — no pages were evaluated.",
            "top_issues": [],
        }
        report = self._minimal_report(qa_data)
        self.assertIsNone(report["overall_pass"])

    # ------------------------------------------------------------------
    # AC1 / AC2: normal evaluated path
    # ------------------------------------------------------------------

    def test_evaluated_status_is_evaluated(self):
        """When qa_data has evaluation_status=evaluated, report must reflect it."""
        qa_data = {
            "evaluation_status": "evaluated",
            "overall_score": 85,
            "overall_pass": True,
            "pages": [{"page_number": 1, "score": 85, "issues": []}],
            "category_scores": {"headings": 90},
            "summary": "Evaluated 1 page.",
            "top_issues": [],
        }
        report = self._minimal_report(qa_data)
        self.assertEqual(report["evaluation_status"], "evaluated")

    def test_evaluated_overall_score_is_integer(self):
        """When evaluation_status=evaluated, overall_score must be an integer."""
        qa_data = {
            "evaluation_status": "evaluated",
            "overall_score": 85,
            "overall_pass": True,
            "pages": [{"page_number": 1, "score": 85, "issues": []}],
            "category_scores": {},
            "summary": "Evaluated 1 page.",
            "top_issues": [],
        }
        report = self._minimal_report(qa_data)
        self.assertIsInstance(report["overall_score"], int)
        self.assertEqual(report["overall_score"], 85)

    def test_evaluated_overall_pass_reflects_threshold(self):
        """overall_pass should be True/False (not None) when status=evaluated."""
        qa_data = {
            "evaluation_status": "evaluated",
            "overall_score": 85,
            "overall_pass": True,
            "pages": [],
            "category_scores": {},
            "summary": "Evaluated 1 page.",
            "top_issues": [],
        }
        report = self._minimal_report(qa_data)
        self.assertIsNotNone(report["overall_pass"])
        self.assertIsInstance(report["overall_pass"], bool)
        # Default pass_threshold is 70 — score 85 should pass
        self.assertTrue(report["overall_pass"])

    def test_evaluated_low_score_fails(self):
        """A low score with status=evaluated yields overall_pass=False (not None)."""
        qa_data = {
            "evaluation_status": "evaluated",
            "overall_score": 40,
            "overall_pass": False,
            "pages": [],
            "category_scores": {},
            "summary": "Evaluated 1 page.",
            "top_issues": [],
        }
        report = self._minimal_report(qa_data)
        self.assertEqual(report["evaluation_status"], "evaluated")
        self.assertEqual(report["overall_score"], 40)
        self.assertFalse(report["overall_pass"])

    # ------------------------------------------------------------------
    # Legacy path: no evaluation_status key defaults to "evaluated"
    # ------------------------------------------------------------------

    def test_no_evaluation_status_key_defaults_to_evaluated(self):
        """qa_data without an evaluation_status key defaults to evaluated behaviour."""
        qa_data = {
            "overall_score": 75,
            "pages": [],
            "category_scores": {},
            "summary": "Old-format report.",
            "top_issues": [],
        }
        report = self._minimal_report(qa_data)
        self.assertEqual(report["evaluation_status"], "evaluated")
        self.assertEqual(report["overall_score"], 75)
        self.assertIsNotNone(report["overall_pass"])


class TestBuildReportCoverageAccounting(unittest.TestCase):
    """EB-340 F1: requested-vs-effective coverage fields in build_report."""

    def _report(self, qa_data, **overrides):
        kwargs = dict(
            book_path="/fake/path/book.kfx",
            qa_data=qa_data,
            total_pages=600,
            pages_sampled=2,
            dpi=72,
            model="test-model",
            input_tokens=0,
            output_tokens=0,
            provider=FakeProvider(),
        )
        kwargs.update(overrides)
        return build_report(**kwargs)

    @staticmethod
    def _evaluated_qa(n_pages):
        return {
            "evaluation_status": "evaluated",
            "overall_score": 90,
            "pages": [{"page_number": i + 1, "score": 90, "issues": []}
                      for i in range(n_pages)],
            "category_scores": {},
            "summary": f"Evaluated {n_pages} pages.",
            "top_issues": [],
        }

    def test_explicit_flags_report_complete_with_honored_dpi(self):
        """Requested == effective (explicit-flag run) -> complete, fields equal."""
        report = self._report(
            self._evaluated_qa(40), total_pages=600, pages_sampled=40, dpi=150,
            pages_requested=40, requested_dpi=150, effective_dpi=150,
            coverage_reason=None,
        )
        self.assertEqual(report["pages_requested"], 40)
        self.assertEqual(report["requested_dpi"], 150)
        self.assertEqual(report["effective_dpi"], 150)
        self.assertIsNone(report["coverage_reason"])
        self.assertEqual(report["coverage_status"], "complete")

    def test_default_reduction_marks_partial_with_reason(self):
        """A default large-file reduction -> partial + reason, effective < requested."""
        report = self._report(
            self._evaluated_qa(4), total_pages=900, pages_sampled=4, dpi=72,
            pages_requested=50, requested_dpi=150, effective_dpi=72,
            coverage_reason="large_file_default_reduction",
        )
        self.assertEqual(report["requested_dpi"], 150)
        self.assertEqual(report["effective_dpi"], 72)
        self.assertLess(report["effective_dpi"], report["requested_dpi"])
        self.assertEqual(report["pages_requested"], 50)
        self.assertEqual(report["coverage_reason"], "large_file_default_reduction")
        self.assertEqual(report["coverage_status"], "partial")

    def test_legacy_call_defaults_are_sensible(self):
        """Legacy callers (no coverage kwargs) get non-null, self-consistent fields."""
        report = self._report(self._evaluated_qa(2), pages_sampled=2, dpi=150)
        self.assertIn("pages_requested", report)
        self.assertEqual(report["requested_dpi"], 150)
        self.assertEqual(report["effective_dpi"], 150)
        self.assertEqual(report["pages_requested"], 2)
        self.assertIsNone(report["coverage_reason"])
        self.assertEqual(report["coverage_status"], "complete")


if __name__ == "__main__":
    unittest.main()
