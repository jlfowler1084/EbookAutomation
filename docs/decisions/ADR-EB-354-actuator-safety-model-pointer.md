# ADR-EB-354: Actuator Safety Model (pointer)

**Status:** Pointer / mirror -- canonical decision lives in ClaudeInfra.
**Canonical ADR:** ClaudeInfra **ADR-0045** -- "book_filer Actuator Safety Model"
(`docs/decisions/ADR-0045-book-filer-actuator-safety-model.md` in the ClaudeInfra repo).
**Tickets:** INFRA-552 (ADR authoring) relates to EB-354 (EbookAutomation actuator, Plan 5).

## Why this file exists

The book_filer actuator (EB-354, Plan 5 -- the in-place file-mover for the signed-GREEN
manifest) is gated by a safety-model decision record. Per the ClaudeInfra ADR convention
(ADR-00NN series, ticket-anchored), the authoritative decision record lives in ClaudeInfra,
not here. This pointer exists so the gate is discoverable from the EbookAutomation side.

The EB-354 requirements and plan originally cited "ADR-0043" for this record; that number was
already assigned to the unrelated Hermes Tiered Autonomy ADR (INFRA-491). The actuator safety
model took the next free slot, **ADR-0045**, and the EB-354 references were corrected.

## Decision summary (canonical text in ClaudeInfra ADR-0045)

Core invariant: the actuator never deletes and never overwrites in place; the only removal
primitive is move-to-`_Trash_Pending`; every mutation is journaled write-ahead. Four decisions:

- **D1 -- In-place atomic-rename moves** (`os.replace`, same volume); no copy tree.
- **D2 -- External-mirror backup gate** verified by file count + deterministic sampled sha256
  vs a proof manifest; refuse to apply on mismatch.
- **D3 -- Append-only JSONL journal** as source of truth, with a **write-ahead intent record
  (`fsync`) before each move** and a commit record after; reconciliation on resume/undo closes
  the crash window; idempotent/resumable.
- **D4 -- One-command reverse-replay `undo`** to the exact original layout, available until an
  explicit `finalize` that deletes nothing.

Manifest-to-verdict binding via `sha256(canonical_projection(rows))`; the actuator asserts the
signed machine gates (`auto_shelf_floor` + `trash_safety`), not a bare verdict. EB-360 reparse
fail-closed on source + destination ancestry before every move.

## See also

- ClaudeInfra `docs/decisions/ADR-0045-book-filer-actuator-safety-model.md` (canonical)
- `docs/brainstorms/2026-06-04-eb354-book-filer-actuator-requirements.md`
- `docs/plans/2026-06-04-001-feat-eb354-book-filer-actuator-plan.md`
- `docs/decisions/ADR-EB-181-data-exemption-scope.md` (where the journal/run artifacts may land)
