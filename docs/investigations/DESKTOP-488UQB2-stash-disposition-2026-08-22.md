# Disposition — Stashes Salvaged from DESKTOP-488UQB2

**Date:** 2026-08-22
**Ticket:** [SCRUM-329](https://jlfowler1084.atlassian.net/browse/SCRUM-329)
**Origin:** [INFRA-597](https://jlfowler1084.atlassian.net/browse/INFRA-597) — decommission workstation identity on DESKTOP-488UQB2
**Replaces:** `docs/investigations/DESKTOP-488UQB2-stash-salvage-2026-08-22/` (removed by this commit)

This record exists so a future inventory does not re-salvage work that was
deliberately dropped. All three patches were reviewed hunk-by-hunk against
`master` at `af86249`.

## Summary

| Patch | Disposition | Reason |
|---|---|---|
| `stash-0.patch` | **Partially applied** | 3 of 5 hunks already in `master`; hunk 2 was a live defect and is fixed here |
| `stash-1.patch` | **Discarded — superseded** | Every added line already present in `master` |
| `stash-3.patch` | **Discarded — superseded** | Every added line present in `master`, which is strictly ahead |

## Why patch-level disposition was the wrong granularity

All three tested INDETERMINATE under `git apply --check` in both directions, so
neither "applies cleanly" nor "reverse-applies cleanly" could decide anything.
The verdict has to be reached per hunk, by reading `master`.

`stash-0` is why. Three of its five hunks had landed, so the feature *looked*
shipped — the parameters were present on every function involved. The hunk that
had not landed was the one that forwarded them. Judging that patch as a unit, in
either direction, produces the wrong answer.

## stash-0 — partially applied

Origin: WIP on `feature/book-metadata-capture` (`062432a`).

| Hunk | In `master`? | Disposition |
|---|---|---|
| 1 — `Convert-ToKindle` gains `-Profile` + `-No*` params | Yes | No action (a `HelpMessage` attribute differs; cosmetic) |
| 2 — `Invoke-EbookPipeline` forwards them to `Convert-ToKindle` | **No** | **Applied** — see below |
| 3 — `Invoke-ConvergeLoop` gains the same params | Yes | No action |
| 4 — scanned-PDF advisory `Write-EbookLog` | No | **Discarded** — see below |
| 5 — `Invoke-ConvergeLoop` forwards via `$convertParams` | Yes | No action |

### Hunk 2 — applied (defect fix)

`Invoke-EbookPipeline` declared `-Profile`, `-NoFootnotes`, `-NoIndex`,
`-NoBibliography`, `-NoHyperlinks`, `-NoFrontMatter`, `-NoBackMatter`,
`-NoImages`, and `-NoBlockQuotes`, and passed **none** of them to
`Convert-ToKindle`. Verified against the AST: no splatting and no
`$PSBoundParameters` anywhere in the function body — the parameter declarations
were the only occurrences of those variables.

The flags therefore appeared in `Get-Help`, tab-completed, and validated their
arguments, then did nothing. `Invoke-EbookPipeline -Profile text-only -NoImages`
ran a full conversion and silently discarded both flags. `Invoke-ConvergeLoop`
was unaffected — hunk 5 landed, so that path forwarded correctly.

The patch did not apply: `master`'s call site has since gained `-UseVision`,
`-VisionCostLimit`, `-UseGemini`, `-GeminiRemediate`, `-GeminiCostLimit`, and
`-ApplyAIFixes`, and uses `-UseOCR:$useOcrAuto`. The fix was rewritten by hand
against current `master`, and includes `-NoBibliography`, which `master` added
after the stash was taken.

Covered by `tests/Invoke-EbookPipeline.ProfileForwarding.Tests.ps1`, which
derives the flag list from the parameter declaration rather than hard-coding it,
so a content flag added later is covered without editing the test.

### Hunk 4 — discarded

An advisory `Write-EbookLog ... -Level WARN` suggesting `-Profile text-only` for
scanned PDFs. Discarded for two reasons: the block it anchored to
(`"Recommended strategies: ..."`) no longer exists in `Invoke-ConvergeLoop`, and
`master` now handles the same scanned-PDF concern *functionally* rather than
advisorily — the content-density sanity check zeroes implausible high scores on
low-density scanned sources. A suggestion printed alongside a correction that
already fires would be noise.

## stash-1 — discarded (superseded)

Origin: WIP on `feature/conversion-profiles` (`6cb1ce1`). Added `-Profile` and
seven `-No*` switches to `Invoke-EbookPipeline`'s param block, and nothing else.

Every added line is present in `master`. The parameters are not merely declared
there — each appears 6–11 times module-wide, i.e. declared *and* consumed. The
shipped version also carries comment-based help the stash lacked, and adds
`-NoBibliography`.

Note this patch declared parameters without wiring them; the wiring gap it left
in `Invoke-EbookPipeline` is exactly what stash-0 hunk 2 fixes above.

## stash-3 — discarded (superseded)

Origin: WIP on `feature/chapter-detection` (`4f09078`). Reworked
`tools/send_to_kindle.py` for MTP device support (Kindle Scribe and newer) with
a USBMS fallback, plus a `config/settings.json` change enabling
`kindle_delivery`.

Every added line is present in `master`, and `master` is ahead:

- `find_kindle_mtp` and `find_kindle_usbms` exist with full type annotations
  (`scanner_devices: Any, timeout: int = 60) -> tuple[Any, Any]`); the stash's
  signatures are un-annotated. These two signature lines were the *only* content
  the comparison reported as absent, and they are absent solely because the
  annotated form supersedes them.
- The MTP-then-USBMS fallback chain and the
  `upload_books()` / `upload_to_device()` split are both present.
- `config/settings.json` already has `kindle_delivery.enabled: true` and the
  library path, plus an `email` block the stash predates.

## Provenance note

These were copies, not moves — the originals still exist on DESKTOP-488UQB2 and
are removed by INFRA-597's deletion phase, which was gated on this ticket.

`stash@{2}` was excluded from the salvage set at extraction time:
`git apply --check --reverse` succeeded against this repo, so its content was
already present.
