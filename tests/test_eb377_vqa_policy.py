import sys, threading
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import batch_qa  # noqa: E402


def test_vqa_argv_is_calibrated_and_fallback_off(tmp_path):
    kfx = tmp_path / "book.kfx"
    kfx.write_bytes(b"x")
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["timeout"] = kwargs.get("timeout")
        return mock.Mock(returncode=0, stdout="", stderr="")

    with mock.patch.object(batch_qa.subprocess, "run", side_effect=fake_run):
        batch_qa.run_visual_qa_for_book(str(kfx))

    argv = captured["argv"]
    assert "--full" in argv
    assert argv[argv.index("--provider") + 1] == "local"
    assert argv[argv.index("--fallback-enabled") + 1] == "false"
    assert captured["timeout"] == 900


def test_vqa_semaphore_is_single_permit():
    assert isinstance(batch_qa._VQA_SEMAPHORE, threading.Semaphore)
    assert batch_qa._VQA_SEMAPHORE._value == 1


def test_vqa_call_is_wrapped_by_semaphore(tmp_path):
    """The subprocess.run must execute INSIDE the semaphore context — guards
    against a future edit that drops the `with _VQA_SEMAPHORE:` wrapper while
    leaving the semaphore object in place (which the _value check alone misses)."""
    kfx = tmp_path / "book.kfx"
    kfx.write_bytes(b"x")
    events = []

    class RecordingCM:
        def __enter__(self):
            events.append("enter")
            return self

        def __exit__(self, *exc):
            events.append("exit")
            return False

    def fake_run(argv, **kwargs):
        events.append("run")
        return mock.Mock(returncode=0, stdout="", stderr="")

    with mock.patch.object(batch_qa, "_VQA_SEMAPHORE", RecordingCM()), \
         mock.patch.object(batch_qa.subprocess, "run", side_effect=fake_run):
        batch_qa.run_visual_qa_for_book(str(kfx))

    assert events == ["enter", "run", "exit"]
