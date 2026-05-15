---
title: "INFRA-392: Figma MCP setup for design-driven leafbind workflow"
type: requirements
status: deferred-pending-evidence
date: 2026-05-15
origin: https://jlfowler1084.atlassian.net/browse/INFRA-392
related:
  - https://jlfowler1084.atlassian.net/browse/EB-45
  - https://jlfowler1084.atlassian.net/browse/EB-233
  - https://jlfowler1084.atlassian.net/browse/INFRA-390
  - https://jlfowler1084.atlassian.net/browse/INFRA-391
deferred_pending:
  - "Concrete brand-drift incident on a real leafbind page that cannot be fixed via web-aesthetics + Playwright iteration"
  - "Decision on Figma Professional+ paid seat (Starter plan caps MCP at 6 tool calls/month)"
---

## Decision (2026-05-15): Deferred pending evidence

This requirements doc is preserved as a **decision record**, not an active spec. After
`ce:brainstorm` produced a complete workflow design, the `document-review` pass returned
strong cross-reviewer agreement (product-lens + adversarial + scope-guardian) that the
premise was unproven: Claude has shipped three brand-polished tickets (EB-233, EB-239,
EB-240) using just `web-aesthetics` + Playwright visual-iteration, with no Figma involvement
and no documented brand-drift incident. Feasibility separately found a P0 blocker — the
Figma MCP Starter-plan rate limit (6 tool calls/month) makes the iteration loop non-viable
without a paid seat (~$15/mo).

**Path chosen:** build the next concrete deliverable (Stripe checkout success page,
filed as **EB-248**) using the existing toolchain. If the result is on-brand and
on-spec, INFRA-392 stays deferred. If a specific drift pattern surfaces that's hard to
fix without a visual spec, this doc becomes the active requirements again — with the
failure mode as concrete evidence justifying the workflow's cost. EB-248 AC #6 is the
evidence-gathering hook.

Everything below this section reflects the workflow as designed before the deferral
decision, kept for future reference if the ticket reactivates.

---

# INFRA-392: Figma MCP setup for design-driven leafbind workflow

## Why now

EB-233 shipped on 2026-05-14, followed by the EB-240 brand/palette refinement merged
2026-05-15 (PR #81). The result: `web_service/frontend/design-tokens.ts` holds the
sand/forest palette, the Newsreader/DM Sans/Plex Mono typography wired via `next/font`,
and the custom leaf-with-paper-curl logo. The tokens are stable. The next deferred design
deliverable — the Stripe checkout success page — has been waiting on "the tokens to exist"
(per the EB-233 plan's *Deferred to Separate Tasks* section).

That is the inflection point where Figma starts paying for itself. Without a design surface,
the existing `compound-engineering:design:figma-design-sync` and `compound-engineering:design:design-iterator`
agents have nothing to consume — they go unused, and Claude generates "plausible-looking" UIs
from prose descriptions that drift from the established brand. With Figma wired up, Claude can
read against a real spec instead of guessing.

## Goal

Establish a one-directional Figma-as-spec workflow for new leafbind pages, where Figma is
the source of truth for layout and `web_service/frontend/design-tokens.ts` remains the source
of truth for color/type/spacing values, with a Figma library that mirrors the code-side tokens
so the two stay aligned.

After this ticket ships, building a new leafbind page looks like:

1. Open Figma, compose a frame using the leafbind library (constrained palette and type).
2. Hand the Figma URL + node ID to Claude.
3. `figma-design-sync` reads the frame, generates React/Tailwind code that consumes existing
   tokens from `design-tokens.ts`, screenshots the rendered result, and iterates until visual
   parity is reached.
4. Commit the page, ship.

## Workflow direction (resolved in brainstorm)

| Decision | Choice | Why |
| --- | --- | --- |
| Direction of truth | Figma → code (forward), new pages only | EB-233 already established code as source of truth for *existing* pages; retrofitting them into Figma has no payoff |
| Figma library | Build a library mirroring `design-tokens.ts` | Constrains Figma so designs cannot drift from code tokens; turns `figma-design-sync` from fuzzy mapping to precise translation |
| First real consumer | Stripe checkout success page | Filed as a separate downstream ticket; not in INFRA-392 scope |
| Project scope | EbookAutomation (leafbind) only | CareerPilot has no concrete upcoming design need; deferring avoids config-drift for unused setup |
| Primary agent | `figma-design-sync` | Direction matches the agent's assumption (Figma is the spec) |
| Bootstrap agent | `compound-engineering:frontend-design` skill | For greenfield composition, copy, motion when starting from a Figma frame |
| Iteration fallback | `compound-engineering:design:design-iterator` | When iterating on code without re-touching Figma |

## Scope

### In scope

1. Install the `figma` plugin from the official Anthropic marketplace at user scope:
   `claude plugin install figma@claude-plugins-official`. Upstream source is
   `figma/mcp-server-guide` (Figma-authored, distributed via the Anthropic marketplace).
2. Authenticate the Figma MCP via OAuth on first tool call — same model as Stripe
   (INFRA-390) and Cloudflare (INFRA-391). No personal access token, no `.env` entry.
   OAuth flow is browser-based and one-time per machine.
3. Wire `.mcp.json` in `F:\Projects\EbookAutomation` to add the Figma MCP entry:
   `"figma": {"type": "http", "url": "https://mcp.figma.com/mcp"}`.
4. Update `.claude/settings.local.json` to allow the Figma tool permission patterns.
5. Update the MCP registry in `F:\Projects\ClaudeInfra\configs\mcp-server-registry.json` —
   add `figma` to the EbookAutomation `servers` array, bump version, reference this ticket.
6. Update `F:\Projects\ClaudeInfra\docs\registries\mcp-servers.md` with the new EbookAutomation row.
7. Update `F:\Projects\EbookAutomation\CLAUDE.md` "MCP Servers" section to list `figma` in the
   allowed-MCP set.
8. Build a leafbind Figma library that mirrors `web_service/frontend/design-tokens.ts`:
   - **Color styles**: every entry in the `colors` export — currently 9 entries
     (brand, brandDark, accent, surface, surfaceMuted, border, textBase, textMuted,
     paperBack) — created as Figma color styles with names matching the token keys.
   - **Type styles**: 7 size tokens (`scaleXs` through `scale3Xl`) × 3 font families
     (fontSans = DM Sans, fontSerif = Newsreader, fontMono = IBM Plex Mono). Naming
     convention and semantic-role mapping (does `scale3Xl + Newsreader` = "display"?)
     is a design decision flagged in Open Questions, not auto-derivable.
   - **Spacing scale**: every key in the `space` export — currently 8 entries on a 4-point
     base (1, 2, 3, 4, 6, 8, 12, 16) — documented in a Figma frame so designs reference
     them rather than inventing arbitrary pixel gaps.
   - **Shadows + radii**: 3 shadow tokens (sm, md, lg) and 2 radii tokens (sm, md) as
     Figma effect styles.
   - **Components**: 5 components total — `Button` (with primary and ghost variants),
     `Card`, `Input`, `Nav`, `Footer` — built once so per-page work composes rather than
     redraws. Component-level state inventory (Button disabled/loading, Input focused/error,
     Nav mobile-collapsed) is a design decision flagged in Open Questions.
9. Smoke test: from a fresh Claude session, fetch the leafbind Figma library file by URL,
   return frame/component data, and confirm at least one named color style and one named
   type style come back with the values matching `design-tokens.ts`.

### Out of scope

- **Stripe checkout success page implementation** — separate downstream ticket. INFRA-392
  proves the workflow works; that ticket exercises it on the first real product page.
- **Marketing collateral (OG images, social graphics)** — different design domain; if
  needed, a later ticket can extend Figma usage to that surface.
- **CareerPilot Figma integration** — deferred until CareerPilot has a concrete upcoming
  design need. Re-evaluating in a follow-up ticket is cheaper than maintaining unused config.
- **Dark mode in the Figma library** — matches EB-233's "light mode only" scope. Add when
  dark mode lands in code.
- **Two-way Figma↔code sync** — code is authoritative for tokens; library updates flow
  from code to Figma manually when tokens change. Automating that is not worth the
  carrying cost for a solo dev.
- **Generating Figma files programmatically via the MCP** — read-only token; designs are
  composed by the user in Figma, not by Claude.

## Acceptance criteria

1. `figma` plugin appears in `C:\Users\Joe\.claude\plugins\installed_plugins.json` at user scope.
2. Figma MCP authenticates successfully via OAuth on first tool call. No `FIGMA_ACCESS_TOKEN`
   stored anywhere — the MCP uses OAuth identical to Stripe (INFRA-390) and Cloudflare
   (INFRA-391). OAuth handshake completes from a fresh Claude Code session without errors.
3. `F:\Projects\EbookAutomation\.mcp.json` has exactly this `figma` entry alongside the
   existing `atlassian`, `stripe`, and `cloudflare` entries:
   `"figma": {"type": "http", "url": "https://mcp.figma.com/mcp"}`.
4. `F:\Projects\EbookAutomation\.claude\settings.local.json` `permissions.allow` includes
   the Figma tool permission patterns. Predicted pattern: `mcp__plugin_figma_figma__*`
   (matches the Playwright plugin precedent — both are Claude Code plugins bundling their
   own MCP). Confirm at install; only deviate if the install output disagrees. Enumerate
   the exact tool list and prefer named-tool allowlist over wildcard if any write tools
   appear in the plugin's surface.
5. `F:\Projects\ClaudeInfra\configs\mcp-server-registry.json` includes `figma` in
   EbookAutomation's `servers`, with version bumped and `notes` referencing INFRA-392.
   (Requires ClaudeInfra worktree to be available locally; if not, the AC #5/#6 sub-task
   can be split to a follow-up PR in ClaudeInfra rather than blocking INFRA-392.)
6. `F:\Projects\ClaudeInfra\docs\registries\mcp-servers.md` has a row reflecting the new
   EbookAutomation/figma allowlist.
7. `F:\Projects\EbookAutomation\CLAUDE.md` "MCP Servers" section mentions `figma` as
   allowed and links INFRA-392 for the rationale (matching the prose style used for
   Stripe under INFRA-390 and Cloudflare/Playwright/GitHub under INFRA-391).
8. A leafbind Figma library file exists in the user's Figma workspace with:
   - Color styles matching every key in `web_service/frontend/design-tokens.ts` `colors`
     export (9 entries).
   - Text styles for every entry in the `type` export's size scale (7 entries:
     `scaleXs` through `scale3Xl`), with the appropriate font family applied per the
     semantic-mapping decision from Open Questions.
   - Spacing styles or a documented frame for every entry in the `space` export
     (8 entries: 1, 2, 3, 4, 6, 8, 12, 16).
   - 5 components: `Button` (with primary and ghost variants), `Card`, `Input`, `Nav`,
     `Footer`.
   - File URL recorded in `docs/figma-library-url.md` so downstream tickets can
     reference it.
9. **Smoke test passes**: in a fresh Claude Code session after a restart, the user can run
   a prompt like *"Fetch the leafbind Figma library, list the color styles and one component."*
   and Claude returns matching data from the MCP without errors. The smoke-test result is
   captured in the PR description so reviewers can confirm.
10. Token-mirror drift check: at least one color style and one type style in the Figma
    library are spot-checked against `design-tokens.ts`. Same hex values, same px sizes.
    If a mismatch exists, the Figma library is the side that gets corrected (code is
    authoritative).

## Prerequisites (user-blocked)

These must be done by the human before Claude can implement:

1. **Figma account.** Sign up at figma.com.
2. **Figma workspace.** Create a team. The free Starter plan technically works but caps
   the Figma MCP at **6 tool calls per month per user**, which is not viable for the
   intended iteration loop — see the open question on plan tier.
3. **OAuth on first call.** After `claude plugin install figma@claude-plugins-official`
   and the first tool invocation, complete the browser-based OAuth handshake. Claude
   cannot do this step; the user must approve the OAuth grant interactively.

Until step 1 and step 2 are done, implementation work blocks at AC #2. Step 3 happens
inline during AC #2 execution.

## Success criteria

- A fresh-session smoke test (AC #9) returns Figma data without errors.
- The leafbind Figma library has the full token mirror per AC #8: 9 color styles,
  7 type-size styles (multiplied by font-family assignment per the semantic-mapping
  decision), 8 spacing values, and 5 components.
- The first downstream ticket (Stripe checkout success page) can begin without re-litigating
  any of the decisions in this brainstorm.
- The MCP integration is documented at the same level of detail as the Stripe MCP
  (INFRA-390 precedent), so a future reader can understand why and how it was added.

## Open questions for planning

The following are deliberate hand-offs to `ce:plan` — too implementation-detailed for the
brainstorm but real decisions:

- **Figma plan tier:** Starter (free) caps the MCP at 6 tool calls per month. A Dev or
  Full seat on Professional+ is required for the iteration loop to be usable. Decision
  affects whether INFRA-392 includes a paid-seat prerequisite or scopes itself to the
  6-call budget and defers the iteration loop.
- **Type-style semantic mapping:** The 7 scale tokens (`scaleXs`..`scale3Xl`) do not
  carry semantic role names (display, h1–h6, body, caption, eyebrow). Either (a) introduce
  semantic-role keys in `design-tokens.ts` as a code change before this ticket ships,
  or (b) keep scale names in the Figma library and let downstream pages compose roles
  from sizes. Pick one — the AC #8 token-mirror check depends on it.
- **Component variant inventory:** Which states do `Button`, `Input`, `Nav` need in the
  library? At minimum: Button disabled + loading, Input error + focused + disabled,
  Nav mobile-collapsed. Lock the variant set before building, or AC #8 is subjective.
- **Color profile:** Figma defaults to Display P3 for new files since 2024. `design-tokens.ts`
  is sRGB hex. Set the Figma file to sRGB color profile so AC #10's "same hex values"
  check is meaningful.
- **Rem-to-px base:** Figma type styles are px-only. `design-tokens.ts` uses rem
  (`0.75rem`, `1rem`, etc.). Confirm the root font-size assumption (16px standard?
  17px optical sizing for Newsreader?) before mapping scales to Figma text styles.
- **Library build method:** Manually in Figma (estimated 2–5 hours including component
  variants) or scripted via a Tokens Studio import that reads `design-tokens.ts`?
  Trade-off: manual is faster to start, scripted gives a repeatable refresh path when
  tokens change (which recent history — EB-240 just changed brand+surface+paperBack —
  shows happens per design ticket).
- **Drift trigger:** Define the threshold at which manual mirror is replaced by scripted
  refresh (e.g., "if 2 or more tokens change in a single quarter, file the refresh-script
  ticket"). Without a trigger, "revisit if tokens change often" never gets revisited.
- **Figma file visibility:** Set the library file to "only invited members" before
  committing its URL to `docs/figma-library-url.md`. The repo is private (mitigates leak
  risk) but explicit setting prevents future visibility regressions.
- **Token rotation cadence:** N/A under OAuth — Figma OAuth tokens auto-refresh via the
  plugin. (This question existed under the PAT model; removed.)

## Follow-up tickets (to file after this ships)

1. **EB-XXX: Stripe checkout success page (Figma→code pilot)** — first real consumer of
   the wired-up MCP. Designs the page in Figma using the leafbind library, runs
   `figma-design-sync`, ships the implementation.
2. **EB-XXX: Stripe post-purchase email design** — co-deferred with the success page in
   EB-233. Similar workflow, different surface (transactional email HTML).
3. **INFRA-XXX: CareerPilot Figma MCP integration** — file when CareerPilot has its own
   concrete design need. Will reuse the install + permission pattern from INFRA-392.
4. **EB-XXX: Figma library refresh script** (only if needed) — automate the
   `design-tokens.ts` → Figma library mirror if tokens change often enough that manual
   updates become friction.

## References

- `web_service/frontend/design-tokens.ts` — source of truth being mirrored
- `docs/plans/2026-05-14-002-feat-eb233-leafbind-design-system-plan.md` — the plan that
  produced the design system being reflected
- `C:\Users\Joe\.claude\plugins\cache\compound-engineering-plugin\compound-engineering\2.65.0\agents\design\figma-design-sync.md` — primary agent
- `C:\Users\Joe\.claude\plugins\cache\compound-engineering-plugin\compound-engineering\2.65.0\agents\design\design-iterator.md` — iteration fallback
- INFRA-70 — MCP registry source of truth
- INFRA-390 — Stripe MCP install precedent (same trust model)
- INFRA-391 — sibling MCP-bundle ticket (Cloudflare / Playwright / GitHub)
- ADR-0027 — per-project MCP restrictions policy
