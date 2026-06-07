import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import select_batch_corpus as sbc  # noqa: E402


def _touch(p: Path, mb=1.0):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"0" * int(mb * 1024 * 1024))


def _fixture(tmp_path):
    arch = tmp_path / "archive"
    fresh = tmp_path / "fresh"
    for name in [
        "On First Principles - Origen.pdf", "Pilgrim People.pdf",
        "The Oil Kings - Cooper.pdf", "Mexico's Illicit Drug Networks.pdf",
        "The Return of the Gods - Cahn.pdf", "Python in easy steps.pdf",
        "Atomic Habits - Clear.pdf", "Decline of the West Vol 1 and 2.pdf",
        "Dionysius the Areopagite.pdf", "Reading Genesis After Darwin.pdf",
        "Fate of Empires - Glubb.pdf",
    ]:
        _touch(arch / name)
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
