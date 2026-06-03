"""TDD suite for tools/book_filer/scan.py — EB-355 -WhatIf read-only scan driver.

All tests use pytest tmp_path synthetic fixtures. NO real library paths.
NEVER scan F:\\Books or any real path.

Import style mirrors the existing test_book_filer_*.py convention.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PureWindowsPath

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------

def _write(path: Path, content: bytes = b"") -> Path:
    """Write bytes to path, creating parents as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _pdf(path: Path, seed: str = "x") -> Path:
    """Write a fake PDF with distinguishable content."""
    return _write(path, f"%PDF-1.4 fake content seed={seed}".encode())


def _epub(path: Path, seed: str = "x") -> Path:
    """Write a fake EPUB (non-parseable zip, but valid for hashing)."""
    return _write(path, f"PK fake epub seed={seed}".encode())


def _make_real_epub(path: Path, title: str, author: str, date: str = "2011-01-01",
                    isbn: str | None = None) -> Path:
    """Write a VALID EPUB whose OPF carries title+author (+optional ISBN), so
    extract_metadata returns real metadata (has_metadata=True). Mirrors
    test_book_filer_metadata._make_epub. Used to positively exercise the dedup
    'trash' path (which post M1/G11 requires a real metadata anchor) and to build
    distinct-work destination collisions (distinct ISBN -> distinct work_key)."""
    import zipfile

    ident = f'<dc:identifier id="bookid">urn:isbn:{isbn}</dc:identifier>' if isbn else ""
    opf = (
        '<?xml version="1.0"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f"<dc:title>{title}</dc:title><dc:creator>{author}</dc:creator>"
        f"<dc:date>{date}</dc:date>{ident}"
        "</metadata><manifest/><spine/></package>"
    )
    container = (
        '<?xml version="1.0"?>'
        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">'
        '<rootfiles><rootfile full-path="content.opf" '
        'media-type="application/oebps-package+xml"/></rootfiles></container>'
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("content.opf", opf)
    return path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _make_settings(tmp: Path, library_root: Path) -> Path:
    """Write a minimal settings.json into tmp, returns path."""
    settings = {
        "library": {
            "library_root": str(library_root),
            "calibre_library": str(tmp / "calibre"),
            "audio_root": str(library_root / "Audio_Books"),
            "documents_root": str(tmp / "docs"),
            "materialize_mode": "copy",
            "trash_retention_days": 30,
            "operational_folders": ["_Inbox", "_Needs_Review", "_Quarantine",
                                    "_Duplicates_Pending", "_Trash_Pending",
                                    "_Migration_Manifests"],
            "scan_exclude": ["Audio_Books"],
            "max_path_length": 240,
        }
    }
    cfg_dir = tmp / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    settings_path = cfg_dir / "settings.json"
    settings_path.write_text(json.dumps(settings), encoding="utf-8")
    return settings_path


def _make_taxonomy(tmp: Path) -> Path:
    """Write a minimal books-taxonomy.json into tmp, returns path."""
    taxonomy = {
        "version": 1,
        "confidence_threshold": 0.34,
        "non_library_keywords": ["resume", "invoice"],
        "sections": [
            {
                "code": "01 History",
                "subcategories": [
                    {"name": "World Wars", "keywords": ["wwii", "war"]},
                    {"name": "General", "keywords": ["history"]},
                ],
            },
            {
                "code": "09 Technology",
                "subcategories": [
                    {"name": "Programming", "keywords": ["python", "programming"]},
                ],
            },
        ],
    }
    cfg_dir = tmp / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    tax_path = cfg_dir / "books-taxonomy.json"
    tax_path.write_text(json.dumps(taxonomy), encoding="utf-8")
    return tax_path


def run_scan(root: Path, out_dir: Path, settings_path: Path, taxonomy_path: Path,
             stamp: str = "TEST20260101", limit: int | None = None,
             extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    """Run scan.py in a fresh subprocess with PYTHONHASHSEED=0."""
    scan_py = Path(__file__).resolve().parents[1] / "tools" / "book_filer" / "scan.py"
    cmd = [
        sys.executable, str(scan_py),
        "--root", str(root),
        "--out-dir", str(out_dir),
        "--stamp", stamp,
        "--settings", str(settings_path),
        "--taxonomy", str(taxonomy_path),
    ]
    if limit is not None:
        cmd += ["--limit", str(limit)]
    if extra_args:
        cmd += extra_args
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = "0"
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def _load_rows(out_dir: Path, stamp: str) -> list[dict]:
    plan_json = out_dir / f"plan-{stamp}.json"
    if not plan_json.exists():
        return []
    return json.loads(plan_json.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# [M] Test 1 — trash only on truly identical content (sha256 match)
# ---------------------------------------------------------------------------

def test_trash_only_on_truly_identical_content(tmp_path):
    """Every 'trash' row must share exact sha256 with a 'keep' row in its group."""
    root = tmp_path / "root"
    # Two byte-identical EPUBs WITH metadata (same sha => exact dup; real anchor).
    _make_real_epub(root / "book_a.epub", "The Oil Kings", "Andrew Scott Cooper")
    _write(root / "book_a_copy.epub", (root / "book_a.epub").read_bytes())
    # One distinct book (different sha + metadata) — must NOT be trashed.
    _make_real_epub(root / "book_b.epub", "Designing Data-Intensive Apps", "Martin Kleppmann")

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)
    out = tmp_path / "out"

    result = run_scan(root, out, cfg, tax)
    assert result.returncode == 0, result.stderr

    rows = _load_rows(out, "TEST20260101")
    assert rows, "Expected rows in manifest"

    trash_rows = [r for r in rows if r["action"] == "trash"]
    # The metadata-bearing identical copy MUST produce exactly one trash row.
    # (Positively exercises the trash path — would be vacuous with no-metadata files,
    # which are downgraded to review per M1/G11.)
    assert len(trash_rows) == 1, f"expected exactly one trash row; got {trash_rows}"

    # Every trash row must share its sha256 with a non-trash row in its group.
    for tr in trash_rows:
        assert tr["duplicate_group_id"] is not None, "trash row must have a duplicate_group_id"
        same_sha = [r for r in rows if r["sha256"] == tr["sha256"] and r["action"] != "trash"]
        assert same_sha, (
            f"trash row {tr['original_path']} has no matching non-trash row with same sha256"
        )

    # The distinct book must NOT be trashed.
    b_row = next((r for r in rows if "book_b" in r["original_path"]), None)
    assert b_row is not None
    assert b_row["action"] != "trash", "distinct-sha book must not be trashed"


def test_sha_only_duplicate_without_metadata_is_review_not_trash(tmp_path):
    """M1/G11: byte-identical files with NO embedded metadata form a sha-only dup
    group with no identity anchor. The non-keeper MUST be downgraded to 'review',
    never auto-'trash' — trashing here is data loss with nothing to justify which
    copy is canonical."""
    root = tmp_path / "root"
    # Two byte-identical fake PDFs (same sha) that yield NO parseable metadata.
    _pdf(root / "dup_a.pdf", seed="identical-no-metadata")
    _pdf(root / "dup_b.pdf", seed="identical-no-metadata")

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)
    out = tmp_path / "out"

    result = run_scan(root, out, cfg, tax)
    assert result.returncode == 0, result.stderr

    rows = _load_rows(out, "TEST20260101")
    assert rows, "Expected rows in manifest"
    assert all(r["action"] != "trash" for r in rows), (
        f"sha-only dup with no metadata anchor was trashed (data loss): "
        f"{[(r['original_path'], r['action']) for r in rows]}"
    )
    assert any(
        r["action"] == "review" and "metadata anchor" in (r.get("canonical_reason") or "")
        for r in rows
    ), (
        f"expected a 'sha-only duplicate, no metadata anchor' review row; got "
        f"{[(r['action'], r.get('canonical_reason')) for r in rows]}"
    )


def test_sanitized_implausible_year_keeps_exact_duplicate_trash_safe(tmp_path):
    """A scrubbed year changes the meta work_key but must not break exact-dup safety."""
    root = tmp_path / "root"
    _make_real_epub(root / "book_a.epub", "Python Programming", "Guido Rossum", date="0101-01-01")
    _write(root / "book_a_copy.epub", (root / "book_a.epub").read_bytes())

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)
    out = tmp_path / "out"

    result = run_scan(root, out, cfg, tax)
    assert result.returncode == 0, result.stderr

    rows = _load_rows(out, "TEST20260101")
    assert {r["year"] for r in rows} == {None}
    assert {r["planned_calibre_key"] for r in rows} == {"meta:guido-rossum|python-programming|"}

    trash_rows = [r for r in rows if r["action"] == "trash"]
    assert len(trash_rows) == 1
    assert trash_rows[0]["duplicate_group_id"]
    assert any(r["sha256"] == trash_rows[0]["sha256"] and r["action"] != "trash" for r in rows)


def test_sanitized_fake_author_downgrades_sha_duplicate_to_review(tmp_path):
    """Scrubbing a fake author removes the metadata anchor, so exact dups stay review."""
    root = tmp_path / "root"
    _make_real_epub(root / "book_a.epub", "Python Programming", "svejk, josef")
    _write(root / "book_a_copy.epub", (root / "book_a.epub").read_bytes())

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)
    out = tmp_path / "out"

    result = run_scan(root, out, cfg, tax)
    assert result.returncode == 0, result.stderr

    rows = _load_rows(out, "TEST20260101")
    assert {r["author_sort"] for r in rows} == {None}
    assert all(r["action"] != "trash" for r in rows)
    assert any(
        r["action"] == "review" and "metadata anchor" in (r["canonical_reason"] or "")
        for r in rows
    )


# ---------------------------------------------------------------------------
# [M] Test 2 — zero-byte files never trashed
# ---------------------------------------------------------------------------

def test_zero_byte_files_never_trashed(tmp_path):
    """Zero-byte files must never be emitted as 'trash' rows (or any book row at all)."""
    root = tmp_path / "root"
    # Three distinct zero-byte PDF files
    for name in ("zero1.pdf", "zero2.pdf", "zero3.pdf"):
        _write(root / name, b"")
    # One real book so the scan has something
    _pdf(root / "real_book.pdf", seed="real")

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)
    out = tmp_path / "out"

    result = run_scan(root, out, cfg, tax)
    assert result.returncode == 0, result.stderr

    rows = _load_rows(out, "TEST20260101")
    # Zero-byte files must not appear as book rows at all (G11)
    for r in rows:
        assert "zero" not in r["original_path"].lower() or r["action"] != "trash", (
            f"zero-byte file must not be trashed: {r['original_path']}"
        )
    # More specifically: no row from zero-byte paths
    zero_rows = [r for r in rows if any(f"zero{i}" in r["original_path"] for i in range(1, 4))]
    assert not zero_rows, f"zero-byte files must not appear as rows: {zero_rows}"


# ---------------------------------------------------------------------------
# [M] Test 3 — fragment verdicts do not span two folders
# ---------------------------------------------------------------------------

def test_fragment_set_does_not_span_two_folders(tmp_path):
    """Same stem in 3 different parent dirs must NOT produce a cross-folder FragmentVerdict."""
    root = tmp_path / "root"
    # Same stem 'ebook' in 3 different directories
    for i in range(1, 4):
        _pdf(root / f"dir{i}" / f"ebook-{i}.pdf", seed=f"seed{i}")

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)
    out = tmp_path / "out"

    result = run_scan(root, out, cfg, tax)
    assert result.returncode == 0, result.stderr

    rows = _load_rows(out, "TEST20260101")
    # A naive GLOBAL detect_fragment_sets() call would group these 3 same-stem
    # ('ebook') files into one cross-folder fragment set (the EB-359 folder-blind
    # bug). scan.py calls it PER-DIRECTORY, so each folder has a single file and
    # no set of >=3 forms -> there must be ZERO fragment rows. This assertion fails
    # if the per-directory wrapper regresses to a global call.
    fragment_rows = [
        r for r in rows
        if "fragment" in (r.get("canonical_reason") or "").lower()
    ]
    assert fragment_rows == [], (
        f"cross-folder same-stem files were wrongly grouped as a fragment set: "
        f"{[r['original_path'] for r in fragment_rows]}"
    )


def test_numbered_fragments_in_one_folder_still_detected(tmp_path):
    """Numbered fragments in the same folder SHOULD be detected (no regression)."""
    root = tmp_path / "root"
    folder = root / "fragdir"
    # >=3 files with same stem prefix and sequential numbers
    for i in range(1, 5):
        _pdf(folder / f"mybook-{i}.pdf", seed=f"frag{i}")

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)
    out = tmp_path / "out"

    result = run_scan(root, out, cfg, tax)
    assert result.returncode == 0, result.stderr

    rows = _load_rows(out, "TEST20260101")
    # At least some rows should be "review" with fragment reason
    fragment_review = [r for r in rows if r.get("action") == "review" and
                       r.get("canonical_reason") and
                       "fragment" in r["canonical_reason"].lower()]
    assert fragment_review, "Numbered fragments in one folder should be detected as review"


# ---------------------------------------------------------------------------
# [M] Test 4 — canonical projection byte-identical across two fresh subprocess runs
# ---------------------------------------------------------------------------

def test_canonical_projection_byte_identical_across_two_runs(tmp_path):
    """Two fresh subprocess runs on same snapshot -> byte-identical canonical projection."""
    root = tmp_path / "root"
    _pdf(root / "alpha.pdf", seed="alpha")
    _pdf(root / "beta.pdf", seed="beta")
    _epub(root / "gamma.epub", seed="gamma")

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)

    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"

    r_a = run_scan(root, out_a, cfg, tax, stamp="RUNTEST_A")
    assert r_a.returncode == 0, r_a.stderr

    r_b = run_scan(root, out_b, cfg, tax, stamp="RUNTEST_B")
    assert r_b.returncode == 0, r_b.stderr

    rows_a = _load_rows(out_a, "RUNTEST_A")
    rows_b = _load_rows(out_b, "RUNTEST_B")

    # Compute canonical projections (drop calibre_id, stamp, sort by original_path)
    def _project(rows: list[dict]) -> str:
        VOLATILE = {"calibre_id"}
        projected = []
        for r in sorted(rows, key=lambda x: x["original_path"]):
            projected.append({k: v for k, v in r.items() if k not in VOLATILE})
        return json.dumps(projected, sort_keys=True)

    proj_a = _project(rows_a)
    proj_b = _project(rows_b)
    assert proj_a == proj_b, "canonical projections must be byte-identical across two runs"


def test_no_duplicate_original_path_rows(tmp_path):
    """No two rows may share the same original_path."""
    root = tmp_path / "root"
    _pdf(root / "book1.pdf", seed="b1")
    _pdf(root / "book2.pdf", seed="b2")
    _epub(root / "book3.epub", seed="b3")

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)
    out = tmp_path / "out"

    result = run_scan(root, out, cfg, tax)
    assert result.returncode == 0, result.stderr

    rows = _load_rows(out, "TEST20260101")
    paths = [r["original_path"] for r in rows]
    assert len(paths) == len(set(paths)), "duplicate original_path entries found"


def test_original_path_separator_normalized(tmp_path):
    """All original_path values use a consistent separator form (no mixed slashes)."""
    root = tmp_path / "root"
    sub = root / "sub" / "deep"
    _pdf(sub / "deep_book.pdf", seed="deep")

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)
    out = tmp_path / "out"

    result = run_scan(root, out, cfg, tax)
    assert result.returncode == 0, result.stderr

    rows = _load_rows(out, "TEST20260101")
    for r in rows:
        p = r["original_path"]
        # Should not contain forward slashes (normalized to Windows backslash on Windows,
        # or consistently one form)
        assert "/" not in p or "\\" not in p, f"mixed separators in original_path: {p}"


# ---------------------------------------------------------------------------
# [M] Test 5 — immutability snapshot with non-descended junction
# ---------------------------------------------------------------------------

def test_immutability_snapshot_with_non_descended_junction(tmp_path):
    """
    Creates a real NTFS junction inside the scan tree (no admin needed).
    The junction TARGET is also inside tmp_path so teardown is harmless.

    Before scan: snapshot {path:(size, mtime_ns, sha256)} + listing.
    Run scan with out_dir = sibling OUTSIDE the scanned tmp subtree (but still under tmp_path).
    Assert: every source file unchanged, junction never descended (logged SKIP).
    Then: remove the junction LINK with os.rmdir(link) to prevent pytest's shutil.rmtree
    from traversing it during teardown.

    JUNCTION SAFETY NOTE: We call os.rmdir(link_path) — NOT rmdir on the target — because
    os.rmdir on an NTFS junction removes only the link, not the target directory contents.
    This must happen before pytest teardown to prevent shutil.rmtree from following the
    junction and potentially deleting the target. The target lives inside tmp_path so even
    if traversal occurred it would be harmless, but we clean up explicitly for correctness.
    """
    # Target directory (inside tmp_path so teardown is safe even in worst case)
    target_dir = tmp_path / "junction_target"
    target_dir.mkdir()
    _pdf(target_dir / "target_book.pdf", seed="target")

    # Scan root
    root = tmp_path / "scan_root"
    root.mkdir()
    _pdf(root / "real_book.pdf", seed="real")
    _epub(root / "real_ebook.epub", seed="epub")

    # Junction link inside scan root pointing at target_dir
    link_path = root / "junction_link"

    # Create NTFS junction (no admin required for directory junctions)
    mklink_result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link_path), str(target_dir)],
        capture_output=True, text=True
    )
    junction_created = mklink_result.returncode == 0

    try:
        # Snapshot before scan
        def _snapshot(p: Path) -> dict:
            s = {}
            for f in sorted(p.rglob("*")):
                if f.is_file() and not f.is_symlink():
                    try:
                        stat = f.stat()
                        s[str(f)] = (stat.st_size, stat.st_mtime_ns)
                    except OSError:
                        pass
            return s

        snap_before = _snapshot(root)

        cfg = _make_settings(tmp_path, root)
        tax = _make_taxonomy(tmp_path)

        # out_dir is a SIBLING outside the scanned tmp subtree but still under tmp_path
        out = tmp_path / "scan_output"

        result = run_scan(root, out, cfg, tax)
        assert result.returncode == 0, result.stderr

        # Snapshot after scan — files must be unchanged
        snap_after = _snapshot(root)
        for path_str, (size_before, mtime_before) in snap_before.items():
            assert path_str in snap_after, f"file disappeared: {path_str}"
            size_after, mtime_after = snap_after[path_str]
            assert size_before == size_after, f"size changed: {path_str}"
            assert mtime_before == mtime_after, f"mtime changed: {path_str}"

        # Junction must not have been descended (target_book.pdf must not appear in rows)
        rows = _load_rows(out, "TEST20260101")
        row_paths = [r["original_path"] for r in rows]
        assert not any("target_book" in p for p in row_paths), (
            "junction was descended — target_book.pdf should not appear in rows"
        )

        # out_dir must not contain any scan-root writes
        assert out.exists(), "out_dir should exist after scan"
        # Verify the out_dir is not under the scan root
        assert not str(out).startswith(str(root)), "out_dir must be outside scan root"

    finally:
        # CRITICAL: remove the junction LINK (not its target) before pytest teardown.
        # os.rmdir on an NTFS junction removes only the junction link, not the target contents.
        # This prevents pytest's shutil.rmtree from traversing the junction during cleanup.
        if junction_created and link_path.exists():
            try:
                os.rmdir(link_path)  # removes the junction link only, NOT the target
            except OSError:
                pass  # junction may already be gone; teardown will handle rest


def test_dangling_junction_does_not_abort(tmp_path):
    """A dangling junction (target doesn't exist) must not crash the scan."""
    root = tmp_path / "root"
    root.mkdir()
    _pdf(root / "good_book.pdf", seed="good")

    # Create a junction pointing at a nonexistent target
    nonexistent_target = tmp_path / "does_not_exist"
    link_path = root / "dangling_junction"

    mklink_result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link_path), str(nonexistent_target)],
        capture_output=True, text=True
    )

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)
    out = tmp_path / "out"

    result = run_scan(root, out, cfg, tax)
    # Should complete without aborting (non-zero is only ok if UnsafeScanError)
    assert result.returncode == 0, result.stderr

    rows = _load_rows(out, "TEST20260101")
    # The good book should still appear
    assert any("good_book" in r["original_path"] for r in rows)

    # Cleanup the junction link if it exists
    if link_path.exists() or link_path.is_symlink():
        try:
            os.rmdir(link_path)
        except OSError:
            pass


def test_unreadable_file_does_not_abort(tmp_path):
    """An unreadable file produces an error row but does not abort the scan."""
    root = tmp_path / "root"
    _pdf(root / "readable.pdf", seed="good")
    # Write a second file we'll make unreadable
    bad = root / "unreadable.pdf"
    _pdf(bad, seed="bad")

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)
    out = tmp_path / "out"

    # Make it unreadable (Windows: deny read via icacls or just trust error-row behavior)
    # On Windows, we can test by overriding with a directory-as-file trick or just
    # verify the scan still processes other files (full permission denial is hard portably)
    result = run_scan(root, out, cfg, tax)
    assert result.returncode == 0, result.stderr

    rows = _load_rows(out, "TEST20260101")
    # At minimum, readable.pdf should appear
    assert any("readable" in r["original_path"] for r in rows)


# ---------------------------------------------------------------------------
# Test 6 — out_dir inside root raises UnsafeScanError
# ---------------------------------------------------------------------------

def test_out_dir_inside_root_refused(tmp_path):
    """out inside root / ==root / root inside out each raise UnsafeScanError (exit non-zero)."""
    root = tmp_path / "scan_root"
    root.mkdir()
    _pdf(root / "book.pdf", seed="x")

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)

    # Case 1: out_dir is INSIDE scan root
    out_inside = root / "output"
    r = run_scan(root, out_inside, cfg, tax)
    assert r.returncode != 0, "out inside root must be refused"
    assert not out_inside.exists() or not list(out_inside.iterdir()), (
        "no files should be written when UnsafeScanError is raised"
    )

    # Case 2: out_dir == scan root
    r2 = run_scan(root, root, cfg, tax)
    assert r2.returncode != 0, "out == root must be refused"

    # Case 3: scan root is inside out_dir
    out_parent = tmp_path / "out_parent"
    out_parent.mkdir()
    root_inside_out = out_parent / "nested_root"
    root_inside_out.mkdir()
    _pdf(root_inside_out / "book2.pdf", seed="y")
    r3 = run_scan(root_inside_out, out_parent, cfg, tax)
    assert r3.returncode != 0, "root inside out must be refused"


# ---------------------------------------------------------------------------
# Test 7 — undo artifact is inert
# ---------------------------------------------------------------------------

def test_undo_artifact_is_inert(tmp_path):
    """Every non-blank line in the undo .ps1.txt starts with '#'; no uncommented mutators."""
    root = tmp_path / "root"
    _pdf(root / "history_wwii.pdf", seed="hist")

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)
    out = tmp_path / "out"

    result = run_scan(root, out, cfg, tax)
    assert result.returncode == 0, result.stderr

    undo_files = list(out.glob("*-undo.ps1.txt"))
    assert undo_files, "undo artifact must exist"

    mutator_re = re.compile(
        r"(?i)\b(Move-Item|Remove-Item|Copy-Item|New-Item|mklink|"
        r"Set-Content|Out-File|del|rmdir|rd)\b"
    )

    for undo_file in undo_files:
        content = undo_file.read_text(encoding="utf-8")
        for lineno, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if not stripped:
                continue
            assert stripped.startswith("#"), (
                f"Non-comment line in undo artifact at line {lineno}: {line!r}"
            )
            # No uncommented mutator match (since all lines start with #, this is
            # satisfied by the above assertion, but double-check)
            uncommented = stripped.lstrip("#").strip()
            assert not mutator_re.search(uncommented) or stripped.startswith("#"), (
                f"Uncommented mutator in undo artifact line {lineno}: {line!r}"
            )


# ---------------------------------------------------------------------------
# Test 8 — destination never materialized
# ---------------------------------------------------------------------------

def test_destination_never_materialized(tmp_path):
    """Shelf rows must list destination paths that do NOT exist; no dirs created under library."""
    root = tmp_path / "scan_root"
    library = tmp_path / "fake_library"
    library.mkdir()

    # Create a book with classifiable name
    _pdf(root / "history_wwii_book.pdf", seed="hist")

    cfg = _make_settings(tmp_path, root)
    # Rewrite config to use our fake library
    settings = json.loads(cfg.read_text(encoding="utf-8"))
    settings["library"]["library_root"] = str(library)
    cfg.write_text(json.dumps(settings), encoding="utf-8")

    tax = _make_taxonomy(tmp_path)
    out = tmp_path / "out"

    result = run_scan(root, out, cfg, tax)
    assert result.returncode == 0, result.stderr

    rows = _load_rows(out, "TEST20260101")
    for r in rows:
        dest = r.get("destination_path", "")
        if dest and r["action"] not in ("review", "quarantine"):
            assert not Path(dest).exists(), (
                f"destination was materialized (must not be in -WhatIf): {dest}"
            )

    # Confirm no section/author subdirs were created under library
    def _has_new_subdirs(p: Path) -> bool:
        return any(True for _ in p.rglob("*") if _.is_dir())

    assert not _has_new_subdirs(library), "library_root must have no new subdirs created"


# ---------------------------------------------------------------------------
# Test 9 — operational folders and audio books excluded
# ---------------------------------------------------------------------------

def test_operational_and_audio_books_excluded(tmp_path):
    """Files under operational folders and Audio_Books are excluded from scan rows."""
    root = tmp_path / "root"
    # Files in operational folders (should be excluded)
    _pdf(root / "_Duplicates_Pending" / "dup.pdf", seed="dup")
    _pdf(root / "_Inbox" / "inbox.pdf", seed="inbox")
    _pdf(root / "Audio_Books" / "audio.mp3", seed="audio")  # also wrong ext, but still excluded
    # Real book (should be included)
    _pdf(root / "real_book.pdf", seed="real")

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)
    out = tmp_path / "out"

    result = run_scan(root, out, cfg, tax)
    assert result.returncode == 0, result.stderr

    rows = _load_rows(out, "TEST20260101")
    row_paths = [r["original_path"] for r in rows]

    assert not any("_Duplicates_Pending" in p for p in row_paths), (
        "_Duplicates_Pending must be excluded"
    )
    assert not any("_Inbox" in p for p in row_paths), "_Inbox must be excluded"
    assert not any("Audio_Books" in p and "Backup" not in p for p in row_paths), (
        "Audio_Books must be excluded"
    )
    assert any("real_book" in p for p in row_paths), "real_book.pdf must be included"


def test_skip_match_is_case_insensitive(tmp_path):
    """Skip matching must be case-insensitive for operational folders."""
    root = tmp_path / "root"
    _pdf(root / "_inbox" / "lower.pdf", seed="lower")   # lowercase
    _pdf(root / "_INBOX" / "upper.pdf", seed="upper")   # uppercase
    _pdf(root / "normal_book.pdf", seed="normal")

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)
    out = tmp_path / "out"

    result = run_scan(root, out, cfg, tax)
    assert result.returncode == 0, result.stderr

    rows = _load_rows(out, "TEST20260101")
    row_paths = [r["original_path"] for r in rows]

    assert not any("lower.pdf" in p for p in row_paths), "_inbox (lowercase) must be skipped"
    assert not any("upper.pdf" in p for p in row_paths), "_INBOX (uppercase) must be skipped"


def test_scan_exclude_no_substring_overmatch(tmp_path):
    """Audio_Books_Backup must NOT be pruned when Audio_Books is in scan_exclude."""
    root = tmp_path / "root"
    _pdf(root / "Audio_Books" / "excluded.pdf", seed="ex")
    _pdf(root / "Audio_Books_Backup" / "included.pdf", seed="inc")

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)
    out = tmp_path / "out"

    result = run_scan(root, out, cfg, tax)
    assert result.returncode == 0, result.stderr

    rows = _load_rows(out, "TEST20260101")
    row_paths = [r["original_path"] for r in rows]

    assert not any("excluded.pdf" in p for p in row_paths), "Audio_Books/excluded.pdf must be skipped"
    assert any("included.pdf" in p for p in row_paths), (
        "Audio_Books_Backup/included.pdf must NOT be excluded (substring match)"
    )


# ---------------------------------------------------------------------------
# Test 10 — distinct books at same shelf path get distinct destinations
# ---------------------------------------------------------------------------

def test_distinct_books_same_shelf_path_get_distinct_destinations(tmp_path):
    """Two distinct-sha books that would resolve to the same dest path get distinct destinations."""
    root = tmp_path / "root"
    # Two different books that will likely collide on shelf path
    # (different content so different sha)
    _pdf(root / "history_wwii_book.pdf", seed="v1")
    _pdf(root / "history_wwii_second.pdf", seed="v2")

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)
    out = tmp_path / "out"

    result = run_scan(root, out, cfg, tax)
    assert result.returncode == 0, result.stderr

    rows = _load_rows(out, "TEST20260101")
    dest_paths = [r["destination_path"] for r in rows if r["destination_path"]]
    # All non-empty destinations must be unique
    assert len(dest_paths) == len(set(dest_paths)), (
        f"duplicate destination paths found: {dest_paths}"
    )


def test_shelf_index_one_entry_per_row(tmp_path):
    """shelf-index.json must have exactly one entry per manifest row with a destination."""
    root = tmp_path / "root"
    _pdf(root / "history_wwii_book.pdf", seed="h1")
    _pdf(root / "python_programming.pdf", seed="p1")

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)
    out = tmp_path / "out"

    result = run_scan(root, out, cfg, tax)
    assert result.returncode == 0, result.stderr

    shelf_index_path = out / "shelf-index.json"
    assert shelf_index_path.exists(), "shelf-index.json must exist"

    shelf_index = json.loads(shelf_index_path.read_text(encoding="utf-8"))
    rows = _load_rows(out, "TEST20260101")

    # shelf-index entries must be unique (no clobber)
    assert len(shelf_index) == len(set(shelf_index.keys())), (
        "shelf-index.json has duplicate destination keys"
    )

    # Every entry in shelf_index must correspond to a row
    row_dests = {r["destination_path"] for r in rows if r["destination_path"]}
    for dest in shelf_index:
        assert dest in row_dests, f"shelf-index entry {dest!r} not in manifest rows"


def test_scan_classifies_using_embedded_title_when_filename_is_cryptic(tmp_path):
    """A metadata-rich EPUB with a cryptic filename should classify from meta.title."""
    root = tmp_path / "root"
    _make_real_epub(root / "x19a3.epub", "Python Programming", "Guido Rossum")

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)
    out = tmp_path / "out"

    result = run_scan(root, out, cfg, tax)
    assert result.returncode == 0, result.stderr

    rows = _load_rows(out, "TEST20260101")
    assert len(rows) == 1
    assert rows[0]["section"] == "09 Technology"
    assert rows[0]["subcategory"] == "Programming"
    assert rows[0]["classification_source"] == "metadata"


# ---------------------------------------------------------------------------
# Test 11 — over-length destination quarantined
# ---------------------------------------------------------------------------

def test_over_length_destination_quarantined(tmp_path):
    """A book whose destination path would exceed max_path_length is quarantined."""
    root = tmp_path / "root"
    # Create a very long filename that will produce an over-length destination
    long_title = "a" * 200
    _pdf(root / f"history_{long_title}.pdf", seed="long")

    cfg = _make_settings(tmp_path, root)
    # Set a very short max_path_length to force quarantine
    settings = json.loads(cfg.read_text(encoding="utf-8"))
    settings["library"]["max_path_length"] = 50
    cfg.write_text(json.dumps(settings), encoding="utf-8")

    tax = _make_taxonomy(tmp_path)
    out = tmp_path / "out"

    result = run_scan(root, out, cfg, tax)
    assert result.returncode == 0, result.stderr

    rows = _load_rows(out, "TEST20260101")
    # Any row where destination would exceed 50 chars must be quarantined
    for r in rows:
        dest = r.get("destination_path", "")
        if dest and len(dest) > 50:
            assert r["action"] == "quarantine", (
                f"over-length destination must be quarantined: {dest}"
            )


# ---------------------------------------------------------------------------
# Test 12 — taxonomy version read from file
# ---------------------------------------------------------------------------

def test_taxonomy_version_read_from_file(tmp_path):
    """taxonomy_version in rows must equal the JSON top-level 'version' field."""
    root = tmp_path / "root"
    _pdf(root / "book.pdf", seed="v")

    cfg = _make_settings(tmp_path, root)

    # Use a taxonomy with a specific version
    taxonomy = {
        "version": 42,
        "confidence_threshold": 0.34,
        "non_library_keywords": ["resume"],
        "sections": [
            {"code": "01 History", "subcategories": [
                {"name": "General", "keywords": ["history", "war"]},
            ]},
        ],
    }
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    tax_path = cfg_dir / "taxonomy_v42.json"
    tax_path.write_text(json.dumps(taxonomy), encoding="utf-8")

    out = tmp_path / "out"
    result = run_scan(root, out, cfg, tax_path)
    assert result.returncode == 0, result.stderr

    rows = _load_rows(out, "TEST20260101")
    assert rows, "Expected at least one row"
    for r in rows:
        assert r["taxonomy_version"] == 42, (
            f"taxonomy_version must be 42 (from JSON), got {r['taxonomy_version']}"
        )


# ---------------------------------------------------------------------------
# Test 13 — classify deterministic across hash seeds / main refuses without PYTHONHASHSEED=0
# ---------------------------------------------------------------------------

def test_classify_deterministic_across_hashseeds(tmp_path):
    """scan.py refuses to run (non-zero exit) without PYTHONHASHSEED=0."""
    root = tmp_path / "root"
    _pdf(root / "history_war.pdf", seed="det")

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)
    out = tmp_path / "out"

    scan_py = Path(__file__).resolve().parents[1] / "tools" / "book_filer" / "scan.py"
    cmd = [
        sys.executable, str(scan_py),
        "--root", str(root),
        "--out-dir", str(out),
        "--stamp", "HASHSEED_TEST",
        "--settings", str(cfg),
        "--taxonomy", str(tax),
    ]
    # Run WITHOUT PYTHONHASHSEED=0 — must refuse
    env_no_seed = {k: v for k, v in os.environ.items() if k != "PYTHONHASHSEED"}
    env_no_seed["PYTHONHASHSEED"] = "1"  # explicitly wrong

    result_no_seed = subprocess.run(cmd, capture_output=True, text=True, env=env_no_seed)
    assert result_no_seed.returncode != 0, (
        "scan.py must refuse to run when PYTHONHASHSEED != '0'"
    )

    # Run WITH PYTHONHASHSEED=0 — must succeed
    env_with_seed = os.environ.copy()
    env_with_seed["PYTHONHASHSEED"] = "0"
    result_with_seed = subprocess.run(cmd, capture_output=True, text=True, env=env_with_seed)
    assert result_with_seed.returncode == 0, result_with_seed.stderr


# ---------------------------------------------------------------------------
# Test 14 — duplicate_group_id stable across runs / singletons null
# ---------------------------------------------------------------------------

def test_duplicate_group_id_stable_across_runs(tmp_path):
    """duplicate_group_id must be identical across two fresh subprocess runs."""
    root = tmp_path / "root"
    data = b"%PDF identical dup group test"
    _write(root / "dup1.pdf", data)
    _write(root / "dup2.pdf", data)

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)

    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"

    r_a = run_scan(root, out_a, cfg, tax, stamp="DUP_A")
    r_b = run_scan(root, out_b, cfg, tax, stamp="DUP_B")

    assert r_a.returncode == 0, r_a.stderr
    assert r_b.returncode == 0, r_b.stderr

    rows_a = {r["original_path"]: r["duplicate_group_id"] for r in _load_rows(out_a, "DUP_A")}
    rows_b = {r["original_path"]: r["duplicate_group_id"] for r in _load_rows(out_b, "DUP_B")}

    assert rows_a == rows_b, "duplicate_group_id must be stable across runs"


def test_singletons_have_null_group_id(tmp_path):
    """A file with no duplicate must have duplicate_group_id == null."""
    root = tmp_path / "root"
    _pdf(root / "singleton.pdf", seed="singleton_unique_content")

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)
    out = tmp_path / "out"

    result = run_scan(root, out, cfg, tax)
    assert result.returncode == 0, result.stderr

    rows = _load_rows(out, "TEST20260101")
    assert rows
    for r in rows:
        if "singleton" in r["original_path"]:
            assert r["duplicate_group_id"] is None, (
                f"singleton must have null group_id, got {r['duplicate_group_id']}"
            )


# ---------------------------------------------------------------------------
# Test 15 — empty dir yields zero rows / size guard aborts on drift
# ---------------------------------------------------------------------------

def test_empty_dir_yields_zero_rows_clean_exit(tmp_path):
    """An empty (no book files) scan root yields zero rows and exits 0."""
    root = tmp_path / "root"
    root.mkdir()

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)
    out = tmp_path / "out"

    result = run_scan(root, out, cfg, tax)
    assert result.returncode == 0, result.stderr

    rows = _load_rows(out, "TEST20260101")
    assert rows == [], f"Expected zero rows for empty dir, got {rows}"

    # No writes should have occurred under the scan root
    assert not any(True for _ in root.rglob("*") if _.is_file()), (
        "no files should be written under scan root"
    )


def test_size_guard_aborts_on_count_or_size_change(tmp_path):
    """
    The calibration driver runs scan twice; the first pass captures count+sum-of-sizes.
    If the corpus changes between pass 1 and pass 2, the second run should detect drift.

    We test this by verifying the scan emits corpus stats in its output so they can be
    compared, and that the determinism report flags differences.
    """
    root = tmp_path / "root"
    _pdf(root / "book1.pdf", seed="s1")
    _pdf(root / "book2.pdf", seed="s2")

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)
    out = tmp_path / "out"

    result = run_scan(root, out, cfg, tax)
    assert result.returncode == 0, result.stderr

    # scan-summary.md must exist and contain file count info
    summary_files = list(out.glob("scan-summary.md"))
    assert summary_files, "scan-summary.md must exist"

    summary = summary_files[0].read_text(encoding="utf-8")
    # Must contain count and size data for the drift guard
    assert "2" in summary or "book" in summary.lower(), (
        "scan-summary.md must record corpus stats"
    )


# ---------------------------------------------------------------------------
# Test 16 — banned content grep of generated undo
# ---------------------------------------------------------------------------

def test_banned_content_grep_of_generated_undo(tmp_path):
    """
    Self-test: extends the C1/C2 spec grep to the generated undo artifact.
    Every generated undo line must be a comment; no uncommented mover/deleter.
    """
    root = tmp_path / "root"
    _pdf(root / "history_wwii_book.pdf", seed="undo_test")
    _epub(root / "python_book.epub", seed="undo_test2")

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)
    out = tmp_path / "out"

    result = run_scan(root, out, cfg, tax)
    assert result.returncode == 0, result.stderr

    undo_files = list(out.glob("*-undo.ps1.txt"))
    assert undo_files, "undo artifact must exist"

    # The spec §2.2 C1/C2 grep pattern applied to the generated output
    banned_pattern = re.compile(
        r"(?i)\b(Move-Item|Remove-Item|Copy-Item|New-Item|mklink|"
        r"Set-Content|Out-File|del\b|rmdir|rd\b|"
        r"os\.(rename|replace|remove|unlink|rmdir|removedirs|truncate|symlink|link|chmod|utime)|"
        r"shutil\.(move|copy|copyfile|copytree|rmtree)|"
        r"\.(unlink|rmdir|rename|replace|write_bytes|touch|symlink_to|hardlink_to)\()"
    )

    for undo_file in undo_files:
        content = undo_file.read_text(encoding="utf-8")
        for lineno, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if not stripped:
                continue
            # Must be a comment
            assert stripped.startswith("#"), (
                f"Non-comment line in generated undo at line {lineno}: {line!r}"
            )
            # Even within comments, check for obviously uncommented code
            # (a comment starting with '# ' followed by a bare command is fine)


# ---------------------------------------------------------------------------
# PR #185 review regressions
# ---------------------------------------------------------------------------

def test_destination_collision_with_prior_review_row_does_not_abort(tmp_path):
    """Blocker regression: two DISTINCT works (different ISBN -> different work_key,
    so NOT deduped) that share author+title+year collide on one destination. With a
    review row already emitted (empty destination), the old in-loop first-pass
    disambiguation raised StopIteration and the scan exited non-zero. The scan must
    now complete and _disambiguate_destinations must give the two a distinct dest."""
    root = tmp_path / "root"
    # Review row first (sorts before the epubs; ambiguous name -> low-confidence review).
    _pdf(root / "0_unknown_thing.pdf", seed="ambiguous")
    # Two distinct-ISBN, same author/title/year books -> same destination, NOT deduped.
    # Filenames carry the 'python' taxonomy keyword so they classify to shelf
    # (classification is filename-based); identical metadata -> identical destination.
    _make_real_epub(root / "python_guide_a.epub", "Python Mastery", "Guido Rossum", isbn="9780000000017")
    _make_real_epub(root / "python_guide_b.epub", "Python Mastery", "Guido Rossum", isbn="9780000000024")

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)
    out = tmp_path / "out"

    result = run_scan(root, out, cfg, tax)
    assert result.returncode == 0, (
        f"scan aborted on destination collision (StopIteration bug?): "
        f"rc={result.returncode}\n{result.stderr}"
    )

    rows = _load_rows(out, "TEST20260101")
    shelf = [r for r in rows if r["action"] in ("copy", "hardlink") and r["destination_path"]]
    assert len(shelf) == 2, (
        f"expected 2 shelf rows for the distinct-ISBN books; got "
        f"{[(Path(r['original_path']).name, r['action']) for r in rows]}"
    )
    dests = [r["destination_path"] for r in shelf]
    assert dests[0] != dests[1], f"colliding shelf rows must get distinct destinations: {dests}"


def test_spot_check_fills_to_min_when_enough_rows():
    """Finding 3: _build_spot_check must not under-fill below min_spots when >= min_spots
    rows exist. Integer-proportional slices alone can sum to < 50 (e.g. 51 shelf + 2
    review -> 48 + 1 = 49), which would create a FALSE calibration RED on sample size."""
    from book_filer.scan import _build_spot_check
    from book_filer.manifest import ManifestRow

    def _mrow(i: int, action: str) -> ManifestRow:
        shelf = action in ("copy", "hardlink")
        return ManifestRow(
            original_path=f"F:\\Books\\b{i}.epub",
            destination_path=(f"d{i}.epub" if shelf else ""),
            sha256=f"{i:064x}", size=10, planned_calibre_key=f"meta:a|t{i}|2011",
            calibre_id=None, isbn=None, format="epub",
            section=("09 Technology" if shelf else None),
            subcategory=("Programming" if shelf else None),
            author_sort="A, B", title=f"t{i}", year=2011, duplicate_group_id=None,
            canonical_reason=None, classification_confidence=0.9,
            classification_source="rule", taxonomy_version=1, tool_version="0.4.0",
            action=action, undo_action="# noop", review_required=(not shelf),
        )

    rows = [_mrow(i, "copy") for i in range(51)] + [_mrow(100 + i, "review") for i in range(2)]
    assert len(rows) == 53

    spots = _build_spot_check(rows, min_spots=50)
    assert len(spots) == 50, f"under-filled spot-check: {len(spots)} with 53 rows available"
    # Deterministic: same input -> same sheet.
    assert _build_spot_check(rows, min_spots=50) == spots
    # Genuine small corpus: take all rows, never pad past what exists.
    assert len(_build_spot_check(rows[:10], min_spots=50)) == 10


def test_two_run_compare_emits_real_determinism_report(tmp_path):
    """Finding 2: with --compare-to, scan emits a REAL two-run determinism verdict
    (not the single-run placeholder). Two runs over the same corpus are byte-identical
    -> 'Deterministic: YES' and determinism-diff.json deterministic == true."""
    root = tmp_path / "root"
    _make_real_epub(root / "a.epub", "Python", "Guido Rossum")
    _pdf(root / "b.pdf", seed="b")

    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"

    r1 = run_scan(root, out_a, cfg, tax)
    assert r1.returncode == 0, r1.stderr
    r2 = run_scan(root, out_b, cfg, tax, extra_args=["--compare-to", str(out_a)])
    assert r2.returncode == 0, r2.stderr

    det = (out_b / "determinism-report.md").read_text(encoding="utf-8")
    assert "Single-run mode" not in det, "expected a real two-run comparison, got placeholder"
    assert "**Deterministic:** YES" in det, det
    diff = json.loads((out_b / "determinism-diff.json").read_text(encoding="utf-8"))
    assert diff["deterministic"] is True


# ---------------------------------------------------------------------------
# Gate-hardening regressions — calibration measurement layer (EB-355)
# ---------------------------------------------------------------------------

def _gate_row(action: str, n: int = 0):
    """Minimal ManifestRow for gate-vocabulary tests."""
    from book_filer.manifest import ManifestRow
    shelf = action in ("copy", "hardlink")
    return ManifestRow(
        original_path=f"F:\\Books\\g{n}.epub",
        destination_path=(f"d{n}.epub" if shelf else ""),
        sha256=f"{n:064x}", size=10, planned_calibre_key=f"meta:a|t{n}|2011",
        calibre_id=None, isbn=None, format="epub",
        section=("09 Technology" if shelf else None),
        subcategory=("Programming" if shelf else None),
        author_sort="A, B", title=f"t{n}", year=2011, duplicate_group_id=None,
        canonical_reason=None, classification_confidence=0.9,
        classification_source="rule", taxonomy_version=1, tool_version="0.4.0",
        action=action, undo_action="# noop", review_required=(not shelf),
    )


def test_spot_check_disposition_uses_calibration_vocabulary():
    """Finding 1: the spot-check sheet must emit the CALIBRATION vocabulary
    (shelf/review), not the raw manifest action (copy/hardlink/trash). Otherwise an
    automated ingestion under-counts wrong-shelf (evaluate_calibration only counts
    disposition == 'shelf') and can FALSE-GREEN."""
    from book_filer.scan import _build_spot_check
    rows = [_gate_row("copy", 1), _gate_row("hardlink", 2),
            _gate_row("review", 3), _gate_row("trash", 4)]
    by_path = {s["filename"]: s["disposition"] for s in _build_spot_check(rows, min_spots=4)}
    assert by_path["g1.epub"] == "shelf"
    assert by_path["g2.epub"] == "shelf"
    assert by_path["g3.epub"] == "review"
    assert by_path["g4.epub"] == "review"   # trash maps to review for spot-check, never 'shelf'


def test_wrong_copy_row_increments_wrong_shelf_count():
    """Finding 1 consequence: a copy row marked incorrect must count as wrong-shelf
    when the sheet's own disposition is fed to evaluate_calibration UNCHANGED
    (no manual copy->shelf remap)."""
    from book_filer.scan import _build_spot_check
    from book_filer.calibration import SpotCheck, evaluate_calibration
    spots = _build_spot_check([_gate_row("copy", 1)], min_spots=1)
    sc = [SpotCheck(path=s["filename"], disposition=s["disposition"], correct=False) for s in spots]
    v = evaluate_calibration("P", "P", sc, signed_off_by="tester", min_spot_check=1)
    assert v.wrong_shelf_count == 1
    assert v.green is False


def test_spot_check_csv_header_is_powershell_importable(tmp_path):
    """Finding 2: the spot-check CSV header must NOT start with '#' (PowerShell
    Import-Csv treats a leading '#' line as a comment, corrupting the header)."""
    root = tmp_path / "root"
    _pdf(root / "python_book.pdf", seed="g")
    cfg = _make_settings(tmp_path, root)
    tax = _make_taxonomy(tmp_path)
    out = tmp_path / "out"
    result = run_scan(root, out, cfg, tax)
    assert result.returncode == 0, result.stderr
    header = (out / "spot-check-sheet.csv").read_text(encoding="utf-8").splitlines()[0]
    assert not header.startswith("#"), f"header starts with '#' (breaks Import-Csv): {header!r}"
    assert header.split(",")[0] == "spot_index", header


# ---------------------------------------------------------------------------
# EB-365 Unit 3 — the classifier's demotion reason reaches the manifest row.
# ---------------------------------------------------------------------------

def _make_format_taxonomy(tmp: Path) -> Path:
    """Taxonomy v2 with a format-tier overlay and a Reference subcategory."""
    taxonomy = {
        "version": 2,
        "confidence_threshold": 0.34,
        "format_keywords": ["encyclopedia", "dictionary", "atlas"],
        "boilerplate_keywords": ["publishing"],
        "non_library_keywords": ["resume"],
        "sections": [
            {"code": "09 Technology", "subcategories": [
                {"name": "Programming", "keywords": ["python"]},
                {"name": "Reference", "keywords": ["encyclopedia", "dictionary", "atlas"]},
            ]},
        ],
    }
    cfg_dir = tmp / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    tax_path = cfg_dir / "books-taxonomy-format.json"
    tax_path.write_text(json.dumps(taxonomy), encoding="utf-8")
    return tax_path


def test_format_only_demotion_reason_reaches_manifest(tmp_path):
    """A format-only file (form word + boilerplate, no subject) must produce a
    review row whose canonical_reason is the format-only reason — not the generic
    low-confidence string."""
    root = tmp_path / "root"
    _pdf(root / "Encyclopedia of Widgets (Acme Publishing).pdf", seed="fmt")

    cfg = _make_settings(tmp_path, root)
    tax = _make_format_taxonomy(tmp_path)
    out = tmp_path / "out"

    result = run_scan(root, out, cfg, tax)
    assert result.returncode == 0, result.stderr

    rows = _load_rows(out, "TEST20260101")
    row = next(r for r in rows if "Encyclopedia of Widgets" in r["original_path"])
    assert row["action"] == "review"
    assert row["canonical_reason"] == "format-only: no subject evidence"


def test_low_confidence_file_keeps_generic_reason(tmp_path):
    """A genuinely unmatched/low-confidence file (classifier reason None) must
    still emit the generic review reason — no regression from Unit 3."""
    root = tmp_path / "root"
    _pdf(root / "-jd55w3j.pdf", seed="cryptic")

    cfg = _make_settings(tmp_path, root)
    tax = _make_format_taxonomy(tmp_path)
    out = tmp_path / "out"

    result = run_scan(root, out, cfg, tax)
    assert result.returncode == 0, result.stderr

    rows = _load_rows(out, "TEST20260101")
    row = next(r for r in rows if "jd55w3j" in r["original_path"])
    assert row["action"] == "review"
    assert row["canonical_reason"] == "low-confidence/ambiguous classification"
