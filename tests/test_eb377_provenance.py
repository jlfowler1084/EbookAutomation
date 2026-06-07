import sys, json, hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_batch_provenance as prov  # noqa: E402

_PARA = ('viii ON FIRST PRINCIPLES and the argument runs on here with more '
         'body text following the welded header token')
WELDED = (
    '<html><body>'
    + ''.join(f'<a id="page_{n}"></a><p>{_PARA}</p>' for n in range(1, 6))
    + '</body></html>'
)


def _manifest(tmp_path):
    src = tmp_path / "src" / "On First Principles.pdf"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"pdf-bytes")
    staged = tmp_path / "stage" / "On First Principles.pdf"
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"pdf-bytes")
    return {"anchors": [str(src)], "fresh": [],
            "_staged_dir": str(tmp_path / "stage")}


def test_join_and_sha_and_weld(tmp_path):
    manifest = _manifest(tmp_path)
    kfx_dir = tmp_path / "kindle"
    inter = kfx_dir / ".intermediates"
    inter.mkdir(parents=True)
    (kfx_dir / "On First Principles.kfx").write_bytes(b"kfx")
    (inter / "On First Principles_kindle.html").write_text(WELDED, encoding="utf-8")
    (kfx_dir / "On First Principles_visual_qa_report.json").write_text(
        json.dumps({"overall_score": 88}), encoding="utf-8")
    header_out = tmp_path / "hb"

    result = prov.build_provenance(manifest, str(kfx_dir), str(header_out))
    book = result["books"][0]
    assert book["sha256"] == hashlib.sha256(b"pdf-bytes").hexdigest()
    assert book["weld_total"] >= 1
    assert book["coverage"]["kfx"] is True
    assert book["status"] == "complete"


def test_missing_intermediate_is_coverage_gap(tmp_path):
    manifest = _manifest(tmp_path)
    kfx_dir = tmp_path / "kindle"
    kfx_dir.mkdir()
    (kfx_dir / "On First Principles.kfx").write_bytes(b"kfx")  # KFX but no html
    result = prov.build_provenance(manifest, str(kfx_dir), str(tmp_path / "hb"))
    book = result["books"][0]
    assert book["weld_total"] is None
    assert book["coverage"]["intermediate_html"] is False
    assert book["status"] == "coverage_gap"
