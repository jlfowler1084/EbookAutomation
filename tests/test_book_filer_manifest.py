import sys
import json
import csv
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from book_filer.manifest import ManifestRow, write_manifest, canonical_projection, generate_undo_script


def _row(**kw) -> ManifestRow:
    base = dict(
        original_path=r"F:\Books\_Inbox\x.epub", destination_path=r"F:\Books\01 History\a.epub",
        sha256="abc123", size=10, planned_calibre_key="isbn:9780", calibre_id=None, isbn="9780",
        format="epub", section="01 History", subcategory="Modern & 20th-Century General",
        author_sort="A, B", title="T", year=2000, duplicate_group_id=None, canonical_reason=None,
        classification_confidence=0.9, classification_source="rule", taxonomy_version=1,
        tool_version="0.4.0", action="copy", undo_action="Remove-Item -LiteralPath dest", review_required=False,
    )
    base.update(kw)
    return ManifestRow(**base)


def test_write_manifest_emits_csv_json_md(tmp_path):
    base = write_manifest([_row()], tmp_path, stamp="20260601-000000")
    assert Path(f"{base}.csv").exists() and Path(f"{base}.json").exists() and Path(f"{base}.md").exists()
    data = json.loads(Path(f"{base}.json").read_text(encoding="utf-8"))
    assert data[0]["section"] == "01 History"
    with open(f"{base}.csv", encoding="utf-8") as f:
        assert next(csv.DictReader(f))["action"] == "copy"


def test_canonical_projection_is_order_and_calibre_id_invariant():
    a = [_row(original_path="b", calibre_id=None), _row(original_path="a", calibre_id=None)]
    b = [_row(original_path="a", calibre_id="123"), _row(original_path="b", calibre_id="456")]
    # Sorted by original_path AND calibre_id dropped -> identical projection (determinism gate).
    assert canonical_projection(a) == canonical_projection(b)


def test_canonical_projection_detects_real_drift():
    a = [_row(original_path="a", section="01 History")]
    b = [_row(original_path="a", section="04 Politics & Society")]
    assert canonical_projection(a) != canonical_projection(b)


def test_generate_undo_script_reverses_in_order(tmp_path):
    rows = [_row(original_path="a", undo_action="Move-Item A"), _row(original_path="b", undo_action="Move-Item B")]
    script = generate_undo_script(rows)
    # Undo replays in REVERSE order (last action undone first).
    assert script.index("Move-Item B") < script.index("Move-Item A")
    assert script.startswith("#")  # a commented header
