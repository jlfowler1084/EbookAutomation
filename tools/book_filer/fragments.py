"""Fragment-set detection (spec §6.3). Policy: ALWAYS route to review, never auto-trash."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import PureWindowsPath

# stem ending in -N, (N), or _NN  (N >= 1)
_NUMBERED_RE = re.compile(r"^(?P<stem>.+?)[ _-]\(?(?P<num>\d{1,3})\)?$")
_EPUB_DEBRIS = {".xhtml", ".opf", ".ncx", ".css"}


@dataclass(frozen=True)
class FragmentVerdict:
    members: tuple[str, ...]
    disposition: str   # always "review"
    reason: str


def detect_fragment_sets(paths: list[str]) -> list[FragmentVerdict]:
    verdicts: list[FragmentVerdict] = []
    used: set[str] = set()

    # 1. Exploded-EPUB debris: a directory containing OPF/NCX/XHTML/CSS together.
    by_dir: dict[str, list[str]] = defaultdict(list)
    for p in paths:
        by_dir[str(PureWindowsPath(p).parent)].append(p)
    for _dir, members in by_dir.items():
        exts = {PureWindowsPath(m).suffix.lower() for m in members}
        if len(_EPUB_DEBRIS & exts) >= 2:
            verdicts.append(FragmentVerdict(tuple(sorted(members)), "review",
                                            "exploded-EPUB debris (OPF/NCX/XHTML/CSS in one folder)"))
            used.update(members)

    # 2. Numbered-suffix sets: >= 3 files sharing a stem with consecutive-ish
    #    numbers IN THE SAME FOLDER. The grouping key includes the parent dir
    #    (EB-359) so a shared stem across different real folders cannot merge
    #    into one cross-folder set. This mirrors step 1's by_dir keying.
    by_dir_stem: dict[tuple[str, str], list[str]] = defaultdict(list)
    for p in paths:
        if p in used:
            continue
        pw = PureWindowsPath(p)
        m = _NUMBERED_RE.match(pw.stem)
        if m:
            by_dir_stem[(str(pw.parent), m.group("stem"))].append(p)
    for (_dir, stem), members in by_dir_stem.items():
        if len(members) >= 3:
            verdicts.append(FragmentVerdict(tuple(sorted(members)), "review",
                                            f"numbered fragment set (stem '{stem}', {len(members)} parts)"))

    return verdicts
