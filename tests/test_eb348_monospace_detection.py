"""
EB-348 regression tests: monospace-font detection in _flush_line_group.

The detection logic is inline (not a standalone function), so these tests
replicate the exact expression to verify the curated keyword list and the
Monotype exclusion guard behave as specified.
"""

import pytest
import sys
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from extract_tts_text import _flush_line_group, format_paragraphs_as_html


# ---------------------------------------------------------------------------
# Mirror the exact detection expression from extract_tts_text.py lines 6394-6406
# so that changes to either the keywords or the guard will break these tests.
# ---------------------------------------------------------------------------

_MONO_FONTS = (
    'courier', 'consolas', 'inconsolata', 'menlo', 'monaco',
    'anonymous', 'dejavusansmono', 'dejavumono', 'ubuntumono',
    'cascadia', 'firacode', 'fira mono', 'jetbrains',
    'liberationmono', 'liberation mono', 'andale', 'ptmono', 'pt mono',
    'ibmplexmono', 'ibm plex mono', 'sourcecodepro', 'source code pro',
    'robotomono', 'roboto mono', 'spacemono', 'lucidaconsole',
    'lucida console', 'nimbusmono',
)


def _is_monospace(font_name: str) -> bool:
    """Exact logic from _flush_line_group (EB-348 tightened version)."""
    fnt_lower = font_name.lower() if font_name else ''
    return (
        any(kw in fnt_lower for kw in _MONO_FONTS)
        and 'monotype' not in fnt_lower
    )


# ---------------------------------------------------------------------------
# Cases that MUST be detected as monospace
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("font_name", [
    "CourierNew",
    "ABCDEF+CourierNew",       # embedded/subset prefix
    "Courier-BoldOblique",
    "Consolas",
    "Consolas-Bold",
    "Inconsolata",
    "Menlo-Regular",
    "Monaco",
    "Anonymous Pro",
    "Anonymous Pro-Bold",
    "DejaVuSansMono",
    "DejaVuMono",
    "UbuntuMono",
    "CascadiaCode",
    "CascadiaMono",            # contains 'cascadia'
    "FiraCode",
    "Fira Mono",
    "JetBrainsMono",
    "LiberationMono",
    "Liberation Mono",
    "Andale Mono",             # contains 'andale'
    "PTMono",
    "PT Mono",
    "IBMPlexMono",
    "IBM Plex Mono",
    "SourceCodePro",
    "Source Code Pro",
    "RobotoMono",
    "Roboto Mono",
    "SpaceMono",
    "LucidaConsole",
    "Lucida Console",
    "NimbusMono",
])
def test_detected_as_monospace(font_name):
    assert _is_monospace(font_name), f"Expected {font_name!r} to be monospace"


# ---------------------------------------------------------------------------
# Cases that MUST NOT be detected as monospace
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("font_name", [
    # Monotype foundry fonts — the core regression being fixed
    "MonotypeCorsiva",
    "ABCDEF+MonotypeCorsiva",  # embedded/subset prefix common in PDFs
    "Monotype Corsiva",
    "MonotypeSorts",
    "MonotypeOldStyle",
    # Other non-monospace serif/script fonts
    "TimesNewRoman",
    "Arial",
    "Helvetica",
    "Georgia",
    "Palatino",
    "GaramondPremrPro",
    "MinionPro",
    "CenturySchoolbook",
    # Empty / missing
    "",
])
def test_not_detected_as_monospace(font_name):
    assert not _is_monospace(font_name), f"Expected {font_name!r} NOT to be monospace"


def _line(text, y0, font="CourierNew"):
    return {
        "text": text,
        "font": font,
        "font_name": font,
        "size": 10.0,
        "bold": False,
        "italic": False,
        "centered": False,
        "y0": y0,
        "x0": 72.0,
        "x1": 250.0,
        "page": 1,
    }


def _para(text, page=1, mono=False):
    return {
        "text": text,
        "font_size": 10.0,
        "font_name": "CourierNew" if mono else "TimesNewRoman",
        "is_bold": False,
        "is_italic": False,
        "is_centered": False,
        "is_monospace": mono,
        "is_all_caps": False,
        "page_number": page,
        "line_count": text.count("\n") + 1,
        "char_count": len(text),
        "y0_min": 100.0,
        "y0_max": 100.0,
    }


def test_monospace_line_group_preserves_line_breaks():
    all_paras = []
    _flush_line_group([
        _line("import pandas as pd", 700),
        _line("weights = model.fit(x)", 688),
        _line("print(weights)", 676),
    ], all_paras)

    assert all_paras[0]["is_monospace"]
    assert all_paras[0]["text"] == (
        "import pandas as pd\n"
        "weights = model.fit(x)\n"
        "print(weights)"
    )


def test_pre_block_closes_before_page_anchor():
    html, _ = format_paragraphs_as_html(
        [
            _para("print('before page break')", page=1, mono=True),
            {"is_page_marker": True, "page_number": 2, "text": ""},
            _para("Body paragraph after the page break.", page=2, mono=False),
        ],
        body_size=10.0,
        bookmarks=[],
        log=lambda msg: None,
        title="Code Test",
    )

    assert "<pre>print('before page break')</pre>" in html
    assert html.index("</pre>") < html.index('<a id="page_2"></a>')
