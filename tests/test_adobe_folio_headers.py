"""Encoded smallcaps/folio headers must be isolated before text rejoining."""

from __future__ import annotations

import sys
import json
import re
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from extract_tts_text import (
    _fix_ligature_splits, _mark_a2_running_headers, _mark_adobe_folio_headers,
    rejoin_html_fragments, extract_with_pdfminer_html, normalize_encoding,
)


def encoded(text: str) -> str:
    return ''.join(chr(0xF761 + ord(char.lower()) - ord('a')) if char.isalpha()
                   else chr(0xF730 + int(char)) if char.isdigit() else char for char in text)


def paragraph(text: str, page: int, margin: bool = False) -> dict:
    return {'text': text, 'page_number': page, 'font_size': 11,
            'is_bold': False, 'is_italic': False, 'is_all_caps': False,
            '_margin_zone': margin}


def test_tracked_encoded_headers_do_not_interrupt_a_hyphenated_body_word() -> None:
    headers = [paragraph(encoded(f'{title} {page - 7}'), page, True)
               for page, title in zip(range(10, 20, 2), [
                   'ESOTERICISM IN EARLY AM ERIC A', 'ESOTERICISM IN EAR LY A MERICA',
                   'ESOTERICISM IN EARLY AMERICA', 'ESOTERICISM IN EARLY AM ERIC A',
                   'ESOTERICISM IN EAR LY A MERICA'])]
    body_before = paragraph('During that era there were some who den-', 18)
    body_after = paragraph('igrated esotericism, although the traditions remained influential.', 19)
    paragraphs = headers[:-1] + [body_before, headers[-1], body_after,
                               paragraph('A final complete paragraph.', 241)]
    _mark_a2_running_headers(paragraphs, lambda _: None)
    assert all(header.get('_is_a2_running_header') for header in headers)
    rejoin_html_fragments(paragraphs, 11, lambda _: None)
    assert body_before['text'] == 'During that era there were some who denigrated esotericism, although the traditions remained influential.'
    assert not any(0xF761 <= ord(char) <= 0xF77A for char in body_before['text'])


def test_separate_encoded_margin_folios_are_marked_with_their_headers() -> None:
    paragraphs = []
    for page in range(20, 30, 2):
        paragraphs += [paragraph(encoded(str(page - 7)), page, True),
                       paragraph(encoded('THE ESOTERIC ORIGINS OF THE AMERICAN RENAISSANCE'), page, True)]
    _mark_a2_running_headers(paragraphs, lambda _: None)
    assert all(para.get('_is_a2_running_header') for para in paragraphs)


@pytest.mark.parametrize('margin,folios', [(False, [3, 5, 7, 9, 11]), (True, [1, 2, 3, 4, 5])])
def test_body_smallcaps_or_inconsistent_folio_offsets_are_preserved(margin: bool, folios: list[int]) -> None:
    paragraphs = [paragraph(encoded(f'IMPORTANT REPEATED TEXT {folio}'), page, margin)
                  for page, folio in zip(range(10, 20, 2), folios)]
    originals = [para['text'] for para in paragraphs]
    _mark_a2_running_headers(paragraphs, lambda _: None)
    assert not any(para.get('_is_a2_running_header') for para in paragraphs)
    assert [para['text'] for para in paragraphs] == originals


@pytest.mark.parametrize('punctuation', [',', ';', ':'])
def test_fragment_repair_preserves_punctuation_boundaries(punctuation: str) -> None:
    paragraphs = [{'text': f'the Hermetic Rite{punctuation} es tablished around 1770.'}]
    _fix_ligature_splits(paragraphs, lambda _: None)
    assert paragraphs[0]['text'] == f'the Hermetic Rite{punctuation} established around 1770.'


def test_fragment_repair_still_joins_valid_ligature_fragments() -> None:
    paragraphs = [{'text': 'These are fi gures from an estab lished order.'}]
    _fix_ligature_splits(paragraphs, lambda _: None)
    assert paragraphs[0]['text'] == 'These are figures from an established order.'


def test_notes_ranges_group_with_alternating_folios_and_figure_dashes() -> None:
    headers = []
    for page in range(201, 224):
        span = f'{page - 100} ‒ {page - 91}'
        label = 'N OTES TO PAG ES' if page % 2 else 'NOTES TO PAGES'
        text = f'{page - 7} {label} {span}' if page % 2 else f'{label} {span} {page - 7}'
        headers.append(paragraph(encoded(text), page, True))
    note = paragraph('208. This real note cites pages 127–133 of an earlier work.', 215, True)
    paragraphs = headers + [note]
    assert _mark_adobe_folio_headers(paragraphs, lambda _: None) == 23
    assert all(header.get('_is_a2_running_header') for header in headers)
    assert not note.get('_is_a2_running_header')
    assert note['text'] == '208. This real note cites pages 127–133 of an earlier work.'


@pytest.mark.parametrize('use_encoding', [False, True])
def test_numeric_ranges_do_not_override_encoding_or_stable_offset_guards(use_encoding: bool) -> None:
    text = '208 NOTES TO PAGES 127 ‒ 133'
    paragraphs = [paragraph(encoded(text) if use_encoding else text, page, True)
                  for page in range(201, 207)]
    assert _mark_adobe_folio_headers(paragraphs, lambda _: None) == 0
    assert not any(para.get('_is_a2_running_header') for para in paragraphs)


def test_real_b4_all_23_notes_headers_marked_without_changing_note_body() -> None:
    manifest_path = Path(__file__).resolve().parents[1] / 'data' / 'scan_bench' / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    source = next(Path(book['source_path']) for book in manifest['books'] if book['id'] == 'B4')
    if not source.is_file():
        pytest.skip('Local B4 corpus PDF unavailable')
    paragraphs, _ = extract_with_pdfminer_html(str(source), lambda _: None)
    notes_headers = []
    for para in paragraphs:
        visible, _ = normalize_encoding(para.get('text', ''))
        if len(visible) < 120 and 'NOTESTOPAGES' in re.sub(r'\s+', '', visible):
            notes_headers.append(para)
    note_body = [(para, para['text']) for para in paragraphs
                 if 201 <= para['page_number'] <= 223 and len(para['text']) > 150]
    assert len(notes_headers) == 23
    assert note_body
    _mark_a2_running_headers(paragraphs, lambda _: None)
    assert all(para.get('_is_a2_running_header') for para in notes_headers)
    assert all(para['text'] == original and not para.get('_is_a2_running_header')
               for para, original in note_body)
