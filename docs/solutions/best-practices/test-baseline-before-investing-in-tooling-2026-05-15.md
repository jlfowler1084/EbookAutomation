---
title: Test the simpler baseline before investing in new tooling or infra
date: 2026-05-15
category: best-practices
module: workflow
problem_type: best_practice
component: planning_workflow
severity: medium
applies_when:
  - A ticket proposes adding new infrastructure (MCP, service, library) to fix a quality or workflow problem
  - The problem framing relies on a hypothesized failure mode that hasn't been observed on a real artifact yet
  - An existing toolchain already covers the rough shape of the use case but is dismissed without comparison
  - Reviewer agents (product-lens, adversarial, scope-guardian) converge on "premise unproven" or "baseline not tested"
tags: [planning, ce-brainstorm, document-review, yagni, premise-testing, opus-sonnet-handoff]
related_decisions:
  - INFRA-392 (deferred 2026-05-15)
  - docs/brainstorms/2026-05-15-infra392-figma-mcp-setup-requirements.md
---

# Test the simpler baseline before investing in new tooling or infra

## Context

INFRA-392 proposed wiring the Figma MCP to enable a design-driven workflow for leafbind
(Figma → code via `figma-design-sync`, anchored to a Figma library mirroring
`design-tokens.ts`). The brainstorm produced a complete, internally-coherent workflow
design. The 7-persona `document-review` pass returned strong cross-reviewer agreement
on a single thesis: **the premise hadn't been tested**.

The motivating claim — "Claude generates plausible-looking UIs that drift from the
established brand" — was asserted but uncited. In the same week the ticket was
brainstormed, three brand-touching tickets shipped polished UIs using just the existing
`web-aesthetics` skill + Playwright visual-iteration loop, with no Figma involvement
and no observed drift:

- EB-233 (design system, custom logo, palette + token wiring)
- EB-239 (page-curl geometry adoption)
- EB-240 (Newsreader/DM Sans fonts, sand accent, warmer palette, Plex Mono eyebrows)

Feasibility separately found a P0 blocker — Figma Starter plan caps the MCP at 6 tool
calls/month, making the proposed iteration loop non-viable without a paid Dev/Full seat
(~$15/mo). Combined with the unproven premise, this meant **paying for new tooling to
solve a problem that hadn't surfaced on any real artifact**.

The decision: defer INFRA-392, build the next concrete deliverable (Stripe checkout
success page) using the existing stack, and reactivate the Figma ticket only if a
specific drift pattern surfaces that's hard to fix without a visual spec.

## Guidance

Before investing in new tooling or infrastructure to address a quality or workflow
problem, run this check sequence:

1. **Cite a concrete failure.** Find a real artifact (PR, screenshot, ticket comment,
   user-visible defect) that demonstrates the problem. If you can't cite one, the
   problem is hypothetical and the proposal is speculative.

2. **Try the baseline first.** Identify the simplest existing toolchain that plausibly
   solves the problem. Ship one real artifact through it. If the baseline succeeds,
   the proposed new tooling is solving a non-problem.

3. **Compare against the proposed tooling.** Only after the baseline is exercised, ask
   whether the new tooling's marginal benefit justifies its ongoing carrying cost
   (configuration, registry updates, auth rotation, drift maintenance, paid seats,
   permissions audit surface). For solo projects, ongoing maintenance compounds against
   you because you are the captive user.

4. **Acknowledge "tool exists, must be used" as a red flag.** Framing like "the
   existing agents have nothing to consume — they go unused" reverses product logic.
   Agent existence is not evidence that the workflow is needed.

## How this surfaces in document-review

The `compound-engineering:document-review` skill's persona suite catches this pattern
reliably. Watch for cross-reviewer convergence from:

- **product-lens-reviewer** — flags premise claims and do-nothing alternatives (look
  for findings tagged `right_problem`, `do_nothing`, `inversion`, `alternatives`).
- **adversarial-document-reviewer** — constructs failure scenarios that defeat the
  proposed workflow (look for `alternative-blindness` and `premise-challenging`).
- **scope-guardian-reviewer** — challenges scope creep into adjacent decisions that
  the original ticket out-of-scoped.

When two or more of these converge with confidence ≥0.70 on "the premise is unproven,"
the right move is to defer the ticket, not to refine the spec. Refining a spec for an
unproven premise produces a more polished doc, not a more grounded decision.

## Counter-cases (when to push through anyway)

This guidance is not absolute. Push through despite weak baseline-comparison evidence
when:

- The new tooling is reversible and zero-cost (e.g., a single MCP entry with no paid
  tier, no manual library to maintain) — the carrying cost is low enough that
  speculative provisioning is fine.
- A regulatory, security, or compliance gate requires the tooling regardless of
  observed need (e.g., audit logging, data-residency control).
- The proposed tooling is upstream of multiple consumers and the cost of provisioning
  now is much lower than re-provisioning per consumer later — but verify that multiple
  consumers actually exist, not just that they're plausible.

## References

- INFRA-392 — the deferred ticket (decision documented in Jira comment 2026-05-15)
- `docs/brainstorms/2026-05-15-infra392-figma-mcp-setup-requirements.md` — preserved as
  a decision record; reactivates if a concrete drift incident appears
- `docs/plans/2026-05-14-002-feat-eb233-leafbind-design-system-plan.md` — the design
  system that the existing `web-aesthetics` + Playwright stack delivered without Figma
- `compound-engineering:document-review` skill — the multi-persona review pass that
  surfaced the premise gap
