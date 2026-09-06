#!/usr/bin/env python3
"""Tests for the EB-361 VQA grader determinism self-check.

EB-361: the local VQA grader is not bit-deterministic under concurrent node
load (batch-invariance failure on the shared llama.cpp Vulkan node). The fix
direction approved for this ticket is a *self-check guard*, not a cure: run the
same input twice and refuse to trust the scores unless the two runs agree
per-page. This encodes the global calibration rule ("run twice on the same
input; if results differ, the metric is non-deterministic; fix before using").

These tests pin two layers:
  1. ``compare_reports`` -- the pure comparator over two VQA report dicts. This
     is the gate: per-page score delta within ``tolerance`` (default strict 0,
     EB-361 requirement), plus page-set parity. Issue-set drift is surfaced as a
     secondary diagnostic but does NOT fail the score gate.
  2. ``run_determinism_check`` -- thin orchestration that invokes an injected
     ``runner`` N times and compares run 0 against each later run. Dependency
     injection keeps the live-node path out of the unit tests entirely.

All tests are hermetic: no live node, no API keys, no Calibre.

Usage:
    python -m pytest tests/test_vqa_determinism_check.py -v
"""

from __future__ import annotations

import sys
import unittest
import unittest.mock
from pathlib import Path

# Ensure tools/ is importable (mirrors tests/test_vqa_grader_calibration.py).
TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import vqa_determinism_check as dc  # noqa: E402
from llm_providers.local_provider import LocalVisionProvider  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _issue(category: str, severity: str = "major") -> dict:
    return {
        "category": category,
        "severity": severity,
        "description": "x",
        "suggestion": "y",
    }


def _page(page_number: int, score: int, issues: list[dict] | None = None) -> dict:
    return {
        "page_number": page_number,
        "page_type": "body",
        "score": score,
        "pass": score >= 70,
        "issues": issues or [],
    }


def _report(pages: list[dict], overall: int | None = None,
            status: str = "evaluated") -> dict:
    return {
        "evaluation_status": status,
        "overall_score": overall,
        "pages": pages,
    }


# ---------------------------------------------------------------------------
# compare_reports -- score gate
# ---------------------------------------------------------------------------

class TestCompareReportsScoreGate(unittest.TestCase):
    """Per-page score delta is the gate (EB-361: 0/50 per-page diffs)."""

    def test_identical_reports_are_deterministic(self):
        a = _report([_page(1, 100), _page(2, 85)], overall=92)
        b = _report([_page(1, 100), _page(2, 85)], overall=92)
        v = dc.compare_reports(a, b)
        self.assertTrue(v.deterministic)
        self.assertEqual(v.n_score_diffs, 0)
        self.assertEqual(v.max_abs_delta, 0)
        self.assertEqual(v.pages_compared, 2)
        self.assertEqual(v.page_deltas, [], "no differing pages → empty delta list")

    def test_single_page_score_diff_is_nondeterministic(self):
        # Mirrors EB-361's p38 90→70 observation.
        a = _report([_page(1, 100), _page(38, 90)], overall=95)
        b = _report([_page(1, 100), _page(38, 70)], overall=85)
        v = dc.compare_reports(a, b)
        self.assertFalse(v.deterministic)
        self.assertEqual(v.n_score_diffs, 1)
        self.assertEqual(v.max_abs_delta, 20)
        diffs = {d.page_number: d for d in v.page_deltas}
        self.assertIn(38, diffs)
        self.assertEqual(diffs[38].abs_delta, 20)
        self.assertTrue(diffs[38].score_differs)

    def test_default_tolerance_is_strict_zero(self):
        # EB-361 user decision: a single point of drift must fail.
        a = _report([_page(1, 86)], overall=86)
        b = _report([_page(1, 85)], overall=85)
        v = dc.compare_reports(a, b)
        self.assertFalse(v.deterministic, "1-point delta must fail the strict-0 gate")
        self.assertEqual(v.max_abs_delta, 1)
        self.assertEqual(v.n_score_diffs, 1)

    def test_tolerance_band_passes_within_and_fails_beyond(self):
        a = _report([_page(1, 90), _page(2, 90)])
        b = _report([_page(1, 88), _page(2, 87)])  # deltas: 2 and 3
        v2 = dc.compare_reports(a, b, tolerance=2)
        self.assertFalse(v2.deterministic, "page 2 delta 3 exceeds tolerance 2")
        self.assertEqual(v2.n_score_diffs, 1)
        v3 = dc.compare_reports(a, b, tolerance=3)
        self.assertTrue(v3.deterministic, "both deltas within tolerance 3")
        self.assertEqual(v3.n_score_diffs, 0)

    def test_overall_delta_reported(self):
        # Mirrors EB-361's 86→75 spread.
        a = _report([_page(1, 86)], overall=86)
        b = _report([_page(1, 75)], overall=75)
        v = dc.compare_reports(a, b)
        self.assertEqual(v.overall_score_a, 86)
        self.assertEqual(v.overall_score_b, 75)
        self.assertEqual(v.overall_abs_delta, 11)


# ---------------------------------------------------------------------------
# compare_reports -- page-set parity
# ---------------------------------------------------------------------------

class TestCompareReportsPageParity(unittest.TestCase):
    """A page present in one run but not the other is itself non-determinism."""

    def test_missing_page_in_one_run_is_nondeterministic(self):
        a = _report([_page(1, 100), _page(2, 90)])
        b = _report([_page(1, 100)])  # page 2 dropped (e.g. one run's batch failed)
        v = dc.compare_reports(a, b)
        self.assertFalse(v.deterministic)
        self.assertIn(2, v.missing_pages)
        diffs = {d.page_number: d for d in v.page_deltas}
        self.assertIn(2, diffs)
        self.assertEqual(diffs[2].missing_in, "b")
        self.assertIsNone(diffs[2].abs_delta)


# ---------------------------------------------------------------------------
# compare_reports -- issue drift (secondary signal, non-gating)
# ---------------------------------------------------------------------------

class TestCompareReportsIssueDrift(unittest.TestCase):
    """Issue-set drift is surfaced but does not fail the score gate."""

    def test_issue_drift_surfaced_but_does_not_fail_score_gate(self):
        # Both pages score 75 (one major = -25), but the category differs.
        a = _report([_page(1, 75, [_issue("text_integrity", "major")])])
        b = _report([_page(1, 75, [_issue("paragraph_flow", "major")])])
        v = dc.compare_reports(a, b)
        self.assertTrue(v.deterministic, "score gate passes when per-page scores match")
        self.assertEqual(v.n_issue_drift_pages, 1)
        diffs = {d.page_number: d for d in v.page_deltas}
        self.assertIn(1, diffs)
        self.assertTrue(diffs[1].issues_differ)
        self.assertFalse(diffs[1].score_differs)

    def test_identical_issues_no_drift(self):
        a = _report([_page(1, 75, [_issue("text_integrity", "major")])])
        b = _report([_page(1, 75, [_issue("text_integrity", "major")])])
        v = dc.compare_reports(a, b)
        self.assertTrue(v.deterministic)
        self.assertEqual(v.n_issue_drift_pages, 0)
        self.assertEqual(v.page_deltas, [])


# ---------------------------------------------------------------------------
# compare_reports -- error handling
# ---------------------------------------------------------------------------

class TestCompareReportsErrors(unittest.TestCase):
    """A failed/empty run cannot be assessed for determinism -- raise loudly."""

    def test_empty_pages_raises(self):
        a = _report([], overall=None, status="api_failure")
        b = _report([_page(1, 100)])
        with self.assertRaises(ValueError):
            dc.compare_reports(a, b)

    def test_non_evaluated_status_raises(self):
        a = _report([_page(1, 100)], status="api_failure")
        b = _report([_page(1, 100)])
        with self.assertRaises(ValueError):
            dc.compare_reports(a, b)


# ---------------------------------------------------------------------------
# compare_reports -- evaluated_degraded is evaluable (EB-392 review: adversarial
# finding -- a transient n_ctx-probe hiccup must not cascade into "could not
# reach the provider" for the whole harness run)
# ---------------------------------------------------------------------------

class TestEvaluatedDegradedIsEvaluable(unittest.TestCase):
    def test_evaluated_degraded_report_passes_require_evaluable(self):
        # Must not raise -- a real, scored report with pages, just graded
        # under an unconfirmed context window.
        dc._require_evaluable(_report([_page(1, 100)], status="evaluated_degraded"), "a")

    def test_both_evaluated_degraded_compares_normally_and_is_deterministic(self):
        a = _report([_page(1, 100)], overall=100, status="evaluated_degraded")
        b = _report([_page(1, 100)], overall=100, status="evaluated_degraded")
        v = dc.compare_reports(a, b)
        self.assertTrue(v.deterministic)
        self.assertTrue(v.degraded)

    def test_one_side_evaluated_degraded_still_sets_degraded_flag(self):
        a = _report([_page(1, 100)], overall=100, status="evaluated")
        b = _report([_page(1, 100)], overall=100, status="evaluated_degraded")
        v = dc.compare_reports(a, b)
        self.assertTrue(v.deterministic)
        self.assertTrue(v.degraded)

    def test_fully_evaluated_reports_are_not_flagged_degraded(self):
        a = _report([_page(1, 100)], overall=100, status="evaluated")
        b = _report([_page(1, 100)], overall=100, status="evaluated")
        v = dc.compare_reports(a, b)
        self.assertFalse(v.degraded)

    def test_still_evaluated_status_other_than_evaluated_or_degraded_raises(self):
        a = _report([_page(1, 100)], status="api_failure")
        b = _report([_page(1, 100)], status="evaluated_degraded")
        with self.assertRaises(ValueError):
            dc.compare_reports(a, b)


# ---------------------------------------------------------------------------
# run_determinism_check -- orchestration via injected runner
# ---------------------------------------------------------------------------

class TestRunDeterminismCheck(unittest.TestCase):
    """Run the injected runner N times; compare run 0 against each later run."""

    def test_runs_runner_n_times_and_reports_deterministic(self):
        calls: list[int] = []

        def runner(i: int) -> dict:
            calls.append(i)
            return _report([_page(1, 100), _page(2, 90)], overall=95)

        v = dc.run_determinism_check(runner, runs=2)
        self.assertEqual(calls, [0, 1], "runner must be called once per run, in order")
        self.assertTrue(v.deterministic)

    def test_detects_nondeterminism_across_runs(self):
        reports = [
            _report([_page(1, 100), _page(38, 90)], overall=95),
            _report([_page(1, 100), _page(38, 70)], overall=85),
        ]
        v = dc.run_determinism_check(lambda i: reports[i], runs=2)
        self.assertFalse(v.deterministic)
        self.assertEqual(v.max_abs_delta, 20)

    def test_three_runs_flags_if_any_pair_differs(self):
        reports = [
            _report([_page(1, 100)]),
            _report([_page(1, 100)]),
            _report([_page(1, 80)]),  # third run diverges from run 0
        ]
        v = dc.run_determinism_check(lambda i: reports[i], runs=3)
        self.assertFalse(v.deterministic)
        self.assertEqual(v.max_abs_delta, 20)

    def test_runs_must_be_at_least_two(self):
        with self.assertRaises(ValueError):
            dc.run_determinism_check(lambda i: _report([_page(1, 100)]), runs=1)


# ---------------------------------------------------------------------------
# verdict_to_exit_code -- CLI gate mapping
# ---------------------------------------------------------------------------

class TestVerdictToExitCode(unittest.TestCase):
    """0 = deterministic, 1 = non-deterministic. Infra errors map to 2 in main()."""

    def test_deterministic_maps_to_zero(self):
        a = _report([_page(1, 100)])
        b = _report([_page(1, 100)])
        self.assertEqual(dc.verdict_to_exit_code(dc.compare_reports(a, b)), 0)

    def test_nondeterministic_maps_to_one(self):
        a = _report([_page(1, 100)])
        b = _report([_page(1, 70)])
        self.assertEqual(dc.verdict_to_exit_code(dc.compare_reports(a, b)), 1)


# ---------------------------------------------------------------------------
# EB-392 Unit 2: provider/server drift detection between runs
# ---------------------------------------------------------------------------

class TestProviderDriftDetection(unittest.TestCase):
    """run_determinism_check must surface each run's provider_resolved block
    and refuse to compare scores (could_not_assess, exit 2) when the resolved
    server identity changed between runs -- a server change mid-check makes
    any score delta meaningless, not a determinism finding.
    """

    def test_provider_resolved_surfaced_for_each_run(self):
        pr = {
            "provider": "local", "base_url": "http://x.test/v1", "n_ctx": 32768,
            "n_ctx_source": "models", "total_slots": 1, "model_path": None,
            "probe_ok": True,
        }
        reports = [
            {**_report([_page(1, 100)], overall=100), "provider_resolved": dict(pr)},
            {**_report([_page(1, 100)], overall=100), "provider_resolved": dict(pr)},
        ]
        v = dc.run_determinism_check(lambda i: reports[i], runs=2)
        self.assertEqual(v.provider_resolved_runs, [pr, pr])
        self.assertFalse(v.could_not_assess)
        self.assertIsNone(v.could_not_assess_reason)
        self.assertTrue(v.deterministic)
        self.assertEqual(dc.verdict_to_exit_code(v), 0)

    def test_missing_provider_resolved_does_not_break_score_comparison(self):
        """Older/legacy reports (or a runner not yet emitting provider_resolved)
        must not be treated as drift -- an absent block on both sides means
        "nothing to compare", not "different"."""
        reports = [
            _report([_page(1, 100)], overall=100),
            _report([_page(1, 100)], overall=100),
        ]
        v = dc.run_determinism_check(lambda i: reports[i], runs=2)
        self.assertEqual(v.provider_resolved_runs, [{}, {}])
        self.assertFalse(v.could_not_assess)
        self.assertTrue(v.deterministic)

    def test_n_ctx_drift_between_runs_yields_could_not_assess_exit_2(self):
        reports = [
            {**_report([_page(1, 100)], overall=100),
             "provider_resolved": {"base_url": "http://x.test/v1", "n_ctx": 32768,
                                    "total_slots": 1, "model_path": None}},
            {**_report([_page(1, 100)], overall=100),
             "provider_resolved": {"base_url": "http://x.test/v1", "n_ctx": 8192,
                                    "total_slots": 1, "model_path": None}},
        ]
        v = dc.run_determinism_check(lambda i: reports[i], runs=2)
        self.assertTrue(v.could_not_assess)
        self.assertIn("n_ctx", v.could_not_assess_reason)
        self.assertEqual(dc.verdict_to_exit_code(v), 2)

    def test_base_url_drift_between_runs_yields_could_not_assess_exit_2(self):
        reports = [
            {**_report([_page(1, 100)], overall=100),
             "provider_resolved": {"base_url": "http://a.test/v1", "n_ctx": 32768,
                                    "total_slots": 1, "model_path": None}},
            {**_report([_page(1, 100)], overall=100),
             "provider_resolved": {"base_url": "http://b.test/v1", "n_ctx": 32768,
                                    "total_slots": 1, "model_path": None}},
        ]
        v = dc.run_determinism_check(lambda i: reports[i], runs=2)
        self.assertTrue(v.could_not_assess)
        self.assertIn("base_url", v.could_not_assess_reason)
        self.assertEqual(dc.verdict_to_exit_code(v), 2)

    def test_model_path_true_mismatch_both_non_null_yields_could_not_assess_exit_2(self):
        """The actual mismatch-detected branch (both sides non-null, differing)
        -- previously untested; only the None-skip case was covered."""
        reports = [
            {**_report([_page(1, 100)], overall=100),
             "provider_resolved": {"base_url": "http://x.test/v1", "n_ctx": 32768,
                                    "total_slots": 1, "model_path": "/models/a.gguf"}},
            {**_report([_page(1, 100)], overall=100),
             "provider_resolved": {"base_url": "http://x.test/v1", "n_ctx": 32768,
                                    "total_slots": 1, "model_path": "/models/b.gguf"}},
        ]
        v = dc.run_determinism_check(lambda i: reports[i], runs=2)
        self.assertTrue(v.could_not_assess)
        self.assertIn("model_path", v.could_not_assess_reason)
        self.assertEqual(dc.verdict_to_exit_code(v), 2)

    def test_model_served_drift_both_non_null_yields_could_not_assess_exit_2(self):
        reports = [
            {**_report([_page(1, 100)], overall=100),
             "provider_resolved": {"base_url": "http://x.test/v1", "n_ctx": 32768,
                                    "total_slots": 1, "model_path": None, "model_served": "sb-vision"}},
            {**_report([_page(1, 100)], overall=100),
             "provider_resolved": {"base_url": "http://x.test/v1", "n_ctx": 32768,
                                    "total_slots": 1, "model_path": None, "model_served": "sb-vision-2"}},
        ]
        v = dc.run_determinism_check(lambda i: reports[i], runs=2)
        self.assertTrue(v.could_not_assess)
        self.assertIn("model_served", v.could_not_assess_reason)
        self.assertEqual(dc.verdict_to_exit_code(v), 2)

    def test_model_served_drift_ignored_when_either_run_is_null(self):
        reports = [
            {**_report([_page(1, 100)], overall=100),
             "provider_resolved": {"base_url": "http://x.test/v1", "n_ctx": 32768,
                                    "total_slots": 1, "model_path": None, "model_served": "sb-vision"}},
            {**_report([_page(1, 100)], overall=100),
             "provider_resolved": {"base_url": "http://x.test/v1", "n_ctx": 32768,
                                    "total_slots": 1, "model_path": None, "model_served": None}},
        ]
        v = dc.run_determinism_check(lambda i: reports[i], runs=2)
        self.assertFalse(v.could_not_assess)
        self.assertTrue(v.deterministic)

    def test_model_path_drift_ignored_when_either_run_is_null(self):
        """model_path is compared only when BOTH runs expose a non-null
        value -- a server without a reachable /props must not be flagged as
        drifted just because one run happens to know the path and the other
        doesn't."""
        reports = [
            {**_report([_page(1, 100)], overall=100),
             "provider_resolved": {"base_url": "http://x.test/v1", "n_ctx": 32768,
                                    "total_slots": 1, "model_path": "/models/a.gguf"}},
            {**_report([_page(1, 100)], overall=100),
             "provider_resolved": {"base_url": "http://x.test/v1", "n_ctx": 32768,
                                    "total_slots": 1, "model_path": None}},
        ]
        v = dc.run_determinism_check(lambda i: reports[i], runs=2)
        self.assertFalse(v.could_not_assess)
        self.assertTrue(v.deterministic)

    def test_probe_n_ctx_drift_between_fresh_constructions_yields_could_not_assess(self):
        """A probe stub returning n_ctx=32768 on the first LocalVisionProvider
        construction and n_ctx=8192 on the second -- mirroring
        build_vqa_runner's Unit 2 fresh-provider-per-run contract (each
        construction re-triggers the probe) -- must surface as
        could_not_assess, naming n_ctx, exit 2.
        """
        n_ctx_values = iter([32768, 8192])

        def flaky_probe(base_url: str, model: str | None, timeout: float = 5.0) -> dict:
            return {
                "n_ctx": next(n_ctx_values), "n_ctx_source": "models",
                "n_ctx_train": None, "model_served": "sb-vision",
                "models_listed": ["sb-vision"], "server_type": "llamacpp",
                "total_slots": 1, "model_path": None, "build_info": None,
                "probe_ok": True,
            }

        def runner(i: int) -> dict:
            # Fresh construction per call -- exactly what build_vqa_runner's
            # runner() closure does for provider_name == "local" since Unit 2.
            provider = LocalVisionProvider(base_url="http://x.test/v1", probe=flaky_probe)
            report = _report([_page(1, 100)], overall=100)
            report["provider_resolved"] = provider.describe()
            return report

        v = dc.run_determinism_check(runner, runs=2)
        self.assertTrue(v.could_not_assess)
        self.assertIn("n_ctx", v.could_not_assess_reason)
        self.assertEqual(dc.verdict_to_exit_code(v), 2)


# ---------------------------------------------------------------------------
# main() -- post-verdict remediation text must match the actual failure mode
# (cli-readiness review: exit 2 for could_not_assess/drift was reusing the
# NON-DETERMINISTIC single-slot-quiesce advice, which fixes nothing for a
# server/model identity change between the two internal runs)
# ---------------------------------------------------------------------------

class TestMainRemediationText(unittest.TestCase):
    def test_could_not_assess_exit_prints_drift_reason_not_quiesce_advice(self):
        reports = [
            {**_report([_page(1, 100)], overall=100),
             "provider_resolved": {"base_url": "http://a.test/v1", "n_ctx": 32768,
                                    "total_slots": 1, "model_path": None}},
            {**_report([_page(1, 100)], overall=100),
             "provider_resolved": {"base_url": "http://b.test/v1", "n_ctx": 32768,
                                    "total_slots": 1, "model_path": None}},
        ]

        def fake_build_vqa_runner(*args, **kwargs):
            return lambda i: reports[i]

        with unittest.mock.patch.object(dc, "build_vqa_runner", fake_build_vqa_runner):
            with self.assertLogs("vqa_determinism_check", level="WARNING") as cm:
                code = dc.main(["--input", "fake.kfx", "--json"])

        self.assertEqual(code, 2)
        joined = "\n".join(cm.output)
        self.assertIn("COULD NOT BE ASSESSED", joined)
        self.assertIn("base_url", joined)
        self.assertNotIn("Quiesce the node", joined)

    def test_nondeterministic_exit_still_prints_quiesce_advice(self):
        reports = [
            _report([_page(1, 100)], overall=100),
            _report([_page(1, 70)], overall=70),
        ]

        def fake_build_vqa_runner(*args, **kwargs):
            return lambda i: reports[i]

        with unittest.mock.patch.object(dc, "build_vqa_runner", fake_build_vqa_runner):
            with self.assertLogs("vqa_determinism_check", level="WARNING") as cm:
                code = dc.main(["--input", "fake.kfx", "--json"])

        self.assertEqual(code, 1)
        joined = "\n".join(cm.output)
        self.assertIn("NON-DETERMINISTIC", joined)
        self.assertIn("Quiesce the node", joined)


if __name__ == "__main__":
    unittest.main(verbosity=2)
