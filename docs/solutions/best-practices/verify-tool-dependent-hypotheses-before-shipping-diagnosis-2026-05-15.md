---
title: Verify tool-dependent hypotheses with the alternative measurement before shipping a diagnosis
date: 2026-05-15
category: best-practices
module: workflow
problem_type: best_practice
component: tooling
severity: medium
applies_when:
  - A parallel-hypothesis investigation (e.g., the `hunt` skill, multi-agent disconfirmation pattern) is reporting a HIGH-confidence verdict
  - The leading hypothesis claims that an observed value is a measurement-tool artifact (projection, simulation, throttle model, transformation)
  - The cheap counter-measurement (alternative tool method, raw underlying data, second tool instance) has not yet been run
  - Multiple parallel agents return converging verdicts but none ran the verifying measurement
tags: [investigation, hypothesis-driven, parallel-agents, hunt, measurement, calibration, premise-testing]
related_decisions:
  - EB-249 (closed 2026-05-15 — original Phase 1 diagnosis falsified within 75 min)
  - docs/solutions/eb249-ttfb-diagnosis-2026-05-15.md
  - docs/solutions/best-practices/test-baseline-before-investing-in-tooling-2026-05-15.md
---

# Verify tool-dependent hypotheses with the alternative measurement before shipping a diagnosis

## Context

EB-249 Phase 1 was a `hunt`-style parallel investigation: four read-only agents dispatched concurrently, one per hypothesis listed in the ticket (Lighthouse Lantern projection artifact, RSC server overhead, Cloudflare-Vercel relay, render-blocking CSS). Each agent ran 30–90 seconds, returned a verdict + confidence, and surfaced evidence. Three of the four came back UNLIKELY-HIGH; the remaining one (H1: "the 2.4s TTFB is a Lantern projection artifact") came back LIKELY-HIGH.

That convergence felt robust — three falsifications + one converging confirmation, all at high confidence. The Phase 1 diagnosis doc was committed to master, the Jira ticket got an authoritative comment, and closure was proposed as "methodology corrected; infrastructure healthy."

The leading hypothesis, however, depended on a property of the measurement tool: it claimed Lighthouse's `simulate` (Lantern) throttling method was inflating TTFB relative to what `devtools` (real Chrome network emulation) would report. **That claim was never tested.** No agent ran `lighthouse --throttling-method=devtools`. The agents triangulated the *implications* of the hypothesis (curl is fast, server is fast, infra is healthy) but the underlying property was inferred from prior knowledge of how Lantern works, not measured.

Seventy-five minutes later, a single local Lighthouse run with `--throttling-method=devtools` returned the identical ~2.4s TTFB as `simulate`. The hypothesis collapsed. The diagnosis had to be revised, the EB-233 close-out doc had to be updated, a second Jira comment had to be posted correcting the first, and a feedback memory had to be saved so the conflation didn't recur.

The root cause of the wasted cycle: **strong parallel-agent convergence felt like ground truth, but the verifying measurement was cheap and had not been run.**

## Guidance

When a hypothesis-driven investigation reports a HIGH-confidence verdict and the leading hypothesis depends on a property of the measurement tool (projection, throttling model, simulation layer, transformation pass), run the alternative measurement BEFORE writing the diagnosis. The verification cost is almost always smaller than the cost of revising a shipped diagnosis.

The check sequence:

1. **Identify whether the hypothesis is tool-dependent.** A hypothesis is tool-dependent when its truth conditions reference the measurement tool itself, not the underlying system. Examples:
   - "Lighthouse Lantern projection inflates TTFB" — *Lantern is a property of Lighthouse, not the website.*
   - "The static analyzer is reporting a false positive" — *false positives are a property of the analyzer, not the code.*
   - "The benchmark is measurement noise, not a real regression" — *noise is a property of the benchmark harness, not the code under test.*

   If the hypothesis can be falsified by switching tool modes or running a parallel tool, it is tool-dependent.

2. **Find the cheap counter-measurement.** For most tool-dependent hypotheses there is a one-command verification: an alternative mode (`--throttling-method=devtools`), a different tool implementation (clang-tidy vs gcc, jest vs vitest), or raw underlying data (curl timing, kernel trace, profiler output).

3. **Run the verification before declaring confidence.** If the verifying measurement isn't run, do not report the verdict at HIGH confidence. Report it at MEDIUM with an explicit "verifying measurement not run" caveat, or downgrade to LIKELY-pending-verification.

4. **Treat parallel-agent convergence as suggestive, not confirmatory, until the verifying measurement lands.** Three agents disconfirming alternative hypotheses doesn't prove the remaining hypothesis is correct — they prove the others are wrong. The leading hypothesis still needs its own direct test.

## Why this matters

**The asymmetry of costs.** Running the verifying measurement typically takes 1–10 minutes (one CLI command, one alternative tool invocation). Revising a shipped diagnosis takes much longer: doc rewrites, Jira corrections, downstream-doc updates, and the credibility cost of "I was confident; I was wrong." In EB-249, the verification cost ~60 seconds; the correction cost ~30 minutes of doc work plus a permanent record in two Jira comments and three doc updates.

**Parallel-agent investigation amplifies premature confidence.** The `hunt` pattern is structurally biased toward seeming robust — multiple independent perspectives, explicit confidence labels, structured evidence tables. When agents converge it *feels* like evidence. But agents share the same input (the ticket), often the same priors (well-known tool behaviors), and the same blind spots. Convergence can be an artifact of common priors, not independent confirmation.

**Tool-dependent claims are uniquely cheap to falsify.** Unlike most hypotheses (where verification requires deploying a fix or observing real-world behavior), tool-dependent claims can be tested by switching the tool's mode. Lighthouse has `--throttling-method`. Linters have `--rule-set`. Benchmarks have multiple harnesses. The verification is one command away. There is rarely a good reason to ship without running it.

## When to apply

- Any `hunt` or parallel-hypothesis investigation where the leading hypothesis includes the words "artifact," "projection," "simulated," "modeled," "false positive," or "measurement bug."
- Any perf investigation that uses Lighthouse, WebPageTest, k6, or similar tools that have multiple throttling/measurement modes — always run at least two modes before reporting which one is "right."
- Any flake-vs-real-failure investigation in CI — run the test under a different harness (single-threaded, different runner, different platform) before declaring "it's a flake."
- Any "the tool is wrong" claim before opening an issue against the tool's project — verify with a second tool first.

## Examples

### Bad (the EB-249 morning Phase 1 pattern)

```
H1: TTFB ~2.4s is a Lantern projection artifact
  Evidence: real-network curl shows ~80ms TTFB (10–30× gap vs Lighthouse)
  Reasoning: Lantern is known to apply RTT/throughput multipliers; a 20× gap
             on a CDN-fronted origin is the signature of Lantern inflation.
  Verifying measurement: --throttling-method=devtools — NOT RUN
  Verdict: LIKELY-HIGH
```

Curl-from-desktop and Lighthouse-mobile-slow-4G measure different scenarios entirely (unthrottled WAN vs throttled mobile network model). The "20× gap" is not the signature of Lantern inflation; it's the signature of an unthrottled measurement compared to a throttled one. The agent inferred Lantern as the cause from prior knowledge of how Lantern *can* inflate, not from direct evidence that it *did* in this case.

### Good (what should have happened)

```
H1: TTFB ~2.4s is a Lantern projection artifact
  Evidence: real-network curl shows ~80ms TTFB
  Reasoning: candidate hypothesis — Lantern can inflate TTFB on CDN origins
  Verifying measurement: --throttling-method=devtools — pending
  Verdict: PENDING — run devtools throttling before declaring
```

Then run the verification. Two outcomes:

- **devtools shows ~80ms TTFB:** H1 confirmed. Lantern is the culprit. Diagnosis: "methodology adjustment recommended."
- **devtools shows ~2.4s TTFB (what actually happened):** H1 falsified. The 2.4s is real for the modeled throttle network. Diagnosis pivots toward "throttle models a network the page can't escape; either accept the target as unachievable or change the measurement methodology."

The pivot from one to the other is *exactly* the kind of diagnosis revision the morning Phase 1 doc had to make in commit `be215a5`. Running the verifying measurement in Phase 1 itself would have produced the correct diagnosis the first time.

## Counter-cases (when shipping without verification is acceptable)

This guidance is not absolute. Ship without the verifying measurement when:

- **The verifying measurement is unavailable in the session.** PSI/CrUX API quota was 0 in the EB-249 afternoon. Pulling CrUX field data was genuinely blocked. In that case, document the gap explicitly ("verifying measurement X not available; relying on inference from Y") and downgrade confidence accordingly. Don't claim HIGH confidence and hope no one runs the verification later.
- **The decision is reversible and the verification is high-cost.** If the diagnosis informs a decision that can be cheaply walked back (e.g., a draft plan, a brainstorm note), and the verification would take hours, shipping the inference and verifying later is fine. The EB-249 case did not qualify — the diagnosis was committed to master and posted as an authoritative Jira comment.
- **Multiple independent verifying measurements have already corroborated the hypothesis under similar conditions in prior work.** This is rare; cite the prior work explicitly.

## How this surfaces in `hunt` outputs

The `hunt` skill prompts agents to acknowledge "what I couldn't verify." Read that section critically. If the leading hypothesis is tool-dependent and the agent acknowledges they couldn't run the verifying measurement, **the verdict should be downgraded from HIGH to MEDIUM or PENDING regardless of how clean the other evidence looks.**

Pattern to watch for in agent output:

```
**What I couldn't verify:**
- Cannot run Lighthouse with --throttling-method=devtools to get a definitive
  comparison.
```

When an agent admits this in a tool-dependent hypothesis context, the coordinator should treat the verdict as conditional and either (a) run the verification before synthesis, or (b) explicitly mark the diagnosis as "tool-property X assumed but not measured."

## References

- EB-249 — the ticket that closed as no-fix after the diagnosis revision (decision documented in Jira comments 2026-05-15, transitions to Done after `be215a5`)
- `docs/solutions/eb249-ttfb-diagnosis-2026-05-15.md` — the corrected diagnosis with the morning first-pass preserved for institutional memory
- `docs/solutions/best-practices/test-baseline-before-investing-in-tooling-2026-05-15.md` — related lesson on premise-testing before investing; this doc complements it for the measurement-property case
- `superpowers:hunt` skill — the parallel-hypothesis pattern this lesson refines
