#!/usr/bin/env python3
"""
Kokoro TTS synthesizer for EbookAutomation pipeline.

Reads a _balabolka.txt file, splits on ALL-CAPS chapter headings, synthesizes
each chapter via Kokoro ONNX, and optionally stitches to a chaptered M4B.

Usage:
    py -3.12 tools/kokoro_synth.py --input output/balabolka-txt/MyBook_balabolka.txt --output-dir output/audiobooks
    py -3.12 tools/kokoro_synth.py --input output/balabolka-txt/MyBook_balabolka.txt --output-dir output/audiobooks --stitch
    py -3.12 tools/kokoro_synth.py --list-voices
    py -3.12 tools/kokoro_synth.py --input ... --stitch-only   # stitch existing WAVs without re-synthesizing
"""

import argparse
import json
import logging
import re
import subprocess
import sys
import wave
from pathlib import Path

log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

# Matches SAPI XML voice/silence/rate tags emitted by pdf_to_balabolka.py
_SAPI_TAG_RE = re.compile(
    r'<voice[^>]*>|</voice>'
    r'|<silence\s+msec="\d+"\s*/?>'
    r'|<rate[^>]*>|</rate>',
    re.IGNORECASE,
)

DEFAULT_VOICE    = "af_heart"
DEFAULT_SPEED    = 1.0
DEFAULT_MODEL_DIR = Path(__file__).resolve().parent / "kokoro-models"
_PROGRESS_SUFFIX  = ".kokoro_progress.json"

# Direct download URLs — kokoro-onnx v0.5.0+ uses v1.0 model files
_MODEL_URL  = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
_VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
_MODEL_FILE  = "kokoro-v1.0.onnx"
_VOICES_FILE = "voices-v1.0.bin"


# ── Chapter splitting ──────────────────────────────────────────────────────────

def _is_chapter_heading(line: str) -> bool:
    """True if line is an ALL-CAPS chapter heading (mirrors format_output() logic)."""
    if not line or len(line) > 120:
        return False
    if line != line.upper():
        return False
    alpha = [w for w in line.split() if len(w) >= 2 and w.isalpha()]
    return bool(alpha)


def split_into_chapters(text: str) -> list:
    """Split text into [(title, body), ...] on ALL-CAPS heading boundaries."""
    paragraphs = text.split("\n\n")
    chapters = []
    current_title = "FRONT MATTER"
    current_body: list = []

    for para in paragraphs:
        stripped = para.strip()
        if _is_chapter_heading(stripped):
            if current_body:
                chapters.append((current_title, "\n\n".join(current_body)))
            current_title = stripped
            current_body = []
        else:
            if stripped:
                current_body.append(stripped)

    if current_body:
        chapters.append((current_title, "\n\n".join(current_body)))

    return chapters


def strip_sapi_tags(text: str) -> str:
    """Remove SAPI XML voice/silence/rate tags so Kokoro receives plain text."""
    return _SAPI_TAG_RE.sub(" ", text).strip()


# ── Model management ────────────────────────────────────────────────────────────

def _download_file(url: str, dest: Path) -> None:
    """Download a file with progress logging using urllib."""
    import urllib.request
    log.info("Downloading %s ...", dest.name)
    dest.parent.mkdir(parents=True, exist_ok=True)

    def _progress(count, block, total):
        if total > 0 and count % 100 == 0:
            pct = min(100, count * block * 100 // total)
            log.info("  %s: %d%%", dest.name, pct)

    urllib.request.urlretrieve(url, dest, reporthook=_progress)
    log.info("  Saved: %s (%.1f MB)", dest, dest.stat().st_size / 1_048_576)


def ensure_models(model_dir: Path) -> tuple:
    """Ensure model files exist, downloading if necessary. Returns (model_path, voices_path)."""
    model_path  = model_dir / _MODEL_FILE
    voices_path = model_dir / _VOICES_FILE

    if not model_path.exists():
        _download_file(_MODEL_URL, model_path)
    if not voices_path.exists():
        _download_file(_VOICES_URL, voices_path)

    return model_path, voices_path


# ── Synthesis ──────────────────────────────────────────────────────────────────

def load_kokoro(model_path: Path, voices_path: Path, device: str = "auto"):
    """Load Kokoro model.

    kokoro-onnx v0.5.0+ manages GPU detection internally via onnxruntime-gpu
    presence; passing providers= to the constructor is no longer supported.
    The --device flag now sets ONNX_PROVIDER env var for cpu/gpu override.
    """
    try:
        from kokoro_onnx import Kokoro
    except ImportError:
        log.error(
            "kokoro-onnx not installed.\n"
            "Run: scripts\\install-kokoro.ps1  (or: py -3.12 -m pip install kokoro-onnx soundfile)"
        )
        sys.exit(1)

    import os
    if device == "gpu":
        os.environ["ONNX_PROVIDER"] = "CUDAExecutionProvider"
        log.info("Kokoro: forcing GPU via ONNX_PROVIDER=CUDAExecutionProvider")
    elif device == "cpu":
        os.environ["ONNX_PROVIDER"] = "CPUExecutionProvider"
        log.info("Kokoro: forcing CPU via ONNX_PROVIDER=CPUExecutionProvider")
    else:
        # auto: kokoro-onnx picks GPU if onnxruntime-gpu is installed
        try:
            import onnxruntime as ort
            available = ort.get_available_providers()
            if "CUDAExecutionProvider" in available:
                log.info("Kokoro: GPU detected (CUDAExecutionProvider available)")
            else:
                log.info("Kokoro: CPU only (CUDAExecutionProvider not available)")
        except Exception:
            pass

    return Kokoro(str(model_path), str(voices_path))


def synthesize_chapter(kokoro, text: str, wav_path: Path, voice: str, speed: float) -> bool:
    """Synthesize one chapter to a WAV file. Returns True on success."""
    try:
        import soundfile as sf
    except ImportError:
        log.error("soundfile not installed. Run: py -3.12 -m pip install soundfile")
        sys.exit(1)

    clean = strip_sapi_tags(text)
    if not clean.strip():
        log.warning("Empty chapter after tag-strip — skipping: %s", wav_path.name)
        return False

    try:
        samples, sample_rate = kokoro.create(clean, voice=voice, speed=speed, lang="en-us")
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(wav_path), samples, sample_rate)
        duration_s = len(samples) / sample_rate
        log.info("  OK  %s  (%.1f s, %.1f MB)", wav_path.name, duration_s, wav_path.stat().st_size / 1_048_576)
        return True
    except Exception as exc:
        log.error("Synthesis failed for %s: %s", wav_path.name, exc)
        return False


# ── Progress tracking ──────────────────────────────────────────────────────────

def _progress_path(wav_dir: Path, stem: str) -> Path:
    return wav_dir / f"{stem}{_PROGRESS_SUFFIX}"


def load_progress(progress_file: Path) -> set:
    if progress_file.exists():
        try:
            return set(json.loads(progress_file.read_text("utf-8")).get("completed", []))
        except Exception:
            pass
    return set()


def save_progress(progress_file: Path, completed: set) -> None:
    progress_file.write_text(json.dumps({"completed": sorted(completed)}, indent=2), "utf-8")


# ── M4B stitching ─────────────────────────────────────────────────────────────

def stitch_to_m4b(wav_files: list, output_m4b: Path, ffmpeg: str = "ffmpeg") -> bool:
    """Stitch [(title, wav_path), ...] into a chaptered M4B. Returns True on success."""
    if not wav_files:
        log.error("No WAV files supplied for stitching")
        return False

    concat_txt  = output_m4b.with_suffix(".concat.txt")
    meta_txt    = output_m4b.with_suffix(".ffmeta")

    try:
        # Build concat list
        with open(concat_txt, "w", encoding="utf-8") as f:
            for _, wav_path in wav_files:
                f.write(f"file '{wav_path.as_posix()}'\n")

        # Accumulate chapter timestamps (milliseconds)
        timestamps = [0]
        for _, wav_path in wav_files:
            with wave.open(str(wav_path), "rb") as wf:
                ms = int(wf.getnframes() / wf.getframerate() * 1000)
            timestamps.append(timestamps[-1] + ms)

        # Write ffmetadata chapter markers
        with open(meta_txt, "w", encoding="utf-8") as f:
            f.write(";FFMETADATA1\n")
            for i, (title, _) in enumerate(wav_files):
                safe = title.replace("=", "\\=").replace(";", "\\;").replace("#", "\\#")
                f.write(
                    f"\n[CHAPTER]\nTIMEBASE=1/1000\n"
                    f"START={timestamps[i]}\nEND={timestamps[i + 1]}\ntitle={safe}\n"
                )

        # ffmpeg: concat → AAC → M4B with embedded chapters
        cmd = [
            ffmpeg, "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_txt),
            "-i", str(meta_txt),
            "-map_metadata", "1",
            "-c:a", "aac", "-b:a", "64k",
            str(output_m4b),
        ]
        log.info("Stitching %d chapters → %s", len(wav_files), output_m4b.name)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log.error("ffmpeg failed:\n%s", result.stderr[-3000:])
            return False

        log.info("M4B written: %s  (%.1f MB)", output_m4b, output_m4b.stat().st_size / 1_048_576)
        return True

    finally:
        for f in (concat_txt, meta_txt):
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-5s] %(message)s",
        datefmt="%H:%M:%S",
    )

    ap = argparse.ArgumentParser(description="Kokoro TTS synthesizer — EbookAutomation pipeline")
    ap.add_argument("--input",       help="Path to _balabolka.txt input file")
    ap.add_argument("--output-dir",  help="Output directory for chapter WAVs / final M4B")
    ap.add_argument("--voice",       default=DEFAULT_VOICE,
                    help=f"Kokoro voice ID (default: {DEFAULT_VOICE})")
    ap.add_argument("--speed",       type=float, default=DEFAULT_SPEED,
                    help="Speech speed multiplier (default: 1.0)")
    ap.add_argument("--model-dir",   default=str(DEFAULT_MODEL_DIR),
                    help="Directory holding kokoro-v0.19.onnx + voices.bin")
    ap.add_argument("--device",      choices=["auto", "cpu", "gpu"], default="auto",
                    help="Inference device (default: auto)")
    ap.add_argument("--stitch",      action="store_true",
                    help="Stitch per-chapter WAVs to a chaptered M4B after synthesis")
    ap.add_argument("--stitch-only", action="store_true",
                    help="Skip synthesis; stitch existing WAVs in --output-dir/<stem>/")
    ap.add_argument("--ffmpeg",      default="ffmpeg",
                    help="ffmpeg executable (default: ffmpeg from PATH)")
    ap.add_argument("--list-voices", action="store_true",
                    help="Print available Kokoro voices and exit")
    args = ap.parse_args()

    model_dir = Path(args.model_dir)

    # ── list-voices ────────────────────────────────────────────────────────────
    if args.list_voices:
        model_path, voices_path = ensure_models(model_dir)
        kokoro = load_kokoro(model_path, voices_path, args.device)
        voices = kokoro.get_voices()
        print(f"Available voices ({len(voices)}):")
        for v in voices:
            print(f"  {v}")
        return 0

    if not args.input or not args.output_dir:
        ap.error("--input and --output-dir are required (unless --list-voices)")

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)

    if not input_path.exists():
        log.error("Input not found: %s", input_path)
        return 1

    stem    = input_path.stem.replace("_balabolka", "")
    wav_dir = output_dir / stem
    wav_dir.mkdir(parents=True, exist_ok=True)

    # Parse chapters
    text     = input_path.read_text(encoding="utf-8")
    chapters = split_into_chapters(text)
    log.info("Chapters detected: %d  |  Source: %s", len(chapters), input_path.name)

    if not chapters:
        log.error("No chapters found — is this a _balabolka.txt file?")
        return 1

    # ── stitch-only ────────────────────────────────────────────────────────────
    if args.stitch_only:
        wav_files = []
        for i, (title, _) in enumerate(chapters):
            wp = wav_dir / f"chapter_{i:03d}.wav"
            if wp.exists():
                wav_files.append((title, wp))
            else:
                log.warning("Missing WAV chapter_%03d — excluded from stitch", i)
        if not wav_files:
            log.error("No WAV files found under %s", wav_dir)
            return 1
        m4b_path = output_dir / f"{stem}.m4b"
        return 0 if stitch_to_m4b(wav_files, m4b_path, args.ffmpeg) else 1

    # ── synthesis ─────────────────────────────────────────────────────────────
    model_path, voices_path = ensure_models(model_dir)
    kokoro = load_kokoro(model_path, voices_path, args.device)

    progress_file = _progress_path(wav_dir, stem)
    completed     = load_progress(progress_file)
    wav_files     = []
    all_ok        = True

    for i, (title, body) in enumerate(chapters):
        wav_path = wav_dir / f"chapter_{i:03d}.wav"
        wav_files.append((title, wav_path))

        if i in completed and wav_path.exists():
            log.info("[%d/%d] RESUME  %s", i + 1, len(chapters), title[:70])
            continue

        log.info("[%d/%d] %s", i + 1, len(chapters), title[:70])
        spoken = f"{title}. {body}" if title != "FRONT MATTER" else body
        ok = synthesize_chapter(kokoro, spoken, wav_path, args.voice, args.speed)
        if ok:
            completed.add(i)
            save_progress(progress_file, completed)
        else:
            all_ok = False

    if not all_ok:
        log.warning("Some chapters failed — M4B stitch skipped")
        return 1

    if args.stitch:
        m4b_path = output_dir / f"{stem}.m4b"
        if not stitch_to_m4b(wav_files, m4b_path, args.ffmpeg):
            return 1
        progress_file.unlink(missing_ok=True)  # clean up sidecar on full success

    log.info("Complete. %d chapters synthesized.", len(chapters))
    return 0


if __name__ == "__main__":
    sys.exit(main())
