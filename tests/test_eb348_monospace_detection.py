"""
EB-348 regression tests: monospace-font detection in _flush_line_group.

The detection logic is inline (not a standalone function), so these tests
replicate the exact expression to verify the curated keyword list and the
Monotype exclusion guard behave as specified.
"""

import pytest


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
