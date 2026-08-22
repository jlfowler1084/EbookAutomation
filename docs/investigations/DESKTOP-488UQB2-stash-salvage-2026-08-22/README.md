# Salvaged Stashes from DESKTOP-488UQB2

**Date:** 2026-08-22
**Origin ticket:** [INFRA-597](https://jlfowler1084.atlassian.net/browse/INFRA-597) (decommission workstation identity on DESKTOP-488UQB2)
**Status:** Preserved, **not applied.** Disposition is a human decision.

## Why these exist

DESKTOP-488UQB2 (the R9700 inference node) held a stale `EbookAutomation` checkout from before it took that role. Its `master` was **133 commits behind** with **zero unpushed commits** -- by that measure the clone looked safe to delete.

It was not. Four stashes sat underneath.

Stashes live in `refs/stash`, which is outside both `--branches` and `--remotes`. They are invisible to `git log --branches --not --remotes` **and** to ahead/behind counts. Every common "is this repo safe to delete?" check misses them. Deleting that clone on the strength of "0 unpushed" would have silently destroyed the work captured here.

## Contents

| Patch | Origin | Files | Size |
|---|---|---|---|
| `stash-0.patch` | WIP on `feature/book-metadata-capture` (`062432a`) | `module/EbookAutomation.psm1` | +56 / -3 |
| `stash-1.patch` | WIP on `feature/conversion-profiles` (`6cb1ce1`) | `module/EbookAutomation.psm1` | +12 / -1 |
| `stash-3.patch` | WIP on `feature/chapter-detection` (`4f09078`) | `tools/send_to_kindle.py`, `config/settings.json` | +116 / -75 |

`stash@{2}` from the same host is **not** included: `git apply --check --reverse` succeeds against this repo, so its content is already present here.

## Disposition status

All three were tested against this repo with `git apply --check` in both directions and came back **INDETERMINATE** -- this repo has moved from 2026-04 to 2026-06 and the surrounding context has drifted, so neither a clean forward apply nor a clean reverse apply is possible.

That means an automated decision is not available. Each patch needs a human to decide whether the change is still wanted, and if so, to re-apply it by hand against current `master`.

`stash-3.patch` is the substantial one: 187 changed lines in `send_to_kindle.py`, on a `feature/chapter-detection` base.

## How to review one

```bash
# See what it changes
git apply --stat docs/investigations/DESKTOP-488UQB2-stash-salvage-2026-08-22/stash-3.patch

# Try a 3-way merge into a scratch branch (do NOT do this on master)
git switch -c salvage/eba-stash-3
git apply --3way docs/investigations/DESKTOP-488UQB2-stash-salvage-2026-08-22/stash-3.patch
```

If a patch turns out to be unwanted, delete it from this directory in a commit that records *why* -- so the decision is auditable and nobody re-salvages it later.

## Provenance

Extracted read-only over SSH by streaming `git stash show -p 'stash@{N}'` to stdout. Nothing was written to DESKTOP-488UQB2, and the stashes **still exist on that host** -- these are copies, not moves. The originals are only removed when INFRA-597's deletion phase runs, which is gated on this directory being resolved.
