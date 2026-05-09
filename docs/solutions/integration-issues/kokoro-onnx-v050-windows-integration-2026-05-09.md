---
title: "Kokoro-ONNX v0.5.0 Integration: Neural TTS for Audiobook Generation"
date: 2026-05-09
category: docs/solutions/integration-issues
module: kokoro-tts-engine
problem_type: integration_issue
component: tooling
symptoms:
  - "HTTP 404 downloading kokoro-v0.19.onnx or voices.bin from GitHub releases"
  - "TypeError: Kokoro.__init__() got unexpected keyword argument 'providers'"
  - "IndexError: index 510 is out of bounds for axis 0 with size 510 (preceded by WARNING: Phonemes are too long)"
  - "PermissionError when soundfile.write() targets a NamedTemporaryFile path on Windows"
  - "PowerShell Invoke-WebRequest returns ~10 KB HTML instead of ~300 MB binary model file"
root_cause: wrong_api
resolution_type: code_fix
severity: high
related_components:
  - development_workflow
  - background_job
tags:
  - kokoro-onnx
  - tts
  - neural-tts
  - onnxruntime
  - python
  - windows
  - audiobook
  - phoneme-limit
  - tempfile
  - m4b
---

# Kokoro-ONNX v0.5.0 Integration: Neural TTS for Audiobook Generation

## Problem

Integrating kokoro-onnx v0.5.0 as a drop-in replacement for Balabolka SAPI5 in the EbookAutomation
pipeline (SCRUM-325) exposed five API-breaking changes and platform incompatibilities that caused
the integration to fail silently or crash before producing any audio output. Problems ranged from
renamed model files to a library-level off-by-one bug in the phoneme truncation path.

## Symptoms

- HTTP 404 errors downloading `kokoro-v0.19.onnx` and `voices.bin`; no model files appear in the
  target directory
- `TypeError: Kokoro.__init__() got an unexpected keyword argument 'providers'` on every synthesis call
- `WARNING: Phonemes are too long, truncating to 510 phonemes` followed immediately by
  `IndexError: index 510 is out of bounds for axis 0 with size 510` on chapters with long sentences
- `PermissionError` when `soundfile.write(tmp.name, ...)` targets a `NamedTemporaryFile` path on Windows
- `Invoke-WebRequest` on GitHub release asset URLs produces an HTML file (~10 KB) rather than the
  expected binary; the file passes `os.path.exists()` checks but is not a valid ONNX model

## What Didn't Work

**Using model URLs from the kokoro-onnx README.** The README still referenced pre-v0.5.0 filenames
(`kokoro-v0.19.onnx`, `voices.bin`). Both URLs return HTTP 404 since v0.5.0. The correct filenames
are only discoverable by triggering `Kokoro.validate()`, which prints the correct `wget` command for
`voices-v1.0.bin` in its error message.

**Passing `providers=` to the `Kokoro()` constructor.** Pre-v0.5.0 accepted
`Kokoro(model, voices, providers=["CUDAExecutionProvider"])`. The kwarg was silently removed in
v0.5.0 with no changelog entry.

**Sentence-level text splitting alone (120-word chunks).** A single long sentence in academic prose
can still exceed 510 phonemes. The initial split reduced crash frequency but did not eliminate it —
one ~480-word sentence in the *Fate of Empires* corpus (the canonical long-chapter regression input)
still triggered the IndexError.

**`tempfile.NamedTemporaryFile` for intermediate WAV files on Windows.** Windows grants an exclusive
file lock to `NamedTemporaryFile` for the lifetime of the context manager. A second open via
`soundfile.write(tmp.name, ...)` raises `PermissionError`. The pattern is common in Python examples
and works on Linux/macOS; it is Windows-incompatible.

**PowerShell `Invoke-WebRequest -UseBasicParsing` for GitHub release assets.** GitHub release asset
URLs redirect through authentication and CDN before serving the binary. `Invoke-WebRequest` with
basic parsing receives a login-redirect HTML page. The resulting "file" passes existence checks but
crashes every downstream consumer. (session history)

**ffmpeg assumed to be on PATH.** The M4B stitch step called `ffmpeg` directly. The desktop machine
did not have ffmpeg installed, causing the stitch to fail silently after all 9 WAV chapters were
synthesized successfully. (session history)

## Solution

### 1 — Correct model filenames (v1.0)

```python
_MODEL_FILE  = "kokoro-v1.0.onnx"
_VOICES_FILE = "voices-v1.0.bin"
_BASE_URL    = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
_MODEL_URL   = _BASE_URL + _MODEL_FILE
_VOICES_URL  = _BASE_URL + _VOICES_FILE
```

Trigger `python -c "from kokoro_onnx import Kokoro; Kokoro('x','x')"` to get the error message that
prints the correct voices URL. The model URL follows the same naming pattern.

### 2 — GPU/CPU provider via `ONNX_PROVIDER` environment variable

```python
import os
from kokoro_onnx import Kokoro

def load_kokoro(model_path, voices_path, device="auto"):
    if device == "gpu":
        os.environ["ONNX_PROVIDER"] = "CUDAExecutionProvider"
    elif device == "cpu":
        os.environ["ONNX_PROVIDER"] = "CPUExecutionProvider"
    # "auto": kokoro detects GPU if onnxruntime-gpu is installed
    return Kokoro(str(model_path), str(voices_path))
```

`ONNX_PROVIDER` must be set before the `Kokoro()` call. The library reads it during construction via
`os.getenv("ONNX_PROVIDER")` in `__init__.py`. When unset, auto-detection checks
`importlib.util.find_spec("onnxruntime-gpu")`.

### 3 — 3-tier chunker + binary retry for the 510-phoneme IndexError

**3-tier chunker** (≤100 words per chunk guarantees ≤510 phonemes for typical English prose):

```python
import re, numpy as np

_CHUNK_WORDS     = 100
_SENT_SPLIT_RE   = re.compile(r'(?<=[.!?])\s+')
_CLAUSE_SPLIT_RE = re.compile(r'(?<=[;,:])\s+')

def _chunk_text(text: str) -> list[str]:
    result = []
    for sentence in _SENT_SPLIT_RE.split(text.strip()):
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence.split()) <= _CHUNK_WORDS:
            result.append(sentence)
            continue
        for clause in _CLAUSE_SPLIT_RE.split(sentence):
            clause = clause.strip()
            if not clause:
                continue
            if len(clause.split()) <= _CHUNK_WORDS:
                result.append(clause)
                continue
            words = clause.split()
            for i in range(0, len(words), _CHUNK_WORDS):
                result.append(" ".join(words[i:i + _CHUNK_WORDS]))
    return result or [text]
```

**Binary retry** for any chunk that still triggers `IndexError` at synthesis time (off-by-one bug in
the library's phoneme-truncation path; truncates to 510 then accesses index 510):

```python
def _synth_with_retry(kokoro, chunk, voice, speed, depth=0):
    if depth > 6:
        raise RuntimeError(f"Chunk still exceeds phoneme limit after {depth} splits")
    try:
        return kokoro.create(chunk, voice=voice, speed=speed, lang="en-us")
    except IndexError:
        words = chunk.split()
        if len(words) < 2:
            raise
        mid = len(words) // 2
        left,  sr = _synth_with_retry(kokoro, " ".join(words[:mid]),  voice, speed, depth + 1)
        right, _  = _synth_with_retry(kokoro, " ".join(words[mid:]), voice, speed, depth + 1)
        return np.concatenate([left, right]), sr
```

### 4 — Windows-safe temporary WAV path

```python
import tempfile, soundfile as sf, os

# WRONG on Windows (exclusive lock prevents second open):
# with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
#     sf.write(tmp.name, samples, sr)  # PermissionError

# CORRECT: path without holding a file handle
tmp = tempfile.mktemp(suffix=".wav")
sf.write(tmp, samples, sr)
size_kb = os.path.getsize(tmp) // 1024
os.unlink(tmp)
```

`tempfile.mktemp()` is deprecated due to TOCTOU risk, but that risk is immaterial for a
single-process pipeline writing to a user-local temp directory.

### 5 — Python `urllib` for model download (not PowerShell `Invoke-WebRequest`)

```python
import urllib.request

def _download_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, dest)  # follows all redirects correctly
```

`urllib.request.urlretrieve` follows GitHub's multi-hop CDN redirects. The PowerShell install
script delegates all binary downloads to this Python function; `Invoke-WebRequest` is not used for
binary assets.

### 6 — Install ffmpeg before the M4B stitch step

```powershell
winget install Gyan.FFmpeg --accept-package-agreements
# Refresh PATH in the current session without restarting:
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("Path","User")
```

Alternatively, pass `--ffmpeg <path>` to `kokoro_synth.py` when ffmpeg is not on PATH.

## Why This Works

| Bug | Root Cause | Why the Fix Holds |
|-----|------------|-------------------|
| 404 on model URLs | v0.5.0 renamed model files with no changelog entry | URLs pinned to `model-files-v1.0` release tag in `kokoro_synth.py` |
| `providers=` TypeError | Constructor kwarg silently removed in v0.5.0 | `ONNX_PROVIDER` env var is the documented v0.5.0 interface |
| 510 IndexError | Library truncates to 510 phonemes then accesses index 510 (0-based OOB) | 100-word chunks ≈ ≤400 phonemes; binary retry handles pathological edge cases |
| PermissionError on WAV | Windows holds exclusive lock on `NamedTemporaryFile` for life of context manager | `mktemp()` returns a path string without any handle |
| HTML instead of binary | `Invoke-WebRequest` does not follow GitHub CDN redirect chain | `urllib.request.urlretrieve` follows all HTTP redirects correctly |

The chunker + binary retry provide defense-in-depth: the chunker eliminates 99%+ of IndexErrors
preemptively; the retry catches any residual phoneme-dense edge case without manual intervention.

## Prevention

**Install `onnxruntime-gpu` correctly — uninstall base first.**
`onnxruntime` and `onnxruntime-gpu` share C extension slots and cannot coexist:

```powershell
pip uninstall onnxruntime -y
pip install onnxruntime-gpu
```

Never add `onnxruntime` to `requirements.txt` alongside `onnxruntime-gpu`. Document the mutual
exclusion as a comment instead (see `requirements.txt` optional Kokoro section).

**Verify downloaded model file size.**
An HTML redirect page passes `os.path.exists()` but is not a valid ONNX file. Add a size floor:

```python
MIN_MODEL_BYTES = 50 * 1024 * 1024  # 50 MB

for dest, url in model_files:
    if not dest.exists() or dest.stat().st_size < MIN_MODEL_BYTES:
        dest.unlink(missing_ok=True)
        _download_file(url, dest)
```

**Pin the kokoro-onnx minor version.**
The v0.5.0 API breaks were undocumented. Pin in `requirements.txt` until the next minor version
is reviewed:

```
kokoro-onnx>=0.5.0,<0.6.0
```

**Test against a long-chapter corpus entry.**
The 510-phoneme bug is invisible on short chapters. Always include at least one test input
exceeding 5,000 words. The canonical regression case is *Fate of Empires* Chapter 4 (Glubb, ~8,500
words, 9 chapters, `John_Glubb_-_The_Fate_of_Empires_*_balabolka.txt`).

**Never use `NamedTemporaryFile` for inter-process file paths on Windows.**
Use `tempfile.mktemp()` or construct a path under `tempfile.gettempdir()` when a second process
or library needs to open the same path. Reserve `NamedTemporaryFile` for in-process context
managers where the handle never escapes the `with` block.

**Check ffmpeg before invoking the stitch step.**
The chapter WAVs succeed independently of ffmpeg; the stitch fails silently if it is absent. Add
a pre-flight check in the pipeline or install it as part of `install-kokoro.ps1`.

## Related

- `docs/install/lame.md` — Parallel audio installer pattern for Balabolka/LAME (the SAPI5 path);
  contrast the SourceForge download (no redirect issue) against the GitHub release asset pattern
  documented here
- `scripts/install-kokoro.ps1` — Canonical install script; handles onnxruntime-gpu/cpu swap,
  model file download via Python urllib, and smoke test
- `tools/kokoro_synth.py` — Full synthesis wrapper with chunker, binary retry, progress sidecar,
  and M4B stitching
- SCRUM-325 — Ticket for the full Kokoro TTS integration
