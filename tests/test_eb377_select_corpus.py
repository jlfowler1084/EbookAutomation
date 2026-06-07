import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import select_batch_corpus as sbc  # noqa: E402


ANCHOR_NAMES = [
    "On First Principles - Origen.pdf", "Pilgrim People.pdf",
    "The Oil Kings - Cooper.pdf", "Mexico's Illicit Drug Networks.pdf",
    "The Return of the Gods - Cahn.pdf", "Python in easy steps.pdf",
    "Atomic Habits - Clear.pdf", "Decline of the West Vol 1 and 2.pdf",
    "Dionysius the Areopagite.pdf", "Reading Genesis After Darwin.pdf",
    "Fate of Empires - Glubb.pdf",
]


def _touch(p: Path, mb=1.0):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"0" * int(mb * 1024 * 1024))


def _anchors(arch: Path):
    for name in ANCHOR_NAMES:
        _touch(arch / name)


def _fixture(tmp_path):
    arch = tmp_path / "archive"
    fresh = tmp_path / "fresh"
    _anchors(arch)
    hist = fresh / "History"
    for i in range(30):
        _touch(hist / f"history_book_{i}.pdf", mb=2.0 + i * 0.1)
    for i in range(30):
        _touch(fresh / f"misc_book_{i}.pdf", mb=1.0)
    _touch(fresh / "2024_tax_return.pdf")
    _touch(fresh / "Joe_Fowler_resume.pdf")
    _touch(fresh / "history_book_0 (1).pdf")
    _touch(fresh / "audiobook.mp3")
    return arch, fresh


def test_counts_and_no_junk(tmp_path):
    arch, fresh = _fixture(tmp_path)
    result = sbc.select_corpus(str(arch), str(fresh), n_fresh=39, seed=377)
    assert len(result["anchors"]) == 11
    assert len(result["fresh"]) == 39
    picked = [Path(f["path"]).name for f in result["fresh"]]
    assert not any("tax_return" in n or "resume" in n for n in picked)
    assert not any(n.endswith(" (1).pdf") for n in picked)
    assert not any(n.endswith(".mp3") for n in picked)
    assert result["strata_counts"]


def test_seed_is_reproducible(tmp_path):
    arch, fresh = _fixture(tmp_path)
    a = sbc.select_corpus(str(arch), str(fresh), n_fresh=39, seed=377)
    b = sbc.select_corpus(str(arch), str(fresh), n_fresh=39, seed=377)
    assert [f["path"] for f in a["fresh"]] == [f["path"] for f in b["fresh"]]


def test_each_anchor_pattern_resolves_once(tmp_path):
    arch, _ = _fixture(tmp_path)
    for pat in sbc.ANCHOR_PATTERNS:
        matches = list(Path(arch).glob(pat))
        assert len(matches) == 1, f"{pat} -> {matches}"


def test_dedupes_by_basename(tmp_path):
    """Two fresh files sharing a basename must collapse to one — Task 3 joins by
    basename and stage() copies by basename, so a collision corrupts provenance."""
    arch = tmp_path / "archive"
    fresh = tmp_path / "fresh"
    _anchors(arch)
    _touch(fresh / "A" / "collide.pdf", mb=2.0)
    _touch(fresh / "B" / "collide.pdf", mb=2.0)
    _touch(fresh / "unique1.pdf", mb=1.0)
    _touch(fresh / "unique2.pdf", mb=1.0)
    result = sbc.select_corpus(str(arch), str(fresh), n_fresh=39, seed=377)
    names = [Path(f["path"]).name for f in result["fresh"]]
    assert names.count("collide.pdf") == 1
    assert len(result["fresh"]) == 3  # collide (deduped) + 2 uniques


def test_excludes_trash_and_nonbook_folders(tmp_path):
    arch = tmp_path / "archive"
    fresh = tmp_path / "fresh"
    _anchors(arch)
    _touch(fresh / "_Trash_Pending" / "old.pdf", mb=1.0)
    _touch(fresh / "Non_Books" / "spreadsheet.pdf", mb=1.0)
    _touch(fresh / "Real" / "good_book.pdf", mb=1.0)
    result = sbc.select_corpus(str(arch), str(fresh), n_fresh=39, seed=377)
    names = [Path(f["path"]).name for f in result["fresh"]]
    assert "old.pdf" not in names
    assert "spreadsheet.pdf" not in names
    assert "good_book.pdf" in names


def test_excludes_spanish_and_amazon_junk(tmp_path):
    arch = tmp_path / "archive"
    fresh = tmp_path / "fresh"
    _anchors(arch)
    _touch(fresh / "Tu pasabordo.pdf", mb=0.5)
    _touch(fresh / "Amazon.com - Order 123-4567890-1234567.pdf", mb=0.5)
    _touch(fresh / "A Real Book.pdf", mb=1.0)
    result = sbc.select_corpus(str(arch), str(fresh), n_fresh=39, seed=377)
    names = [Path(f["path"]).name for f in result["fresh"]]
    assert not any("pasabordo" in n.lower() for n in names)
    assert not any("amazon" in n.lower() for n in names)
    assert "A Real Book.pdf" in names


def test_caps_per_subject_folder(tmp_path):
    """No single subject folder may dominate the fresh picks — guards against the
    real-pool skew where one un-filed folder supplied ~70% of the batch."""
    from collections import Counter
    arch = tmp_path / "archive"
    fresh = tmp_path / "fresh"
    _anchors(arch)
    for i in range(30):  # one dominant folder
        _touch(fresh / "Dominant" / f"d{i}.pdf", mb=1.0)
    for folder in ("Alpha", "Beta", "Gamma", "Delta"):  # 4 small folders, 5 each
        for i in range(5):
            _touch(fresh / folder / f"{folder.lower()}{i}.pdf", mb=1.0)
    result = sbc.select_corpus(str(arch), str(fresh), n_fresh=20, seed=377,
                               max_per_folder=6)
    folders = Counter(Path(f["path"]).parent.name for f in result["fresh"])
    assert max(folders.values()) <= 6      # cap honored
    assert len(result["fresh"]) == 20      # still reaches the target


# ── EB-377 selector hardening (preflight review found ~8-10 bad fresh picks) ──

def test_excludes_undersized_stub(tmp_path):
    """Zero-byte / broken downloads (a ~1000pg book at 0 bytes) must be dropped —
    else they become kfx_failed noise, not pipeline signal."""
    arch = tmp_path / "archive"
    fresh = tmp_path / "fresh"
    _anchors(arch)
    _touch(fresh / "Real Book.pdf", mb=1.0)
    (fresh / "Broken Stub.pdf").parent.mkdir(parents=True, exist_ok=True)
    (fresh / "Broken Stub.pdf").write_bytes(b"0" * 2048)  # 2 KB stub
    result = sbc.select_corpus(str(arch), str(fresh), n_fresh=39, seed=377)
    names = [Path(f["path"]).name for f in result["fresh"]]
    assert "Real Book.pdf" in names
    assert "Broken Stub.pdf" not in names


def test_excludes_quarantine_folder(tmp_path):
    arch = tmp_path / "archive"
    fresh = tmp_path / "fresh"
    _anchors(arch)
    _touch(fresh / "_Quarantine" / "Obfuscating_Code.pdf", mb=1.0)
    _touch(fresh / "Good" / "real.pdf", mb=1.0)
    result = sbc.select_corpus(str(arch), str(fresh), n_fresh=39, seed=377)
    names = [Path(f["path"]).name for f in result["fresh"]]
    assert "Obfuscating_Code.pdf" not in names
    assert "real.pdf" in names


def test_excludes_annas_archive_fragments(tmp_path):
    """Split-facsimile fragments end '... Anna's Archive <n>' — drop them, but
    keep whole Anna's Archive files (no trailing bare number)."""
    arch = tmp_path / "archive"
    fresh = tmp_path / "fresh"
    _anchors(arch)
    _touch(fresh / "First Folio (hash -- Anna’s Archive 57.pdf", mb=0.2)
    _touch(fresh / "First Folio (hash -- Anna’s Archive 59.pdf", mb=0.2)
    _touch(fresh / "Whole Book -- Anna’s Archive.pdf", mb=1.0)
    result = sbc.select_corpus(str(arch), str(fresh), n_fresh=39, seed=377)
    names = [Path(f["path"]).name for f in result["fresh"]]
    assert not any("Archive 57" in n or "Archive 59" in n for n in names)
    assert any("Whole Book" in n for n in names)


def test_dedupes_same_title_different_filenames(tmp_path):
    """Same book, different filenames (basename-dedup misses these)."""
    arch = tmp_path / "archive"
    fresh = tmp_path / "fresh"
    _anchors(arch)
    _touch(fresh / "Wilkinson, Barton - Reading Galaxies After Sunset.pdf", mb=1.0)
    _touch(fresh / "Reading Galaxies After Sunset -- Barton Wilkinson Oxford.pdf", mb=1.0)
    _touch(fresh / "An Entirely Separate Treatise.pdf", mb=1.0)
    result = sbc.select_corpus(str(arch), str(fresh), n_fresh=39, seed=377)
    names = [Path(f["path"]).name for f in result["fresh"]]
    assert len([n for n in names if "Reading Galaxies After Sunset" in n]) == 1
    assert any("Entirely Separate" in n for n in names)


def test_drops_fresh_matching_an_anchor_title(tmp_path):
    """A fresh pick that is the same book as a regression anchor must be dropped
    (else the anchor is converted twice and double-counted)."""
    arch = tmp_path / "archive"
    fresh = tmp_path / "fresh"
    _anchors(arch)  # includes 'Reading Genesis After Darwin.pdf'
    _touch(fresh / "Wilkinson, Barton & David - Reading Genesis After Darwin.pdf", mb=1.0)
    _touch(fresh / "An Unrelated Monograph.pdf", mb=1.0)
    result = sbc.select_corpus(str(arch), str(fresh), n_fresh=39, seed=377)
    names = [Path(f["path"]).name for f in result["fresh"]]
    assert not any("Reading Genesis After Darwin" in n for n in names)
    assert any("Unrelated Monograph" in n for n in names)


def test_keeps_distinct_series_volumes(tmp_path):
    """Volume markers must survive title-dedup — Vol I/II/V are different books."""
    arch = tmp_path / "archive"
    fresh = tmp_path / "fresh"
    _anchors(arch)
    _touch(fresh / "Arthur Link - Woodrow Wilson Volume I The Road.pdf", mb=1.0)
    _touch(fresh / "Arthur Link - Woodrow Wilson Volume II The New Freedom.pdf", mb=1.0)
    _touch(fresh / "Arthur Link - Woodrow Wilson Volume V Campaigns.pdf", mb=1.0)
    result = sbc.select_corpus(str(arch), str(fresh), n_fresh=39, seed=377)
    vols = [n for n in [Path(f["path"]).name for f in result["fresh"]]
            if "Woodrow Wilson Volume" in n]
    assert len(vols) == 3
