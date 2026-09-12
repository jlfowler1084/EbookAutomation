"""Regression for invisible Fournier expert-font text in the Versluis PDF."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from extract_tts_text import normalize_encoding


def test_adobe_expert_year_and_chapter_are_readable():
    source = '\uf761\uf772\uf774\uf768\uf775\uf772 \uf732\uf730\uf730\uf731'
    text, stats = normalize_encoding(source)
    assert text == 'ARTHUR 2001'
    assert stats['adobe_glyphs_fixed'] == 10
    assert stats['replacements_made'] == 10


def test_all_expert_digits_and_small_caps():
    source = ''.join(chr(cp) for cp in range(0xF730, 0xF73A))
    source += ''.join(chr(cp) for cp in range(0xF761, 0xF77B))
    text, _ = normalize_encoding(source)
    assert text == '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'


def test_unrelated_pua_and_clean_unicode_are_preserved():
    source = 'Readable café Ελληνικά Hebrew עברית \ue000\uf020\uf8ff\uf740\uf760\uf77b'
    text, stats = normalize_encoding(source)
    assert text == source
    assert stats['replacements_made'] == 0


def test_normalization_is_idempotent():
    once, _ = normalize_encoding('Chapter \uf731: \uf761\uf762\uf763')
    twice, stats = normalize_encoding(once)
    assert twice == once
    assert stats['replacements_made'] == 0
