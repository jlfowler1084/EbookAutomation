"""Migration manifest engine (spec §6.1, §6.2). Pure: writes files, mutates no library."""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

# calibre_id is assigned only at APPLY (Plan 5); excluded from the determinism projection.
_VOLATILE = {"calibre_id"}


@dataclass
class ManifestRow:
    original_path: str
    destination_path: str
    sha256: str
    size: int
    planned_calibre_key: str
    calibre_id: str | None
    isbn: str | None
    format: str
    section: str | None
    subcategory: str | None
    author_sort: str | None
    title: str | None
    year: int | None
    duplicate_group_id: str | None
    canonical_reason: str | None
    classification_confidence: float
    classification_source: str
    taxonomy_version: int
    tool_version: str
    action: str
    undo_action: str
    review_required: bool


_FIELD_NAMES = [f.name for f in fields(ManifestRow)]


def write_manifest(rows: list[ManifestRow], out_dir: Path, stamp: str) -> Path:
    """Write plan-<stamp>.{csv,json,md}; returns the path stem. `stamp` is supplied by the caller."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / f"plan-{stamp}"
    dicts = [asdict(r) for r in rows]

    with open(f"{base}.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_FIELD_NAMES)
        writer.writeheader()
        writer.writerows(dicts)

    Path(f"{base}.json").write_text(json.dumps(dicts, indent=2), encoding="utf-8")

    lines = [f"# Migration plan {stamp}", "", f"{len(rows)} item(s).", ""]
    lines += ["| action | section | subcategory | original → destination |",
              "|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r.action} | {r.section or ''} | {r.subcategory or ''} | "
                     f"`{r.original_path}` → `{r.destination_path}` |")
    Path(f"{base}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return base


def canonical_projection(rows: list[ManifestRow]) -> str:
    """Deterministic projection for the calibration gate: sorted by original_path,
    volatile fields dropped, keys sorted. Identical inputs -> identical string."""
    projected = []
    for row in sorted(rows, key=lambda r: r.original_path):
        projected.append({k: v for k, v in asdict(row).items() if k not in _VOLATILE})
    return json.dumps(projected, sort_keys=True)


def generate_undo_script(rows: list[ManifestRow]) -> str:
    """Emit a PowerShell undo script that replays each row's undo_action in REVERSE order."""
    out = [
        "# Auto-generated undo script. Reverses the migration actions, last-first.",
        "$ErrorActionPreference = 'Stop'",
    ]
    for row in reversed(rows):
        if row.undo_action:
            out.append(row.undo_action)
    return "\n".join(out) + "\n"
