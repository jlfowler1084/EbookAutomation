#!/usr/bin/env python3
"""
Ebook to Balabolka Converter
Extracts and cleans ebook text (PDF, EPUB, MOBI, AZW, DJVU),
removes front/back matter, and formats chapter headings in ALL CAPS
for Balabolka TTS splitting.

Usage:
    GUI mode (no arguments):
        python pdf_to_balabolka.py

    CLI mode (for pipeline / PowerShell automation):
        python pdf_to_balabolka.py --input book.pdf --output-dir output/balabolka-txt
        python pdf_to_balabolka.py --input book.epub --output-dir output/balabolka-txt
        python pdf_to_balabolka.py --input book.pdf --output-dir . --suffix _tts.txt
        python pdf_to_balabolka.py --input book.pdf   (output defaults to same folder as input)

Requirements: pip install pypdf ebooklib beautifulsoup4
"""

import argparse
import logging
import sys
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import threading
import json
import re
import statistics
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent.parent / '.env')

SUPPORTED_FORMATS = ['pdf', 'epub', 'mobi', 'azw', 'azw3', 'djvu']


def _load_api_model(tier="haiku"):
    """Load API model string from config/settings.json, falling back to defaults."""
    import json as _json
    from pathlib import Path as _Path
    _defaults = {
        "haiku": "claude-haiku-4-5-20251001",
        "sonnet": "claude-sonnet-4-20250514",
        "sonnet_latest": "claude-sonnet-4-6",
        "gemini_flash": "gemini-2.5-flash",
    }
    try:
        settings_path = _Path(__file__).resolve().parent.parent / "config" / "settings.json"
        if settings_path.exists():
            with open(settings_path, 'r', encoding='utf-8') as f:
                cfg = _json.load(f)
            return cfg.get("api_models", {}).get(tier, _defaults.get(tier, _defaults["haiku"]))
    except Exception:
        pass
    return _defaults.get(tier, _defaults["haiku"])

# ── OCR Substitution Table Loader ──────────────────────────────────────

_OCR_SUBSTITUTIONS_CACHE = None


def load_ocr_substitutions(custom_path=None):
    """Load OCR substitution table from config/ocr_substitutions.json.

    Falls back to hardcoded defaults if file is missing.
    Caches the loaded table for subsequent calls.

    Args:
        custom_path: Optional path to a custom substitution JSON file.
                     Merged on top of the base config (custom entries win).
    Returns:
        dict with keys: mojibake_map, unicode_normalization, backtick_replacements,
                        merged_word_splits, ligature_map, chapter_keywords
    """
    global _OCR_SUBSTITUTIONS_CACHE

    if _OCR_SUBSTITUTIONS_CACHE is not None and custom_path is None:
        return _OCR_SUBSTITUTIONS_CACHE

    result = _get_hardcoded_defaults()

    # Default path: config/ocr_substitutions.json relative to project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_path = os.path.join(os.path.dirname(script_dir), 'config', 'ocr_substitutions.json')

    if os.path.isfile(default_path):
        try:
            with open(default_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            result = _merge_substitution_data(result, data)
        except (json.JSONDecodeError, IOError):
            pass  # fall back to hardcoded defaults silently

    if custom_path and os.path.isfile(custom_path):
        try:
            with open(custom_path, 'r', encoding='utf-8') as f:
                custom_data = json.load(f)
            result = _merge_substitution_data(result, custom_data)
        except (json.JSONDecodeError, IOError):
            pass

    if custom_path is None:
        _OCR_SUBSTITUTIONS_CACHE = result

    return result


def _get_hardcoded_defaults():
    """Return hardcoded defaults as fallback if JSON file is missing."""
    return {
        'mojibake_map': {
            '\xe2\x80\x99': '\u2019', '\xe2\x80\x98': '\u2018',
            '\xe2\x80\x9c': '\u201C', '\xe2\x80\x9d': '\u201D',
            '\xe2\x80\x93': '\u2013', '\xe2\x80\x94': '\u2014',
            '\xe2\x80\xa6': '\u2026', '\xe2\x80\xa2': '\u2022',
            '\xe2\x80\xb2': '\u2032', '\xe2\x80\xb3': '\u2033',
            '\xe2\x84\xa2': '\u2122',
            '\xc3\xa9': 'é', '\xc3\xa8': 'è', '\xc3\xaa': 'ê', '\xc3\xab': 'ë',
            '\xc3\xa0': 'à', '\xc3\xa1': 'á', '\xc3\xa2': 'â', '\xc3\xa4': 'ä',
            '\xc3\xa7': 'ç', '\xc3\xad': 'í', '\xc3\xaf': 'ï', '\xc3\xb1': 'ñ',
            '\xc3\xb3': 'ó', '\xc3\xb6': 'ö', '\xc3\xba': 'ú', '\xc3\xbc': 'ü',
            '\xc3\x9f': 'ß', '\xc3\x86': 'Æ', '\xc3\xa6': 'æ',
            '\xc3\x98': 'Ø', '\xc3\xb8': 'ø',
            '\xc2\xa3': '£', '\xc2\xa9': '©', '\xc2\xae': '®',
            '\xc2\xb0': '°', '\xc2\xb7': '·',
            '\xc2\xbd': '½', '\xc2\xbc': '¼', '\xc2\xbe': '¾',
        },
        'unicode_normalization': {
            '\u2018': "'", '\u2019': "'",
            '\u201c': '"', '\u201d': '"',
            '\u2013': '-', '\u2014': '--',
            '\u2026': '...',
        },
        'backtick_replacements': ['bl', 'dd', 'ff', 'fi', 'fl', 'tt', 'll', 'ft', 'fb', 'ffi', 'ffl'],
        'merged_word_splits': {
            'ofthe': 'of the', 'ofthis': 'of this', 'ofthat': 'of that',
            'oftheir': 'of their', 'inthe': 'in the', 'inthis': 'in this',
            'inthat': 'in that', 'tothe': 'to the', 'forthe': 'for the',
            'onthe': 'on the', 'atthe': 'at the', 'bythe': 'by the',
            'isthe': 'is the', 'andthe': 'and the', 'fromthe': 'from the',
            'withthe': 'with the', 'asthe': 'as the', 'butthe': 'but the',
        },
        'ligature_map': {
            '\ufb01': 'fi', '\ufb02': 'fl', '\ufb00': 'ff',
            '\ufb03': 'ffi', '\ufb04': 'ffl',
        },
        'chapter_keywords': [
            'Genesis', 'Exodus', 'Leviticus', 'Numbers', 'Deuteronomy',
            'Chapter', 'Chapters', 'chapter', 'chapters',
            'Samuel', 'Kings', 'Chronicles', 'Corinthians',
            'Thessalonians', 'Timothy', 'Peter', 'John',
            'Psalm', 'Isaiah', 'Jeremiah', 'Ezekiel', 'Daniel',
            'verse', 'verses', 'Verse', 'Verses',
        ],
    }


def _merge_substitution_data(base, overlay):
    """Deep-merge overlay onto base. Overlay values win for conflicts."""
    result = dict(base)
    for key in overlay:
        if key.startswith('_'):
            continue  # skip _comment, _version
        if key not in result:
            result[key] = overlay[key]
            continue
        ov = overlay[key]
        bv = result[key]
        # Handle JSON wrapper structure: {entries: {...}}, {candidates: [...]}, {words: [...]}
        if isinstance(ov, dict):
            if 'entries' in ov and isinstance(bv, dict):
                result[key] = dict(bv)
                result[key].update(ov['entries'])
            elif 'candidates' in ov and isinstance(bv, list):
                result[key] = ov['candidates']
            elif 'words' in ov and isinstance(bv, list):
                result[key] = ov['words']
            elif isinstance(bv, dict):
                result[key] = dict(bv)
                result[key].update(ov)
            else:
                result[key] = ov
        elif isinstance(ov, list) and isinstance(bv, list):
            result[key] = ov
        else:
            result[key] = ov
    return result


# Module-level storage for font inventory (set by extract_with_pdfminer_html)
_last_font_inventory = []

# ── TTS Enhancement Constants ─────────────────────────────────────────
EMPHATIC_MAX_WORDS = 18        # Max words for a sentence to qualify as emphatic closer
EMPHATIC_MIN_WORDS = 3         # Min words (avoid tagging fragments)
CHAPTER_SILENCE_MS = 800       # Silence after chapter headings
PART_SILENCE_MS = 1200         # Silence after part headings
SCENE_BREAK_SILENCE_MS = 600   # Silence for scene breaks (*** etc.)
EMPHATIC_SILENCE_MS = 500      # Silence after emphatic closers
EMPHATIC_RATE = "-1"           # Rate for emphatic closers (slower)

# ── Vision Transcription Prompt (Tier 3) ─────────────────────────────
_VISION_TRANSCRIPTION_PROMPT = """You are a precise document transcription engine. Your task is to transcribe the text from each page image EXACTLY as it appears, preserving all content.

RULES:
1. Transcribe ALL text on each page. Never summarize, skip, or paraphrase.
2. Preserve paragraph breaks as blank lines between paragraphs.
3. Mark chapter/section headings with ## (level 2) or ### (level 3) prefix.
4. Preserve italic text with *italic* markers and bold text with **bold** markers.
5. Preserve footnote reference numbers as superscript markers: [^1], [^2], etc.
6. For block quotes, prefix each line with >
7. Transcribe non-Latin scripts (Hebrew, Greek, German, etc.) accurately in their original script. Do NOT transliterate.
8. If a word is hyphenated across a line break, rejoin it (e.g., "con-\\ntinue" -> "continue").
9. Do NOT include page numbers, running headers, or running footers.
10. Do NOT include any commentary, notes, or metadata about the transcription itself.
11. Separate each page's transcription with a page marker on its own line: <<PAGE:N>> where N is the page number.
12. If a page is blank or contains only images/diagrams with no text, output just the page marker.

OUTPUT FORMAT:
<<PAGE:1>>
[transcribed text of page 1]

<<PAGE:2>>
[transcribed text of page 2]

Begin transcription now."""


# ───────────────────────────────────────────────────────────
#  CORE PROCESSING LOGIC
# ───────────────────────────────────────────────────────────

# ── Common English Words (top ~750 high-frequency words from COCA) ────────
# Used by score_text_layer_quality() for word plausibility checks.
# Includes academic/religious terms since the corpus is heavy on those.
_COMMON_ENGLISH_WORDS = {
    # Function words & pronouns
    'the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'i', 'it',
    'for', 'not', 'on', 'with', 'he', 'as', 'you', 'do', 'at', 'this',
    'but', 'his', 'by', 'from', 'they', 'we', 'say', 'her', 'she', 'or',
    'an', 'will', 'my', 'one', 'all', 'would', 'there', 'their', 'what',
    'so', 'up', 'out', 'if', 'about', 'who', 'get', 'which', 'go', 'me',
    'when', 'make', 'can', 'like', 'time', 'no', 'just', 'him', 'know',
    'take', 'people', 'into', 'year', 'your', 'good', 'some', 'could',
    'them', 'see', 'other', 'than', 'then', 'now', 'look', 'only', 'come',
    'its', 'over', 'think', 'also', 'back', 'after', 'use', 'two', 'how',
    'our', 'work', 'first', 'well', 'way', 'even', 'new', 'want',
    'because', 'any', 'these', 'give', 'day', 'most', 'us',
    # Common verbs & adjectives
    'great', 'has', 'had', 'was', 'were', 'been', 'said', 'each', 'more',
    'may', 'such', 'much', 'should', 'very', 'made', 'did', 'where',
    'before', 'between', 'being', 'under', 'never', 'same', 'another',
    'while', 'last', 'might', 'own', 'still', 'found', 'many', 'through',
    'long', 'those', 'does', 'down', 'part', 'must', 'world', 'again',
    'here', 'both', 'during', 'set', 'three', 'small', 'right', 'house',
    'place', 'high', 'every', 'hand', 'large', 'old', 'off', 'left',
    'end', 'along', 'little', 'state', 'men', 'man', 'life', 'head',
    'too', 'went', 'few', 'without', 'against', 'until', 'since',
    # Academic/religious terms (corpus-relevant)
    'god', 'church', 'chapter', 'king', 'however', 'power', 'book',
    'given', 'among', 'rather', 'often', 'already', 'lord', 'son',
    'point', 'fact', 'general', 'name', 'upon', 'though', 'second',
    'called', 'case', 'number', 'water', 'money', 'really', 'body',
    'father', 'keep', 'eyes', 'mind', 'children', 'city', 'earth',
    'mother', 'light', 'story', 'young', 'night', 'home', 'turn',
    'play', 'run', 'read', 'help', 'line', 'things', 'move', 'live',
    'believe', 'tell', 'hold', 'bring', 'happen', 'next', 'put',
    'need', 'late', 'hard', 'start', 'open', 'try', 'walk', 'begin',
    'show', 'hear', 'close', 'seem', 'stop', 'change', 'call', 'pay',
    'let', 'mean', 'leave', 'keep', 'form', 'become', 'different',
    'important', 'always', 'country', 'thought', 'find', 'thing',
    'might', 'went', 'made', 'world', 'enough', 'almost', 'took',
    'away', 'something', 'nothing', 'got', 'own', 'really', 'being',
    'above', 'below', 'within', 'later', 'done', 'political',
    'government', 'woman', 'following', 'number', 'four', 'five',
    'six', 'seven', 'eight', 'nine', 'ten', 'hundred', 'thousand',
    # Content words (extended)
    'able', 'across', 'act', 'actually', 'age', 'ago', 'agree', 'air',
    'although', 'american', 'answer', 'appear', 'area', 'ask', 'away',
    'bad', 'based', 'became', 'best', 'better', 'big', 'black', 'blood',
    'blue', 'boy', 'brought', 'build', 'business', 'buy', 'came',
    'car', 'care', 'carry', 'cause', 'central', 'certain', 'child',
    'clear', 'coming', 'common', 'community', 'company', 'complete',
    'continue', 'control', 'course', 'court', 'cut', 'dark', 'data',
    'dead', 'deal', 'death', 'deep', 'development', 'early', 'east',
    'economic', 'effect', 'either', 'else', 'enough', 'entire',
    'especially', 'ever', 'evidence', 'example', 'experience', 'eye',
    'face', 'family', 'far', 'feel', 'field', 'figure', 'final',
    'fire', 'follow', 'food', 'force', 'foreign', 'free', 'front',
    'full', 'further', 'future', 'girl', 'going', 'green', 'ground',
    'group', 'grow', 'growth', 'guy', 'half', 'having', 'health',
    'human', 'idea', 'include', 'including', 'increase', 'indeed',
    'individual', 'information', 'instead', 'interest', 'issue',
    'job', 'kind', 'known', 'land', 'language', 'law', 'least',
    'less', 'level', 'local', 'looking', 'lose', 'lost', 'love',
    'low', 'making', 'market', 'matter', 'member', 'military',
    'million', 'moment', 'month', 'morning', 'move', 'national',
    'natural', 'nature', 'near', 'necessary', 'nor', 'north', 'note',
    'office', 'once', 'order', 'own', 'past', 'period', 'perhaps',
    'person', 'personal', 'place', 'plan', 'point', 'police',
    'policy', 'position', 'possible', 'present', 'president',
    'problem', 'process', 'produce', 'program', 'provide', 'public',
    'question', 'quite', 'rate', 'real', 'reason', 'receive',
    'recent', 'record', 'red', 'region', 'remain', 'remember',
    'report', 'require', 'research', 'result', 'return', 'road',
    'room', 'rule', 'school', 'sense', 'serve', 'service', 'several',
    'shall', 'short', 'side', 'significant', 'similar', 'simply',
    'single', 'sit', 'situation', 'social', 'society', 'south',
    'space', 'speak', 'special', 'stand', 'strong', 'study',
    'subject', 'support', 'sure', 'system', 'table', 'taken',
    'talk', 'tell', 'term', 'test', 'themselves', 'therefore',
    'third', 'today', 'together', 'toward', 'true', 'try',
    'type', 'understand', 'united', 'value', 'view', 'voice',
    'war', 'week', 'west', 'whether', 'white', 'whole', 'whose',
    'why', 'wife', 'wish', 'woman', 'word', 'write', 'written',
    'wrong', 'year', 'yes', 'yet',
    # Religious/theological (corpus-heavy)
    'spirit', 'temple', 'priest', 'prophet', 'israel', 'jerusalem',
    'jewish', 'christian', 'bible', 'scripture', 'faith', 'prayer',
    'heaven', 'holy', 'ancient', 'text', 'verse', 'psalm', 'prophet',
    'worship', 'covenant', 'kingdom', 'salvation', 'divine', 'sacred',
    'doctrine', 'tradition', 'teaching', 'revelation', 'angel',
    'sin', 'grace', 'soul', 'blessing', 'people', 'law', 'truth',
    # Academic/scholarly
    'theory', 'analysis', 'approach', 'argument', 'author',
    'century', 'chapter', 'claim', 'concept', 'conclusion',
    'context', 'critical', 'cultural', 'discussion', 'editor',
    'essay', 'focus', 'historical', 'history', 'interpretation',
    'introduction', 'journal', 'literature', 'method', 'modern',
    'moral', 'movement', 'noted', 'original', 'page', 'particular',
    'passage', 'perspective', 'philosophical', 'practice',
    'primary', 'principle', 'published', 'reference', 'role',
    'scholar', 'section', 'series', 'source', 'suggests', 'theory',
    'thesis', 'thus', 'university', 'volume', 'according',
}


def detect_scripts(text, sample_size=10000):
    """Detect Unicode script blocks present in text.

    Returns a dict of script names to percentages.
    Used to identify multi-script books needing Vision extraction.
    """
    if not text or len(text.strip()) < 50:
        return {"latin": 100.0}

    text_len = len(text)
    start = text_len // 10
    end = min(start + sample_size, text_len * 9 // 10)
    sample = text[start:end]

    script_ranges = {
        'latin':    lambda cp: (0x0000 <= cp <= 0x024F) or (0x1E00 <= cp <= 0x1EFF),
        'greek':    lambda cp: (0x0370 <= cp <= 0x03FF) or (0x1F00 <= cp <= 0x1FFF),
        'cyrillic': lambda cp: (0x0400 <= cp <= 0x04FF) or (0x0500 <= cp <= 0x052F),
        'hebrew':   lambda cp: (0x0590 <= cp <= 0x05FF) or (0xFB1D <= cp <= 0xFB4F),
        'arabic':   lambda cp: (0x0600 <= cp <= 0x06FF) or (0x0750 <= cp <= 0x077F) or (0xFB50 <= cp <= 0xFDFF),
        'cjk':      lambda cp: (0x4E00 <= cp <= 0x9FFF) or (0x3400 <= cp <= 0x4DBF) or (0xF900 <= cp <= 0xFAFF),
        'devanagari': lambda cp: (0x0900 <= cp <= 0x097F),
        'thai':     lambda cp: (0x0E00 <= cp <= 0x0E7F),
    }

    counts = {name: 0 for name in script_ranges}
    counts['other'] = 0
    total_alpha = 0

    for ch in sample:
        if not ch.isalpha():
            continue
        total_alpha += 1
        cp = ord(ch)
        matched = False
        for name, check in script_ranges.items():
            if check(cp):
                counts[name] += 1
                matched = True
                break
        if not matched:
            counts['other'] += 1

    if total_alpha == 0:
        return {"latin": 100.0}

    return {name: round((count / total_alpha) * 100, 1)
            for name, count in counts.items() if count > 0}


def _score_single_sample(sample):
    """Score a single text sample on 5 quality checks. Returns weighted score (0-100)."""
    total_chars = len(sample)
    if total_chars < 50:
        return 50  # Not enough data

    # Check 1: Unicode printable ratio (25%)
    printable_count = sum(
        1 for ch in sample
        if (ch.isprintable() or ch in ('\n', '\r', '\t'))
        and not (0xE000 <= ord(ch) <= 0xF8FF)
    )
    printable_ratio = printable_count / max(total_chars, 1)
    if printable_ratio > 0.99:
        c1 = 100
    elif printable_ratio < 0.85:
        c1 = 0
    else:
        c1 = int(((printable_ratio - 0.85) / 0.14) * 100)

    # Check 2: Common word hit rate (25%)
    raw_words = sample.split()
    stripped_words = [
        w.lower().strip('.,;:!?()[]{}"\'-—–…»«""''')
        for w in raw_words
    ]
    stripped_words = [w for w in stripped_words if w and w.isalpha() and len(w) > 1]
    word_sample = stripped_words[:500]
    if word_sample:
        hits = sum(1 for w in word_sample if w in _COMMON_ENGLISH_WORDS)
        hit_rate = hits / len(word_sample)
    else:
        hit_rate = 0.0
    if hit_rate > 0.40:
        c2 = 100
    elif hit_rate < 0.10:
        c2 = 0
    else:
        c2 = int(((hit_rate - 0.10) / 0.30) * 100)

    # Check 3: Word length distribution (15%)
    word_lengths = [len(w) for w in word_sample] if word_sample else []
    if len(word_lengths) >= 10:
        avg_len = statistics.mean(word_lengths)
        std_len = statistics.stdev(word_lengths)
        penalty = 0
        if avg_len < 4.0:
            penalty += min(40, int((4.0 - avg_len) * 20))
        elif avg_len > 7.0:
            penalty += min(40, int((avg_len - 7.0) * 15))
        if std_len < 2.0:
            penalty += min(30, int((2.0 - std_len) * 15))
        elif std_len > 5.0:
            penalty += min(30, int((std_len - 5.0) * 10))
        c3 = max(0, 100 - penalty)
    else:
        c3 = 50

    # Check 4: Encoding artifacts (20%)
    fffd_count = sample.count('\ufffd')
    latin1_debris = len(re.findall(r'[ÃÂ][\x80-\xBF]|â€[^\w]', sample))
    win1252_count = sum(1 for ch in sample if 0x0080 <= ord(ch) <= 0x009F)
    non_ascii_seqs = re.findall(r'[^\x00-\x7F\u00C0-\u024F]{3,}', sample)
    artifact_count = fffd_count + latin1_debris + win1252_count + len(non_ascii_seqs)
    per_1000 = (artifact_count / max(total_chars, 1)) * 1000
    if per_1000 == 0:
        c4 = 100
    elif per_1000 < 1:
        c4 = 80
    elif per_1000 > 10:
        c4 = 0
    else:
        c4 = max(0, int(80 - ((per_1000 - 1) / 9) * 80))

    # Check 5: Repeated lines (15%)
    lines = [l.strip() for l in sample.split('\n') if l.strip()]
    if len(lines) >= 10:
        from collections import Counter as _Counter
        line_counts = _Counter(lines)
        repeated = sum(c for _, c in line_counts.items() if c >= 3)
        repeat_ratio = repeated / len(lines)
        if repeat_ratio < 0.02:
            c5 = 100
        elif repeat_ratio > 0.15:
            c5 = 0
        else:
            c5 = max(0, int(100 - ((repeat_ratio - 0.02) / 0.13) * 100))
    else:
        c5 = 80

    return max(0, min(100, int(round(
        c1 * 0.25 + c2 * 0.25 + c3 * 0.15 + c4 * 0.20 + c5 * 0.15
    ))))


def score_text_layer_quality(text, log=None, multi_sample=False):
    """Score extracted text quality on a 0-100 scale.

    Used as a quality gate after extraction to decide whether the result
    is good enough to proceed, or should escalate to a higher extraction tier.

    Checks:
    - Character validity (Unicode printable ratio)
    - Word plausibility (common word hit rate)
    - Word length distribution (detects merges and garbling)
    - Encoding artifacts (replacement chars, Latin-1 debris)
    - Repetition (detects OCR stuttering, header/footer repeats)

    Args:
        text: Extracted text string (at least 1000 chars for reliable scoring)
        log: Optional logging function
        multi_sample: If True, sample 5 positions and report quality variance

    Returns:
        dict with keys:
            'score': int (0-100)
            'details': dict of per-check scores and findings
            'recommendation': str ('accept', 'try_reocr', 'try_vision', 'manual_review')
            'tier_suggestion': int (1=accept, 2=re-ocr, 3=vision)
    """
    if log is None:
        log = lambda msg: None

    # Short-circuit for empty or very short text
    if not text or len(text.strip()) < 100:
        return {
            'score': 0,
            'details': {'error': 'Text too short for reliable scoring'},
            'recommendation': 'manual_review',
            'tier_suggestion': 3,
        }

    # ── Sample from the middle of the book (avoid front/back matter) ──
    text_len = len(text)
    start = text_len // 10
    end = text_len * 9 // 10
    if (end - start) > 5000:
        sample = text[start:start + 5000]
    else:
        sample = text[start:end] if end > start else text

    details = {}

    # ── Check 1: Unicode printable ratio (25% weight) ──────────────
    printable_count = 0
    total_chars = len(sample)
    for ch in sample:
        cp = ord(ch)
        if ch.isprintable() or ch in ('\n', '\r', '\t'):
            if not (0xE000 <= cp <= 0xF8FF):
                printable_count += 1
    printable_ratio = printable_count / max(total_chars, 1)
    if printable_ratio > 0.99:
        check1_score = 100
    elif printable_ratio < 0.85:
        check1_score = 0
    else:
        check1_score = int(((printable_ratio - 0.85) / 0.14) * 100)
    details['unicode_printable'] = {
        'score': check1_score,
        'ratio': round(printable_ratio, 4),
        'non_printable_count': total_chars - printable_count,
    }

    # ── Check 2: Common word hit rate (25% weight) ─────────────────
    raw_words = sample.split()
    stripped_words = []
    for w in raw_words:
        cleaned = w.lower().strip('.,;:!?()[]{}"\'-—–…»«""''')
        if cleaned and cleaned.isalpha() and len(cleaned) > 1:
            stripped_words.append(cleaned)
    if stripped_words:
        word_sample = stripped_words[:500]
        hits = sum(1 for w in word_sample if w in _COMMON_ENGLISH_WORDS)
        hit_rate = hits / len(word_sample)
    else:
        hit_rate = 0.0
    if hit_rate > 0.40:
        check2_score = 100
    elif hit_rate < 0.10:
        check2_score = 0
    else:
        check2_score = int(((hit_rate - 0.10) / 0.30) * 100)
    details['common_word_rate'] = {
        'score': check2_score,
        'hit_rate': round(hit_rate, 4),
        'words_sampled': len(stripped_words[:500]),
        'hits': hits if stripped_words else 0,
    }

    # ── Check 3: Word length distribution (15% weight) ─────────────
    word_lengths = [len(w) for w in stripped_words[:500]] if stripped_words else []
    if len(word_lengths) >= 10:
        avg_len = statistics.mean(word_lengths)
        std_len = statistics.stdev(word_lengths)
        avg_ok = 4.0 <= avg_len <= 7.0
        std_ok = 2.0 <= std_len <= 5.0
        if avg_ok and std_ok:
            check3_score = 100
        else:
            penalty = 0
            if avg_len < 4.0:
                penalty += min(40, int((4.0 - avg_len) * 20))
            elif avg_len > 7.0:
                penalty += min(40, int((avg_len - 7.0) * 15))
            if std_len < 2.0:
                penalty += min(30, int((2.0 - std_len) * 15))
            elif std_len > 5.0:
                penalty += min(30, int((std_len - 5.0) * 10))
            check3_score = max(0, 100 - penalty)
    else:
        check3_score = 50
        avg_len = 0.0
        std_len = 0.0
    details['word_length_distribution'] = {
        'score': check3_score,
        'avg_length': round(avg_len, 2),
        'stddev': round(std_len, 2),
        'words_measured': len(word_lengths),
    }

    # ── Check 4: Encoding artifact count (20% weight) ──────────────
    artifact_count = 0
    fffd_count = sample.count('\ufffd')
    artifact_count += fffd_count
    latin1_debris = len(re.findall(r'[ÃÂ][\x80-\xBF]|â€[^\w]', sample))
    artifact_count += latin1_debris
    win1252_count = sum(1 for ch in sample if 0x0080 <= ord(ch) <= 0x009F)
    artifact_count += win1252_count
    non_ascii_seqs = re.findall(r'[^\x00-\x7F\u00C0-\u024F]{3,}', sample)
    artifact_count += len(non_ascii_seqs)

    per_1000 = (artifact_count / max(total_chars, 1)) * 1000
    if per_1000 == 0:
        check4_score = 100
    elif per_1000 < 1:
        check4_score = 80
    elif per_1000 > 10:
        check4_score = 0
    else:
        check4_score = max(0, int(80 - ((per_1000 - 1) / 9) * 80))
    details['encoding_artifacts'] = {
        'score': check4_score,
        'total_artifacts': artifact_count,
        'per_1000_chars': round(per_1000, 2),
        'fffd_count': fffd_count,
        'latin1_debris': latin1_debris,
        'win1252_control': win1252_count,
        'non_ascii_sequences': len(non_ascii_seqs),
    }

    # ── Check 5: Repeated line ratio (15% weight) ──────────────────
    lines = [l.strip() for l in sample.split('\n') if l.strip()]
    total_lines = len(lines)
    if total_lines >= 10:
        from collections import Counter as _Counter
        line_counts = _Counter(lines)
        repeated_occurrences = sum(
            count for line, count in line_counts.items() if count >= 3
        )
        repeat_ratio = repeated_occurrences / total_lines
        if repeat_ratio < 0.02:
            check5_score = 100
        elif repeat_ratio > 0.15:
            check5_score = 0
        else:
            check5_score = max(0, int(100 - ((repeat_ratio - 0.02) / 0.13) * 100))
    else:
        check5_score = 80
        repeat_ratio = 0.0
    details['repeated_lines'] = {
        'score': check5_score,
        'ratio': round(repeat_ratio, 4) if total_lines >= 10 else 0.0,
        'total_lines': total_lines,
    }

    # ── Weighted overall score ─────────────────────────────────────
    weighted_score = (
        check1_score * 0.25 +
        check2_score * 0.25 +
        check3_score * 0.15 +
        check4_score * 0.20 +
        check5_score * 0.15
    )
    score = max(0, min(100, int(round(weighted_score))))

    # ── Multi-sample quality variance (FU-1) ───────────────────────
    if multi_sample and text_len > 2000:
        positions = [0.10, 0.25, 0.50, 0.75, 0.90]
        sample_scores = []
        for pos in positions:
            s = int(text_len * pos)
            e = min(s + 2000, text_len)
            chunk = text[s:e]
            if len(chunk.strip()) < 100:
                continue
            sample_scores.append({
                'position': pos,
                'score': _score_single_sample(chunk),
            })
        if sample_scores:
            scores = [ss['score'] for ss in sample_scores]
            details['multi_sample'] = {
                'samples': sample_scores,
                'variance': max(scores) - min(scores),
                'min_score': min(scores),
                'max_score': max(scores),
                'problem_regions': [ss for ss in sample_scores if ss['score'] < 60],
            }

    # ── Recommendation logic ───────────────────────────────────────
    if score >= 75:
        recommendation = 'accept'
        tier_suggestion = 1
    elif score >= 50:
        recommendation = 'try_reocr'
        tier_suggestion = 2
    elif score >= 30:
        recommendation = 'try_vision'
        tier_suggestion = 3
    else:
        recommendation = 'manual_review'
        tier_suggestion = 3

    return {
        'score': score,
        'details': details,
        'recommendation': recommendation,
        'tier_suggestion': tier_suggestion,
    }


def extract_cover_image(pdf_path, output_path, log, dpi=300, poppler_path=None):
    """
    Render the first page of a PDF as a JPEG cover image.

    Uses pdf2image (poppler) to render at high DPI for crisp Kindle display.
    Pass poppler_path to specify the poppler bin directory explicitly.
    Returns the output path if successful, None if failed.
    """
    try:
        from pdf2image import convert_from_path

        log("  Rendering first page as cover image...")
        kwargs = {
            'first_page': 1,
            'last_page': 1,
            'dpi': dpi,
            'fmt': 'jpeg',
        }
        if poppler_path:
            kwargs['poppler_path'] = poppler_path

        images = convert_from_path(pdf_path, **kwargs)

        if images:
            images[0].save(output_path, 'JPEG', quality=90)
            width, height = images[0].size
            file_size_kb = os.path.getsize(output_path) / 1024
            log(f"  Cover image saved: {output_path}")
            log(f"  Dimensions: {width}x{height}, Size: {file_size_kb:.0f} KB")
            return output_path
        else:
            log("  No pages rendered from PDF")
            return None

    except ImportError:
        log("  pdf2image not installed -- skipping cover extraction (pip install pdf2image)")
        return None
    except Exception as e:
        log(f"  Cover extraction failed: {e}")
        return None


def extract_bookmarks(pdf_path, log):
    """Extract bookmarks/outline from PDF with page numbers."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        outline = reader.outline
        if not outline:
            log("  No bookmarks found in PDF")
            return []

        bookmarks = []
        def walk(items, depth=0):
            for item in items:
                if isinstance(item, list):
                    walk(item, depth + 1)
                else:
                    try:
                        page = reader.get_destination_page_number(item) + 1  # convert 0-indexed to 1-indexed
                        title = item.title.strip()
                        # Normalize garbage Unicode: strip replacement chars, control chars
                        title = re.sub(r'[\ufffd\x00-\x1f]+', ' ', title)
                        title = re.sub(r'\s+', ' ', title).strip()
                        title_lower = title.lower()

                        # Always skip these (truly not useful)
                        skip_always = ['e n d', 'end', 'finis', 'half title', 'frontmatter']
                        if title_lower.strip() in skip_always:
                            continue
                        if title.startswith('\xa9') or title.startswith('\u00a9'):
                            continue

                        # Strip author names after *** separator
                        if '***' in title:
                            title = title.split('***')[0].strip()

                        # Detect front matter sections
                        front_matter_patterns = ['title', 'copyright', 'contents',
                                                'contributor', 'acknowledgment',
                                                'dedication', 'colophon', 'foreword',
                                                'preface']
                        is_front_matter = any(title_lower.startswith(s) for s in front_matter_patterns)
                        # Also catch © symbol
                        if title.startswith('\xa9') or '\xa9' in title:
                            is_front_matter = True

                        # Detect back matter sections (keep as navigable headings)
                        back_matter_patterns = ['index', 'bibliography', 'references',
                                               'notes', 'endnotes', 'footnotes', 'appendix',
                                               'glossary', 'works cited', 'further reading',
                                               'selected bibliography', 'abbreviation']
                        is_back_matter = any(bm_pat in title_lower for bm_pat in back_matter_patterns)

                        # Determine level and classification
                        top_level_patterns = [
                            r'^(?:Part|PART|Volume|VOLUME)\b',
                            r'^(?:Epilogue|EPILOGUE)\b',
                            r'^(?:Prologue|PROLOGUE)\b',
                            r'^(?:About|ABOUT)\b',
                            r'^(?:Afterword|AFTERWORD)\b',
                            r'^(?:Conclusion|CONCLUSION)\b',
                        ]
                        is_top_level = any(re.match(pat, title, re.IGNORECASE) for pat in top_level_patterns)
                        if is_back_matter:
                            is_top_level = True

                        # Front matter entries are level 2 (nested under "Front Matter" h1)
                        # Top-level entries are level 1
                        # Everything else is level 2 (chapters)
                        if is_front_matter:
                            level = 2  # will be nested under synthetic "Front Matter" h1
                        elif is_top_level:
                            level = 1
                        else:
                            level = 2

                        bookmarks.append({
                            'title': title,
                            'page': page,
                            'level': level,
                            'front_matter': is_front_matter,
                            'back_matter': is_back_matter
                        })
                    except Exception:
                        continue

        walk(outline)

        # Fix common OCR artifact: "rn" ligature extracted as "m" in bookmark titles.
        # E.g., "Modem Science" → "Modern Science", "Modem Authors" → "Modern Authors".
        # Strategy: extract body text, then for each "m" word in a bookmark, check
        # if the "rn" version appears in the body text. This handles any word
        # without needing a predefined context list.
        try:
            from spellchecker import SpellChecker
            _spell = SpellChecker()

            # Build a set of words from the body text for lookup
            body_words = set()
            try:
                from pypdf import PdfReader
                reader = PdfReader(pdf_path)
                sample_pages = min(50, len(reader.pages))
                for pg in reader.pages[:sample_pages]:
                    page_text = pg.extract_text() or ''
                    body_words.update(w.lower().strip('.,;:!?()[]"\'')
                                      for w in page_text.split() if len(w) > 3)
            except Exception:
                pass  # body text extraction failed — fall back to spellchecker only

            for bm in bookmarks:
                words = bm['title'].split()
                fixed_words = []
                changed = False
                for wi, w in enumerate(words):
                    clean = w.strip('.,;:!?()[]"\'')
                    if 'm' not in clean.lower() or len(clean) <= 3:
                        fixed_words.append(w)
                        continue
                    # Try replacing each internal 'm' with 'rn'
                    best_candidate = None
                    for pos in range(1, len(clean)):
                        if clean[pos].lower() != 'm':
                            continue
                        repl = 'rn' if clean[pos].islower() else 'Rn'
                        candidate = clean[:pos] + repl + clean[pos+1:]
                        cand_lower = candidate.lower()
                        # Case 1: m version is unknown word → fix if rn version is known
                        if _spell.unknown([clean.lower()]) and not _spell.unknown([cand_lower]):
                            best_candidate = candidate
                            break
                        # Case 2: both are valid words → check if rn version appears
                        # in the body text (e.g., "Modern" in body but "Modem" in bookmark)
                        if cand_lower in body_words and clean.lower() not in body_words:
                            best_candidate = candidate
                            break
                        # Case 3: rn version in body text AND is a more common word
                        if not _spell.unknown([cand_lower]) and cand_lower in body_words:
                            orig_freq = _spell.word_usage_frequency(clean.lower())
                            cand_freq = _spell.word_usage_frequency(cand_lower)
                            if cand_freq > orig_freq * 3:
                                best_candidate = candidate
                                break
                    if best_candidate:
                        w = w.replace(clean, best_candidate)
                        changed = True
                    fixed_words.append(w)
                if changed:
                    old_title = bm['title']
                    bm['title'] = ' '.join(fixed_words)
                    log(f"    [bookmark fix] '{old_title[:50]}' → '{bm['title'][:50]}'")
        except ImportError:
            pass  # pyspellchecker not installed — skip

        log(f"  Found {len(bookmarks)} content bookmarks in PDF")
        for bm in bookmarks:
            log(f"    [{bm['level']}] p.{bm['page']}: {bm['title'][:60]}")
        return bookmarks
    except Exception as e:
        log(f"  Bookmark extraction failed: {e}")
        return []


def detect_pdf_type(pdf_path, log):
    """Detect whether a PDF contains extractable text or is image-only (scanned).

    Samples pages evenly through the document and checks text density.
    Returns dict with 'pdf_type' ('structured' or 'image'), stats.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        log("  pypdf not installed -- assuming structured PDF")
        return {'pdf_type': 'structured', 'avg_chars_per_page': -1,
                'pages_sampled': 0, 'total_pages': 0}

    try:
        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)

        if total_pages == 0:
            log("  PDF type detection: empty PDF (0 pages)")
            return {'pdf_type': 'image', 'avg_chars_per_page': 0,
                    'pages_sampled': 0, 'total_pages': 0}

        # Sample up to 10 pages evenly distributed through the document
        if total_pages <= 5:
            sample_indices = list(range(total_pages))
        else:
            num_samples = min(10, total_pages)
            sample_indices = [int(total_pages * (i + 1) / (num_samples + 1))
                              for i in range(num_samples)]
            # Clamp to valid range
            sample_indices = [min(i, total_pages - 1) for i in sample_indices]
            # Deduplicate while preserving order
            seen = set()
            sample_indices = [i for i in sample_indices if not (i in seen or seen.add(i))]

        total_chars = 0
        for idx in sample_indices:
            try:
                text = reader.pages[idx].extract_text() or ''
                non_ws = len(re.sub(r'\s', '', text))
                total_chars += non_ws
            except Exception:
                pass  # skip unreadable pages

        avg_chars = total_chars / len(sample_indices) if sample_indices else 0
        pdf_type = 'structured' if avg_chars >= 50 else 'image'

        log(f"  PDF type detection: {pdf_type} (avg {avg_chars:.0f} chars/page "
            f"from {len(sample_indices)}/{total_pages} pages)")

        return {
            'pdf_type': pdf_type,
            'avg_chars_per_page': avg_chars,
            'pages_sampled': len(sample_indices),
            'total_pages': total_pages,
        }
    except Exception as e:
        log(f"  PDF type detection failed: {e} -- assuming structured")
        return {'pdf_type': 'structured', 'avg_chars_per_page': -1,
                'pages_sampled': 0, 'total_pages': 0}


def detect_column_layout(pdf_path, log, sample_pages=8):
    """Detect whether a PDF uses a multi-column layout by analyzing text block positions.

    Uses PyMuPDF to extract text blocks with coordinates, then checks whether blocks
    cluster into distinct x-coordinate ranges (indicating columns).

    Returns:
        dict with keys:
            'is_multicolumn': bool
            'num_columns': int (1, 2, or 3)
            'column_boundaries': list of (x_start, x_end) tuples
            'confidence': float (0.0 to 1.0)
            'page_width': float
    """
    try:
        import pymupdf
    except ImportError:
        log("  [WARN] pymupdf not installed — column detection unavailable")
        log("  [WARN] Run: python -m pip install pymupdf")
        return {'is_multicolumn': False, 'num_columns': 1,
                'column_boundaries': [], 'confidence': 0.0, 'page_width': 0.0}

    try:
        doc = pymupdf.open(pdf_path)
        total_pages = len(doc)

        # Skip first 5 pages (often title/TOC with different layout)
        start_page = min(5, max(0, total_pages // 2))
        n_sample = min(sample_pages, total_pages - start_page)
        if n_sample <= 0:
            doc.close()
            return {'is_multicolumn': False, 'num_columns': 1,
                    'column_boundaries': [], 'confidence': 0.0, 'page_width': 0.0}

        # Evenly sample pages from the body of the document
        sample_indices = [start_page + int(i * (total_pages - start_page) / n_sample)
                          for i in range(n_sample)]
        sample_indices = list(dict.fromkeys(sample_indices))  # deduplicate

        # page_width: used for histogram bins only — first sample page is intentional for consistency across the loop.
        # Per-page actual width is computed inside the loop as page_width_local (used only for the full-width filter).
        page_width = doc[sample_indices[0]].rect.width
        pages_with_two_clusters = 0
        column_boundaries_list = []

        for pg_idx in sample_indices:
            page = doc[pg_idx]
            blocks = page.get_text("blocks")
            # block format: (x0, y0, x1, y1, text, block_no, block_type)
            page_height = page.rect.height
            page_width_local = page.rect.width
            text_blocks = [b for b in blocks
                           if b[6] == 0                                     # text blocks only
                           and len((b[4] or '').strip()) >= 50              # not too short
                           and b[1] / page_height <= 0.88                   # exclude bottom 12% (footnotes)
                           and (b[2] - b[0]) / page_width_local <= 0.70]   # exclude full-width blocks

            if len(text_blocks) < 3:
                continue  # too few blocks to classify this page

            x0_values = [b[0] for b in text_blocks]

            # Histogram approach: divide page width into 20 bins, find the gap
            bin_width = page_width / 20
            histogram = [0] * 20
            for x0 in x0_values:
                bin_idx = min(int(x0 / bin_width), 19)
                histogram[bin_idx] += 1

            # Find left cluster (bins 1-8) and right cluster (bins 9-16)
            left_bins  = [(i, histogram[i]) for i in range(0, 9)  if histogram[i] > 0]
            right_bins = [(i, histogram[i]) for i in range(9, 20) if histogram[i] > 0]

            if left_bins and right_bins:
                left_peak_bin  = max(left_bins,  key=lambda x: x[1])[0]
                right_peak_bin = max(right_bins, key=lambda x: x[1])[0]
                gap = (right_peak_bin - left_peak_bin) * bin_width
                gap_threshold = page_width * 0.15  # gap must be >15% of page width

                if gap >= gap_threshold:
                    pages_with_two_clusters += 1
                    col1_start = 0
                    col1_end   = left_peak_bin * bin_width + bin_width * 2
                    col2_start = right_peak_bin * bin_width - bin_width
                    col2_end   = page_width
                    column_boundaries_list.append(
                        [(col1_start, col1_end), (col2_start, col2_end)]
                    )

        doc.close()

        confidence = pages_with_two_clusters / len(sample_indices) if sample_indices else 0.0
        is_multicolumn = confidence >= 0.6

        # Use median column boundaries across sampled pages for consistency
        if column_boundaries_list:
            col_bounds = column_boundaries_list[len(column_boundaries_list) // 2]
        else:
            col_bounds = []

        log(f"  Column detection: {pages_with_two_clusters}/{len(sample_indices)} pages "
            f"show 2-column layout (confidence: {confidence:.0%})")

        return {
            'is_multicolumn': is_multicolumn,
            'num_columns': 2 if is_multicolumn else 1,
            'column_boundaries': col_bounds,
            'confidence': confidence,
            'page_width': page_width,
        }

    except Exception as e:
        log(f"  [WARN] Column layout detection failed: {e}")
        return {'is_multicolumn': False, 'num_columns': 1,
                'column_boundaries': [], 'confidence': 0.0, 'page_width': 0.0}


def detect_image_density(pdf_path, log, sample_pages=10):
    """Detect embedded image density in a PDF (DE-4).

    A PDF with ~1 image per page is likely a scan.
    Returns dict: {total_images, pages_sampled, images_per_page, likely_scan}
    """
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)
        if total_pages == 0:
            return {'total_images': 0, 'pages_sampled': 0,
                    'images_per_page': 0, 'likely_scan': False}

        num_samples = min(sample_pages, total_pages)
        if total_pages <= sample_pages:
            sample_indices = list(range(total_pages))
        else:
            sample_indices = list(set(
                min(int(total_pages * (i + 1) / (num_samples + 1)), total_pages - 1)
                for i in range(num_samples)
            ))

        total_images = 0
        for idx in sample_indices:
            try:
                page = reader.pages[idx]
                resources = page.get('/Resources')
                if resources:
                    xobjects = resources.get('/XObject')
                    if xobjects:
                        xobj = xobjects.get_object() if hasattr(xobjects, 'get_object') else xobjects
                        if isinstance(xobj, dict):
                            for _, obj_ref in xobj.items():
                                try:
                                    obj = obj_ref.get_object() if hasattr(obj_ref, 'get_object') else obj_ref
                                    if isinstance(obj, dict) and obj.get('/Subtype') == '/Image':
                                        total_images += 1
                                except Exception:
                                    pass
            except Exception:
                pass

        images_per_page = total_images / len(sample_indices) if sample_indices else 0
        likely_scan = images_per_page >= 0.8 and total_images >= len(sample_indices) * 0.8

        return {
            'total_images': total_images,
            'pages_sampled': len(sample_indices),
            'images_per_page': round(images_per_page, 2),
            'likely_scan': likely_scan,
        }
    except Exception as e:
        log(f"  Image density detection failed: {e}")
        return {'total_images': 0, 'pages_sampled': 0,
                'images_per_page': 0, 'likely_scan': False}


def analyze_encoding_distribution(text, sample_size=10000):
    """Analyze character encoding distribution of extracted text (DE-5).

    Returns percentages of characters in different Unicode ranges.
    High latin_ext_pct correlates with encoding confusion.
    """
    if not text or len(text.strip()) < 50:
        return {'ascii_pct': 0, 'latin_ext_pct': 0, 'high_unicode_pct': 0,
                'control_chars': 0, 'replacement_chars': 0}

    text_len = len(text)
    start = text_len // 10
    end = min(start + sample_size, text_len * 9 // 10)
    sample = text[start:end] if end > start else text[:sample_size]

    total = len(sample)
    ascii_count = 0
    latin_ext = 0
    high_unicode = 0
    control = 0
    replacement = 0

    for ch in sample:
        cp = ord(ch)
        if cp == 0xFFFD:
            replacement += 1
        elif cp < 32 and ch not in ('\n', '\r', '\t'):
            control += 1
        elif cp < 128:
            ascii_count += 1
        elif cp < 256:
            latin_ext += 1
        else:
            high_unicode += 1

    return {
        'ascii_pct': round(ascii_count / max(total, 1) * 100, 1),
        'latin_ext_pct': round(latin_ext / max(total, 1) * 100, 1),
        'high_unicode_pct': round(high_unicode / max(total, 1) * 100, 1),
        'control_chars': control,
        'replacement_chars': replacement,
    }


def normalize_encoding(text, log=None):
    """Fix common encoding corruption patterns in extracted PDF text.

    Handles three main corruption types:
    1. Latin-1/Windows-1252 bytes misinterpreted as UTF-8 (mojibake)
       e.g., "\xe2\x80\x99" should be "\u2019", "\xc3\xa9" should be "é"
    2. Replacement characters (U+FFFD) from failed decoding
    3. Control characters that shouldn't appear in text

    Runs after extraction, before formatting. Non-destructive on clean text —
    only modifies characters that are clearly encoding artifacts.

    Returns: (cleaned_text, stats_dict)
        stats_dict: {replacements_made, mojibake_fixed, control_chars_removed,
                     replacement_chars_found}
    """
    if not text:
        return text, {'replacements_made': 0}

    if log is None:
        log = lambda msg: None

    stats = {
        'replacements_made': 0,
        'mojibake_fixed': 0,
        'control_chars_removed': 0,
        'replacement_chars_found': 0,
    }

    # ── Pattern 1: UTF-8 mojibake from Windows-1252 / Latin-1 ──────────
    # Loaded from substitution table (config/ocr_substitutions.json)
    _subs_for_mojibake = load_ocr_substitutions()
    mojibake_map = _subs_for_mojibake.get('mojibake_map', {})

    for bad, good in mojibake_map.items():
        if bad in text:
            count = text.count(bad)
            text = text.replace(bad, good)
            stats['mojibake_fixed'] += count
            stats['replacements_made'] += count

    # ── Pattern 1b: Generic Latin-1 -> UTF-8 mojibake detection ─────────
    # Catch remaining Ã+byte patterns that aren't in the explicit map
    # Only fix if the result is a valid printable character
    def _fix_c3_mojibake(match):
        """Fix Ã+byte mojibake: try decoding the two bytes as UTF-8."""
        try:
            b1 = ord('\xc3')  # 0xC3
            b2 = ord(match.group(1))
            decoded = bytes([b1, b2]).decode('utf-8')
            if decoded.isprintable():
                stats['mojibake_fixed'] += 1
                stats['replacements_made'] += 1
                return decoded
        except (UnicodeDecodeError, ValueError):
            pass
        return match.group(0)  # Return unchanged if can't fix

    # Match Ã followed by a byte in the 0x80-0xBF range (UTF-8 continuation bytes)
    text = re.sub(r'\xc3([\x80-\xbf])', _fix_c3_mojibake, text)

    # Match Â followed by a byte in the 0x80-0xBF range
    def _fix_c2_mojibake(match):
        try:
            b1 = ord('\xc2')  # 0xC2
            b2 = ord(match.group(1))
            decoded = bytes([b1, b2]).decode('utf-8')
            if decoded.isprintable() or decoded in ('\u00a0',):  # Allow NBSP
                stats['mojibake_fixed'] += 1
                stats['replacements_made'] += 1
                return decoded
        except (UnicodeDecodeError, ValueError):
            pass
        return match.group(0)

    text = re.sub(r'\xc2([\x80-\xbf])', _fix_c2_mojibake, text)

    # ── Pattern 2: Replacement characters (U+FFFD) ────────────────────
    # Count them but don't remove — they indicate data loss that can't be recovered
    replacement_count = text.count('\ufffd')
    if replacement_count > 0:
        stats['replacement_chars_found'] = replacement_count
        log(f"  Encoding: found {replacement_count} replacement characters (U+FFFD)")

    # ── Pattern 3: Control characters ─────────────────────────────────
    # Remove ASCII control characters (0x00-0x1F) except tab, newline, carriage return
    control_pattern = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')
    control_matches = control_pattern.findall(text)
    if control_matches:
        text = control_pattern.sub('', text)
        stats['control_chars_removed'] = len(control_matches)
        stats['replacements_made'] += len(control_matches)

    # ── Pattern 4: Stray Windows-1252 characters in the 0x80-0x9F range ──
    # These are control characters in Latin-1 but printable in Windows-1252
    win1252_map = {
        '\x80': '\u20AC',  # Euro sign €
        '\x85': '\u2026',  # Ellipsis …
        '\x91': '\u2018',  # Left single quote '
        '\x92': '\u2019',  # Right single quote '
        '\x93': '\u201C',  # Left double quote "
        '\x94': '\u201D',  # Right double quote "
        '\x95': '\u2022',  # Bullet •
        '\x96': '\u2013',  # En dash –
        '\x97': '\u2014',  # Em dash —
        '\x99': '\u2122',  # Trademark ™
    }

    for bad, good in win1252_map.items():
        if bad in text:
            count = text.count(bad)
            text = text.replace(bad, good)
            stats['mojibake_fixed'] += count
            stats['replacements_made'] += count

    # ── Log summary ──────────────────────────────────────────────────
    total = stats['replacements_made']
    if total > 0:
        log(f"  Encoding normalization: {total} fixes "
            f"({stats['mojibake_fixed']} mojibake, "
            f"{stats['control_chars_removed']} control chars)")

    return text, stats


def extract_text_ocr(pdf_path, log, tesseract_path=None, poppler_path=None, dpi=300):
    """Extract text from an image-only PDF using Tesseract OCR.

    Renders each page as an image, runs OCR, returns text with
    <<PAGE:N>> markers matching the format of extract_text().

    Requires: pytesseract, pdf2image, Tesseract executable, poppler
    """
    try:
        import pytesseract
    except ImportError:
        raise RuntimeError(
            "pytesseract is required for OCR extraction. "
            "Install with: python -m pip install pytesseract")

    try:
        from pdf2image import convert_from_path
    except ImportError:
        raise RuntimeError(
            "pdf2image is required for OCR extraction. "
            "Install with: python -m pip install pdf2image")

    if tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = tesseract_path

    # Verify Tesseract is actually reachable before processing 400+ pages
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        cmd = pytesseract.pytesseract.tesseract_cmd
        raise RuntimeError(
            f"Tesseract executable not found at '{cmd}'. "
            "Install from github.com/UB-Mannheim/tesseract/wiki "
            "or pass --tesseract-path pointing to tesseract.exe")

    # Get total page count first
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)
    except Exception:
        # Fall back to pdf2image info if pypdf fails
        from pdf2image import pdfinfo_from_path
        kwargs = {}
        if poppler_path:
            kwargs['poppler_path'] = poppler_path
        info = pdfinfo_from_path(pdf_path, **kwargs)
        total_pages = info.get('Pages', 0)

    if total_pages == 0:
        log("  OCR: PDF has 0 pages")
        return ""

    log(f"  OCR: Rendering {total_pages} pages at {dpi} DPI...")

    pages_text = []
    pages_with_text = 0
    total_chars = 0
    batch_size = 25

    for batch_start in range(1, total_pages + 1, batch_size):
        batch_end = min(batch_start + batch_size - 1, total_pages)

        try:
            kwargs = {
                'first_page': batch_start,
                'last_page': batch_end,
                'dpi': dpi,
            }
            if poppler_path:
                kwargs['poppler_path'] = poppler_path

            images = convert_from_path(pdf_path, **kwargs)
        except Exception as e:
            log(f"  OCR: Failed to render pages {batch_start}-{batch_end}: {e}")
            continue

        for i, image in enumerate(images):
            page_num = batch_start + i
            try:
                text = pytesseract.image_to_string(image, lang='eng')
                text = text.strip()
                if text:
                    pages_text.append(f"<<PAGE:{page_num}>>\n{text}")
                    pages_with_text += 1
                    total_chars += len(text)
            except Exception as e:
                log(f"  OCR: Page {page_num} failed: {e}")
                continue

        # Log progress every batch
        if batch_end % batch_size == 0 or batch_end == total_pages:
            log(f"  OCR: Processed {batch_end}/{total_pages} pages...")

    result = "\n".join(pages_text)
    log(f"  OCR: Extracted text from {pages_with_text}/{total_pages} pages "
        f"({total_chars:,} characters)")

    return result


def ocr_text_to_para_dicts(ocr_text, log):
    """Convert OCR-extracted text (with <<PAGE:N>> markers) into paragraph dicts
    compatible with the HTML formatting pipeline.

    Since OCR doesn't provide font metadata, heading detection relies on
    pattern-based promotion (Chapter X, ALL CAPS) in format_paragraphs_as_html().

    Returns: (para_dicts, body_size) tuple matching extract_with_pdfminer_html() signature.
    """
    if not ocr_text or not ocr_text.strip():
        log("  OCR->HTML bridge: no text to convert")
        return [], 12.0

    para_dicts = []
    current_page = 1
    body_size = 12.0  # Default — OCR doesn't know real font sizes

    lines = ocr_text.split('\n')
    current_paragraph = []

    for line in lines:
        page_match = re.match(r'<<PAGE:(\d+)>>', line)
        if page_match:
            if current_paragraph:
                text = ' '.join(current_paragraph).strip()
                if text:
                    para_dicts.append({
                        'text': text, 'sz': body_size,
                        'bold': False, 'italic': False,
                        'page': current_page, 'tag': None,
                    })
                current_paragraph = []
            current_page = int(page_match.group(1))
            continue

        stripped = line.strip()

        if not stripped:
            if current_paragraph:
                text = ' '.join(current_paragraph).strip()
                if text:
                    para_dicts.append({
                        'text': text, 'sz': body_size,
                        'bold': False, 'italic': False,
                        'page': current_page, 'tag': None,
                    })
                current_paragraph = []
            continue

        # Detect likely headings by heuristic
        is_likely_heading = False
        if len(stripped) < 80:
            words = stripped.split()
            if stripped == stripped.upper() and any(c.isalpha() for c in stripped):
                alpha_words = [w for w in words if len(w) >= 2 and w.isalpha()]
                if alpha_words:
                    is_likely_heading = True
            if re.match(r'^(?:Chapter|CHAPTER|Part|PART|Section|SECTION)\s+[\dIVXLCivxlc]+',
                        stripped, re.IGNORECASE):
                is_likely_heading = True

        if is_likely_heading:
            if current_paragraph:
                text = ' '.join(current_paragraph).strip()
                if text:
                    para_dicts.append({
                        'text': text, 'sz': body_size,
                        'bold': False, 'italic': False,
                        'page': current_page, 'tag': None,
                    })
                current_paragraph = []
            para_dicts.append({
                'text': stripped, 'sz': body_size * 1.5,
                'bold': True, 'italic': False,
                'page': current_page, 'tag': None,
            })
            continue

        current_paragraph.append(stripped)

    if current_paragraph:
        text = ' '.join(current_paragraph).strip()
        if text:
            para_dicts.append({
                'text': text, 'sz': body_size,
                'bold': False, 'italic': False,
                'page': current_page, 'tag': None,
            })

    log(f"  OCR->HTML bridge: {len(para_dicts)} paragraphs from {current_page} pages")
    return para_dicts, body_size


def extract_text_vision(pdf_path, log, api_key=None, poppler_path=None,
                        dpi=200, batch_size=3, cost_limit=15.0):
    """Extract text from PDF pages using Claude Vision API (Tier 3).

    Renders every page as an image and sends to Claude for transcription.
    Highest quality — handles multi-script, custom fonts, degraded scans.

    Cost: ~$0.02-0.04 per page (Sonnet). Cached after first extraction.

    Returns:
        dict with text, pages_processed, total_pages, input_tokens,
        output_tokens, cost_usd — or None on failure/abort.
    """
    if not api_key:
        api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError(
            "Claude Vision extraction requires ANTHROPIC_API_KEY. "
            "Set as environment variable or pass --api-key.")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    from visual_qa import (render_pages_to_png, call_claude_vision,
                           find_poppler_path, get_pdf_page_count)

    total_pages = get_pdf_page_count(pdf_path)
    if total_pages == 0:
        log("  Vision: PDF has 0 pages")
        return None

    log(f"  Vision: PDF has {total_pages} pages")

    # Cost estimate (Sonnet: $3/M input, $15/M output)
    est_input_tokens = total_pages * 2000
    est_output_tokens = total_pages * 800
    est_cost = (est_input_tokens / 1_000_000) * 3.0 + (est_output_tokens / 1_000_000) * 15.0

    log(f"  Vision: Estimated cost: ${est_cost:.2f} "
        f"(~{total_pages * 2800:,} tokens, {total_pages} pages at {dpi} DPI)")

    if est_cost > cost_limit:
        log(f"  Vision: ABORTED — estimated cost ${est_cost:.2f} exceeds "
            f"limit ${cost_limit:.2f}")
        log(f"  Vision: Use --vision-cost-limit to increase")
        return None

    resolved_poppler = find_poppler_path(poppler_path)
    model = _load_api_model("sonnet")

    all_page_numbers = list(range(1, total_pages + 1))
    all_text_parts = []
    total_input = 0
    total_output = 0
    pages_processed = 0

    import base64

    for batch_start in range(0, len(all_page_numbers), batch_size):
        batch_pages = all_page_numbers[batch_start:batch_start + batch_size]
        batch_num = (batch_start // batch_size) + 1
        total_batches = (len(all_page_numbers) + batch_size - 1) // batch_size

        log(f"  Vision: Batch {batch_num}/{total_batches} — "
            f"pages {batch_pages[0]}-{batch_pages[-1]}")

        try:
            page_images = render_pages_to_png(
                pdf_path, batch_pages, dpi=dpi, poppler_path=resolved_poppler)
        except Exception as e:
            log(f"  Vision: Failed to render batch {batch_num}: {e}")
            continue

        if not page_images:
            continue

        content = []
        for page_num, png_bytes in page_images:
            b64_data = base64.b64encode(png_bytes).decode('utf-8')
            content.append({"type": "text", "text": f"--- Page {page_num} ---"})
            content.append({
                "type": "image",
                "source": {
                    "type": "base64", "media_type": "image/png",
                    "data": b64_data,
                }
            })
        content.append({
            "type": "text",
            "text": f"Transcribe pages {batch_pages[0]} through {batch_pages[-1]} now."
        })

        payload = {
            "model": model,
            "max_tokens": 16384,
            "system": _VISION_TRANSCRIPTION_PROMPT,
            "messages": [{"role": "user", "content": content}]
        }

        try:
            raw_text, in_tok, out_tok = call_claude_vision(payload, api_key)
            total_input += in_tok
            total_output += out_tok
            pages_processed += len(batch_pages)
            if raw_text:
                all_text_parts.append(raw_text)
            log(f"  Vision: Batch {batch_num} complete — "
                f"{in_tok:,} in / {out_tok:,} out tokens")
        except Exception as e:
            log(f"  Vision: Batch {batch_num} API call failed: {e}")
            continue

    if not all_text_parts:
        log("  Vision: No text extracted from any batch")
        return None

    full_text = '\n'.join(all_text_parts)
    actual_cost = (total_input / 1_000_000) * 3.0 + (total_output / 1_000_000) * 15.0
    word_count = len(full_text.split())
    log(f"  Vision: Extraction complete — {pages_processed}/{total_pages} pages, "
        f"{word_count:,} words, ${actual_cost:.4f}")

    return {
        'text': full_text,
        'pages_processed': pages_processed,
        'total_pages': total_pages,
        'input_tokens': total_input,
        'output_tokens': total_output,
        'cost_usd': actual_cost,
    }


def vision_text_to_para_dicts(vision_text, log):
    """Convert Vision-transcribed Markdown text into paragraph dicts.

    Handles: ## headings, *italic*, **bold**, > blockquotes,
    [^N] footnotes, <<PAGE:N>> page markers.

    Output keys match format_paragraphs_as_html() expectations:
      font_size, is_bold, is_italic, is_centered, is_all_caps,
      page_number, char_count, is_page_marker.

    Returns: (para_dicts, body_size) tuple.
    """
    if not vision_text or not vision_text.strip():
        log("  Vision->HTML bridge: no text to convert")
        return [], 12.0

    para_dicts = []
    current_page = 1
    body_size = 12.0
    heading_count = 0
    last_emitted_page = 0  # track which page markers we've emitted

    lines = vision_text.split('\n')
    current_paragraph = []

    def _emit_page_marker_if_needed():
        """Emit a page marker entry when the page changes."""
        nonlocal last_emitted_page
        if current_page != last_emitted_page:
            para_dicts.append({
                'text': '', 'font_size': 0, 'is_bold': False,
                'is_italic': False, 'is_centered': False,
                'is_all_caps': False, 'page_number': current_page,
                'line_count': 0, 'char_count': 0,
                'is_page_marker': True,
            })
            last_emitted_page = current_page

    def _make_para(text, font_size=None, is_bold=False, is_italic=False,
                   is_all_caps=False):
        """Build a paragraph dict with correct keys for format_paragraphs_as_html."""
        _emit_page_marker_if_needed()
        return {
            'text': text,
            'font_size': font_size if font_size is not None else body_size,
            'is_bold': is_bold,
            'is_italic': is_italic,
            'is_centered': False,
            'is_all_caps': is_all_caps,
            'page_number': current_page,
            'char_count': len(text),
        }

    def flush_paragraph():
        nonlocal current_paragraph
        if current_paragraph:
            text = ' '.join(current_paragraph).strip()
            if text:
                text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
                text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)',
                              r'<em>\1</em>', text)
                text = re.sub(r'\[\^(\d+)\]', r'<sup>\1</sup>', text)
                para_dicts.append(_make_para(text))
            current_paragraph = []

    for line in lines:
        page_match = re.match(r'<<PAGE:(\d+)>>', line)
        if page_match:
            flush_paragraph()
            current_page = int(page_match.group(1))
            continue

        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            continue

        words_in_line = stripped.split()

        # Rule 1: ## HEADING markers from Gemini/Vision
        heading_match = re.match(r'^(#{1,3})\s+(.+)$', stripped)
        if heading_match:
            flush_paragraph()
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()
            heading_text = re.sub(r'\*\*(.+?)\*\*', r'\1', heading_text)
            sz_multiplier = {1: 2.0, 2: 1.5, 3: 1.25}.get(level, 1.25)
            para_dicts.append(_make_para(
                heading_text, font_size=body_size * sz_multiplier,
                is_bold=True, is_all_caps=(heading_text == heading_text.upper()),
            ))
            heading_count += 1
            continue

        # Rule 2: ALL CAPS heading detection
        if len(stripped) < 100 and stripped == stripped.upper() and any(c.isalpha() for c in stripped):
            alpha_words = [w for w in words_in_line if len(w) >= 2 and w.isalpha()]
            if alpha_words:
                # Filter: not ending with period (running headers), not starting
                # with digit (page numbers), has a word with 3+ letters
                has_long_word = any(len(w) >= 3 for w in alpha_words)
                if (has_long_word
                        and not stripped.endswith('.')
                        and not stripped[0].isdigit()):
                    flush_paragraph()
                    sz_mult = 1.5 if len(alpha_words) <= 4 else 1.25
                    para_dicts.append(_make_para(
                        stripped, font_size=body_size * sz_mult,
                        is_bold=True, is_all_caps=True,
                    ))
                    heading_count += 1
                    continue

        # Rule 3: Chapter/Part/Section keyword heading detection
        chapter_match = re.match(
            r'^(?:Chapter|CHAPTER|Part|PART|Section|SECTION|Book|BOOK|'
            r'Introduction|INTRODUCTION|Preface|PREFACE|Foreword|FOREWORD|'
            r'Prologue|PROLOGUE|Epilogue|EPILOGUE|Conclusion|CONCLUSION|'
            r'Appendix|APPENDIX|Bibliography|BIBLIOGRAPHY|Index|INDEX)'
            r'(?:\s+[\dIVXLCivxlc]+)?(?:[.:]\s+.*)?$',
            stripped, re.IGNORECASE
        )
        if chapter_match and len(stripped) < 120:
            flush_paragraph()
            para_dicts.append(_make_para(
                stripped, font_size=body_size * 1.5,
                is_bold=True,
                is_all_caps=(stripped == stripped.upper()),
            ))
            heading_count += 1
            continue

        # Short standalone line heuristic — lines at paragraph boundaries
        # that look like headings (short, no terminal punctuation, capitalized)
        if (len(words_in_line) <= 7 and len(stripped) < 80
                and stripped[-1] not in '.!?,;:)'
                and not current_paragraph
                and stripped[0].isupper()):
            flush_paragraph()
            para_dicts.append(_make_para(
                stripped, font_size=body_size * 1.25,
                is_bold=True,
                is_all_caps=(stripped == stripped.upper()),
            ))
            heading_count += 1
            continue

        if stripped.startswith('> '):
            flush_paragraph()
            quote_text = stripped[2:].strip()
            quote_text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', quote_text)
            quote_text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)',
                                r'<em>\1</em>', quote_text)
            para_dicts.append(_make_para(
                quote_text, is_italic=True,
            ))
            continue

        current_paragraph.append(stripped)

    flush_paragraph()

    total_paras = sum(1 for p in para_dicts if not p.get('is_page_marker'))
    log(f"  Vision->HTML bridge: {heading_count} headings detected "
        f"from {total_paras} paragraphs ({current_page} pages)")
    return para_dicts, body_size


def extract_text(pdf_path, log, force_columns=False, compare_extractors_enabled=False):
    """Extract raw text from all pages, auto-selecting the best extraction backend.

    Tries pypdf first (faster). Samples a few pages and checks for word-merging
    artifacts. If the merge rate is high, falls back to pdfminer.six which handles
    complex font encodings and text positioning much better.
    """
    # --- Column layout detection ---
    # Check if PDF uses multi-column layout (academic papers, commentaries).
    # If detected, route to PyMuPDF column-aware extractor instead.
    # Single-column PDFs fall through to the standard pypdf/pdfminer path below,
    # unless force_columns=True overrides the detection result.
    try:
        column_info = detect_column_layout(pdf_path, log)
        if column_info['is_multicolumn']:
            log(f"  Multi-column layout detected: {column_info['num_columns']} columns "
                f"(confidence: {column_info['confidence']:.0%})")
            return extract_text_columns(pdf_path, log)
        elif force_columns:
            log("  --force-columns set, using column extraction despite low confidence")
            return extract_text_columns(pdf_path, log)
        elif column_info['page_width'] > 0:
            log("  Single-column layout detected — using standard extraction")
        # page_width == 0.0 means pymupdf unavailable; detect_column_layout already
        # logged the WARN, so fall through silently.
    except Exception as e:
        log(f"  [WARN] Column detection failed: {e} — falling back to standard extraction")

    try:
        from pypdf import PdfReader
    except ImportError:
        raise RuntimeError("pypdf is not installed. Run: pip install pypdf")

    reader = PdfReader(pdf_path)
    total = len(reader.pages)
    log(f"  PDF loaded: {total} pages")

    # -- Sample pypdf extraction quality --------------------------
    import re as _re
    sample_start = min(15, total)
    sample_end = min(45, total)
    merge_score = 0
    sample_chars = 0
    for pg_idx in range(sample_start, sample_end):
        text = reader.pages[pg_idx].extract_text() or ""
        if not text.strip():
            continue
        sample_chars += len(text)
        # camelCase merges: "theCouncil", "inAlexandria"
        merge_score += len(_re.findall(r'[a-z][A-Z][a-z]', text))
        # Words longer than 20 chars (likely merged)
        words = text.split()
        merge_score += sum(1 for w in words if len(w) > 20 and not w.startswith('http'))

    merge_rate = (merge_score / max(sample_chars, 1)) * 1000
    log(f"  pypdf quality check: {merge_score} merge indicators in {sample_end - sample_start} sample pages (rate: {merge_rate:.1f}/1000 chars)")

    if merge_rate > 2.0:
        log(f"  High word-merge rate detected -- switching to pdfminer.six")
        return _extract_with_pdfminer(pdf_path, total, log)

    log(f"  Using pypdf extraction (merge rate OK)")
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if text:
            pages.append(f"<<PAGE:{i+1}>>\n{text}")
        if (i + 1) % 50 == 0:
            log(f"  Extracted {i + 1}/{total} pages...")

    full_text = "\n".join(pages)

    # ── Text layer quality scoring ──────────────────────────────────
    quality = score_text_layer_quality(full_text, log)
    log(f"  Text layer quality score: {quality['score']}/100 — {quality['recommendation']}")
    if quality['score'] < 75:
        log(f"  ⚠ Quality below threshold. Details:")
        for check, detail in quality['details'].items():
            if isinstance(detail, dict) and 'score' in detail:
                log(f"    {check}: {detail['score']}/100")

    # Multi-extractor comparison for borderline quality
    if compare_extractors_enabled and 60 <= quality['score'] <= 80:
        log(f"  Borderline quality ({quality['score']}/100) — comparing extractors")
        comparison = compare_extractors(
            pdf_path, log,
            current_text=full_text,
            current_score=quality['score'],
            current_extractor='pypdf',
        )
        if comparison['improved']:
            log(f"  Switching to {comparison['winner']} "
                f"(score: {quality['score']} -> {comparison['score']})")
            full_text = comparison['text']

    return full_text


def extract_text_from_epub(epub_path, log):
    """Extract text from an EPUB file using ebooklib + BeautifulSoup.

    Iterates spine items in reading order, extracts text from XHTML chapters,
    and returns a single joined string matching the contract of extract_text().
    """
    try:
        import ebooklib
        from ebooklib import epub
    except ImportError:
        raise RuntimeError(
            "ebooklib is not installed. Run: python -m pip install ebooklib"
        )
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise RuntimeError(
            "beautifulsoup4 is not installed. Run: python -m pip install beautifulsoup4"
        )

    book = epub.read_epub(epub_path, options={'ignore_ncx': True})
    spine_ids = [item_id for item_id, _ in book.spine]
    items = {item.get_id(): item for item in book.get_items()
             if item.get_type() == ebooklib.ITEM_DOCUMENT}

    spine_items = [items[sid] for sid in spine_ids if sid in items]
    log(f"  EPUB loaded: {len(spine_items)} spine items")

    all_text = []
    for idx, item in enumerate(spine_items):
        soup = BeautifulSoup(item.get_content(), 'html.parser')
        blocks = []
        for tag in soup.find_all(['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            text = tag.get_text(separator=' ', strip=True)
            if text:
                # Normalize whitespace within the paragraph
                text = re.sub(r'\s+', ' ', text).strip()
                blocks.append(text)
        if blocks:
            all_text.append('\n\n'.join(blocks))
        if (idx + 1) % 10 == 0:
            log(f"  Extracted {idx + 1}/{len(spine_items)} chapters...")

    log(f"  EPUB extraction complete: {len(all_text)} chapters with text")
    return '\n\n'.join(all_text)


def _rewrite_epub_links(soup, spine_filenames):
    """Rewrite cross-file EPUB links to in-document fragment anchors.

    'split_020.html#footnote_87' → '#footnote_87'
    'chapter3.xhtml#ref_42'      → '#ref_42'
    'text/split_005.html' (no fragment) → '#'
    """
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']

        # Skip external links and pure fragment links
        if href.startswith(('http://', 'https://', 'mailto:', '#')):
            continue

        # Strip ../ relative path prefixes
        clean_href = href
        while clean_href.startswith('../'):
            clean_href = clean_href[3:]

        # Split into file part and fragment part
        if '#' in clean_href:
            file_part, fragment = clean_href.rsplit('#', 1)
        else:
            file_part = clean_href
            fragment = None

        # Check if the file part matches a known spine item
        file_basename = file_part.rsplit('/', 1)[-1] if '/' in file_part else file_part

        if file_part in spine_filenames or file_basename in spine_filenames:
            if fragment:
                a_tag['href'] = f'#{fragment}'
            else:
                a_tag['href'] = '#'


def _rewrite_image_paths(soup, image_path_map):
    """Rewrite <img src="..."> to point to extracted image files."""
    for img_tag in soup.find_all('img', src=True):
        src = img_tag['src']

        clean_src = src
        while clean_src.startswith('../'):
            clean_src = clean_src[3:]

        basename = clean_src.rsplit('/', 1)[-1] if '/' in clean_src else clean_src

        if clean_src in image_path_map:
            img_tag['src'] = image_path_map[clean_src]
        elif basename in image_path_map:
            img_tag['src'] = image_path_map[basename]

    # Also handle SVG <image> references
    for img_tag in soup.find_all('image'):
        for attr in ['href', 'xlink:href']:
            if img_tag.get(attr):
                src = img_tag[attr]
                clean_src = src
                while clean_src.startswith('../'):
                    clean_src = clean_src[3:]
                basename = clean_src.rsplit('/', 1)[-1] if '/' in clean_src else clean_src
                if clean_src in image_path_map:
                    img_tag[attr] = image_path_map[clean_src]
                elif basename in image_path_map:
                    img_tag[attr] = image_path_map[basename]


def extract_html_from_epub(epub_path, log, output_dir=None):
    """Extract and merge EPUB chapter HTML into a single document.

    Unlike extract_text_from_epub() which flattens to plain text, this
    preserves the EPUB's native HTML structure: headings, bold, italic,
    links, block quotes, lists, etc.

    Cross-file links (footnotes, TOC entries) are rewritten to in-document
    anchors.  Embedded images are extracted to output_dir/images/.

    Returns a dict: {'html': str, 'cover_image': str|None}
    """
    try:
        import ebooklib
        from ebooklib import epub
    except ImportError:
        raise RuntimeError(
            "ebooklib is not installed. Run: python -m pip install ebooklib"
        )
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise RuntimeError(
            "beautifulsoup4 is not installed. Run: python -m pip install beautifulsoup4"
        )

    book = epub.read_epub(epub_path, options={'ignore_ncx': True})
    spine_ids = [item_id for item_id, _ in book.spine]
    items = {item.get_id(): item for item in book.get_items()
             if item.get_type() == ebooklib.ITEM_DOCUMENT}

    spine_items = [items[sid] for sid in spine_ids if sid in items]
    log(f"  EPUB loaded: {len(spine_items)} spine items")

    # Build set of all spine item filenames for cross-file link detection
    spine_filenames = set()
    for item in spine_items:
        name = item.get_name()
        spine_filenames.add(name)
        basename = name.rsplit('/', 1)[-1] if '/' in name else name
        spine_filenames.add(basename)

    # Extract images from the EPUB container
    image_path_map = {}
    cover_image_path = None

    if output_dir:
        image_items = [item for item in book.get_items()
                       if item.get_type() == ebooklib.ITEM_IMAGE
                       or (hasattr(item, 'media_type') and
                           item.media_type and
                           item.media_type.startswith('image/'))]

        if image_items:
            images_dir = os.path.join(output_dir, 'images')
            os.makedirs(images_dir, exist_ok=True)
            images_extracted = 0

            for img_item in image_items:
                try:
                    img_name = img_item.get_name()
                    img_basename = img_name.rsplit('/', 1)[-1] if '/' in img_name else img_name

                    img_output = os.path.join(images_dir, img_basename)
                    with open(img_output, 'wb') as f:
                        f.write(img_item.get_content())

                    new_rel_path = f'images/{img_basename}'
                    image_path_map[img_name] = new_rel_path
                    image_path_map[img_basename] = new_rel_path
                    if '/' in img_name:
                        image_path_map[img_name.rsplit('/', 1)[-1]] = new_rel_path

                    images_extracted += 1
                except Exception as e:
                    log(f"  EPUB image extraction failed for {img_item.get_name()}: {e}")

            if images_extracted:
                log(f"  EPUB: extracted {images_extracted} images to {images_dir}")

            # Identify cover image
            for img_item in image_items:
                if 'cover' in img_item.get_name().lower():
                    img_basename = img_item.get_name().rsplit('/', 1)[-1] if '/' in img_item.get_name() else img_item.get_name()
                    cover_image_path = os.path.join(images_dir, img_basename)
                    break

            # Fallback: check OPF metadata for cover id
            if not cover_image_path:
                for meta in book.get_metadata('OPF', 'cover'):
                    if meta and meta[1]:
                        cover_id = meta[1].get('content', meta[1].get('name', None))
                        if cover_id:
                            cover_item = book.get_item_with_id(cover_id)
                            if cover_item:
                                img_basename = cover_item.get_name().rsplit('/', 1)[-1] if '/' in cover_item.get_name() else cover_item.get_name()
                                cover_image_path = os.path.join(images_dir, img_basename)
                                break

            if cover_image_path and not os.path.isfile(cover_image_path):
                cover_image_path = None

    # Collect the <body> content from each spine item
    body_parts = []
    for idx, item in enumerate(spine_items):
        soup = BeautifulSoup(item.get_content(), 'html.parser')

        # Rewrite cross-file links to in-document anchors
        _rewrite_epub_links(soup, spine_filenames)

        # Rewrite image paths to point to extracted files
        if image_path_map:
            _rewrite_image_paths(soup, image_path_map)

        # Extract the <body> content (or the whole document if no body tag)
        body = soup.find('body')
        if body:
            content = ''.join(str(child) for child in body.children)
        else:
            content = str(soup)

        if content.strip():
            body_parts.append(f'<!-- EPUB chapter {idx + 1}: {item.get_name()} -->')
            body_parts.append(content)

        if (idx + 1) % 10 == 0:
            log(f"  Extracted {idx + 1}/{len(spine_items)} chapters...")

    links_rewritten = sum(1 for part in body_parts if '#' in part) // 2  # rough count
    log(f"  EPUB HTML extraction complete: {len(body_parts) // 2} chapters")

    merged_html = (
        '<!DOCTYPE html>\n<html>\n<head><meta charset="utf-8"></head>\n<body>\n'
        + '\n'.join(body_parts)
        + '\n</body>\n</html>'
    )

    return {'html': merged_html, 'cover_image': cover_image_path}


def extract_text_via_calibre(input_path, log, calibre_path=None):
    """Convert an ebook to plain text via Calibre's ebook-convert CLI.

    Supports MOBI, AZW, AZW3, DJVU, and any other format Calibre handles.
    Returns the extracted text string.
    """
    import subprocess
    import tempfile

    ext = Path(input_path).suffix.lstrip('.').lower()

    # Find Calibre
    if calibre_path and os.path.isfile(calibre_path):
        calibre = calibre_path
    elif os.path.isfile(r"C:\Program Files\Calibre2\ebook-convert.exe"):
        calibre = r"C:\Program Files\Calibre2\ebook-convert.exe"
    else:
        calibre = "ebook-convert"  # hope it's on PATH

    log(f"  Converting {ext.upper()} via Calibre...")

    tmp_dir = tempfile.mkdtemp(prefix='ebook_calibre_')
    tmp_txt = os.path.join(tmp_dir, 'output.txt')
    try:
        result = subprocess.run(
            [calibre, str(input_path), tmp_txt],
            capture_output=True, text=True, encoding='utf-8',
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Calibre conversion failed (exit {result.returncode}):\n{result.stderr}"
            )
        if not os.path.isfile(tmp_txt):
            raise RuntimeError("Calibre produced no output file")

        with open(tmp_txt, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read()

        log(f"  Calibre conversion complete: {len(text):,} chars")
        return text
    finally:
        # Clean up temp directory
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def compare_extractors(pdf_path, log, current_text=None, current_score=None,
                       current_extractor=None, force_columns=False):
    """Run all available Tier 1 extractors and pick the best result.

    Tries up to 3 extractors (pypdf, pdfminer, PyMuPDF), scores each with
    score_text_layer_quality(), and returns the winner.

    Returns:
        dict with keys: winner, text, score, comparison, improved
    """
    import time as _t

    results = {}

    if current_text and current_extractor:
        results[current_extractor] = {
            'text': current_text,
            'score': current_score or 0,
            'word_count': len(current_text.split()),
            'time_seconds': 0,
        }

    extractors = []

    if current_extractor != 'pypdf':
        def _extract_pypdf():
            try:
                from pypdf import PdfReader
            except ImportError:
                return None
            reader = PdfReader(pdf_path)
            pages = []
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    pages.append(f"<<PAGE:{i+1}>>\n{text}")
            return "\n".join(pages) if pages else None
        extractors.append(('pypdf', _extract_pypdf))

    if current_extractor != 'pdfminer':
        def _extract_pdfminer():
            try:
                from pdfminer.layout import LAParams
                from pdfminer.pdfpage import PDFPage
                from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
                from pdfminer.converter import TextConverter
            except ImportError:
                return None
            import io
            laparams = LAParams()
            all_pages = []
            with open(pdf_path, 'rb') as f:
                for i, page in enumerate(PDFPage.get_pages(f)):
                    rsrcmgr = PDFResourceManager()
                    output = io.StringIO()
                    device = TextConverter(rsrcmgr, output, laparams=laparams)
                    interpreter = PDFPageInterpreter(rsrcmgr, device)
                    try:
                        interpreter.process_page(page)
                        text = output.getvalue()
                        if text and text.strip():
                            all_pages.append(f"<<PAGE:{i+1}>>\n{text}")
                    except Exception:
                        pass
                    device.close()
                    output.close()
            return "\n".join(all_pages) if all_pages else None
        extractors.append(('pdfminer', _extract_pdfminer))

    if current_extractor != 'pymupdf':
        def _extract_pymupdf():
            try:
                import pymupdf
            except ImportError:
                return None
            doc = pymupdf.open(pdf_path)
            pages = []
            for pg_idx in range(len(doc)):
                page = doc[pg_idx]
                text = page.get_text("text")
                if text and text.strip():
                    pages.append(f"<<PAGE:{pg_idx+1}>>\n{text}")
            doc.close()
            return "\n".join(pages) if pages else None
        extractors.append(('pymupdf', _extract_pymupdf))

    log(f"  Multi-extractor comparison: testing {len(extractors)} additional extractor(s)...")

    for name, func in extractors:
        start = _t.time()
        try:
            text = func()
            elapsed = round(_t.time() - start, 1)
            if text and len(text.strip()) >= 100:
                quality = score_text_layer_quality(text)
                score = quality.get('score', 0) if quality else 0
                word_count = len(text.split())
                results[name] = {
                    'text': text,
                    'score': score,
                    'word_count': word_count,
                    'time_seconds': elapsed,
                }
                log(f"    {name}: score={score}/100, words={word_count}, time={elapsed}s")
            else:
                log(f"    {name}: insufficient text output ({elapsed}s)")
        except Exception as e:
            elapsed = round(_t.time() - start, 1)
            log(f"    {name}: failed ({e}) ({elapsed}s)")

    if not results:
        log(f"  No extractors produced usable output")
        return {
            'winner': current_extractor or 'none',
            'text': current_text or '',
            'score': current_score or 0,
            'comparison': {},
            'improved': False,
        }

    winner_name = max(results.keys(),
                      key=lambda k: (results[k]['score'], results[k]['word_count']))
    winner = results[winner_name]

    improved = (winner_name != current_extractor) if current_extractor else False
    improvement = winner['score'] - (current_score or 0)

    if improved:
        log(f"  Winner: {winner_name} (score={winner['score']}/100, "
            f"+{improvement} over {current_extractor})")
    else:
        log(f"  Original extractor wins: {winner_name} (score={winner['score']}/100)")

    comparison = {
        name: {
            'score': r['score'],
            'word_count': r['word_count'],
            'time_seconds': r['time_seconds'],
        }
        for name, r in results.items()
    }

    return {
        'winner': winner_name,
        'text': winner['text'],
        'score': winner['score'],
        'comparison': comparison,
        'improved': improved,
    }


def _plain_text_to_para_dicts(text, log):
    """Convert plain text (with <<PAGE:N>> markers) to para_dicts format.

    Used when multi-extractor comparison switches to a non-pdfminer extractor.
    Font metadata is unavailable, so all paragraphs get default styling.
    """
    para_dicts = []
    current_page = 1

    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue

        page_match = re.match(r'<<PAGE:(\d+)>>', line)
        if page_match:
            current_page = int(page_match.group(1))
            para_dicts.append({
                'text': line,
                'font_size': 0,
                'is_bold': False,
                'is_italic': False,
                'page_number': current_page,
                'is_page_marker': True,
            })
            continue

        is_heading = (line == line.upper() and len(line) < 80
                      and len(line.split()) <= 8 and len(line) > 0
                      and line[0].isalpha())

        para_dicts.append({
            'text': line,
            'font_size': 14 if is_heading else 10,
            'is_bold': is_heading,
            'is_italic': False,
            'page_number': current_page,
            'is_page_marker': False,
            'char_count': len(line),
        })

    log(f"  Converted {len(para_dicts)} paragraphs from plain text (no font metadata)")
    body_size = 10
    return para_dicts, body_size


def extract_text_auto(input_path, log, calibre_path=None, force_columns=False):
    """Dispatch text extraction to the best method based on file extension.

    Routes: pdf -> extract_text(), epub -> extract_text_from_epub(),
    mobi/azw/azw3/djvu -> extract_text_via_calibre().
    Returns the raw text string (same contract as extract_text()).
    """
    ext = Path(input_path).suffix.lstrip('.').lower()

    if ext == 'pdf':
        return extract_text(input_path, log, force_columns=force_columns)
    elif ext == 'epub':
        return extract_text_from_epub(input_path, log)
    elif ext in ('mobi', 'azw', 'azw3', 'djvu'):
        return extract_text_via_calibre(input_path, log, calibre_path=calibre_path)
    else:
        raise ValueError(
            f"Unsupported format: .{ext} "
            f"(supported: {', '.join(SUPPORTED_FORMATS)})"
        )


def extract_text_columns(pdf_path, log):
    """Extract text from a multi-column PDF using PyMuPDF, reading left column then right.

    For each page:
      1. Classify text blocks into left or right column by x-midpoint.
      2. Full-width blocks (>70% page width) are emitted at their natural y-position.
      3. Within each column, blocks are sorted top-to-bottom by y0.
      4. Output format: <<PAGE:N>>\\n{text} per page, joined with \\n —
         compatible with extract_text() so all downstream processing works unchanged.
    """
    try:
        import pymupdf
    except ImportError:
        raise RuntimeError(
            "pymupdf is required for column extraction. "
            "Run: python -m pip install pymupdf"
        )

    doc = pymupdf.open(pdf_path)
    total_pages = len(doc)
    log(f"  Column extraction: {total_pages} pages via PyMuPDF")

    pages_text = []
    try:
        for pg_idx in range(total_pages):
            page = doc[pg_idx]
            page_width  = page.rect.width
            page_height = page.rect.height
            midpoint    = page_width / 2.0
            footnote_y  = page_height * 0.85   # bottom 15% = footnote zone

            blocks = page.get_text("blocks")
            # block format: (x0, y0, x1, y1, text, block_no, block_type)
            text_blocks = [(b[0], b[1], b[2], b[3], (b[4] or '').strip())
                           for b in blocks if b[6] == 0 and (b[4] or '').strip()]

            left_col   = []  # (y0, text)
            right_col  = []  # (y0, text)
            full_width = []  # (y0, x0, text) — spans both columns
            footnotes  = []  # (y0, text) — bottom 15%

            for x0, y0, x1, y1, text in text_blocks:
                if not text:
                    continue
                block_width = x1 - x0

                # Footnote zone: separate regardless of column
                if y0 >= footnote_y:
                    footnotes.append((y0, text))
                    continue

                # Full-width: block spans more than 70% of page
                if block_width >= page_width * 0.70:
                    full_width.append((y0, x0, text))
                    continue

                # Column assignment by block center x
                block_center_x = (x0 + x1) / 2.0
                if block_center_x <= midpoint:
                    left_col.append((y0, text))
                else:
                    right_col.append((y0, text))

            # Sort each group top-to-bottom
            left_col.sort(key=lambda t: t[0])
            right_col.sort(key=lambda t: t[0])
            full_width.sort(key=lambda t: t[0])
            footnotes.sort(key=lambda t: t[0])

            parts = []

            # Full-width blocks above any column content go first
            col_start_y = min(
                (left_col[0][0]  if left_col  else 999999),
                (right_col[0][0] if right_col else 999999)
            )
            top_full = [(y, x, t) for y, x, t in full_width if y < col_start_y]
            mid_full = [(y, x, t) for y, x, t in full_width if y >= col_start_y]

            for _, _, t in sorted(top_full, key=lambda item: item[0]):
                parts.append(t)

            # Band-based assembly: for each mid-page full-width block (section headings,
            # figures), emit left+right column content ABOVE it first, then the block.
            # This preserves reading order: finish the section above the heading, then
            # output the heading, then continue with content below.
            left_ptr = 0
            right_ptr = 0

            for break_y, _, fw_text in mid_full:
                # Left column content before this breakpoint
                while left_ptr < len(left_col) and left_col[left_ptr][0] < break_y:
                    parts.append(left_col[left_ptr][1])
                    left_ptr += 1
                # Right column content before this breakpoint
                while right_ptr < len(right_col) and right_col[right_ptr][0] < break_y:
                    parts.append(right_col[right_ptr][1])
                    right_ptr += 1
                # The full-width block itself
                parts.append(fw_text)

            # Remaining column content after all full-width breaks (or all content if
            # there were no mid_full blocks)
            for _, t in left_col[left_ptr:]:
                parts.append(t)
            for _, t in right_col[right_ptr:]:
                parts.append(t)

            for _, t in footnotes:
                parts.append(t)

            if parts:
                page_text = "\n".join(parts)
                pages_text.append(f"<<PAGE:{pg_idx + 1}>>\n{page_text}")

            if (pg_idx + 1) % 50 == 0:
                log(f"  Column extraction: {pg_idx + 1}/{total_pages} pages processed...")
    finally:
        doc.close()

    log(f"  Column extraction complete: {len(pages_text)} pages with text")
    return "\n".join(pages_text)


def _extract_with_pdfminer(pdf_path, total_pages, log):
    """Extract text using pdfminer.six -- handles complex font encodings better than pypdf."""
    try:
        from pdfminer.layout import LAParams
        from pdfminer.pdfpage import PDFPage
        from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
        from pdfminer.converter import TextConverter
    except ImportError:
        log("  [WARN] pdfminer.six not installed -- falling back to pypdf despite merge issues")
        log("  [WARN] Run: pip install pdfminer.six")
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
        return "\n".join(pages)

    import io
    laparams = LAParams()
    all_pages = []

    with open(pdf_path, 'rb') as f:
        for i, page in enumerate(PDFPage.get_pages(f)):
            rsrcmgr = PDFResourceManager()
            output = io.StringIO()
            device = TextConverter(rsrcmgr, output, laparams=laparams)
            interpreter = PDFPageInterpreter(rsrcmgr, device)
            try:
                interpreter.process_page(page)
                text = output.getvalue()
                if text and text.strip():
                    all_pages.append(f"<<PAGE:{i+1}>>\n{text}")
            except Exception as e:
                log(f"  [WARN] pdfminer failed on page {i+1}: {e}")
            device.close()
            output.close()

            if (i + 1) % 50 == 0:
                log(f"  Extracted {i + 1}/{total_pages} pages (pdfminer)...")

    log(f"  pdfminer extraction complete: {len(all_pages)} pages with content")
    full_text = "\n".join(all_pages)

    # ── Text layer quality scoring ──────────────────────────────────
    quality = score_text_layer_quality(full_text, log)
    log(f"  Text layer quality score: {quality['score']}/100 — {quality['recommendation']}")
    if quality['score'] < 75:
        log(f"  ⚠ Quality below threshold. Details:")
        for check, detail in quality['details'].items():
            if isinstance(detail, dict) and 'score' in detail:
                log(f"    {check}: {detail['score']}/100")

    return full_text


# Regex patterns for structural heading detection (used by clean_and_join)
_HEADING_KEYWORD_RE = re.compile(
    r"^(chapter|part|section|prologue|epilogue|introduction|foreword|"
    r"afterword|conclusion|appendix|preface)\b",
    re.IGNORECASE,
)
_NUMBERED_HEADING_RE = re.compile(r"^\d{1,3}[\.\)]\s+[A-Z]")
_ROMAN_HEADING_RE = re.compile(r"^[IVXLC]+[\.\)]\s+[A-Z]")
_PART_HEADING_RE = re.compile(r"^part\s+[IVXLC\d]+", re.IGNORECASE)


def _looks_like_heading(line):
    """Return True if *line* looks like a structural chapter/part heading.

    Rules 1-4 are unconditional strong signals.
    """
    # Rule 1: keyword-prefixed heading
    # Require either multiple words ("Chapter 1", "Introduction to...")
    # or a standalone keyword that works alone ("Introduction", "Conclusion").
    # A bare "Chapter" or "Part" alone is likely a styled text fragment.
    if _HEADING_KEYWORD_RE.match(line):
        words = line.split()
        if len(words) >= 2:
            return True
        # Single-word standalone keywords (not "Chapter" or "Part" which need a number)
        kw = words[0].lower()
        if kw not in ('chapter', 'part', 'section'):
            return True
    # Rule 2: numbered heading like "1. How Should..." or "12) Title"
    if _NUMBERED_HEADING_RE.match(line):
        return True
    # Rule 3: Roman numeral heading like "IV. The Hermeneutics"
    if _ROMAN_HEADING_RE.match(line):
        return True
    # Rule 4: "Part I", "Part III:", "Part 2" etc.
    if _PART_HEADING_RE.match(line):
        return True
    return False


def fix_ocr_artifacts(paragraphs, log, bookmark_titles=None, heading_indices=None, ocr_table_path=None):
    """
    Fix common pypdf text extraction artifacts using dictionary-based validation.

    Most common issues:
      - 'rn' extracted as 'm' or vice versa (kerned fonts): "modern" -> "modem"
      - 'fi'/'fl' ligature decomposition failures
      - Smart quote/dash normalization

    Uses pyspellchecker for dictionary validation to avoid false positives.
    """
    try:
        from spellchecker import SpellChecker
    except ImportError:
        log("  pyspellchecker not installed -- skipping OCR cleanup (pip install pyspellchecker)")
        return paragraphs, {}

    spell = SpellChecker()

    # Load OCR substitution tables (from JSON config, with hardcoded fallback)
    subs = load_ocr_substitutions(custom_path=ocr_table_path)

    # Pre-scan: Detect repeated short paragraphs (running headers) before any phase
    # modifies them. Save these fragments for use in Phase 9 embedded stripping.
    # This catches mixed-case running headers like "C.E. RoltDionysius the Areopagite..."
    # that Phase 0's ALL-CAPS detection won't find.
    _prescan_fragments = set()
    _prescan_candidates = {}
    _prescan_nonum_candidates = {}  # same but with trailing page numbers stripped
    _prescan_leading_candidates = {}  # same but with leading page numbers stripped
    for i, p in enumerate(paragraphs):
        s = p.strip()
        if not s or len(s) > 150 or len(s) < 15:
            continue
        if s.startswith('#') or s.startswith('<<PAGE:'):
            continue
        if heading_indices and i in heading_indices:
            continue
        norm = re.sub(r'\s+', ' ', s).strip()
        if norm not in _prescan_candidates:
            _prescan_candidates[norm] = []
        _prescan_candidates[norm].append(i)
        # Also group by text with trailing page numbers stripped
        norm_nonum = re.sub(r'\s+\d{1,4}\s*$', '', norm).strip()
        if len(norm_nonum) >= 15 and norm_nonum != norm:
            if norm_nonum not in _prescan_nonum_candidates:
                _prescan_nonum_candidates[norm_nonum] = []
            _prescan_nonum_candidates[norm_nonum].append(i)
        # Also group by text with leading page numbers stripped
        # (catches "4 the brother of jesus", "66 the brother of jesus", etc.)
        norm_leadnum = re.sub(r'^\d{1,4}\s+', '', norm).strip()
        if len(norm_leadnum) >= 15 and norm_leadnum != norm:
            if norm_leadnum not in _prescan_leading_candidates:
                _prescan_leading_candidates[norm_leadnum] = []
            _prescan_leading_candidates[norm_leadnum].append(i)
    for norm, indices in _prescan_candidates.items():
        if len(indices) >= 5:
            _prescan_fragments.add(norm)
    # Mixed-case running headers with varying page numbers (e.g.,
    # "State Reaction and Illicit-Network Resilience  21/27/33/...")
    for norm_nonum, indices in _prescan_nonum_candidates.items():
        if len(indices) >= 3:
            _prescan_fragments.add(norm_nonum)
    # Running headers with leading page numbers (e.g.,
    # "4 the brother of jesus", "66 the brother of jesus")
    for norm_leadnum, indices in _prescan_leading_candidates.items():
        if len(indices) >= 3:
            _prescan_fragments.add(norm_leadnum)

    # Pre-scan strip: immediately remove detected repeated fragments before any
    # other phase can mangle them (e.g., Phase 0g partial-stripping bookmark titles
    # from within running headers, creating orphaned "C.E. Rolt...On and the" remnants).
    if _prescan_fragments:
        prescan_standalone = 0
        prescan_embedded = 0
        sorted_frags = sorted(_prescan_fragments, key=len, reverse=True)
        for frag in sorted_frags:
            frag_words = frag.split()
            if not frag_words:
                continue
            frag_pattern = r'\s*'.join(re.escape(w) for w in frag_words)
            frag_re = re.compile(frag_pattern)
            for i, p in enumerate(paragraphs):
                if not p or not p.strip():
                    continue
                if heading_indices and i in heading_indices:
                    continue
                m = frag_re.search(p)
                if m:
                    before = p[:m.start()]
                    after = p[m.end():]
                    new_p = (before.rstrip() + ' ' + after.lstrip()).strip() if before.strip() and after.strip() else (before + after).strip()
                    if not new_p:
                        paragraphs[i] = ''
                        prescan_standalone += 1
                    elif new_p != p.strip():
                        paragraphs[i] = new_p
                        prescan_embedded += 1
        if prescan_standalone or prescan_embedded:
            log(f"  Pre-scan: stripped {prescan_standalone} standalone + {prescan_embedded} embedded repeated headers")

    # Phase 0: Detect and remove running headers/footers
    # These are short lines that repeat chapter titles with page numbers,
    # e.g., "134 EXPLORING THE CONTEMPORARY RELEVANCE" or "GENESIS 1-3 AND MODERN SCIENCE 131"
    # Strategy: find short lines that appear multiple times (with varying page numbers)

    # Page numbers may have OCR artifacts: 1->I, 0->O
    page_num = r'[IO\d!]{1,4}'  # matches "101", "IOI", "1O3", etc.
    header_pattern = re.compile(
        r'^\s*'
        r'(?:'
        r'(' + page_num + r')\s+([A-Z][A-Z\s\-:,\d\.]+)'   # "134 EXPLORING THE..."
        r'|'
        r'([A-Z][A-Z\s\-:,\d\.]+?)\s+(' + page_num + r')'   # "EXPLORING THE... 134"
        r')'
        r'\s*$'
    )

    # First pass: collect candidate header texts (strip page numbers, normalize)
    header_candidates = {}  # normalized text -> list of (index, full_line)
    for i, p in enumerate(paragraphs):
        line = p.strip()
        # Must be relatively short (headers are typically < 80 chars)
        if len(line) > 80 or len(line) < 5:
            continue

        m = header_pattern.match(line)
        if m:
            if m.group(1):  # "134 TITLE TEXT"
                text = m.group(2).strip()
            else:           # "TITLE TEXT 134"
                text = m.group(3).strip()

            # Normalize for grouping (remove minor variations)
            normalized = re.sub(r'\s+', ' ', text.upper()).strip()
            if len(normalized) < 5:
                continue

            if normalized not in header_candidates:
                header_candidates[normalized] = []
            header_candidates[normalized].append(i)

    # A real running header appears at least 3 times across the book
    headers_to_remove = set()
    removed_headers = {}
    for text, indices in header_candidates.items():
        if len(indices) >= 3:
            for idx in indices:
                headers_to_remove.add(idx)
            removed_headers[text] = len(indices)

    if headers_to_remove:
        for idx in headers_to_remove:
            paragraphs[idx] = ''  # blank out, will be skipped in final join
        log(f"  Removed {len(headers_to_remove)} running headers/footers:")
        for text, count in sorted(removed_headers.items(), key=lambda x: -x[1]):
            log(f"    '{text}' (x{count})")

    # Save known header texts for use in later phases (to override quote protection)
    known_headers = set()
    for text, count in removed_headers.items():
        if count >= 3:
            known_headers.add(text.strip().upper())

    # Phase 0b: Strip running headers that got merged into paragraph text
    # e.g., "80 UNDERSTANDING THE HISTORY times, the natures of animals..."
    # These happen when clean_and_join merges a short header line with the next paragraph.
    # Use the header texts we already identified (appeared 3+ times standalone)
    # plus detect the pattern directly in paragraph starts.

    # Also detect common pattern: "PAGE_NUM ALL_CAPS_WORDS" or "ALL_CAPS_WORDS PAGE_NUM"
    # at the start of a paragraph, followed by lowercase text
    ocr_page = r'[IO\d!]{1,4}'
    merged_pattern_front = re.compile(
        r'^(' + ocr_page + r')\s+([A-Z][A-Z\s\-:,\d\.?]+?)\s+(?=[a-z])'
    )
    merged_pattern_back = re.compile(
        r'^([A-Z][A-Z\s\-:,\d\.?]+?)\s+(' + ocr_page + r')\s+(?=[A-Z][a-z]|[a-z])'
    )

    merged_fixes = 0
    for i in range(len(paragraphs)):
        if not paragraphs[i]:
            continue

        line = paragraphs[i]

        # Check for "NUMBER CAPS_TEXT lowercase..." pattern
        m = merged_pattern_front.match(line)
        if m:
            caps_text = m.group(2).strip()
            # Only strip if it looks like a header (mostly uppercase, >= 2 words)
            word_count = len(caps_text.split())
            if word_count >= 2 and caps_text == caps_text.upper():
                paragraphs[i] = line[m.end():].strip()
                # Also strip any leading orphaned page number
                paragraphs[i] = re.sub(r'^[IO\d!]{1,4}\s+(?=[a-z])', '', paragraphs[i])
                merged_fixes += 1
                continue

        # Check for "CAPS_TEXT NUMBER Sentence..." pattern
        m = merged_pattern_back.match(line)
        if m:
            caps_text = m.group(1).strip()
            word_count = len(caps_text.split())
            if word_count >= 2 and caps_text == caps_text.upper():
                paragraphs[i] = line[m.end():].strip()
                # Also strip any leading orphaned page number
                paragraphs[i] = re.sub(r'^[IO\d!]{1,4}\s+(?=[a-z])', '', paragraphs[i])
                merged_fixes += 1
                continue

    if merged_fixes:
        log(f"  Stripped {merged_fixes} merged running headers from paragraph starts")

    # Phase 0c: Strip headers embedded in the MIDDLE of paragraphs
    # Pattern: "...sentence end. NUMBER CAPS_HEADER_TEXT NUMBER/lowercase continuation..."
    # or "...sentence end. CAPS_HEADER_TEXT NUMBER lowercase continuation..."
    mid_header_pattern = re.compile(
        r'(\.\s*(?:\d{1,3}\s*)?)'                          # sentence end, optional footnote num
        r'(?:[IO\d!]{1,4}\s+)?'                              # optional page num before header
        r'(?:[A-Z][A-Z\s\-:,\d\.]{5,}?)'                    # the CAPS header text
        r'(?:\s+[IO\d!]{1,4})?'                              # optional page num after header
        r'(\s+[A-Za-z])'                                    # continuation text
    )

    mid_fixes = 0
    for i in range(len(paragraphs)):
        if not paragraphs[i]:
            continue
        new_text = mid_header_pattern.sub(r'\1\2', paragraphs[i])
        if new_text != paragraphs[i]:
            paragraphs[i] = new_text
            mid_fixes += 1

    if mid_fixes:
        log(f"  Stripped {mid_fixes} mid-paragraph running headers")

    # Phase 0d: Rejoin orphaned sentence fragments after header removal
    # When a header was between two parts of a sentence, removing it leaves
    # an orphan paragraph starting with lowercase (e.g., "was a background of...")
    # Rejoin these to the previous non-empty paragraph.
    rejoined = 0
    for i in range(1, len(paragraphs)):
        if not paragraphs[i]:
            continue
        stripped = paragraphs[i].strip()
        if not stripped:
            continue
        # Fragment starts with lowercase letter — it's a continuation
        if stripped[0].islower():
            # Find the previous non-empty paragraph
            for j in range(i - 1, -1, -1):
                if paragraphs[j] and paragraphs[j].strip():
                    # Don't rejoin to heading paragraphs
                    if heading_indices and j in heading_indices:
                        continue
                    paragraphs[j] = paragraphs[j].rstrip() + ' ' + stripped
                    paragraphs[i] = ''
                    rejoined += 1
                    break

    if rejoined:
        log(f"  Rejoined {rejoined} orphaned sentence fragments")

    # Phase 0e: Strip ALL-CAPS sequences embedded in normal prose
    # Running headers are the only reason 3+ ALL-CAPS words appear inline
    # in otherwise lowercase text. This catches all header variations
    # regardless of page numbers or title abbreviations.

    # Pattern: optional OCR page num + 3+ CAPS words (with allowed punct),
    # appearing inside a paragraph (preceded or followed by lowercase text)
    ocr_page_opt = r'(?:[IO\d!]{1,4}\s+)?'  # optional OCR'd page number before (! = OCR'd 1)
    ocr_page_opt_after = r'(?:\s+[IO\d!]{1,4})?'  # optional after

    # Match CAPS words, allowing OCR'd digit-letter combos like "2Q", "I-", "IO3"
    caps_word = r'[A-Z\d][A-Z\d\-\'\u2019\u2018]*'
    caps_header = re.compile(
        r'(' + ocr_page_opt + r'(?:' + caps_word + r'[\s\-]+){2,}' + caps_word + ocr_page_opt_after + r')'
    )

    caps_fixes = 0
    for i in range(len(paragraphs)):
        if not paragraphs[i]:
            continue
        para = paragraphs[i].strip()
        # Skip short paragraphs UNLESS they match a known bookmark title
        # (running headers like "THE SIX DAYS OF CREATION 41" are short but not real headings)
        if len(para) < 60:
            # Check if this is a heading we should protect
            if heading_indices and i in heading_indices:
                continue
            # Check if it looks like a running header: ALL-CAPS + trailing number
            if not re.match(r'^[A-Z][A-Z\s\-:,]{5,}\s*[IO\d!]{1,4}\s*$', para):
                continue
            # Falls through to stripping if it matches the CAPS+number pattern

        matches = list(caps_header.finditer(para))
        if not matches:
            continue

        for m in reversed(matches):  # reverse to preserve indices
            caps_text = m.group(1).strip()
            # Count pure alpha CAPS words (not OCR fragments like "2Q", "I-")
            all_caps_tokens = [w.strip('-') for w in caps_text.split()]
            caps_words = [w for w in all_caps_tokens if w.replace("'", "").replace("\u2019", "").isalpha()]
            # Need at least 1 CAPS word that's 3+ chars (a real word, not just OCR noise)
            real_words = [w for w in caps_words if len(w) >= 3]
            if not real_words:
                continue

            # Also count single CAPS letters attached by hyphens as part of header
            # e.g., "GENESIS I- Q" has OCR'd "1-9" as "I- Q"
            # Count hyphen-adjacent single caps letters as header fragments
            caps_or_ocr = [w for w in caps_text.split() if
                          w.replace("'", "").replace("\u2019", "").isalpha() or
                          re.match(r'^[A-Z][\-]?$', w) or
                          re.match(r'^[\-][A-Z]$', w)]
            if len(caps_or_ocr) >= 3:
                caps_words = caps_or_ocr  # use the broader count

            # Must have at least 3 actual words (not just page numbers)
            if len(caps_words) < 3:
                continue

            # Don't strip if the CAPS text IS the entire paragraph
            if len(caps_text) > len(para) * 0.8:
                continue

            # Don't strip if the CAPS text is inside quotation marks (dialogue/shouting)
            # UNLESS the CAPS text spans most of the paragraph (then it's a quoted header)
            start, end = m.start(), m.end()
            before = para[:start]
            after = para[end:]
            quote_chars = '""\u201c\u201d'
            in_quotes = (any(before.rstrip().endswith(q) for q in quote_chars) or
                any(after.lstrip().startswith(q) for q in quote_chars) or
                before.count('"') % 2 == 1 or
                before.count('\u201c') > before.count('\u201d'))
            if in_quotes and len(caps_text) < len(para) * 0.4:
                # Override: if this CAPS text is a known running header from Phase 0, strip it anyway
                caps_upper = caps_text.strip().upper()
                is_known_header = any(caps_upper in kh or kh in caps_upper for kh in known_headers) if known_headers else False
                if not is_known_header:
                    continue  # small CAPS inside quotes = dialogue, protect it
                # Known header inside quotes -- fall through to stripping
            # If CAPS text is large portion of paragraph, it's a quoted running header -- strip it

            # Don't strip if it looks like an acronym/abbreviation sequence
            # (all words are very short, like "CIA FBI NSA")
            if all(len(w) <= 4 for w in caps_words):
                continue

            # Strip the match AND any adjacent orphaned page numbers
            before = para[:start].rstrip()
            after = para[end:].lstrip()

            # Strip trailing page number from 'before' text
            # e.g., "...creative.33 In short, there I16" -> "...creative.33 In short, there"
            before = re.sub(r'\s+[IO\d!]{1,4}\s*$', '', before)

            # Strip leading page number from 'after' text
            # e.g., "IO3 the landscape itself..." -> "the landscape itself..."
            after = re.sub(r'^[IO\d!]{1,4}\s+', '', after)

            paragraphs[i] = (before + ' ' + after).strip()
            para = paragraphs[i]
            caps_fixes += 1

    if caps_fixes:
        log(f"  Stripped {caps_fixes} embedded ALL-CAPS running headers")

    # Phase 0e-b: Strip orphaned page numbers embedded mid-paragraph
    # Pattern: "...sentence end. 60 on the other--and..." where the number
    # is a leftover page number between two parts of a sentence.
    mid_pagenum = re.compile(
        r'([\.,:;"\u201d\u2019\)]\s*)'          # sentence-ending punct OR closing quote
        r'([IO\d!]{1,4})'                          # orphaned page number
        r'(\s+[a-zA-Z])'                           # followed by continuation text (upper or lowercase)
    )
    mid_num_fixes = 0
    for i in range(len(paragraphs)):
        if not paragraphs[i]:
            continue
        new_text = mid_pagenum.sub(r'\1\3', paragraphs[i])
        if new_text != paragraphs[i]:
            paragraphs[i] = new_text
            mid_num_fixes += 1
    if mid_num_fixes:
        log(f"  Stripped {mid_num_fixes} orphaned mid-paragraph page numbers")

    # Also catch page numbers wedged between words with no punctuation
    # e.g., "...years and 80 times, the natures..." where "80" is a page number
    # Pattern: word boundary + 2-3 digit number + space + common lowercase word
    wedged_pagenum = re.compile(
        r'(\s)(\d{2,3})(\s+(?:times|the|a|an|and|or|but|in|on|at|to|of|for|is|it|as|by|from|that|this|with|was|were|are|has|had|not|be|he|she|we|they|all|its|if|so|no|do|can|may|who|how|one|two|our|his|her|new|own|now|yet|nor|than|over|into|upon|also|each|most|such|some|any|few|more|much|out|up|been|have|will|very|just|only|then|when|them|what|your|here|there|where|after|about|being|under|these|those|other|their|which|would|could|should|might|still|while|often|since|until|every|never|first|last|both|same|between|before|among|during)\b)',
        re.IGNORECASE
    )

    wedged_fixes = 0
    for i in range(len(paragraphs)):
        if not paragraphs[i]:
            continue
        if len(paragraphs[i]) < 60:
            continue
        new_text = wedged_pagenum.sub(r'\1\3', paragraphs[i])
        if new_text != paragraphs[i]:
            paragraphs[i] = new_text
            wedged_fixes += 1
    if wedged_fixes:
        log(f"  Stripped {wedged_fixes} wedged page numbers between words")

    # Diagnostic: check for remaining 2-3 digit numbers at paragraph starts
    for i in range(len(paragraphs)):
        if not paragraphs[i]:
            continue
        stripped = paragraphs[i].strip()
        m = re.match(r'^(\d{2,3})\s', stripped)
        if m and len(stripped) > 40:
            log(f"  [DIAG] Leading number '{m.group(1)}' at para {i}: {stripped[:80]}")

    # Diagnostic: check for remaining mid-paragraph 2-digit numbers that look like page numbers
    for i in range(len(paragraphs)):
        if not paragraphs[i]:
            continue
        for num_str in ['60 on', '80 times']:
            if num_str in paragraphs[i]:
                idx = paragraphs[i].find(num_str)
                context = paragraphs[i][max(0,idx-40):idx+60]
                log(f"  [DIAG] Found '{num_str}' mid-para {i}: ...{context}...")

    # Also strip trailing page numbers from short quote paragraphs
    # e.g., '"male and female he created them" 187' -> '"male and female he created them"'
    trailing_pagenum = re.compile(r'^(.+["\u201d\u2019])\s+[IO\d!]{1,4}\s*$')
    trailing_fixes = 0
    for i in range(len(paragraphs)):
        if not paragraphs[i]:
            continue
        para = paragraphs[i].strip()
        if len(para) > 200:  # only short paragraphs
            continue
        m = trailing_pagenum.match(para)
        if m:
            paragraphs[i] = m.group(1)
            trailing_fixes += 1
    if trailing_fixes:
        log(f"  Stripped {trailing_fixes} trailing page numbers from quote lines")

    # Phase 0f: Strip standalone ALL-CAPS paragraphs with trailing page numbers
    # These are running headers that ended up as their own paragraph.
    # e.g., "ALL GOD'S CREATURES 151" or "GENESIS AND THE SCIENTISTS IO3"
    # Unlike Phase 0 (which requires 3+ occurrences), these are caught by structure alone:
    # short paragraph, ALL-CAPS words, trailing number, not a protected heading.
    standalone_header = re.compile(
        r'^["\u201c]?'                                          # optional opening quote
        r'(?:[A-Z][A-Z\'\u2019\-]+\s+){2,}'                    # 2+ ALL-CAPS words
        r'[A-Z][A-Z\'\u2019\-]+'                                # final CAPS word
        r'["\u201d]?'                                           # optional closing quote
        r'\s+[IO\d!]{1,4}'                                      # trailing page number
        r'\s*$'                                                  # end of paragraph
    )
    standalone_fixes = 0
    for i in range(len(paragraphs)):
        if not paragraphs[i]:
            continue
        para = paragraphs[i].strip()
        if len(para) > 80:
            continue
        if heading_indices and i in heading_indices:
            continue
        if standalone_header.match(para):
            paragraphs[i] = ''
            standalone_fixes += 1
    if standalone_fixes:
        log(f"  Stripped {standalone_fixes} standalone ALL-CAPS header paragraphs")

    # Phase 0g: Strip running headers based on bookmark titles (case-insensitive)
    # Some running headers are in small caps, which pypdf extracts as lowercase.
    # e.g., '"male and female he created them"' when the chapter title contains
    # '"Male and Female He Created Them" (Genesis 1:27). Interpreting Gender...'
    if bookmark_titles:
        # Build a set of title fragments to match against
        title_fragments = set()
        for title in bookmark_titles:
            # Clean numbering prefix and author suffix
            t = re.sub(r'^\d{1,3}[\.\)]\s*', '', title).strip()
            t = re.sub(r'\s*\*{3}.*$', '', t).strip()  # remove "*** Author Name"

            if len(t) < 10:
                continue

            # Add the full cleaned title
            title_fragments.add(t.lower())

            # Extract quoted portions -- these are often used as running headers
            # e.g., '"Male and Female He Created Them"' from the full title
            quoted = re.findall(r'["\u201c]([^"\u201d]+)["\u201d]', t)
            for q in quoted:
                if len(q) >= 8:
                    title_fragments.add(q.lower())

            # Split on periods and colons for sub-titles
            for part in re.split(r'[\.\:]', t):
                part = part.strip().strip('""\u201c\u201d')
                if len(part) >= 10:
                    title_fragments.add(part.lower())

            # Split on parentheses
            no_parens = re.sub(r'\([^)]*\)', '.', t)
            for part in re.split(r'[\.\:]', no_parens):
                part = part.strip().strip('""\u201c\u201d')
                if len(part) >= 10:
                    title_fragments.add(part.lower())

            # Generate first-N-word prefixes (headers may be truncated)
            # "Male and Female He Created Them" -> also match "Male and Female He Created"
            title_clean_stripped = t.strip('""\u201c\u201d\'"')
            all_words = title_clean_stripped.split()
            for n in range(4, len(all_words)):
                prefix = ' '.join(all_words[:n]).lower()
                if len(prefix) >= 15:
                    title_fragments.add(prefix)

            # Same for quoted portions
            for q in quoted:
                q_words = q.split()
                for n in range(4, len(q_words)):
                    prefix = ' '.join(q_words[:n]).lower()
                    if len(prefix) >= 15:
                        title_fragments.add(prefix)

        # Sort longest first for greedy matching
        sorted_fragments = sorted(title_fragments, key=len, reverse=True)

        title_header_fixes = 0
        for i in range(len(paragraphs)):
            if not paragraphs[i]:
                continue
            if heading_indices and i in heading_indices:
                continue
            para = paragraphs[i].strip()
            para_lower = para.lower()

            for frag in sorted_fragments:
                if frag not in para_lower:
                    continue

                # Found a title fragment in this paragraph
                idx = para_lower.find(frag)
                frag_end = idx + len(frag)

                # Case 1: Short paragraph that IS the running header (+ optional page number)
                if len(para) < 120:
                    # Strip quotes and page numbers, then check if what remains is mostly the fragment
                    para_stripped = re.sub(r'["\u201c\u201d\'\s]', '', para_lower)
                    para_stripped = re.sub(r'[IO\d!]{1,4}$', '', para_stripped).strip()
                    frag_stripped = re.sub(r'["\u201c\u201d\'\s]', '', frag)
                    if frag_stripped in para_stripped or para_stripped in frag_stripped:
                        # Just remove if it's short enough to be a running header
                        if len(para) < 80:
                            paragraphs[i] = ''
                            title_header_fixes += 1
                            break

                # Case 2: Fragment embedded in a longer paragraph (running header mid-text)
                if len(para) > 80:
                    # Don't strip near actual chapter headings UNLESS paragraph is long
                    # (long paragraphs near headings = header merged into body text)
                    if heading_indices and len(para) < 200 and any(abs(i - h) <= 2 for h in heading_indices):
                        continue

                    before = para[:idx].rstrip()
                    after = para[frag_end:].lstrip()

                    # Strip surrounding quotes from the edges
                    before = re.sub(r'["\u201c\u201d]\s*$', '', before).rstrip()
                    after = re.sub(r'^["\u201c\u201d]\s*', '', after).lstrip()

                    # Strip adjacent page numbers
                    before = re.sub(r'\s*[IO\d!]{1,4}\s*$', '', before).rstrip()
                    after = re.sub(r'^[IO\d!]{1,4}\s*', '', after).lstrip()

                    paragraphs[i] = (before + ' ' + after).strip()
                    # After stripping, log if paragraph now starts lowercase
                    if paragraphs[i] and paragraphs[i].strip() and paragraphs[i].strip()[0].islower():
                        log(f"  [DIAG] Phase 0g left lowercase start at para {i}: {paragraphs[i].strip()[:80]}")
                    title_header_fixes += 1
                    break

        if title_header_fixes:
            log(f"  Stripped {title_header_fixes} title-based running headers (case-insensitive)")

        # Rejoin lowercase-starting fragments left after title stripping
        rejoined_0g = 0
        for i in range(1, len(paragraphs)):
            if not paragraphs[i]:
                continue
            stripped = paragraphs[i].strip()
            if not stripped or not stripped[0].islower():
                continue
            for j in range(i - 1, -1, -1):
                if paragraphs[j] and paragraphs[j].strip():
                    if heading_indices and j in heading_indices:
                        continue
                    paragraphs[j] = paragraphs[j].rstrip() + ' ' + stripped
                    paragraphs[i] = ''
                    rejoined_0g += 1
                    break
        if rejoined_0g:
            log(f"  Rejoined {rejoined_0g} fragments after title-based header removal")

        # Strip leading page numbers from paragraphs left by title stripping
        leading_num_fixes = 0
        for i in range(len(paragraphs)):
            if not paragraphs[i]:
                continue
            stripped = paragraphs[i].strip()
            m = re.match(r'^[IO\d!]{1,4}\s+([a-z])', stripped)
            if m and len(stripped) > 30:
                paragraphs[i] = stripped[m.start(1):]
                leading_num_fixes += 1
                # Try to rejoin to previous
                for j in range(i - 1, -1, -1):
                    if paragraphs[j] and paragraphs[j].strip():
                        if heading_indices and j in heading_indices:
                            continue
                        paragraphs[j] = paragraphs[j].rstrip() + ' ' + paragraphs[i]
                        paragraphs[i] = ''
                        break
        if leading_num_fixes:
            log(f"  Stripped {leading_num_fixes} leading page numbers after title removal")

    # Re-run orphan rejoining after this pass
    rejoined2 = 0
    for i in range(1, len(paragraphs)):
        if not paragraphs[i]:
            continue
        stripped = paragraphs[i].strip()
        if not stripped:
            continue
        if stripped[0].islower():
            for j in range(i - 1, -1, -1):
                if paragraphs[j] and paragraphs[j].strip():
                    # Don't rejoin to heading paragraphs
                    if heading_indices and j in heading_indices:
                        continue
                    paragraphs[j] = paragraphs[j].rstrip() + ' ' + stripped
                    paragraphs[i] = ''
                    rejoined2 += 1
                    break

    if rejoined2:
        log(f"  Rejoined {rejoined2} additional orphaned fragments after CAPS cleanup")

    fixes_made = 0
    words_checked = 0
    fix_log = {}  # track unique corrections for logging

    # Phase 1: Normalize Unicode characters (from substitution table)
    unicode_map = subs.get('unicode_normalization', {})
    normalized = 0
    for i in range(len(paragraphs)):
        original = paragraphs[i]
        text = paragraphs[i]
        for src, tgt in unicode_map.items():
            text = text.replace(src, tgt)
        if text != original:
            paragraphs[i] = text
            normalized += 1

    if normalized:
        log(f"  Normalized Unicode in {normalized} paragraphs")

    # Phase 1b: Fix pypdf backtick corruption
    # Some PDF font encodings cause pypdf to extract certain ligatures/glyphs
    # as backtick characters: "able" -> "a`e", "add" -> "a`", "odd" -> "o`"
    # Strategy: find backtick sequences and try dictionary replacement
    backtick_fixes = 0
    backtick_pattern = re.compile(r'\b([a-zA-Z]*`[a-zA-Z]*)\b')

    for i in range(len(paragraphs)):
        if not paragraphs[i] or '`' not in paragraphs[i]:
            continue

        original = paragraphs[i]

        # Common backtick -> letter substitutions (from substitution table)
        replacements = subs.get('backtick_replacements', ['bl', 'dd', 'ff', 'fi', 'fl', 'tt', 'll', 'ft', 'fb', 'ffi', 'ffl'])

        def fix_backtick(m):
            nonlocal backtick_fixes
            word = m.group(1)
            # Try each substitution
            for repl in replacements:
                candidate = word.replace('`', repl, 1)
                if candidate.lower() in spell:
                    backtick_fixes += 1
                    return candidate
            # If no dictionary match, try double-letter substitution
            # (backtick might replace a doubled letter like 'dd', 'tt', 'ff')
            for letter in 'defglmnoprst':
                candidate = word.replace('`', letter + letter, 1)
                if candidate.lower() in spell:
                    backtick_fixes += 1
                    return candidate
            # Try single-letter substitutions as last resort
            for letter in 'abcdefghijklmnopqrstuvwxyz':
                candidate = word.replace('`', letter, 1)
                if candidate.lower() in spell:
                    backtick_fixes += 1
                    return candidate
            return word  # give up, leave as-is

        paragraphs[i] = backtick_pattern.sub(fix_backtick, paragraphs[i])

    if backtick_fixes:
        log(f"  Fixed {backtick_fixes} backtick-corrupted words")

    # Phase 2: Fix rn/m substitution errors using dictionary validation
    def try_rn_m_fix(word):
        """Check if replacing 'm' with 'rn' or vice versa produces a better word."""
        word_lower = word.lower()

        # Skip very short words and words with numbers
        if len(word_lower) < 4 or any(c.isdigit() for c in word_lower):
            return None

        candidates = []

        # m -> rn: "modem" -> "modern", "govemment" -> "government"
        if 'm' in word_lower:
            positions = [i for i, c in enumerate(word_lower) if c == 'm']
            for pos in positions:
                candidate = word[:pos] + ('RN' if word[pos].isupper() else 'rn') + word[pos+1:]
                cand_lower = candidate.lower()
                if cand_lower in spell:
                    # If original is NOT a valid word, definitely fix it
                    if word_lower not in spell:
                        candidates.append(candidate)
                    else:
                        # Both are valid words -- use frequency to decide
                        # "modern" is far more common than "modem"
                        orig_freq = spell.word_usage_frequency(word_lower)
                        cand_freq = spell.word_usage_frequency(cand_lower)
                        if cand_freq > orig_freq * 5:
                            candidates.append(candidate)

        # rn -> m: less common but can happen
        if 'rn' in word_lower:
            idx = 0
            while True:
                idx = word_lower.find('rn', idx)
                if idx == -1:
                    break
                candidate = word[:idx] + ('M' if word[idx].isupper() else 'm') + word[idx+2:]
                cand_lower = candidate.lower()
                if cand_lower in spell:
                    if word_lower not in spell:
                        candidates.append(candidate)
                    else:
                        orig_freq = spell.word_usage_frequency(word_lower)
                        cand_freq = spell.word_usage_frequency(cand_lower)
                        if cand_freq > orig_freq * 5:
                            candidates.append(candidate)
                idx += 1

        if candidates:
            return candidates[0]
        return None

    for i in range(len(paragraphs)):
        words = re.findall(r'\b[A-Za-z]+\b', paragraphs[i])
        for word in words:
            words_checked += 1
            fix = try_rn_m_fix(word)
            if fix:
                # Replace in the paragraph preserving surrounding context
                paragraphs[i] = re.sub(r'\b' + re.escape(word) + r'\b', fix, paragraphs[i], count=1)
                fixes_made += 1
                key = f"{word} -> {fix}"
                fix_log[key] = fix_log.get(key, 0) + 1

    # Phase 2b: Fix OCR "i" -> "1" in years and numbers

    # Fix standalone "i" -> "1" after book/chapter keywords
    # "Genesis i" -> "Genesis 1", "Chapter i" -> "Chapter 1"
    # Build keyword pattern from substitution table
    chapter_kw = subs.get('chapter_keywords', [])
    if chapter_kw:
        kw_pattern = '|'.join(re.escape(kw) for kw in chapter_kw)
        standalone_i_pattern = re.compile(r'\b(' + kw_pattern + r')\s+i\b')
    else:
        standalone_i_pattern = re.compile(
            r'\b(Genesis|Exodus|Leviticus|Numbers|Deuteronomy|'
            r'Chapter|Chapters|chapter|chapters|'
            r'Samuel|Kings|Chronicles|Corinthians|'
            r'Thessalonians|Timothy|Peter|John|'
            r'Psalm|Isaiah|Jeremiah|Ezekiel|Daniel|'
            r'verse|verses|Verse|Verses)\s+i\b'
        )

    standalone_i_fixes = 0
    for i in range(len(paragraphs)):
        if not paragraphs[i]:
            continue
        new_text = standalone_i_pattern.sub(
            lambda m: m.group(1) + ' 1', paragraphs[i]
        )
        if new_text != paragraphs[i]:
            paragraphs[i] = new_text
            standalone_i_fixes += 1

    if standalone_i_fixes:
        log(f"  Fixed {standalone_i_fixes} standalone OCR 'i' -> '1' after book/chapter names")

    # Common OCR error: "1860" -> "i860", "1920" -> "i920"
    # Pattern: lowercase "i" followed by 3 digits forming a plausible year or number
    ocr_i_pattern = re.compile(r'\bi(\d{3,4})\b')

    i_to_1_fixes = 0
    for i in range(len(paragraphs)):
        if not paragraphs[i]:
            continue

        def fix_i_to_1(m):
            nonlocal i_to_1_fixes
            num = '1' + m.group(1)
            # Verify it's a plausible year (1000-2100) or page-range number
            val = int(num)
            if 1000 <= val <= 2100 or val < 500:
                i_to_1_fixes += 1
                return num
            return m.group(0)  # leave as-is

        paragraphs[i] = ocr_i_pattern.sub(fix_i_to_1, paragraphs[i])

    if i_to_1_fixes:
        log(f"  Fixed {i_to_1_fixes} OCR 'i' -> '1' in years/numbers")

    # Phase 2c: Fix OCR lowercase 'o' -> '0' in numbers
    # Common OCR error: "60" -> "6o", "80" -> "8o", "100" -> "1oo" or "10o"
    # Pattern: digit(s) + 'o' or 'o' + digit(s), where the result isn't a real word
    ocr_o_pattern = re.compile(r'\b(\d+[o]+\d*|\d*[o]+\d+)\b')

    o_to_0_fixes = 0
    for i in range(len(paragraphs)):
        if not paragraphs[i]:
            continue

        def fix_o_to_0(m):
            nonlocal o_to_0_fixes
            token = m.group(1)
            # Replace all 'o' with '0'
            fixed = token.replace('o', '0')
            # Verify it's now a valid number
            if fixed.isdigit():
                o_to_0_fixes += 1
                return fixed
            return token  # leave as-is

        paragraphs[i] = ocr_o_pattern.sub(fix_o_to_0, paragraphs[i])

    if o_to_0_fixes:
        log(f"  Fixed {o_to_0_fixes} OCR 'o' -> '0' in numbers")

    # Phase 2d: Fix merged word pairs from pypdf line-break artifacts
    # pypdf sometimes drops the space at line boundaries, joining "of the" -> "ofthe".
    # These are NOT OCR errors -- they're text extraction artifacts.
    _merged_word_fixes = subs.get('merged_word_splits', {})
    _merged_word_patterns = [
        (re.compile(r'\b' + pat + r'\b'), repl)
        for pat, repl in _merged_word_fixes.items()
    ]

    merged_word_count = 0
    for i in range(len(paragraphs)):
        if not paragraphs[i]:
            continue
        for pattern, replacement in _merged_word_patterns:
            new_text, n = pattern.subn(replacement, paragraphs[i])
            if n:
                paragraphs[i] = new_text
                merged_word_count += n

    if merged_word_count:
        log(f"  Fixed {merged_word_count} merged word pairs (pypdf line-break artifacts)")

    # Phase 3: Fix common ligature issues (from substitution table)
    lig_map = subs.get('ligature_map', {})
    ligature_fixes = 0
    for i in range(len(paragraphs)):
        original = paragraphs[i]
        text = paragraphs[i]
        for src, tgt in lig_map.items():
            text = text.replace(src, tgt)
        if text != original:
            paragraphs[i] = text
            ligature_fixes += 1

    if ligature_fixes:
        log(f"  Fixed ligatures in {ligature_fixes} paragraphs")

    # Phase 3b: Rejoin words split by PDF line-break hyphenation
    # pypdf strips the hyphen but leaves a space: "sym-\nbolic" -> "sym bolic"
    # Strategy: find any two adjacent fragments where:
    #   - At least one fragment is NOT a valid word
    #   - The joined result IS a valid word
    #   - At least one fragment is short (< 7 chars) -- hyphen breaks produce short pieces

    dehyphen_count = 0
    for i in range(len(paragraphs)):
        if not paragraphs[i]:
            continue

        # Normalize multi-spaces to single before splitting — pypdf sometimes
        # inserts double spaces at ligature boundaries (fi/fl decomposition)
        paragraphs[i] = re.sub(r'  +', ' ', paragraphs[i])
        words = paragraphs[i].split(' ')
        j = 0
        while j < len(words) - 1:
            left = words[j]
            right = words[j + 1]

            # Strip surrounding punctuation for checking, but preserve it in output
            left_clean = re.sub(r'^[^A-Za-z]*', '', re.sub(r'[^A-Za-z]*$', '', left))
            right_clean = re.sub(r'^[^A-Za-z]*', '', re.sub(r'[^A-Za-z]*$', '', right))

            if not left_clean or not right_clean:
                j += 1
                continue

            # At least one must be short (hyphenation fragment)
            if len(left_clean) > 7 and len(right_clean) > 7:
                j += 1
                continue

            # Skip if both are already valid words
            if left_clean.lower() in spell and right_clean.lower() in spell:
                j += 1
                continue

            # Try joining
            joined = left_clean.lower() + right_clean.lower()
            if joined in spell:
                # Reconstruct with original punctuation
                # Keep leading punct from left, trailing punct from right
                left_prefix = re.match(r'^([^A-Za-z]*)', left).group(1)
                right_suffix = re.search(r'([^A-Za-z]*)$', right).group(1)

                # Preserve capitalization
                if left_clean[0].isupper():
                    rejoined = left_clean + right_clean
                else:
                    rejoined = left_clean + right_clean

                words[j] = left_prefix + rejoined + right_suffix
                words.pop(j + 1)
                dehyphen_count += 1
                continue  # don't increment j, check the new pair

            j += 1

        paragraphs[i] = ' '.join(words)

    if dehyphen_count:
        log(f"  Rejoined {dehyphen_count} hyphen-split words")

    # Phase 3c: Fix "Th e", "Th is", "Th at" etc. — pypdf ligature decomposition
    # artifact where "Th" is extracted as a separate token. Both "th" and "e" are
    # valid words so Phase 3b skips them. Fix by merging when Th+word is a known word.
    th_fix_count = 0
    _th_pat = re.compile(r'\bTh (\w+)')
    for i in range(len(paragraphs)):
        if not paragraphs[i]:
            continue

        def _th_repl(m):
            nonlocal th_fix_count
            suffix = m.group(1)
            merged = 'Th' + suffix
            if merged.lower() in spell:
                th_fix_count += 1
                return merged
            return m.group(0)

        paragraphs[i] = _th_pat.sub(_th_repl, paragraphs[i])

    if th_fix_count:
        log(f"  Fixed {th_fix_count} \"Th e/is/at\" ligature splits")

    # Phase 3d: Fix remaining fi/fl ligature splits in hyphenated compounds
    # and other contexts Phase 3b missed. Targeted regex: find "fi " or "fl "
    # mid-word where merging produces a known dictionary word.
    # Handles: "drug-traffi cking" -> "drug-trafficking", "T raffi cking" -> "Trafficking"
    _fifl_count = 0

    def _fix_fifl(m):
        nonlocal _fifl_count
        prefix = m.group(1)   # e.g., "traffi" or "raffi" or "confl"
        suffix = m.group(2)   # e.g., "cking" or "ict" or "ows"
        merged = prefix + suffix
        # Check if merged form (or its lowercase) is a known word
        if merged.lower() in spell:
            _fifl_count += 1
            return merged
        # Check common suffixes: -ing, -ed, -tion, -ly, -er, -ment, -ness, -ous, -ive, -al
        # Strip suffix and check root
        for suf in ('ing', 'ed', 'tion', 'sion', 'ly', 'er', 'ment', 'ness', 'ous', 'ive', 'al', 'ence', 'ance', 'ity', 'able', 'ible'):
            if merged.lower().endswith(suf):
                root = merged[:len(merged)-len(suf)].lower()
                if root in spell or root + 'e' in spell:
                    _fifl_count += 1
                    return merged
        return m.group(0)

    _fifl_pat = re.compile(r'\b(\w*f[il]) (\w+)')
    for i in range(len(paragraphs)):
        if not paragraphs[i]:
            continue
        paragraphs[i] = _fifl_pat.sub(_fix_fifl, paragraphs[i])

    # Also handle ffi/ffl triple ligature splits: "ra ffi cking" -> "trafficking"
    # Pattern: optional prefix + space + ffi/ffl + space + suffix
    _ffi_count = 0

    def _fix_ffi(m):
        nonlocal _ffi_count
        prefix = m.group(1) or ''  # e.g., "tra", "ra", "" (may be empty)
        lig = m.group(2)           # "ffi" or "ffl"
        suffix = m.group(3)        # e.g., "cking", "ckers"
        merged = prefix + lig + suffix
        if merged.lower() in spell:
            _ffi_count += 1
            # Preserve original capitalization
            if prefix and prefix[0].isupper():
                return merged[0].upper() + merged[1:]
            return merged
        # Try common suffixes
        for suf in ('ing', 'ed', 'tion', 'ly', 'er', 'ers', 'ment', 'es', 'ence', 'ance', 'al', 'le', 'les'):
            if merged.lower().endswith(suf):
                root = merged[:len(merged)-len(suf)].lower()
                if root in spell or root + 'e' in spell:
                    _ffi_count += 1
                    if prefix and prefix[0].isupper():
                        return merged[0].upper() + merged[1:]
                    return merged
        return m.group(0)

    # Match: optional word chars + space? + ffi/ffl + space + word chars
    _ffi_pat = re.compile(r'\b(\w*?)[\s]?(ff[il]) (\w+)')
    for i in range(len(paragraphs)):
        if not paragraphs[i]:
            continue
        paragraphs[i] = _ffi_pat.sub(_fix_ffi, paragraphs[i])

    if _ffi_count:
        log(f"  Fixed {_ffi_count} ffi/ffl triple-ligature splits")

    if _fifl_count:
        log(f"  Fixed {_fifl_count} remaining fi/fl ligature splits in compounds")

    # Phase 4: Strip inline footnote/endnote reference numbers
    # pypdf extracts superscript numbers as full-size digits stuck to text,
    # e.g., "landscape art.3" -> "landscape art."
    #        "natural theology.5Not" -> "natural theology. Not"
    # These reset at 1 each chapter and are useless without linked endnotes.

    footnote_pattern = re.compile(
        r'(?<=[a-zA-Z\.\,\"\'\)\?\!\u201d])'  # after letter, punct, or closing smart quote
        r'(\d{1,3})'                            # the footnote number
        r'(?=\s+[A-Z]|\s*$)'                   # before new sentence or end of paragraph
    )

    # Also catch footnotes jammed right against the next word with no space:
    # "theology.5Not" -> "theology. Not"
    footnote_jammed = re.compile(
        r'(?<=[a-zA-Z\.\,\"\'\)\?\!\u201d])'
        r'(\d{1,3})'
        r'(?=[A-Z][a-z])'                       # immediately followed by capitalized word
    )

    footnote_count = 0
    for i in range(len(paragraphs)):
        if not paragraphs[i]:
            continue
        original = paragraphs[i]
        # First pass: footnotes before whitespace + capital
        paragraphs[i] = footnote_pattern.sub('', paragraphs[i])
        # Second pass: footnotes jammed against next word (add space)
        paragraphs[i] = footnote_jammed.sub(' ', paragraphs[i])
        if paragraphs[i] != original:
            footnote_count += 1

    if footnote_count:
        log(f"  Stripped footnote references from {footnote_count} paragraphs")

    # Phase 5: Clean up orphaned fragments from header/footnote stripping
    # After stripping headers, page numbers and stray characters can be left behind:
    #   - "C its parameters..." (single letter)
    #   - "60 on the other..." (orphaned page number)
    #   - "? against Tom Paine..." (stray punctuation)
    #   - "41" as a standalone short paragraph (just a page number)
    orphan_fixes = 0
    for i in range(len(paragraphs)):
        if not paragraphs[i]:
            continue
        stripped = paragraphs[i].strip()

        # Remove standalone short number-only paragraphs (orphaned page numbers)
        # e.g., "41" or "IO3" left after header text was stripped
        if re.match(r'^[IO\d!]{1,4}$', stripped):
            paragraphs[i] = ''
            orphan_fixes += 1
            continue

        # Remove leading orphaned page number before lowercase continuation
        # e.g., "60 on the other--and it is important..." -> "on the other..."
        # But DON'T match if the number is part of real content like "3 John" or "1 Corinthians"
        m = re.match(r'^[IO\d!]{1,4}\s+([a-z])', stripped)
        if m and len(stripped) > 30:
            paragraphs[i] = stripped[m.start(1):].strip()
            orphan_fixes += 1
            # Rejoin to previous paragraph since this is a continuation
            for j in range(i - 1, -1, -1):
                if paragraphs[j] and paragraphs[j].strip():
                    if heading_indices and j in heading_indices:
                        continue
                    paragraphs[j] = paragraphs[j].rstrip() + ' ' + paragraphs[i]
                    paragraphs[i] = ''
                    break
            continue

        # Catch any leading 2-3 digit number at paragraph start (orphaned page number)
        # Single-digit numbers could be real content ("3 John", "5 reasons"), so skip those
        # but 2-3 digit numbers at paragraph start are virtually always page numbers
        m2 = re.match(r'^(\d{2,3})\s+(\S)', stripped)
        if m2 and len(stripped) > 40:
            paragraphs[i] = stripped[m2.end(1):].strip()
            orphan_fixes += 1
            # Rejoin to previous paragraph if starts with lowercase
            if paragraphs[i] and paragraphs[i][0].islower():
                for j in range(i - 1, -1, -1):
                    if paragraphs[j] and paragraphs[j].strip():
                        if heading_indices and j in heading_indices:
                            continue
                        paragraphs[j] = paragraphs[j].rstrip() + ' ' + paragraphs[i]
                        paragraphs[i] = ''
                        break
            continue

        # Remove leading stray punctuation before text continuation
        # e.g., "? against Tom Paine..." -> "against Tom Paine..."
        m = re.match(r'^[?!;:,\.\-\—]+\s+([A-Za-z])', stripped)
        if m and len(stripped) > 30:
            paragraphs[i] = stripped[m.start(1):].strip()
            orphan_fixes += 1
            # If starts with lowercase, rejoin to previous paragraph
            if paragraphs[i] and paragraphs[i][0].islower():
                for j in range(i - 1, -1, -1):
                    if paragraphs[j] and paragraphs[j].strip():
                        if heading_indices and j in heading_indices:
                            continue
                        paragraphs[j] = paragraphs[j].rstrip() + ' ' + paragraphs[i]
                        paragraphs[i] = ''
                        break
            continue

        # Single non-ASCII character or ASCII letter (not I or A) before lowercase
        # Catches: "C its parameters", etc.
        m = re.match(r'^([^\sa-z\d"\'(]{1,2})\s+([a-z])', stripped)
        if m and len(stripped) > 30:
            fragment = m.group(1)
            # Don't strip if fragment is a valid word
            valid_starts = {'I', 'A', 'In', 'An', 'It', 'Is', 'If', 'Or', 'On', 'At', 'He', 'We', 'So', 'Do', 'No', 'My', 'Up', 'Am', 'As', 'Be', 'By', 'Go', 'Oh'}
            if fragment not in valid_starts:
                paragraphs[i] = stripped[m.end(1):].strip()
                orphan_fixes += 1
                # Rejoin to previous paragraph
                for j in range(i - 1, -1, -1):
                    if paragraphs[j] and paragraphs[j].strip():
                        if heading_indices and j in heading_indices:
                            continue
                        paragraphs[j] = paragraphs[j].rstrip() + ' ' + paragraphs[i]
                        paragraphs[i] = ''
                        break
                continue

        # Remove leading 1-2 random characters before continuation text
        # e.g., "Il the landscape itself" -> "the landscape itself"
        # e.g., "Oj The next sentence" -> "The next sentence"
        m = re.match(r'^([A-Z][a-z]?)\s+(.*)', stripped)
        if m and len(stripped) > 40:
            leading = m.group(1)
            rest = m.group(2)
            if len(leading) <= 2 and leading not in {'I', 'A', 'In', 'An', 'It', 'Is', 'If', 'Or', 'On', 'At', 'He', 'We', 'So', 'Do', 'No', 'My', 'Up', 'Am', 'As', 'Be', 'By', 'Go', 'Oh'}:
                paragraphs[i] = rest.strip()
                orphan_fixes += 1
                # If starts with lowercase, rejoin to previous paragraph
                if paragraphs[i] and paragraphs[i][0].islower():
                    for j in range(i - 1, -1, -1):
                        if paragraphs[j] and paragraphs[j].strip():
                            if heading_indices and j in heading_indices:
                                continue
                            paragraphs[j] = paragraphs[j].rstrip() + ' ' + paragraphs[i]
                            paragraphs[i] = ''
                            break
                continue

    if orphan_fixes:
        log(f"  Cleaned {orphan_fixes} orphaned character/number fragments")

    # Phase 6: Remove duplicate title fragments near chapter headings
    # Only remove short paragraphs that:
    #   - Match a bookmark title fragment
    #   - Don't end with a period (real sentences end with periods)
    #   - Are near other short title-like paragraphs (clustered at chapter starts)
    if bookmark_titles:
        clean_titles = set()
        for title in bookmark_titles:
            t = title.strip().lower()
            clean_titles.add(t)
            t_stripped = re.sub(r'^\d{1,3}[\.\)]\s*', '', t).strip()
            if t_stripped:
                clean_titles.add(t_stripped)
                # Split on periods and colons only (not dashes -- too aggressive)
                for part in re.split(r'[\.\:]', t_stripped):
                    part = part.strip()
                    if len(part) > 10:
                        clean_titles.add(part)

        title_dupes_removed = 0
        for i in range(len(paragraphs)):
            if not paragraphs[i]:
                continue
            para = paragraphs[i].strip()
            if len(para) > 80 or len(para) < 5:
                continue
            # Don't remove if it's a Markdown heading or at a heading index
            if para.startswith('#'):
                continue
            if heading_indices and i in heading_indices:
                continue
            # Don't remove if it ends with sentence-ending punctuation
            # (real content sentences end with periods; title fragments don't)
            if para.endswith(('.', '!', '?', ':')):
                continue

            para_lower = para.lower()

            # Check exact match against title fragments
            matched = para_lower in clean_titles

            # Check if it's a substring of a title AND very short (< 40 chars)
            if not matched and len(para) < 40:
                for title in bookmark_titles:
                    title_clean = re.sub(r'^\d{1,3}[\.\)]\s*', '', title.strip().lower()).strip()
                    if len(para_lower) >= 8 and para_lower in title_clean:
                        matched = True
                        break

            if matched:
                paragraphs[i] = ''
                title_dupes_removed += 1

        if title_dupes_removed:
            log(f"  Removed {title_dupes_removed} duplicate title fragments")

    # Phase 7: Indent dialogue lines
    # Detect patterns like "Koko That me." or "Barbara Is that really you?"
    # where a short line starts with a capitalized name followed by dialogue.
    # These get a leading tab for readability in the final output.
    # Only apply if we detect a cluster of 3+ such lines nearby (confirms dialogue format)

    dialogue_pattern = re.compile(
        r'^([A-Z][a-z]+)\s+((?:[A-Z][a-z]|[A-Z][A-Z]|["\'\(]).+)$'  # "Name Text..."
    )

    # First pass: identify dialogue line candidates
    dialogue_candidates = []
    for i in range(len(paragraphs)):
        if not paragraphs[i]:
            continue
        para = paragraphs[i].strip()
        # Dialogue lines are short (under 120 chars typically)
        if len(para) > 150:
            continue
        if dialogue_pattern.match(para):
            dialogue_candidates.append(i)

    # Second pass: only indent if there's a cluster (3+ candidates within 10 paragraphs)
    dialogue_indices = set()
    for idx in dialogue_candidates:
        nearby = [c for c in dialogue_candidates if abs(c - idx) <= 10]
        if len(nearby) >= 3:
            dialogue_indices.update(nearby)

    # Apply indentation
    dialogue_indented = 0
    for i in dialogue_indices:
        if paragraphs[i] and not paragraphs[i].startswith('\t'):
            paragraphs[i] = '\t' + paragraphs[i]
            dialogue_indented += 1

    if dialogue_indented:
        log(f"  Indented {dialogue_indented} dialogue lines")

    # Phase 8: Collapse spaced-letter pdfminer artifacts
    # pdfminer sometimes extracts certain fonts with spaces between every character:
    # "e x a c t h a r m o n y o f d o m i n i o n" -> "exact harmony of dominion"
    # Detect runs of (single_char space){3,} single_char, collapse spaces, then
    # re-insert word boundaries using dictionary lookup.

    spaced_pattern = re.compile(
        r'(?:(?<=\s)|(?<=^))'            # preceded by whitespace or start
        r'((?:[\w,.\';:!?\-] ){3,}'      # 3+ single chars (incl punctuation) each followed by space
        r'[\w,.\';:!?\-])'               # final single char
        r'(?=\s|$)'                       # followed by whitespace or end
    )

    _vowels = set('aeiouAEIOU')

    def _split_words_greedy(letters, spell_dict):
        """Split a run of letters into words using greedy longest-match dictionary lookup.
        When no dictionary word is found, consumes up to the next vowel-consonant
        boundary where a known word begins, keeping unknown terms intact."""
        result = []
        i = 0
        n = len(letters)
        while i < n:
            # Try longest possible word first, down to length 1
            best = None
            max_len = min(n - i, 20)  # cap at 20-char words
            for length in range(max_len, 0, -1):
                candidate = letters[i:i + length]
                # Single char: only accept 'a', 'I', 'o' (common single-char words)
                if length == 1:
                    if candidate.lower() in ('a', 'i', 'o'):
                        best = candidate
                    break
                if candidate.lower() in spell_dict:
                    best = candidate
                    break
            if best:
                result.append(best)
                i += len(best)
            else:
                # No dictionary match — consume unknown chunk until we find a
                # position where a known word starts (scan from earliest).
                # This keeps unknown terms like "simi" intact instead of "s i m i".
                chunk_end = i + 1
                for k in range(i + 2, n + 1):
                    # Check if a known word starts at position k
                    remainder = letters[k:k + 20] if k < n else ''
                    found_word_at_k = False
                    for wl in range(min(len(remainder), 20), 1, -1):
                        if remainder[:wl].lower() in spell_dict:
                            found_word_at_k = True
                            break
                    if found_word_at_k:
                        chunk_end = k
                        break
                else:
                    # No known word found in remainder — take everything
                    chunk_end = n
                result.append(letters[i:chunk_end])
                i = chunk_end
        return ' '.join(result)

    def _collapse_spaced_run(run_text, spell_dict):
        """Collapse a spaced-letter run back into normal text with word boundaries."""
        # Strip spaces to get raw character stream
        raw = run_text.replace(' ', '')

        # Split into letter-runs and punctuation tokens
        # e.g. "exactharmonyofdominion'because" -> ["exactharmonyofdominion", "'", "because"]
        # e.g. "Son,graceby" -> ["Son", ",", "graceby"]
        tokens = re.findall(r"[a-zA-Z]+|[^a-zA-Z]+", raw)

        rebuilt_parts = []
        for token in tokens:
            if re.match(r'^[a-zA-Z]+$', token):
                # Letter run — split into dictionary words
                words = _split_words_greedy(token, spell_dict)
                rebuilt_parts.append(words)
            else:
                # Punctuation — keep as-is, attach to previous part (no leading space)
                rebuilt_parts.append(token)

        # Join: add space between consecutive letter-run tokens,
        # but punctuation attaches directly to the preceding token
        result_parts = []
        for part in rebuilt_parts:
            if not result_parts:
                result_parts.append(part)
            elif re.match(r'^[a-zA-Z]', part) and result_parts[-1] and re.search(r'[a-zA-Z]$', result_parts[-1]):
                # Two letter-runs adjacent — add space
                result_parts.append(' ' + part)
            elif re.match(r'^[^a-zA-Z]', part):
                # Punctuation — attach directly, then add space after
                result_parts.append(part + ' ')
            else:
                result_parts.append(part)

        return ''.join(result_parts).strip()

    # Build a set for O(1) dictionary lookup from the spellchecker
    spell_words = set(spell.word_frequency.words())

    # Add theological/patristic terms that pyspellchecker won't know
    _theological_terms = [
        'homoousios', 'homoiousios', 'ousia', 'hypostasis', 'hypostases',
        'theologia', 'economia', 'consubstantial', 'basil', 'nicaea',
        'arian', 'arianism', 'eunomius', 'apollinaris', 'gregory', 'nyssa',
        'cappadocian', 'trinitarian', 'godhead', 'athanasius', 'origen',
        'tertullian', 'hilary', 'ambrose', 'eusebius', 'chrysostom',
        'augustine', 'epiphanius', 'didymus', 'marcellus', 'sabellius',
        'subordinationism', 'modalism', 'monarchian', 'christological',
        'pneumatological', 'soteriological', 'eschatological', 'patristic',
        'anathema', 'creed', 'synod', 'ecclesial', 'catechetical',
        'homoian', 'anomoian', 'heteroousios', 'prosopa', 'prosopon',
        'substantia', 'essentia', 'simi', 'similitude',
    ]
    spell_words.update(_theological_terms)

    spaced_collapsed = 0
    for i in range(len(paragraphs)):
        if not paragraphs[i]:
            continue

        line = paragraphs[i]
        matches = list(spaced_pattern.finditer(line))
        if not matches:
            continue

        new_line = line
        # Process matches in reverse order so replacements don't shift offsets
        for m in reversed(matches):
            original_run = m.group(1)
            # Skip false positives: require 3+ distinct letter characters.
            # This filters out TOC dot leaders ('. . . . .') and digit
            # sequences ('9 8 7 6 5 4 3 2') which aren't spaced-letter artifacts.
            distinct_letters = set(c for c in original_run if c.isalpha())
            if len(distinct_letters) < 3:
                continue
            collapsed = _collapse_spaced_run(original_run, spell_words)
            new_line = new_line[:m.start(1)] + collapsed + new_line[m.end(1):]

        if new_line != line:
            spaced_collapsed += 1
            log(f"  [Phase 8] Collapsed spaced-letter artifact in para {i}:")
            log(f"    BEFORE: {line.strip()[:160]}")
            log(f"    AFTER:  {new_line.strip()[:160]}")
            paragraphs[i] = new_line

    if spaced_collapsed:
        log(f"  Phase 8: collapsed {spaced_collapsed} spaced-letter artifact(s)")

    # Phase 9: Detect and remove repeated-fragment running headers
    # Some PDFs have running headers/footers that survived earlier cleanup because
    # they're mixed-case (not ALL-CAPS) and lack page numbers.
    # Two-pass approach:
    #   Pass A: find short paragraphs that repeat 3+ times (standalone headers)
    #   Pass B: find substrings (20+ chars) that appear in 5+ paragraphs (embedded headers)
    phase9_stripped = 0
    phase9_embedded = 0

    # Pass A: Standalone repeated short paragraphs
    frag_candidates = {}
    for i, p in enumerate(paragraphs):
        s = p.strip()
        if not s or len(s) > 150 or len(s) < 10:
            continue
        if s.startswith('#'):
            continue
        if heading_indices and i in heading_indices:
            continue
        norm = re.sub(r'\s+', ' ', s).strip()
        if norm not in frag_candidates:
            frag_candidates[norm] = []
        frag_candidates[norm].append(i)

    repeated_fragments = {}
    for norm, indices in frag_candidates.items():
        if len(indices) >= 3:
            repeated_fragments[norm] = indices

    if repeated_fragments:
        for norm, indices in repeated_fragments.items():
            for idx in indices:
                paragraphs[idx] = ''
                phase9_stripped += 1
            log(f"  [Phase 9] Stripped repeated fragment (x{len(indices)}): '{norm[:80]}'")

    # Pass B: Detect repeated substrings embedded in longer paragraphs.
    # Strategy: extract candidate substrings from paragraph starts/middles,
    # then count how many distinct paragraphs contain each candidate.
    # A substring appearing in 5+ paragraphs is likely a running header.
    # Use known_headers from Phase 0 AND discover new ones by frequency.
    embedded_headers = set()

    # Add any already-known headers from Phase 0 standalone detection
    for h in known_headers:
        embedded_headers.add(h)

    # Add pre-scan fragments (detected before any phase modified them)
    for frag in _prescan_fragments:
        embedded_headers.add(frag)

    # Also add any Phase 9 standalone fragments we just found
    for norm in repeated_fragments:
        embedded_headers.add(norm)

    # Discover new embedded headers: look for substrings of 20-100 chars
    # that appear as-is in 5+ different paragraphs. Use a sliding window
    # approach on the first occurrence to extract the candidate, then count.
    # Optimization: extract candidate fragments from paragraph prefixes
    # (most running headers appear at paragraph boundaries).
    prefix_candidates = {}
    for i, p in enumerate(paragraphs):
        s = p.strip()
        if not s or len(s) < 30:
            continue
        if s.startswith('#'):
            continue
        if heading_indices and i in heading_indices:
            continue
        # Try the first 40-80 chars as a potential header prefix
        for length in (80, 60, 40):
            if len(s) > length:
                candidate = re.sub(r'\s+', ' ', s[:length]).strip()
                if candidate not in prefix_candidates:
                    prefix_candidates[candidate] = set()
                prefix_candidates[candidate].add(i)

    for candidate, para_set in prefix_candidates.items():
        if len(para_set) >= 5 and len(candidate) >= 20:
            embedded_headers.add(candidate)

    # Now strip all embedded headers from paragraphs
    if embedded_headers:
        # Sort longest first to avoid partial matches
        sorted_headers = sorted(embedded_headers, key=len, reverse=True)
        for frag in sorted_headers:
            frag_words = frag.split()
            if not frag_words:
                continue
            frag_pattern = r'\s*'.join(re.escape(w) for w in frag_words)
            frag_re = re.compile(frag_pattern)
            for i, p in enumerate(paragraphs):
                if not p or not p.strip():
                    continue
                if heading_indices and i in heading_indices:
                    continue
                m = frag_re.search(p)
                if m:
                    before = p[:m.start()]
                    after = p[m.end():]
                    new_p = (before.rstrip() + ' ' + after.lstrip()).strip() if before.strip() and after.strip() else (before + after).strip()
                    if new_p and new_p != p.strip():
                        paragraphs[i] = new_p
                        phase9_embedded += 1
                    elif not new_p:
                        paragraphs[i] = ''
                        phase9_embedded += 1

    if phase9_stripped or phase9_embedded:
        log(f"  Phase 9: stripped {phase9_stripped} standalone + {phase9_embedded} embedded repeated fragments")

    # Log results
    log(f"  OCR cleanup: checked {words_checked:,} words, made {fixes_made} corrections")
    if fix_log:
        # Show top corrections
        sorted_fixes = sorted(fix_log.items(), key=lambda x: -x[1])
        for fix_desc, count in sorted_fixes[:15]:
            log(f"    {fix_desc} (x{count})")
        if len(sorted_fixes) > 15:
            log(f"    ... and {len(sorted_fixes) - 15} more unique corrections")

    # FINAL PASS: Catch any remaining leading page numbers at paragraph starts
    # This runs after ALL phases to catch numbers orphaned by title stripping,
    # header removal, or other late-stage cleanup.
    # Also strips single-digit superscript footnote references that pypdf
    # extracted as full-size digits at paragraph starts (e.g., "5 They compete...")
    final_num_fixes = 0
    for i in range(len(paragraphs)):
        if not paragraphs[i]:
            continue
        stripped = paragraphs[i].strip()
        # 1-3 digit number at paragraph start in a long paragraph
        m = re.match(r'^(\d{1,3})\s+(.*)', stripped, re.DOTALL)
        if m and len(stripped) > 15:
            num = m.group(1)
            rest = m.group(2)
            # Don't strip heading-numbered paragraphs
            if heading_indices and i in heading_indices:
                continue
            # Don't strip if followed by a period (numbered list: "1. Introduction")
            if re.match(r'^(\d{1,3})\.\s', stripped):
                continue
            # Don't strip if followed by a closing paren (numbered list: "1) First item")
            if re.match(r'^(\d{1,3})\)\s', stripped):
                continue
            # Don't strip if it looks like a real address or list item
            next_word = rest.split()[0] if rest.split() else ''
            # Keep if: starts with a capitalized word that could be a name/place
            # AND the number could be a street address (next word capitalized)
            if next_word and next_word[0].isupper() and num in ('198', '200', '100', '300', '400', '500'):
                continue  # likely a street address
            # Don't strip if the remaining text is very short AND starts with
            # a digit (would be stripping part of a number sequence like "1 2 3")
            if len(rest.strip()) < 5:
                continue
            # Don't strip if the next word is a unit/quantity — the number is
            # content, not a footnote (e.g., "90 percent", "25 million barrels")
            next_lower = next_word.lower().rstrip('.,;:')
            _unit_words = {
                'percent', 'per', 'million', 'billion', 'thousand', 'hundred',
                'tons', 'barrels', 'cents', 'years', 'months', 'days', 'hours',
                'minutes', 'miles', 'kilometers', 'feet', 'meters', 'pounds',
                'kilograms', 'gallons', 'liters', 'acres', 'people', 'men',
                'women', 'children', 'soldiers', 'troops', 'ships', 'planes',
            }
            if next_lower in _unit_words:
                continue
            # Don't strip if next word is lowercase — the number is likely
            # part of the sentence (e.g., "10 of the 12 ministers")
            if next_word and next_word[0].islower():
                continue

            paragraphs[i] = rest
            final_num_fixes += 1
            # If starts with lowercase, rejoin to previous
            if rest and rest[0].islower():
                for j in range(i - 1, -1, -1):
                    if paragraphs[j] and paragraphs[j].strip():
                        if heading_indices and j in heading_indices:
                            continue
                        paragraphs[j] = paragraphs[j].rstrip() + ' ' + paragraphs[i]
                        paragraphs[i] = ''
                        break

    if final_num_fixes:
        log(f"  [FINAL] Stripped {final_num_fixes} remaining leading page numbers")

    # Phase 9b: Re-strip embedded headers that may have been reintroduced
    # by the FINAL PASS orphan rejoining (joining lowercase-start fragments
    # back into paragraphs that previously had their headers stripped).
    if embedded_headers:
        phase9b_count = 0
        sorted_headers = sorted(embedded_headers, key=len, reverse=True)
        for frag in sorted_headers:
            frag_words = frag.split()
            if not frag_words:
                continue
            frag_pattern = r'\s*'.join(re.escape(w) for w in frag_words)
            frag_re = re.compile(frag_pattern)
            for i, p in enumerate(paragraphs):
                if not p or not p.strip():
                    continue
                if heading_indices and i in heading_indices:
                    continue
                m = frag_re.search(p)
                if m:
                    before = p[:m.start()]
                    after = p[m.end():]
                    new_p = (before.rstrip() + ' ' + after.lstrip()).strip() if before.strip() and after.strip() else (before + after).strip()
                    if new_p and new_p != p.strip():
                        paragraphs[i] = new_p
                        phase9b_count += 1
                    elif not new_p:
                        paragraphs[i] = ''
                        phase9b_count += 1
        if phase9b_count:
            log(f"  Phase 9b: stripped {phase9b_count} additional embedded headers after FINAL PASS")

    # Phase 10: Rejoin page-boundary sentence splits.
    # pypdf treats each page as a separate text block, so sentences that span
    # page boundaries get split into separate paragraphs. Detect and merge.
    phase10_merged = 0

    # Sentence-ending punctuation (with optional trailing quotes/parens)
    _sent_end_re = re.compile(
        r'[.!?][\u201d\u2019"\')]*\s*$'      # period/excl/question + optional close quotes
        r'|'
        r'[\u201d\u2019"\')]\s*$'             # closing quote/paren at end (implied sentence end)
        r'|'
        r'[:\-\u2014]\s*$'                     # colon/dash at end (quote intro — don't merge)
        r'|'
        r'\]\s*$'                              # closing bracket
    )

    # Patterns that indicate the next paragraph is a new section, not a continuation
    _new_section_re = re.compile(
        r'^(?:'
        r'#'                                   # heading
        r'|<<PAGE:'                            # page marker
        r'|\d+\.\s+[A-Z]'                     # numbered heading like "2. Even the..."
        r'|Chapter\s'                          # chapter heading
        r'|Part\s'                             # part heading
        r'|\[(?:The |Ed)'                      # editorial bracket like "[The writer..."
        r'|"\s*$'                              # lone opening quote
        r')'
    )

    # Orphaned footnote/page numbers at paragraph end (strip before checking)
    _trailing_nums_re = re.compile(r'\s+\d{1,3}(?:\s+\d{1,3})*\s*$')

    i = 0
    while i < len(paragraphs) - 1:
        curr = paragraphs[i].strip()
        if not curr or len(curr) < 20 or curr.startswith('#') or curr.startswith('<<PAGE:'):
            i += 1
            continue
        # Don't merge FROM a heading paragraph
        if heading_indices and i in heading_indices:
            i += 1
            continue

        # Find next non-empty paragraph
        j = i + 1
        while j < len(paragraphs) and not paragraphs[j].strip():
            j += 1
        if j >= len(paragraphs):
            break

        nxt = paragraphs[j].strip()
        if not nxt or len(nxt) < 10 or nxt.startswith('#') or nxt.startswith('<<PAGE:'):
            i = j + 1
            continue
        # Don't merge INTO a heading paragraph
        if heading_indices and j in heading_indices:
            i = j + 1
            continue

        # Skip if next paragraph looks like a new section
        if _new_section_re.match(nxt):
            i = j + 1
            continue

        # Strip trailing orphan footnote/page numbers for end-of-sentence check
        curr_clean = _trailing_nums_re.sub('', curr).rstrip()
        if not curr_clean:
            i = j + 1
            continue

        # Check if current paragraph ends mid-sentence
        if _sent_end_re.search(curr_clean):
            # Ends with sentence-ending punctuation — don't merge
            i = j + 1
            continue

        # Current paragraph ends mid-sentence. Merge with next.
        # Join with a space (the sentence continues)
        paragraphs[i] = curr.rstrip() + ' ' + nxt.lstrip()
        paragraphs[j] = ''
        phase10_merged += 1
        # Don't advance i — the merged paragraph might need another merge
        continue

    if phase10_merged:
        log(f"  Phase 10: merged {phase10_merged} page-boundary sentence splits")

    fix_stats = {
        'unicode_normalized': normalized,
        'backtick_fixes': backtick_fixes,
        'rn_m_fixes': fixes_made,
        'i_to_1_fixes': i_to_1_fixes + standalone_i_fixes,
        'o_to_0_fixes': o_to_0_fixes,
        'merged_word_fixes': merged_word_count,
        'ligature_fixes': ligature_fixes,
        'dehyphenation_fixes': dehyphen_count,
    }
    return paragraphs, fix_stats


def _extract_html_with_pymupdf_columns(pdf_path, log):
    """Extract HTML-ready paragraph dicts from a two-column PDF using PyMuPDF.

    Uses page.get_text("dict") for font metadata (size, bold, italic, superscript)
    per span. Processes blocks in two-column reading order: top headers, left column
    body, right column body, left column footnotes, right column footnotes, bottom
    footers. Footnote zone = bottom 15% of page (y0 >= page_height * 0.85).

    Returns (para_dicts, body_size) with the same schema as extract_with_pdfminer_html(),
    so all downstream processing (rejoin_html_fragments, format_paragraphs_as_html,
    _link_endnotes) works unchanged.
    """
    import pymupdf
    import re
    from collections import defaultdict, Counter

    doc = pymupdf.open(pdf_path)
    total_pages = len(doc)
    all_paras = []

    try:
        for pg_idx in range(total_pages):
            pg = pg_idx + 1  # 1-indexed
            page = doc[pg_idx]
            page_dict = page.get_text("dict")
            page_w = page.rect.width
            page_h = page.rect.height
            if page_w <= 0 or page_h <= 0:
                continue
            page_mid = page_w / 2.0
            footnote_y_hard = page_h * 0.85   # hard threshold: always footnote
            footnote_y_soft = page_h * 0.60   # soft threshold: footnote if smaller font

            # Insert page marker (same schema as extract_with_pdfminer_html)
            all_paras.append({
                'text': '', 'font_size': 0, 'is_bold': False, 'is_italic': False,
                'is_centered': False, 'is_all_caps': False, 'page_number': pg,
                'line_count': 0, 'char_count': 0, 'is_page_marker': True
            })

            # Pre-scan: compute dominant font size per block for footnote detection
            text_blocks = []
            for block in page_dict["blocks"]:
                if block["type"] != 0:
                    continue
                x0, y0, x1, y1 = block["bbox"]
                has_text = any(
                    span["text"].strip()
                    for line in block["lines"]
                    for span in line["spans"]
                )
                if not has_text:
                    continue
                # Compute dominant font size for this block
                sw = defaultdict(int)
                for line in block["lines"]:
                    for span in line["spans"]:
                        n = len(span["text"].strip())
                        if n > 0:
                            sw[round(span["size"] * 2) / 2] += n
                dom_size = max(sw, key=sw.get, default=0.0) if sw else 0.0
                text_blocks.append((block, dom_size))

            # Estimate body font size from upper 60% of page (above footnote zone)
            upper_sizes = defaultdict(int)
            for block, dom_size in text_blocks:
                if block["bbox"][1] < footnote_y_soft and dom_size > 0:
                    span_ratio = (block["bbox"][2] - block["bbox"][0]) / page_w
                    if span_ratio <= 0.70:  # column blocks only
                        for line in block["lines"]:
                            for span in line["spans"]:
                                n = len(span["text"].strip())
                                if n > 0:
                                    upper_sizes[round(span["size"] * 2) / 2] += n
            page_body_size = max(upper_sizes, key=upper_sizes.get, default=0.0) if upper_sizes else 0.0

            # Classify blocks into zones
            top_wide       = []
            left_col_body  = []
            right_col_body = []
            left_col_fnotes  = []
            right_col_fnotes = []
            bottom_wide    = []
            col_blocks     = []
            wide_blocks_raw = []

            for block, dom_size in text_blocks:
                x0, y0, x1, y1 = block["bbox"]
                span_ratio = (x1 - x0) / page_w
                x_mid = (x0 + x1) / 2.0

                # Hybrid footnote detection:
                # 1. Hard threshold (y >= 85%): always footnote
                # 2. Soft threshold (y >= 60% AND font < 90% of body): likely footnote
                is_fn = False
                if span_ratio <= 0.70:  # only classify column blocks as footnotes
                    if y0 >= footnote_y_hard:
                        is_fn = True
                    elif (y0 >= footnote_y_soft and page_body_size > 0
                          and dom_size > 0 and dom_size < page_body_size * 0.95):
                        is_fn = True

                if span_ratio > 0.70:
                    wide_blocks_raw.append(block)
                elif is_fn:
                    if x_mid < page_mid:
                        left_col_fnotes.append(block)
                    else:
                        right_col_fnotes.append(block)
                else:
                    col_blocks.append(block)
                    if x_mid < page_mid:
                        left_col_body.append(block)
                    else:
                        right_col_body.append(block)

            # Partition wide blocks relative to first column content
            if col_blocks:
                min_col_y0 = min(b["bbox"][1] for b in col_blocks)
                for b in wide_blocks_raw:
                    if b["bbox"][1] < min_col_y0:
                        top_wide.append(b)
                    else:
                        bottom_wide.append(b)
            else:
                # No column blocks on this page — all wide blocks go to top_wide
                top_wide = wide_blocks_raw[:]

            # Sort each group by y0
            top_wide.sort(key=lambda b: b["bbox"][1])
            left_col_body.sort(key=lambda b: b["bbox"][1])
            right_col_body.sort(key=lambda b: b["bbox"][1])
            left_col_fnotes.sort(key=lambda b: b["bbox"][1])
            right_col_fnotes.sort(key=lambda b: b["bbox"][1])
            bottom_wide.sort(key=lambda b: b["bbox"][1])

            ordered = (top_wide + left_col_body + right_col_body
                       + left_col_fnotes + right_col_fnotes + bottom_wide)
            footnote_blocks = set(id(b) for b in left_col_fnotes + right_col_fnotes)
            # Running header candidates: column blocks in the top 15% of the page
            # (not wide blocks — those are title-page or index content)
            _header_y_threshold = page_h * 0.15
            header_candidate_blocks = set(
                id(b) for b in (left_col_body + right_col_body)
                if b["bbox"][1] < _header_y_threshold
            )

            for block in ordered:
                x0, y0, x1, y1 = block["bbox"]
                _is_footnote_block = id(block) in footnote_blocks
                _is_header_candidate = id(block) in header_candidate_blocks

                # Step 1: compute dominant font properties (weighted by character count)
                size_weight  = defaultdict(int)
                bold_chars   = 0
                italic_chars = 0
                total_chars  = 0
                for line in block["lines"]:
                    for span in line["spans"]:
                        n = len(span["text"].strip())
                        if n == 0:
                            continue
                        size_weight[round(span["size"] * 2) / 2] += n   # round to 0.5pt
                        if span["flags"] & 16:
                            bold_chars += n
                        if span["flags"] & 2:
                            italic_chars += n
                        total_chars += n

                if total_chars == 0:
                    continue

                dominant_size = max(size_weight, key=size_weight.get, default=0.0)
                is_bold   = bold_chars   > total_chars * 0.5
                is_italic = italic_chars > total_chars * 0.5

                # Step 2: build text with <sup>, <em>, <strong> tags
                # Superscript: flags & 1 set AND noticeably smaller than dominant size
                # Bold/italic: per-span flags that DIFFER from block's dominant style
                parts  = []
                in_sup = False
                in_em = False
                in_strong = False
                for line in block["lines"]:
                    line_parts = []
                    for span in line["spans"]:
                        text = span["text"]
                        if not text:
                            continue
                        flags = span["flags"]
                        is_sup = (flags & 1) and (span["size"] < dominant_size * 0.75)
                        span_bold = bool(flags & 16)
                        span_italic = bool(flags & 2)
                        want_strong = span_bold and not is_bold
                        want_em = span_italic and not is_italic

                        # Close tags no longer needed (reverse order)
                        if in_sup and not is_sup:
                            line_parts.append('</sup>')
                            in_sup = False
                        if in_em and not want_em:
                            line_parts.append('</em>')
                            in_em = False
                        if in_strong and not want_strong:
                            line_parts.append('</strong>')
                            in_strong = False

                        # Open tags now needed
                        if want_strong and not in_strong:
                            line_parts.append('<strong>')
                            in_strong = True
                        if want_em and not in_em:
                            line_parts.append('<em>')
                            in_em = True
                        if is_sup and not in_sup:
                            line_parts.append('<sup>')
                            in_sup = True

                        line_parts.append(text)
                    # Close any open tags at end of line
                    if in_sup:
                        line_parts.append('</sup>')
                        in_sup = False
                    if in_em:
                        line_parts.append('</em>')
                        in_em = False
                    if in_strong:
                        line_parts.append('</strong>')
                        in_strong = False
                    line_text = ''.join(line_parts).strip()
                    if not line_text:
                        continue
                    # Hyphenated line break: remove hyphen and join to next line
                    if parts and parts[-1].endswith('-') and line_text and line_text[0].islower():
                        parts[-1] = parts[-1][:-1] + line_text
                    else:
                        parts.append(line_text)

                # Step 3: normalize and finalize
                text = ' '.join(parts)
                text = re.sub(r'[\u00a0\u2000-\u200b\u2028\u2029\u202f\u205f\u3000\t]+', ' ', text)
                text = re.sub(r' +', ' ', text).strip()
                if not text:
                    continue
                if text.strip().isdigit():
                    continue   # bare page number from running header/footer

                is_centered = abs((x0 + x1) / 2 - page_w / 2) < 40
                is_all_caps = (text == text.upper()
                               and len(text) > 3
                               and any(c.isalpha() for c in text))

                all_paras.append({
                    'text':        text,
                    'font_size':   dominant_size,
                    'is_bold':     is_bold,
                    'is_italic':   is_italic,
                    'is_centered': is_centered,
                    'is_all_caps': is_all_caps,
                    'page_number': pg,
                    'line_count':  len(block["lines"]),
                    'char_count':  len(text),
                    '_is_footnote': _is_footnote_block,
                    '_is_running_header_candidate': _is_header_candidate,
                })

            if (pg_idx + 1) % 50 == 0:
                log(f"  PyMuPDF HTML extraction: {pg_idx + 1}/{total_pages} pages...")
    finally:
        doc.close()

    # Compute body_size: font_size with highest total character count across
    # non-marker, non-footnote-zone paragraphs.
    # Weighted by char_count (not paragraph count) so that many small footnote
    # citation blocks (8pt, 1-2 lines each) cannot outvote fewer but longer body
    # paragraphs (e.g., Hermeneia commentaries where footnotes produce 2-3x more
    # blocks than body text despite carrying far fewer total characters).
    # Footnote-zone blocks (tagged _is_footnote) are excluded so that dense
    # Hermeneia-style footnotes do not skew the mode (e.g., Ezekiel II).
    size_char_counts: Counter = Counter()
    for p in all_paras:
        if (not p.get('is_page_marker') and p['font_size'] > 0
                and not p.get('_is_footnote')):
            size_char_counts[p['font_size']] += p.get('char_count', len(p.get('text', '')))
    body_size = size_char_counts.most_common(1)[0][0] if size_char_counts else 12.0

    for p in all_paras:
        p.pop('_is_footnote', None)
        # Keep _is_running_header_candidate — consumed by format_paragraphs_as_html()

    log(f"  PyMuPDF HTML extraction: {total_pages} pages, {len(all_paras)} paragraphs")
    log(f"  Body font detected: {body_size}pt")

    return all_paras, body_size


def extract_with_pdfminer_html(pdf_path, log, force_columns=False):
    """
    Extract PDF content using pdfminer with font metadata preserved.
    Returns list of paragraph dicts with font properties.
    """
    # ── PyMuPDF column detection gate ─────────────────────────────────────────
    # detect_column_layout() handles its own ImportError and returns is_multicolumn=False
    # if pymupdf is not installed — no outer ImportError guard needed here.
    try:
        col_info = detect_column_layout(pdf_path, log)
        if col_info['is_multicolumn'] or force_columns:
            if col_info['is_multicolumn']:
                reason = f"Multi-column layout detected (confidence {col_info['confidence']:.0%})"
            else:
                reason = "Column extraction forced (--force-columns)"
            log(f"  {reason} — using PyMuPDF HTML extraction")
            try:
                para_dicts, body_size = _extract_html_with_pymupdf_columns(pdf_path, log)
                if any(not p.get('is_page_marker') for p in para_dicts):
                    return para_dicts, body_size
                log("  [WARN] PyMuPDF HTML extraction returned empty — falling back to pdfminer")
            except Exception as e:
                log(f"  [WARN] PyMuPDF HTML extraction failed: {e} — falling back to pdfminer")
        else:
            log(f"  Single-column layout (confidence {col_info['confidence']:.0%}) — using pdfminer")
    except Exception as e:
        log(f"  [WARN] Column detection error: {e} — using pdfminer")
    # ── existing pdfminer extraction (UNCHANGED below) ────────────────────────
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTTextBox, LTTextLine, LTChar, LTAnno
    from collections import Counter

    # Tune LAParams for better word-boundary detection.
    # Default word_margin=0.1 misses real word gaps in many PDFs.
    laparams = LAParams(word_margin=0.05)

    all_paras = []
    fonts_seen = set()
    total_pages = 0
    page_heights = {}  # {page_number: height} for footnote zone detection

    for page_num, page_layout in enumerate(extract_pages(pdf_path, laparams=laparams)):
        total_pages += 1
        pg = page_num + 1  # 1-indexed
        page_width = page_layout.width
        page_height = page_layout.height
        page_heights[pg] = page_height

        # Insert page marker
        all_paras.append({
            'text': '', 'font_size': 0, 'is_bold': False, 'is_italic': False,
            'is_centered': False, 'is_all_caps': False, 'page_number': pg,
            'line_count': 0, 'char_count': 0, 'is_page_marker': True,
        })

        # Collect all text lines on this page with font metadata
        page_lines = []
        for element in page_layout:
            if not isinstance(element, LTTextBox):
                continue
            for line in element:
                if not isinstance(line, LTTextLine):
                    continue
                raw_text = line.get_text().strip()
                if not raw_text:
                    continue

                # Collect font info from LTChar objects and detect superscripts.
                # Also detect missing word boundaries via character-gap analysis:
                # if the gap between consecutive LTChar x-positions exceeds 30%
                # of the running average character width, inject a space.
                font_counts = Counter()
                size_counts = Counter()
                char_total = 0
                char_data = []  # (char_text, font_size, font_name_or_None)
                prev_x1 = None
                avg_char_width = None
                for char in line:
                    if isinstance(char, LTChar):
                        if hasattr(char, 'fontname'):
                            fonts_seen.add(char.fontname)
                        # Gap-based space injection
                        if prev_x1 is not None and avg_char_width is not None:
                            gap = char.x0 - prev_x1
                            if gap > avg_char_width * 0.3:
                                # Inject space if last char_data entry isn't already a space
                                if char_data and char_data[-1][0] != ' ':
                                    char_data.append((' ', 0, None))
                        prev_x1 = char.x1
                        char_width = char.x1 - char.x0
                        if char_width > 0:
                            if avg_char_width is None:
                                avg_char_width = char_width
                            else:
                                avg_char_width = avg_char_width * 0.9 + char_width * 0.1
                        sz = round(char.size * 2) / 2
                        font_counts[char.fontname] += 1
                        size_counts[sz] += 1
                        char_total += 1
                        char_data.append((char.get_text(), sz, char.fontname))
                    elif isinstance(char, LTAnno):
                        char_data.append((char.get_text(), 0, None))

                if char_total == 0:
                    continue

                dominant_font = font_counts.most_common(1)[0][0]
                dominant_size = size_counts.most_common(1)[0][0]

                # Detect dominant style from font name
                dom_bold = 'Bold' in dominant_font or 'bold' in dominant_font
                dom_italic = ('Italic' in dominant_font or 'italic' in dominant_font
                              or 'Oblique' in dominant_font or 'oblique' in dominant_font)

                # Build text with <sup>, <em>, <strong> tags for inline style changes
                # A digit is superscript when its font size < 80% of line's dominant size
                # Bold/italic tags wrap spans that DIFFER from the line's dominant style
                sup_threshold = dominant_size * 0.8
                text_parts = []
                in_sup = False
                in_em = False
                in_strong = False
                for ch, sz, fname in char_data:
                    is_sup = (sz > 0 and sz < sup_threshold and ch.isdigit()
                              and dominant_size >= 9)  # only on body-sized lines

                    # Detect per-char bold/italic from font name
                    if fname:
                        ch_bold = 'Bold' in fname or 'bold' in fname
                        ch_italic = ('Italic' in fname or 'italic' in fname
                                     or 'Oblique' in fname or 'oblique' in fname)
                    else:
                        # LTAnno (space chars) — inherit dominant style
                        ch_bold = dom_bold
                        ch_italic = dom_italic

                    # Only tag spans that differ from the dominant style
                    want_em = ch_italic and not dom_italic
                    want_strong = ch_bold and not dom_bold

                    # Close tags that are no longer needed (reverse order of opening)
                    if in_sup and not is_sup:
                        text_parts.append('</sup>')
                        in_sup = False
                    if in_em and not want_em:
                        text_parts.append('</em>')
                        in_em = False
                    if in_strong and not want_strong:
                        text_parts.append('</strong>')
                        in_strong = False

                    # Open tags that are now needed
                    if want_strong and not in_strong:
                        text_parts.append('<strong>')
                        in_strong = True
                    if want_em and not in_em:
                        text_parts.append('<em>')
                        in_em = True
                    if is_sup and not in_sup:
                        text_parts.append('<sup>')
                        in_sup = True

                    text_parts.append(ch)
                # Close any remaining open tags
                if in_sup:
                    text_parts.append('</sup>')
                if in_em:
                    text_parts.append('</em>')
                if in_strong:
                    text_parts.append('</strong>')
                text = ''.join(text_parts)
                # Normalize Unicode whitespace to regular spaces
                text = re.sub(r'[\u00a0\u2000-\u200b\u2028\u2029\u202f\u205f\u3000\t]+', ' ', text)
                text = re.sub(r' +', ' ', text).strip()
                is_bold = 'Bold' in dominant_font or 'bold' in dominant_font
                is_italic = ('Italic' in dominant_font or 'italic' in dominant_font
                             or 'Oblique' in dominant_font or 'oblique' in dominant_font)
                center = (line.x0 + line.x1) / 2
                is_centered = abs(center - page_width / 2) < 40

                page_lines.append({
                    'text': text,
                    'font': dominant_font,
                    'size': dominant_size,
                    'bold': is_bold,
                    'italic': is_italic,
                    'centered': is_centered,
                    'y0': line.y0,
                    'x0': line.x0,
                    'x1': line.x1,
                    'page': pg,
                })

        # Sort lines top-to-bottom (high y0 = top of page)
        page_lines.sort(key=lambda l: -l['y0'])

        # Group consecutive lines into paragraphs by font properties
        current_group = []
        for li, ln in enumerate(page_lines):
            if not current_group:
                current_group.append(ln)
                continue

            prev = current_group[-1]

            # Check if font properties match (same paragraph)
            same_size = abs(ln['size'] - prev['size']) <= 0.5
            same_bold = ln['bold'] == prev['bold']
            same_italic = ln['italic'] == prev['italic']
            same_align = ln['centered'] == prev['centered']

            # Check vertical gap (paragraph break if gap > 1.5× font size)
            vert_gap = prev['y0'] - ln['y0']  # positive = ln is below prev
            line_height = max(prev['size'], ln['size'])
            big_gap = vert_gap > line_height * 1.8

            # For heading-sized bold text, ignore centering differences
            # (decorative chapter titles often mix centered/left-aligned lines)
            is_heading_line = ln['bold'] and ln['size'] > 15
            align_ok = same_align or is_heading_line

            # Force paragraph break at footnote zone boundary
            # pdfminer y-axis: y0=0 is bottom, page_height is top
            # If previous line is in body zone and current crosses into footnote zone,
            # break even if font properties match
            footnote_threshold = page_height * 0.15
            crossing_into_footnotes = (
                prev['y0'] >= footnote_threshold and
                ln['y0'] < footnote_threshold
            )

            if same_size and same_bold and same_italic and align_ok and not big_gap and not crossing_into_footnotes:
                current_group.append(ln)
            else:
                # Flush current group as a paragraph
                _flush_line_group(current_group, all_paras)
                current_group = [ln]

        if current_group:
            _flush_line_group(current_group, all_paras)

        if pg % 50 == 0:
            log(f"  Extracted {pg}/{total_pages}+ pages...")

    # Log font summary
    font_dist = Counter()
    for p in all_paras:
        if p.get('is_page_marker'):
            continue
        key = (p['font_size'], p['is_bold'], p['is_italic'])
        font_dist[key] += 1

    # Detect body font: use character-count weighting (not paragraph count).
    # Running headers / page numbers produce many short paragraphs that can
    # outnumber body text paragraphs despite carrying far fewer total characters.
    # Character weighting ensures the true body font wins.  This mirrors the
    # PyMuPDF path (see _extract_html_with_pymupdf_columns).
    size_char_counts = Counter()
    for p in all_paras:
        if p.get('is_page_marker'):
            continue
        sz = p['font_size']
        if sz > 0:
            size_char_counts[sz] += p.get('char_count', len(p.get('text', '')))
    body_size = size_char_counts.most_common(1)[0][0] if size_char_counts else 12.0

    # Find the most common style at the detected body size for logging
    body_style_dist = Counter()
    for p in all_paras:
        if p.get('is_page_marker'):
            continue
        if abs(p['font_size'] - body_size) <= 0.5:
            key = (p['is_bold'], p['is_italic'])
            body_style_dist[key] += 1
    if body_style_dist:
        (body_bold, body_italic), body_count = body_style_dist.most_common(1)[0]
    else:
        body_bold, body_italic, body_count = False, False, 0

    log(f"  pdfminer extraction: {total_pages} pages, {len(all_paras)} paragraphs")
    log(f"  Body font detected: {body_size}pt {'Bold' if body_bold else ''}{'Italic' if body_italic else 'Regular'} ({body_count} paragraphs, char-weighted)")
    log(f"  Font distribution:")
    for (sz, bld, itl), cnt in font_dist.most_common(10):
        style = 'Bold' if bld else ('Italic' if itl else 'Regular')
        log(f"    {sz}pt {style}: {cnt} paragraphs")

    # Font inventory for data collection
    global _last_font_inventory
    _last_font_inventory = sorted(fonts_seen)
    log(f"  Fonts found: {len(_last_font_inventory)} unique "
        f"({', '.join(_last_font_inventory[:5])}{'...' if len(_last_font_inventory) > 5 else ''})")
    risky_fonts = [f for f in fonts_seen
                   if any(r in f.lower() for r in
                          ['symbol', 'zapfdingbats', 'cid', 'identity-h',
                           'identity-v', 'wingdings'])]
    if risky_fonts:
        log(f"  WARNING: Risky fonts detected: {', '.join(risky_fonts)}")

    # ── Footnote detection: classify small-font paragraphs at page bottoms ──
    # Uses the same dual-threshold approach as the PyMuPDF column path:
    # - Hard threshold: y0 in bottom 15% of page → always footnote (if small font)
    # - Soft threshold: y0 in bottom 40% AND font < 85% of body → likely footnote
    # pdfminer y-axis: y0=0 is page bottom, y0=page_height is page top.
    footnote_count = 0
    for p in all_paras:
        if p.get('is_page_marker'):
            continue

        pg = p.get('page_number', 0)
        ph = page_heights.get(pg, 0)
        if ph <= 0:
            continue

        y0_min = p.get('y0_min')
        if y0_min is None:
            continue

        font_sz = p.get('font_size', 0)
        if font_sz <= 0 or body_size <= 0:
            continue

        # Relative vertical position (0 = page bottom, 1 = page top)
        y_ratio = y0_min / ph

        # Font size ratio relative to body
        size_ratio = font_sz / body_size

        is_footnote = False

        # Hard threshold: bottom 15% of page AND font is smaller than body
        if y_ratio <= 0.15 and size_ratio < 0.95:
            is_footnote = True

        # Soft threshold: bottom 40% of page AND font notably smaller (< 85% body)
        elif y_ratio <= 0.40 and size_ratio < 0.85:
            is_footnote = True

        if is_footnote:
            p['is_footnote'] = True
            footnote_count += 1

    if footnote_count:
        log(f"  Footnote detection: {footnote_count} paragraphs classified as footnotes "
            f"(font < {body_size:.1f}pt at page bottom)")

    return all_paras, body_size


# ── Preposition set for camelCase splitting (used by _fix_word_merges_html) ──
_PREPOSITIONS = frozenset({
    'the', 'a', 'an', 'of', 'in', 'to', 'for', 'on', 'at',
    'by', 'is', 'as', 'and', 'but', 'from', 'with', 'that',
    'this', 'was', 'had', 'has', 'not', 'its', 'his', 'her',
    'are', 'were', 'been', 'be', 'or', 'nor', 'so', 'yet',
})

# Known merge patterns
_MERGE_FIXES = {
    'ofthe': 'of the', 'inthe': 'in the', 'tothe': 'to the',
    'forthe': 'for the', 'onthe': 'on the', 'atthe': 'at the',
    'bythe': 'by the', 'isthe': 'is the', 'andthe': 'and the',
    'fromthe': 'from the', 'withthe': 'with the', 'asthe': 'as the',
    'butthe': 'but the', 'ofthis': 'of this', 'inthis': 'in this',
    'oftheir': 'of their', 'inthat': 'in that', 'tothis': 'to this',
    'wasthe': 'was the', 'hasthe': 'has the', 'hadthe': 'had the',
    'notthe': 'not the', 'orthe': 'or the', 'arethe': 'are the',
}

_MERGE_PATTERNS = [
    (re.compile(r'\b' + pat + r'\b', re.IGNORECASE), repl)
    for pat, repl in _MERGE_FIXES.items()
]

_CAMEL_RE = re.compile(r'(?<=[a-z])(?=[A-Z][a-z])')


def _fix_word_merges_html(para_dicts, log):
    """Fix common word-merge artifacts in HTML extraction output."""
    total_fixes = 0
    for p in para_dicts:
        if p.get('is_page_marker') or not p.get('text'):
            continue
        text = p['text']

        # Apply known merge patterns
        for pattern, replacement in _MERGE_PATTERNS:
            text, n = pattern.subn(replacement, text)
            total_fixes += n

        # CamelCase splitting: only when lowercase prefix is a common word
        segments = re.split(r'(<[^>]+>)', text)
        for si, seg in enumerate(segments):
            if seg.startswith('<'):
                continue

            def _split_camel(m):
                nonlocal total_fixes
                start = m.start()
                # Walk back to find word start in this segment
                word_start = start
                while word_start > 0 and segments[si][word_start - 1].isalpha():
                    word_start -= 1
                prefix = segments[si][word_start:start + 1].lower()
                if prefix in _PREPOSITIONS:
                    total_fixes += 1
                    return ' '
                return m.group()

            segments[si] = _CAMEL_RE.sub(_split_camel, seg)
        text = ''.join(segments)

        p['text'] = text

    if total_fixes:
        log(f"  Fixed {total_fixes} word merges in HTML extraction output")
    return total_fixes


def _flush_line_group(lines, all_paras):
    """Helper: convert a group of lines with same font properties into a paragraph dict."""
    if not lines:
        return
    # Join lines, handling hyphenated word breaks: "chal-" + "lenge" → "challenge"
    parts = []
    for k, ln in enumerate(lines):
        t = ln['text']
        if parts and parts[-1].endswith('-') and t and t[0].islower():
            # Hyphenated break: remove trailing hyphen and join without space
            parts[-1] = parts[-1][:-1]
            parts.append(t)
        else:
            parts.append(t)
    text = re.sub(r'[\u00a0\u2000-\u200b\u2028\u2029\u202f\u205f\u3000\t]+', ' ',
                  ' '.join(parts))
    text = re.sub(r' +', ' ', text).strip()
    first = lines[0]
    all_paras.append({
        'text': text,
        'font_size': first['size'],
        'is_bold': first['bold'],
        'is_italic': first['italic'],
        'is_centered': first['centered'],
        'is_all_caps': text == text.upper() and len(text) > 3 and any(c.isalpha() for c in text),
        'page_number': first['page'],
        'line_count': len(lines),
        'char_count': len(text),
        'y0_min': min(ln['y0'] for ln in lines),   # lowest y0 in group (closest to page bottom)
        'y0_max': max(ln['y0'] for ln in lines),   # highest y0 in group
    })


def rejoin_html_fragments(para_dicts, body_size, log):
    """
    Rejoin page-boundary sentence fragments in pdfminer output.

    pdfminer splits text at LTTextBox boundaries, which often fall at page
    edges.  This produces orphaned sentence tails like:
        'two destroyers "assigned an area from Malaysia to South Africa."'
    that belong to the preceding paragraph.

    Merges paragraph B into paragraph A when both share the same font
    properties, are at body size, and the text continuity signals a split.
    """
    joins = 0
    i = 0
    while i < len(para_dicts) - 1:
        a = para_dicts[i]

        # Skip non-text paragraphs
        if a.get('is_page_marker') or not a.get('text', '').strip():
            i += 1
            continue

        # Find next non-page-marker, non-empty paragraph
        # Skip non-body-sized fragments (footnotes, running headers) between
        # body paragraphs. These small-font interruptions at page boundaries
        # should not prevent merging of split body text.
        j = i + 1
        while j < len(para_dicts):
            cand = para_dicts[j]
            if cand.get('is_page_marker') or not cand.get('text', '').strip():
                j += 1
                continue
            cand_size = cand.get('font_size', 0)
            cand_len = len(cand.get('text', '').strip())
            if (abs(cand_size - body_size) > 1.0
                    and cand_len < 80
                    and abs(a.get('font_size', 0) - body_size) <= 1.0):
                # Non-body-sized short text between body paragraphs — likely a
                # footnote number or running header at a page boundary
                j += 1
                continue
            break
        if j >= len(para_dicts):
            break

        b = para_dicts[j]

        a_text = a['text'].rstrip()
        b_text = b['text'].strip()

        if not a_text or not b_text:
            i = j
            continue

        # ── Must be same font properties ──
        same_size = abs(a.get('font_size', 0) - b.get('font_size', 0)) <= 0.5
        same_bold = a.get('is_bold') == b.get('is_bold')
        same_italic = a.get('is_italic') == b.get('is_italic')
        # Allow italic mismatch for short page-boundary fragments where A
        # ends mid-sentence — italic emphasis can span page breaks, causing
        # pdfminer to classify the fragment differently from the parent.
        italic_mismatch_ok = (
            not same_italic
            and same_size and same_bold
            and len(b_text) < 150
            and a.get('page_number') != b.get('page_number')
        )
        same_font = same_size and same_bold and (same_italic or italic_mismatch_ok)
        if not same_font:
            i = j
            continue

        # ── Must be body-sized text (not headings) ──
        if abs(a.get('font_size', 0) - body_size) > 1.0:
            i = j
            continue

        # ── Skip if B looks like a heading ──
        if (b.get('is_all_caps') and len(b_text) < 100
                and not b_text.endswith('.')):
            i = j
            continue

        # ── Detect whether A ends mid-sentence ──
        terminal = {'.', '!', '?', '\u201d', '\u2019', '"', "'", '\u2018', ')'}
        a_last = a_text[-1]
        a_ends_mid = a_last not in terminal

        # Also treat trailing prepositions/articles as mid-sentence
        trailing_words = {'and', 'or', 'the', 'a', 'an', 'of', 'in', 'to',
                          'for', 'with', 'at', 'by', 'from', 'on', 'as', 'but',
                          'that', 'this', 'its', 'his', 'her', 'their', 'was',
                          'were', 'had', 'has', 'not', 'be', 'is', 'are'}
        a_last_word = a_text.split()[-1].lower().rstrip('.,;:') if a_text.split() else ''
        if a_last_word in trailing_words:
            a_ends_mid = True

        # ── Detect whether B looks like a continuation ──
        b_starts_lower = b_text[0].islower()
        b_starts_continuation = b_text[0] in '.,;:)\u201d\u2019"\']\u2014\u2013'
        b_is_short = len(b_text) < 150

        should_merge = False

        # Case 1: A ends mid-sentence, B continues
        if a_ends_mid and (b_starts_lower or b_starts_continuation):
            should_merge = True

        # Case 2: A ends mid-sentence and B is short (orphaned tail)
        if a_ends_mid and b_is_short:
            should_merge = True

        # Case 3: B is very short (< 80 chars) and starts lowercase or
        # with continuation punctuation — almost certainly a fragment
        if len(b_text) < 80 and (b_starts_lower or b_starts_continuation):
            should_merge = True

        # ── Safety checks ──
        # Don't merge if result would be absurdly long
        if len(a_text) + len(b_text) > 5000:
            should_merge = False

        # Don't merge if B starts uppercase, is > 200 chars, and there's a
        # page boundary between A and B — that's a real new paragraph
        if (not b_starts_lower and not b_starts_continuation
                and len(b_text) > 200
                and a.get('page_number') != b.get('page_number')):
            should_merge = False

        if should_merge:
            separator = ' ' if not a_text.endswith('-') else ''
            if a_text.endswith('-'):
                # Hyphenated word break — join without hyphen
                a_text = a_text[:-1]
            a['text'] = a_text + separator + b_text
            a['char_count'] = len(a['text'])
            a['line_count'] = a.get('line_count', 1) + b.get('line_count', 1)
            # Clear B so it's skipped later
            b['text'] = ''
            b['char_count'] = 0
            joins += 1
            # Don't advance i — check if more fragments follow
        else:
            i = j

    log(f"  Fragment rejoin: {joins} paragraphs merged")
    return para_dicts


def format_paragraphs_as_html(para_dicts, body_size, bookmarks, log, title='Untitled',
                              skip_footnotes=False):
    """
    Convert paragraph dicts with font metadata into semantic HTML.
    Uses font size clusters + bookmark cross-reference for heading levels.
    Skips TOC page content (Calibre builds its own TOC from headings).
    Detects and excludes running headers (repeated bold text across pages).
    """
    from collections import Counter

    import unicodedata
    def _strip_accents(text):
        """Remove accents and normalize quotes for matching: Félix → Felix, ' → '."""
        text = ''.join(c for c in unicodedata.normalize('NFD', text)
                       if unicodedata.category(c) != 'Mn')
        # Normalize smart quotes/dashes to ASCII
        text = text.replace('\u2019', "'").replace('\u2018', "'")
        text = text.replace('\u201c', '"').replace('\u201d', '"')
        text = text.replace('\u2014', '--').replace('\u2013', '-')
        return text

    # Build bookmark title → level mapping for cross-reference
    bm_map = {}
    bm_page_level = {}  # page_number → (level, title) for page-based fallback
    bm_page_title = {}  # page_number → corrected title (for OCR-fixed headings)
    bm_front_matter = set()  # normalized titles of front-matter bookmarks
    bm_back_matter = set()   # normalized titles of back-matter bookmarks
    if bookmarks:
        for bm in bookmarks:
            norm = re.sub(r'\s+', ' ', _strip_accents(bm['title'].strip().lower()))
            bm_map[norm] = bm['level']
            if bm.get('front_matter', False):
                bm_front_matter.add(norm)
            if bm.get('back_matter', False):
                bm_back_matter.add(norm)
            if 'page' in bm:
                bm_page_level[bm['page']] = (bm['level'], bm['title'])
                bm_page_title[bm['page']] = bm['title']

    # Map word-form chapter numbers to digits for bookmark matching
    _word_to_num = {
        'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5',
        'six': '6', 'seven': '7', 'eight': '8', 'nine': '9', 'ten': '10',
        'eleven': '11', 'twelve': '12', 'thirteen': '13', 'fourteen': '14',
        'fifteen': '15', 'sixteen': '16', 'seventeen': '17', 'eighteen': '18',
        'nineteen': '19', 'twenty': '20',
    }

    # Roman numeral → arabic mapping
    _roman_to_num = {
        'i': '1', 'ii': '2', 'iii': '3', 'iv': '4', 'v': '5',
        'vi': '6', 'vii': '7', 'viii': '8', 'ix': '9', 'x': '10',
        'xi': '11', 'xii': '12', 'xiii': '13', 'xiv': '14', 'xv': '15',
        'xvi': '16', 'xvii': '17', 'xviii': '18', 'xix': '19', 'xx': '20',
    }

    def _normalize_chapter_ref(text):
        """Normalize 'Chapter Three MARITAL VOWS' → '3. marital vows' style."""
        norm = text.strip().lower()
        m = re.match(r'^chapter\s+(\w+)\s*[:\s]\s*(.+)$', norm, re.IGNORECASE)
        if m:
            word, subtitle = m.group(1), m.group(2)
            num = _word_to_num.get(word, word)
            return f"{num}. {subtitle.strip()}"
        return None

    def _normalize_part_ref(text):
        """Normalize 'Part I' → 'part one', 'Part 1' → 'part one' for matching."""
        norm = text.strip().lower()
        m = re.match(r'^part\s+(\w+)$', norm)
        if m:
            val = m.group(1)
            # Roman → word: "Part I" → "part one"
            if val in _roman_to_num:
                arabic = _roman_to_num[val]
                for word, num in _word_to_num.items():
                    if num == arabic:
                        return f"part {word}"
            # Arabic → word: "Part 1" → "part one"
            for word, num in _word_to_num.items():
                if num == val:
                    return f"part {word}"
            # Word → try as-is
        return None

    # Pre-compute reverse map: bookmark titles with leading numbers stripped
    bm_map_stripped = {}  # "the state reaction" → level (from "3 the state reaction")
    for bm_norm, level in bm_map.items():
        bm_stripped = re.sub(r'^\d+[\.\):]?\s*', '', bm_norm).strip()
        if bm_stripped and bm_stripped != bm_norm:
            bm_map_stripped[bm_stripped] = level

    def _match_bookmark(text):
        """Check if paragraph text matches a bookmark title. Returns level or None."""
        text = re.sub(r'\s+', ' ', text).strip()
        norm = re.sub(r'\s+', ' ', _strip_accents(text.strip().lower()))
        if norm in bm_map:
            return bm_map[norm]
        # Try without leading numbers on text: "1. A Kind of Super Man" → "a kind of super man"
        stripped = re.sub(r'^\d+[\.\):]?\s*', '', norm).strip()
        if stripped and stripped in bm_map:
            return bm_map[stripped]
        # Try matching text against bookmarks with their leading numbers stripped:
        # text "The State Reaction" → matches bookmark "3 The State Reaction"
        if norm in bm_map_stripped:
            return bm_map_stripped[norm]
        # Try "Part I" → "part one" normalization
        part_norm = _normalize_part_ref(text)
        if part_norm and part_norm in bm_map:
            return bm_map[part_norm]
        # Try "Chapter Three SUBTITLE" → "3. subtitle" matching
        chapter_norm = _normalize_chapter_ref(text)
        if chapter_norm:
            # Normalize smart quotes/accents to match bm_map keys
            chapter_norm = _strip_accents(chapter_norm)
            if chapter_norm in bm_map:
                return bm_map[chapter_norm]
            # Also try just the subtitle portion against bookmark subtitles
            # Use space-collapsed comparison to handle "superman" vs "super man"
            ch_stripped = re.sub(r'^\d+[\.\):]?\s*', '', chapter_norm).strip()
            ch_collapsed = re.sub(r'\s+', '', ch_stripped)
            for bm_norm, level in bm_map.items():
                bm_stripped = re.sub(r'^\d+[\.\):]?\s*', '', bm_norm).strip()
                if ch_stripped and bm_stripped:
                    if ch_stripped == bm_stripped:
                        return level
                    # Space-collapsed match: "superman" == "super man"
                    if ch_collapsed == re.sub(r'\s+', '', bm_stripped):
                        return level
        # Try "Chapter II" / "Chapter 2" / "Chapter Two" matching by normalizing
        # to a common number form and checking if any bookmark starts with the same.
        _ch_match = re.match(r'^chapter\s+(\w+)', norm, re.IGNORECASE)
        if _ch_match:
            ch_val = _ch_match.group(1)
            # Normalize to Arabic digit
            ch_num = _word_to_num.get(ch_val, _roman_to_num.get(ch_val, ch_val))
            if ch_num.isdigit():
                for bm_norm, level in bm_map.items():
                    _bm_ch = re.match(r'^chapter\s+(\w+)', bm_norm)
                    if _bm_ch:
                        bm_val = _bm_ch.group(1)
                        bm_num = _word_to_num.get(bm_val, _roman_to_num.get(bm_val, bm_val))
                        if bm_num == ch_num:
                            return level
        # Try word overlap — only for SHORT text (headings, not body paragraphs)
        # Require high overlap in BOTH directions to prevent sub-section headings
        # like "How Civil Society Galvanizes the State Reaction" from matching
        # the chapter bookmark "3 The State Reaction" via shared stopwords.
        _stopwords = {'the', 'a', 'an', 'and', 'or', 'of', 'in', 'on', 'to',
                      'for', 'with', 'at', 'by', 'from', 'as', 'is', 'its'}
        def _clean_words(s):
            """Split into words and strip trailing punctuation for matching."""
            return set(re.sub(r'[^\w\s]', '', w) for w in s.split() if re.sub(r'[^\w\s]', '', w))
        if len(text.strip()) < 120:
            text_words = _clean_words(norm)
            for bm_norm, level in bm_map.items():
                bm_words = _clean_words(bm_norm)
                if len(bm_words) < 3:
                    continue
                overlap = text_words & bm_words
                # Must match 80%+ of bookmark words
                if len(overlap) < len(bm_words) * 0.8:
                    continue
                # The non-stopword (content) words of the bookmark must mostly
                # appear in the text — prevents matching on shared stopwords alone
                bm_content = bm_words - _stopwords
                if bm_content and len(overlap & bm_content) < len(bm_content) * 0.8:
                    continue
                # Text shouldn't be much longer than bookmark (sub-sections add words)
                if len(text_words) > len(bm_words) * 1.8:
                    continue
                return level
        return None

    # ── Back-matter detection ──────────────────────────────────
    # Identify back-matter start page (Notes, Bibliography, etc.) so that
    # chapter headings repeated inside Notes don't create duplicate TOC entries.
    back_matter_labels = {'notes', 'bibliography', 'index', 'endnotes', 'references',
                          'works cited', 'further reading', 'glossary', 'appendix'}
    back_matter_start_page = None
    back_matter_bm_pages = set()  # pages where back-matter L1 bookmarks land
    if bookmarks:
        for bm in bookmarks:
            if bm['title'].strip().lower() in back_matter_labels and bm.get('page'):
                if back_matter_start_page is None or bm['page'] < back_matter_start_page:
                    back_matter_start_page = bm['page']
                back_matter_bm_pages.add(bm['page'])
    if back_matter_start_page:
        log(f"  Back matter detected starting at page {back_matter_start_page}")

    # ── Content-based back-matter detection (no bookmarks) ─────
    # When bookmarks don't provide a back_matter_start_page, scan paragraphs
    # for back-matter section headings (bold/larger text matching keywords)
    # in the last 40% of the book.
    if back_matter_start_page is None:
        total_pages_est = max(
            (p.get('page_number', 0) for p in para_dicts if p.get('is_page_marker')),
            default=100
        )
        for p in para_dicts:
            if p.get('is_page_marker'):
                continue
            text_check = re.sub(r'<[^>]+>', '', p.get('text', '')).strip().lower()
            sz_check = p.get('font_size', 0)
            if (text_check in back_matter_labels
                    and (p.get('is_bold') or sz_check > body_size)
                    and p.get('page_number', 0) > 0):
                page_pct = p['page_number'] / max(total_pages_est, 1)
                if page_pct > 0.6:
                    back_matter_start_page = p['page_number']
                    log(f"  Back matter detected from content at page "
                        f"{back_matter_start_page} ('{text_check}', "
                        f"{page_pct:.0%} through book)")
                    break

    # ── FIX 1: Font-cluster heading detection ──────────────────
    # Find distinct heading sizes from paragraphs that look like headings:
    # larger than body, AND either bold or (centered + short text).
    # This handles both bold-heading publishers and italic/centered-heading publishers.
    heading_sizes = Counter()
    for p in para_dicts:
        if p.get('is_page_marker'):
            continue
        sz = p.get('font_size', 0)
        bold = p.get('is_bold', False)
        centered = p.get('is_centered', False)
        char_count = p.get('char_count', len(p.get('text', '')))
        if sz > body_size + 0.5:
            if bold or (centered and char_count < 120):
                heading_sizes[sz] += 1

    # Sort heading sizes largest → smallest
    distinct_sizes = sorted(heading_sizes.keys(), reverse=True)

    # Assign: largest → h1 candidates, smaller sizes → h3 candidates
    h1_size = distinct_sizes[0] if len(distinct_sizes) >= 1 else None
    # If there are 3+ sizes, middle sizes also get h3
    mid_sizes = set(distinct_sizes[1:]) if len(distinct_sizes) >= 2 else set()

    if distinct_sizes:
        log(f"  Heading font clusters (> body {body_size}pt, bold or centered+short):")
        for sz in distinct_sizes:
            role = "→ h1 candidates" if sz == h1_size else "→ h3 candidates"
            log(f"    {sz}pt: {heading_sizes[sz]} paragraphs {role}")

    # ── FIX 3: Running header detection ────────────────────────
    # Count frequency of short text strings across pages to detect running headers.
    # Running headers can be bold OR non-bold (e.g. "Introduction" repeated on every
    # page of a chapter). Count by distinct pages to avoid false positives from
    # paragraphs that just happen to repeat on the same page.
    header_page_counts = {}  # text_lower → set of page numbers
    for p in para_dicts:
        if p.get('is_page_marker'):
            continue
        text = p.get('text', '').strip()
        if text and len(text) < 80:
            key = text.lower()
            page_num = p.get('page_number', 0)
            if key not in header_page_counts:
                header_page_counts[key] = set()
            header_page_counts[key].add(page_num)
            # Also count a page-number-stripped version so that
            # "238 INDEX OF MODERN AUTHORS" and "242 INDEX OF MODERN AUTHORS"
            # both contribute to a single "index of modern authors" bucket.
            # Use [\dOoIl] to catch common OCR errors (O→0, l→1, etc.).
            stripped = re.sub(r'^[\dOoIl]+\s+', '', key).strip()
            stripped = re.sub(r'\s+[\dOoIl]+$', '', stripped).strip()
            if stripped and stripped != key and len(stripped) > 3:
                if stripped not in header_page_counts:
                    header_page_counts[stripped] = set()
                header_page_counts[stripped].add(page_num)

    running_headers = set()
    for text_lower, pages in header_page_counts.items():
        if len(pages) >= 5:
            running_headers.add(text_lower)

    # Track which running headers have been seen (first occurrence kept as heading)
    running_header_seen = set()

    if running_headers:
        log(f"  Running headers detected ({len(running_headers)} patterns, first kept, rest skipped):")
        for rh in sorted(running_headers):
            log(f"    '{rh[:60]}' (appears on {len(header_page_counts[rh])} pages)")

    # ── FIX 2: Detect TOC page region ─────────────────────────
    # Find the TOC heading and mark the page range to skip
    toc_start_page = None
    toc_end_page = None
    toc_heading_pattern = re.compile(
        r'^(contents|table of contents)$', re.IGNORECASE
    )

    for i, p in enumerate(para_dicts):
        if p.get('is_page_marker'):
            continue
        text = p.get('text', '').strip()
        if toc_heading_pattern.match(text):
            toc_start_page = p.get('page_number')
            # Find end: next heading on a DIFFERENT page that matches a bookmark
            for j in range(i + 1, len(para_dicts)):
                pj = para_dicts[j]
                if pj.get('is_page_marker'):
                    continue
                pj_text = pj.get('text', '').strip()
                pj_page = pj.get('page_number', toc_start_page)
                if pj_page != toc_start_page and _match_bookmark(pj_text) is not None:
                    toc_end_page = pj_page
                    break
                # Also stop at a large bold heading on a different page
                if (pj_page != toc_start_page and pj.get('is_bold')
                        and pj.get('font_size', 0) > body_size + 2):
                    toc_end_page = pj_page
                    break
            break  # Only process the first TOC heading

    toc_skip_pages = set()
    if toc_start_page:
        # Always scan pages after the TOC heading for TOC-like content.
        # The bookmark-based toc_end_page can fire too early when TOC entries
        # themselves match bookmark titles (they ARE the same titles with page numbers).
        # Limit TOC scan to the first 15% of document pages (safety guard —
        # a Contents page is always near the front of a book).
        total_pages = max(p.get('page_number', 0) for p in para_dicts if p.get('is_page_marker')) or 100
        max_toc_page = max(toc_start_page + 8, int(total_pages * 0.15))
        end = toc_start_page + 1  # at minimum include the heading page
        for scan_page in range(toc_start_page + 1, min(toc_start_page + 8, max_toc_page + 1)):
            page_paras = [p for p in para_dicts
                          if p.get('page_number') == scan_page
                          and not p.get('is_page_marker')
                          and p.get('text', '').strip()]
            if not page_paras:
                break  # empty page = end of TOC
            # Count paragraphs that look like TOC entries:
            # short text ending with digits (page numbers), or short title-case lines
            toc_like = sum(1 for p in page_paras
                           if len(p['text'].strip()) < 120
                           and re.search(r'\d+\s*$', p['text'].strip()))
            # Also count entries matching bookmark titles (TOC without page numbers)
            bm_matches = (sum(1 for p in page_paras
                              if _match_bookmark(p['text'].strip()) is not None)
                          if bookmarks else 0)
            if (toc_like >= len(page_paras) * 0.3 and toc_like >= 2) or bm_matches >= 2:
                end = scan_page + 1  # include this page
            else:
                break  # no longer TOC-like
        # Use bookmark-based end as a fallback floor (don't shrink below it)
        if toc_end_page and toc_end_page > end:
            end = toc_end_page
        toc_skip_pages = set(range(toc_start_page, end))
        log(f"  TOC page(s) detected: pages {toc_start_page}-{end - 1} (content skipped)")

    # ── Classify and emit HTML ─────────────────────────────────
    h1_count = 0
    h2_count = 0
    h3_count = 0
    bq_count = 0
    p_count = 0
    attr_count = 0
    toc_skipped = 0
    running_header_skipped = 0

    # Pre-scan: detect running headers from column extractor's top_wide candidates.
    # Normalize text (strip verse ranges, leading numbers), group by normalized form,
    # and mark as running headers if the same form appears on 3+ distinct pages.
    _rh_strip_indices = set()  # indices of para_dicts to skip as running headers
    _rh_candidates = {}  # normalized → [(index, page_number), ...]
    for idx, p in enumerate(para_dicts):
        if not p.get('_is_running_header_candidate'):
            continue
        text = p.get('text', '').strip()
        if not text:
            continue
        # Normalize: strip leading "5. " etc, trailing verse refs "25:1-32:32"
        norm = re.sub(r'^\d+[.\s]+', '', text)
        norm = re.sub(r'[\d:,\-\u2013]+\s*$', '', norm)
        norm = norm.strip().lower()
        if len(norm) < 3:
            continue
        if norm not in _rh_candidates:
            _rh_candidates[norm] = []
        _rh_candidates[norm].append((idx, p.get('page_number', 0)))
    # Mark repeated candidates for stripping (keep first occurrence)
    for norm, occurrences in _rh_candidates.items():
        distinct_pages = set(pg for _, pg in occurrences)
        if len(distinct_pages) >= 3:
            # Skip all after the first occurrence
            for idx, _ in occurrences[1:]:
                _rh_strip_indices.add(idx)

    if _rh_strip_indices:
        log(f"  Column-path running headers: {len(_rh_strip_indices)} repeats to strip "
            f"({len(_rh_candidates)} normalized patterns)")

    # Clean up _is_running_header_candidate flags
    for p in para_dicts:
        p.pop('_is_running_header_candidate', None)

    html_parts = []
    html_parts.append(f'''<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>{title}</title>
<style>
body {{ font-family: serif; line-height: 1.6; }}
p {{ text-indent: 1.5em; margin: 0; padding: 0; }}
h1 {{ font-size: 1.8em; text-align: center; page-break-before: always; margin-top: 2em; }}
h2 {{ font-size: 1.4em; text-align: center; margin-top: 1.5em; }}
h3 {{ font-size: 1.2em; margin-top: 2em; }}
blockquote {{ margin: 1em 2em; }}
blockquote p {{ text-indent: 0; }}
.attribution {{ font-style: italic; text-align: right; margin-bottom: 1.5em; }}
.section-break {{ font-weight: bold; font-size: 1.1em; margin-top: 2em; }}
hr.footnote-separator {{ border: none; border-top: 1px solid #999; width: 30%; margin: 1.5em 0 0.5em 0; }}
.footnotes {{ font-size: 0.85em; line-height: 1.4; color: #555; }}
.footnotes p {{ text-indent: 0; margin: 0.3em 0; }}
</style>
</head><body>
''')

    # Pre-pass: for each bookmark page, find the paragraph with the largest
    # heading-like font. This allows page-based bookmark matching to tag the
    # right paragraph (e.g. the chapter subtitle, not the chapter number).
    bm_page_best_para = {}  # page → index of best heading candidate
    for idx, p in enumerate(para_dicts):
        if p.get('is_page_marker'):
            continue
        pg = p.get('page_number', 0)
        if pg not in bm_page_level:
            continue
        sz = p.get('font_size', 0)
        bl = p.get('is_bold', False)
        ct = p.get('is_centered', False)
        cc = p.get('char_count', len(p.get('text', '')))
        is_heading_like = bl or (ct and cc < 120)
        if sz > body_size and is_heading_like:
            prev_best = bm_page_best_para.get(pg)
            if prev_best is None:
                bm_page_best_para[pg] = idx
            else:
                # Prefer larger font; if tied, prefer the one with more text
                prev_sz = para_dicts[prev_best].get('font_size', 0)
                if sz > prev_sz or (sz == prev_sz and cc > para_dicts[prev_best].get('char_count', 0)):
                    bm_page_best_para[pg] = idx

    in_blockquote = False
    in_footnotes = False  # tracks whether we're inside a <div class="footnotes"> block
    footnote_rendered = 0  # count of footnote paragraphs rendered
    prev_was_heading = False
    after_heading = False
    current_page = 0
    in_toc_region = False
    last_heading_text = ''  # for duplicate consecutive heading detection
    heading_seen_pages = {}  # text_lower → first page where it was tagged as heading
    heading_dedup_skipped = 0

    for i, p in enumerate(para_dicts):
        text = p.get('text', '').strip()

        # Track current page
        if p.get('is_page_marker'):
            # Close footnotes block at page boundary
            if in_footnotes:
                html_parts.append('</div>\n')
                in_footnotes = False
            current_page = p['page_number']
            # Still emit page anchors even in TOC pages
            html_parts.append(f'<a id="page_{current_page}"></a>\n')
            # Check if we're entering/leaving TOC region
            in_toc_region = current_page in toc_skip_pages
            continue
        if not text:
            continue

        # Handle footnote paragraphs
        if p.get('is_footnote'):
            if skip_footnotes:
                continue  # Drop footnote paragraphs entirely
            # Close blockquote if transitioning into footnotes
            if in_blockquote:
                html_parts.append('</blockquote>\n')
                in_blockquote = False
            if not in_footnotes:
                html_parts.append('<hr class="footnote-separator">\n')
                html_parts.append('<div class="footnotes">\n')
                in_footnotes = True
            escaped_text = _html_escape(text)
            html_parts.append(f'<p>{escaped_text}</p>\n')
            footnote_rendered += 1
            after_heading = False
            continue

        # Close footnotes block when transitioning back to body text
        if in_footnotes:
            html_parts.append('</div>\n')
            in_footnotes = False

        # Skip running header candidates identified by pre-scan
        if i in _rh_strip_indices:
            running_header_skipped += 1
            continue

        size = p.get('font_size', body_size)

        # Strip standalone page numbers (1-3 digit paragraphs at body/small font size)
        # Don't strip decorative chapter numbers (large heading fonts like 42pt)
        if re.match(r'^\d{1,3}$', text) and size <= body_size + 1:
            continue

        # Skip TOC page content (but keep the "Contents" heading itself as h1)
        if in_toc_region:
            # Allow the "CONTENTS" heading itself through
            if not toc_heading_pattern.match(text):
                toc_skipped += 1
                continue

        bold = p.get('is_bold', False)
        italic = p.get('is_italic', False)
        centered = p.get('is_centered', False)
        all_caps = p.get('is_all_caps', False)
        char_count = p.get('char_count', len(text))

        # FIX 3: Skip running headers (text appearing on 5+ distinct pages)
        # Keep the FIRST occurrence as the actual heading; skip all repeats.
        # Also check a page-number-stripped version for headers like "238 INDEX...".
        text_lower = text.lower()
        text_stripped = re.sub(r'^[\dOoIl]+\s+', '', text_lower).strip()
        text_stripped = re.sub(r'\s+[\dOoIl]+$', '', text_stripped).strip()
        rh_key = None
        # Also strip leading chapter number: "5. The Turning Point" → "the turning point"
        text_no_chapnum = re.sub(r'^\d+[\.\):]?\s*', '', text_lower).strip()
        if text_lower in running_headers:
            rh_key = text_lower
        elif text_stripped in running_headers and text_stripped != text_lower:
            rh_key = text_stripped
        elif text_no_chapnum in running_headers and text_no_chapnum != text_lower:
            rh_key = text_no_chapnum
        if rh_key is not None:
            if rh_key in running_header_seen:
                running_header_skipped += 1
                continue
            running_header_seen.add(rh_key)

        # A paragraph looks like a heading if it's bold, or centered+short
        looks_like_heading = bold or (centered and char_count < 120)
        display_override_em = False  # set by dedication guard

        # Check bookmark match first (authoritative for heading LEVEL)
        # Only apply bookmark matching to text at or above body size — small text
        # (headers/footers at 7pt etc.) that happens to word-overlap with a
        # bookmark title should not be promoted to a heading.
        bm_level = None
        if size >= body_size - 0.5:
            bm_level = _match_bookmark(text)

        # Page-based bookmark fallback: if text match failed but this paragraph
        # is the best heading candidate on a bookmark page (largest heading font),
        # inherit the bookmark's level. This handles cases where bookmark titles
        # don't match the visible text (e.g. bookmark says "Chapter One" but the
        # PDF shows "1" + "OH, NO!" as separate paragraphs).
        if bm_level is None and current_page in bm_page_best_para:
            if bm_page_best_para[current_page] == i:
                bm_level = bm_page_level[current_page][0]

        # In back matter, demote re-used chapter headings (e.g. "CHAPTER ONE: ..."
        # inside the Notes section) to h3 to avoid duplicate TOC entries.
        # Only the back-matter section's own L1 headings (Notes, Bibliography, Index)
        # keep their bookmark level.
        in_back_matter = (back_matter_start_page is not None
                         and current_page >= back_matter_start_page)
        if in_back_matter and bm_level is not None:
            # Check if this paragraph IS a back-matter section heading (on its bookmark page)
            # Match exact labels AND multi-word variants like "Index of Modern Authors"
            text_norm = text.strip().lower()
            is_section_heading = (
                text_norm in back_matter_labels
                or any(text_norm.startswith(bml + ' ') or text_norm.startswith(bml + ':')
                       for bml in back_matter_labels)
            )
            if not is_section_heading:
                # It's a repeated chapter heading inside Notes/etc — demote to h3
                bm_level = None

        # Determine tag using bookmark level > font cluster > fallback
        tag = 'p'

        if bm_level is not None:
            # Bookmark is authoritative for heading level.
            # All bookmark-matched headings → h1 (flat TOC, no nesting).
            # Front-matter bookmarks stay h2 (grouped under synthetic Front Matter h1).
            bm_norm_check = re.sub(r'\s+', ' ', _strip_accents(text.strip().lower()))
            if bm_norm_check in bm_front_matter:
                tag = 'h2'
            else:
                tag = 'h1'
        elif h1_size is not None and abs(size - h1_size) <= 0.5 and looks_like_heading:
            # Largest heading cluster → h1
            tag = 'h1'
        elif mid_sizes and any(abs(size - ms) <= 0.5 for ms in mid_sizes) and looks_like_heading:
            # Smaller heading clusters → h3
            tag = 'h3'
        elif size > body_size and looks_like_heading:
            # Any other heading-like text larger than body → h3
            tag = 'h3'
        elif bold and char_count < 100 and not text.endswith('.'):
            # Bold short text at body size → h3
            tag = 'h3'

        # ── Pattern-based heading promotion ────────────────────────
        # If font-cluster detection left this as 'p' or 'h3', check
        # if the text matches specific chapter keyword patterns.
        # Only "Chapter X", "Part X", etc. are promoted here — they're
        # unambiguous. Numbered headings ("1. Title") are left to FIX 9
        # and FIX 6 which have better context for disambiguation.
        if tag in ('p', 'h3') and char_count < 120 and not text.endswith('.'):
            text_stripped_tags = re.sub(r'<[^>]+>', '', text).strip()

            # "Chapter X", "Part II", "Book Three", "Volume 1" — specific keywords
            _ch_pat = re.match(
                r'^(chapter|part|book|volume)\s+(\w+)',
                text_stripped_tags, re.IGNORECASE
            )
            # Standalone structural keywords — only if bold or centered
            _kw_pat = (re.match(
                r'^(prologue|epilogue|foreword|afterword|'
                r'conclusion|preface|postscript)\s*$',
                text_stripped_tags, re.IGNORECASE
            ) if (bold or centered) else None)

            is_chapter_pattern = _ch_pat or _kw_pat

            if is_chapter_pattern:
                if not in_back_matter:
                    tag = 'h2'
                else:
                    tag = 'h3'

        # ── Guard: dedication lines misclassified as headings ───
        # Dedications ("To my family...", "For my mother...") appear in the
        # first 10% of a book and should be <p><em>, not headings.
        if tag in ('h1', 'h2') and i < len(para_dicts) * 0.10:
            _dedication_re = re.compile(
                r'^(To my |For my |In memory of |Dedicated to )',
                re.IGNORECASE
            )
            if _dedication_re.match(text):
                tag = 'p'
                display_override_em = True  # will wrap in <em> below

        # ── Guard: prose fragments misclassified as headings ───
        # Real headings don't start with lowercase, don't contain mid-sentence
        # punctuation (commas, semicolons), and are typically short titles.
        if tag in ('h1', 'h2', 'h3'):
            _starts_lower = text and text[0].islower()
            _ends_sentence = bool(re.search(r'[.,;:!?]$', text))
            _has_mid_comma = bool(re.search(r',\s', text[:-10] if len(text) > 10 else ''))
            _has_verb_pattern = bool(re.search(
                r'\b(is|are|was|were|has|have|had|do|does|did|will|would|could|should|may|might|can|shall|that|which|who|use|uses|used|buy|sell|make|take|give)\b',
                text, re.IGNORECASE
            ))
            # Lowercase-start is never a real heading
            if _starts_lower:
                tag = 'p'
            # Long text (>80 chars) with sentence markers → prose
            elif len(text) > 80 and (_ends_sentence or _has_verb_pattern):
                tag = 'p'
            # Medium text (>40 chars) with mid-sentence commas + verbs → prose
            elif len(text) > 40 and _has_mid_comma and _has_verb_pattern:
                tag = 'p'

        # FIX 1+2: Detect epigraphs: italic paragraphs after a heading until
        # the first non-italic paragraph.  Attribution lines start with em-dash.
        is_attribution = False
        if italic and (after_heading or in_blockquote):
            if text.startswith('\u2014') or text.startswith('--') or text.startswith('\u2013'):
                tag = 'attribution'
                is_attribution = True
            else:
                tag = 'blockquote'

        # Deduplicate headings: if the same heading text (or its page-number-
        # stripped form) was already tagged as h1/h2 within the last 50 pages,
        # skip it. This catches running headers and repeated section titles.
        is_heading = tag in ('h1', 'h2', 'h3')
        if is_heading and tag in ('h1', 'h2'):
            # Check both exact text and stripped form for dedup
            dedup_key = text_lower
            if dedup_key not in heading_seen_pages and text_stripped != text_lower:
                if text_stripped in heading_seen_pages:
                    dedup_key = text_stripped
            if dedup_key in heading_seen_pages:
                if abs(current_page - heading_seen_pages[dedup_key]) < 50:
                    tag = 'p'
                    is_heading = False
                    heading_dedup_skipped += 1
                else:
                    # Far enough away — allow (e.g. front-matter vs back-matter)
                    heading_seen_pages[dedup_key] = current_page
            else:
                heading_seen_pages[text_lower] = current_page
                if text_stripped != text_lower and len(text_stripped) > 3:
                    heading_seen_pages[text_stripped] = current_page

        # Duplicate consecutive heading detection: if this heading is nearly
        # identical to the previous heading (decorative title page + body title),
        # demote the second one. Require very high overlap to avoid false positives
        # on headings that just share some common words.
        if is_heading and tag in ('h1', 'h2') and last_heading_text:
            cur_words = set(text_lower.split())
            prev_words = set(last_heading_text.lower().split())
            if cur_words and prev_words and len(cur_words) >= 2:
                overlap = len(cur_words & prev_words) / max(len(cur_words), len(prev_words))
                if overlap >= 0.9:
                    tag = 'p'
                    is_heading = False
                    heading_dedup_skipped += 1

        # Close blockquote if transitioning out
        if in_blockquote and tag not in ('blockquote', 'attribution'):
            html_parts.append('</blockquote>\n')
            in_blockquote = False

        # Use corrected bookmark title for headings (fixes OCR artifacts like "Modem" → "Modern")
        if is_heading and current_page in bm_page_title:
            bm_title = bm_page_title[current_page]
            # Strip leading number prefix from bookmark for comparison
            bm_stripped = re.sub(r'^\d+[\.\):]?\s*', '', bm_title)
            text_stripped_num = re.sub(r'^\d+[\.\):]?\s*', '', text)
            # Match if stripped versions are similar (allowing m↔rn substitution)
            t_norm = text_stripped_num.lower().replace('m', '')
            b_norm = bm_stripped.lower().replace('rn', '').replace('m', '')
            if t_norm == b_norm or bm_stripped.lower().startswith(text_stripped_num.lower()[:20]):
                text = bm_title

        # FIX 3: Wrap italic text in <em> tags
        escaped_text = _html_escape(text)
        # Strip inline <em>/<strong> from heading text — headings are styled separately
        if tag in ('h1', 'h2', 'h3'):
            escaped_text = (escaped_text.replace('<em>', '').replace('</em>', '')
                            .replace('<strong>', '').replace('</strong>', ''))
        display_text = f'<em>{escaped_text}</em>' if (italic or display_override_em) else escaped_text

        # Wrap bold non-heading body paragraphs in <strong>
        if bold and tag == 'p' and not italic and not display_override_em:
            display_text = f'<strong>{escaped_text}</strong>'
        elif bold and italic and tag == 'p':
            display_text = f'<strong><em>{escaped_text}</em></strong>'

        # FIX 6: Suppress h3 in back matter — use styled paragraph instead
        if in_back_matter and tag == 'h3':
            tag = 'p'
            is_heading = False
            display_text = f'<strong>{escaped_text}</strong>'

        if tag == 'blockquote':
            # FIX: Split embedded attribution from blockquote text.
            # Pattern: '"...end of quote." —Attribution text' or similar
            attr_split = re.split(r'(?<=[.?!"\u201d\u2019])\s*(\u2014.+|—.+|--\s.+)$', text)
            if len(attr_split) >= 2 and attr_split[1]:
                # Quote portion stays in blockquote
                quote_text = _html_escape(attr_split[0].strip())
                attr_text = _html_escape(attr_split[1].strip())
                if not in_blockquote:
                    html_parts.append('<blockquote>\n')
                    in_blockquote = True
                    bq_count += 1
                html_parts.append(f'<p><em>{quote_text}</em></p>\n')
                html_parts.append('</blockquote>\n')
                in_blockquote = False
                html_parts.append(f'<p class="attribution"><em>{attr_text}</em></p>\n')
                attr_count += 1
                after_heading = False
            else:
                if not in_blockquote:
                    html_parts.append('<blockquote>\n')
                    in_blockquote = True
                    bq_count += 1
                html_parts.append(f'<p>{display_text}</p>\n')
                after_heading = False
        elif tag == 'attribution':
            if in_blockquote:
                html_parts.append('</blockquote>\n')
                in_blockquote = False
            html_parts.append(f'<p class="attribution">{display_text}</p>\n')
            attr_count += 1
            after_heading = False
        elif is_heading:
            html_parts.append(f'<{tag}>{escaped_text}</{tag}>\n')
            if tag == 'h1':
                h1_count += 1
            elif tag == 'h2':
                h2_count += 1
            else:
                h3_count += 1
            after_heading = True
            last_heading_text = text
        else:
            html_parts.append(f'<p>{display_text}</p>\n')
            p_count += 1
            after_heading = False

        prev_was_heading = is_heading

    # Close any open blockquote
    if in_blockquote:
        html_parts.append('</blockquote>\n')
    # Close any open footnotes block
    if in_footnotes:
        html_parts.append('</div>\n')

    html_parts.append('</body></html>\n')

    log(f"  HTML formatting: {h1_count} h1, {h2_count} h2, {h3_count} h3, "
        f"{bq_count} blockquote, {attr_count} attribution, {p_count} p"
        + (f", {footnote_rendered} footnotes" if footnote_rendered else ""))
    if toc_skipped:
        log(f"  TOC entries skipped: {toc_skipped}")
    if running_header_skipped:
        log(f"  Running headers skipped: {running_header_skipped}")
    if heading_dedup_skipped:
        log(f"  Duplicate headings demoted to <p>: {heading_dedup_skipped}")

    html = ''.join(html_parts)

    # ── Heading hierarchy normalization ────────────────────────────
    # Safety net: if ALL h1/h2 headings are backmatter labels and h3 headings
    # contain chapter patterns, the hierarchy is inverted. Swap them.
    h1_texts = re.findall(r'<h1>(.*?)</h1>', html)
    h2_texts = re.findall(r'<h2>(.*?)</h2>', html)
    h3_texts = re.findall(r'<h3>(.*?)</h3>', html)

    _h1h2_plain = [re.sub(r'<[^>]+>', '', t).strip().lower()
                   for t in h1_texts + h2_texts]
    _h3_plain = [re.sub(r'<[^>]+>', '', t).strip() for t in h3_texts]

    _h1h2_all_backmatter = (
        bool(_h1h2_plain)
        and all(t in back_matter_labels for t in _h1h2_plain)
    )
    _h3_chapter_pattern = re.compile(
        r'^(chapter|part|\d+[\.\)])\s', re.IGNORECASE
    )
    _h3_has_chapters = any(_h3_chapter_pattern.match(t) for t in _h3_plain)

    if _h1h2_all_backmatter and _h3_has_chapters and len(_h3_plain) >= 3:
        log(f"  Heading hierarchy inversion detected: "
            f"{len(h1_texts)} h1 + {len(h2_texts)} h2 are all backmatter, "
            f"but {len(_h3_plain)} h3 headings contain chapter patterns")
        log(f"  Promoting chapter h3 -> h2, demoting backmatter h1/h2 -> h3")

        # Step 1: temporarily mark backmatter h1/h2 as h4 (placeholder)
        for bm_label in back_matter_labels:
            html = re.sub(
                rf'<h1>([^<]*(?:{re.escape(bm_label)})[^<]*)</h1>',
                r'<h4>\1</h4>', html, flags=re.IGNORECASE
            )
            html = re.sub(
                rf'<h2>([^<]*(?:{re.escape(bm_label)})[^<]*)</h2>',
                r'<h4>\1</h4>', html, flags=re.IGNORECASE
            )
        # Step 2: promote h3 chapters -> h2
        html = re.sub(
            r'<h3>((?:Chapter|Part|\d+[\.\)])\s[^<]*)</h3>',
            r'<h2>\1</h2>', html, flags=re.IGNORECASE
        )
        # Step 3: convert placeholder h4 -> h3
        html = html.replace('<h4>', '<h3>').replace('</h4>', '</h3>')

        _h2_after = len(re.findall(r'<h2>', html))
        log(f"  Hierarchy fix complete: now {_h2_after} h2 chapter headings")

    # ── FIX 6: Bookmark whitelist reconciliation ────────────────────
    # When a book has 5+ descriptive bookmarks, they define the authoritative TOC.
    # WHITELIST: only bookmark-matched text can be h1. Everything else → h3.
    # This prevents page numbers, footnote refs, running headers, and other
    # font-size-classified garbage from appearing in the Kindle TOC.
    _generic_bm = re.compile(
        r'^(chapter|part|section)\s+'
        r'([\dIVXLCivxlc]+|one|two|three|four|five|six|seven|eight|nine|ten|'
        r'eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|'
        r'nineteen|twenty)\s*$', re.IGNORECASE)
    _generic_count = sum(1 for bm in bookmarks if _generic_bm.match(bm['title'].strip()))
    _content_bms = [bm for bm in bookmarks
                    if not bm.get('front_matter') and not bm.get('back_matter')]
    _has_descriptive_bms = _generic_count < len(_content_bms) * 0.5 if _content_bms else True
    # Determine if book has a real Part hierarchy: 2+ L1 content bookmarks
    # that aren't single items like "Conclusion" or "About this book".
    _l1_content_bms = [bm for bm in bookmarks
                       if bm.get('level') == 1
                       and not bm.get('front_matter')
                       and not bm.get('back_matter')]
    _has_part_hierarchy = len(_l1_content_bms) >= 2

    if len(bookmarks) >= 5 and _has_descriptive_bms:
        # WHITELIST PASS: every h1/h2 must match a bookmark to stay.
        # Non-bookmark matches → h3 (visible but not in TOC).
        # Heading level respects bookmark structure:
        #   - Part hierarchy: L1 bookmarks → h1, L2 bookmarks → h2
        #   - No Part hierarchy: back-matter L1 → h1, everything else → h2
        wl_demoted = 0
        wl_kept = 0
        def _whitelist_h1h2(m):
            nonlocal wl_demoted, wl_kept
            tag = m.group(1)   # 'h1' or 'h2'
            content = m.group(2)
            text = re.sub(r'<[^>]+>', '', content).strip()
            # Always keep synthetic "Front Matter" heading
            if text.lower() == 'front matter':
                return m.group(0)
            bm_level = _match_bookmark(text)
            if bm_level is not None:
                bm_norm_check = re.sub(r'\s+', ' ', _strip_accents(text.strip().lower()))
                wl_kept += 1
                # Front-matter bookmarks → h2 (grouped under synthetic Front Matter)
                if bm_norm_check in bm_front_matter:
                    return f'<h2>{content}</h2>'
                # Back-matter bookmarks (Notes, Bibliography, Index) → h1
                if bm_norm_check in bm_back_matter:
                    return f'<h1>{content}</h1>'
                # Content bookmarks: respect hierarchy
                if _has_part_hierarchy and bm_level == 1:
                    return f'<h1>{content}</h1>'
                else:
                    return f'<h2>{content}</h2>'
            else:
                wl_demoted += 1
                return f'<h3>{content}</h3>'

        html = re.sub(r'<(h[12])>(.*?)</\1>', _whitelist_h1h2, html)
        if wl_demoted:
            log(f"  FIX 6: Whitelist demoted {wl_demoted} non-bookmark h1/h2 → h3")
        if wl_kept:
            log(f"  FIX 6: Whitelist kept {wl_kept} bookmark-matched headings"
                f" ({'h1+h2 (Part hierarchy)' if _has_part_hierarchy else 'h2 (flat)'})")

        # RESCUE PASS: promote any h3 that matches a non-front-matter bookmark.
        # This catches bookmark-matched headings that font-size classified as h3.
        rescued = 0
        def _rescue_h3(m_h3):
            nonlocal rescued
            h3_text = re.sub(r'<[^>]+>', '', m_h3.group(1)).strip()
            bm_level = _match_bookmark(h3_text)
            if bm_level is not None:
                bm_norm_check = re.sub(r'\s+', ' ', _strip_accents(h3_text.strip().lower()))
                if bm_norm_check in bm_front_matter:
                    return m_h3.group(0)  # front matter stays h3 (FIX 5 handles it)
                # Back-matter → h1
                if bm_norm_check in bm_back_matter:
                    rescued += 1
                    log(f"  FIX 6: Rescued h3→h1 (back-matter bookmark): '{h3_text[:70]}'")
                    return f'<h1>{m_h3.group(1)}</h1>'
                # Content: h1 only if Part hierarchy + L1, else h2
                if _has_part_hierarchy and bm_level == 1:
                    rescued += 1
                    log(f"  FIX 6: Rescued h3→h1 (L1 bookmark): '{h3_text[:70]}'")
                    return f'<h1>{m_h3.group(1)}</h1>'
                else:
                    rescued += 1
                    log(f"  FIX 6: Rescued h3→h2 (bookmark): '{h3_text[:70]}'")
                    return f'<h2>{m_h3.group(1)}</h2>'
            return m_h3.group(0)

        html = re.sub(r'<h3>(.*?)</h3>', _rescue_h3, html)
        if rescued:
            log(f"  FIX 6: Rescued {rescued} h3(s) (unmatched bookmarks)")

    # ── FIX 9: Chapter heading promotion for bookmark-less PDFs ─────────
    # When a book has no bookmarks (or < 5), the pipeline can't distinguish
    # chapter headings from sub-section headings — everything is h3.
    # Promote "CHAPTER X" / "APPENDIX X" h3 tags to h2, and also promote the
    # ALL-CAPS short title that immediately follows as a chapter heading group.
    if len(bookmarks) < 5:
        _chapter_pattern = re.compile(
            r'(?i)^(CHAPTER|APPENDIX)\s+([IVXLCDM\d]+)\s*$')
        # Find all h3 tags and their positions
        _h3_matches = list(re.finditer(r'<h3>(.*?)</h3>', html))
        _promote_positions = set()  # positions of h3 tags to promote to h2
        for idx, m in enumerate(_h3_matches):
            h3_text = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            if _chapter_pattern.match(h3_text):
                _promote_positions.add(m.start())
                # Check if the next h3 is an ALL-CAPS short title (chapter title)
                if idx + 1 < len(_h3_matches):
                    next_m = _h3_matches[idx + 1]
                    next_text = re.sub(r'<[^>]+>', '', next_m.group(1)).strip()
                    # Must be short, ALL-CAPS (or mostly), and immediately follow
                    # (no body <p> paragraphs between them)
                    between = html[m.end():next_m.start()]
                    has_body_between = bool(re.search(r'<p>[^<]{20,}</p>', between))
                    if (len(next_text) < 80
                            and next_text == next_text.upper()
                            and not has_body_between):
                        _promote_positions.add(next_m.start())

        if _promote_positions:
            def _promote_chapter_h3(m):
                if m.start() in _promote_positions:
                    return f'<h2>{m.group(1)}</h2>'
                return m.group(0)
            html = re.sub(r'<h3>(.*?)</h3>', _promote_chapter_h3, html)
            log(f"  FIX 9: Promoted {len(_promote_positions)} chapter-level h3(s) to h2")

    # ── FIX 7: Post-reconciliation heading deduplication ────────────────
    # After all whitelist/rescue passes, scan h1/h2 tags for duplicates.
    # Same normalized text within 50 pages → running header duplicate → demote to <p>.
    # Same text > 50 pages apart → legitimate (e.g., "Interlude" between parts) → keep both.
    # Normalize: lowercase, strip leading chapter numbers, normalize all quotes to straight.
    def _normalize_heading_for_dedup(text):
        """Normalize heading text for deduplication comparison."""
        t = re.sub(r'<[^>]+>', '', text).strip().lower()
        # Normalize all quote characters to straight double
        t = t.replace('\u201c', '"').replace('\u201d', '"')
        t = t.replace('\u2018', '"').replace('\u2019', '"')
        t = t.replace("'", '"')
        # Strip leading chapter number: "5. The Turning Point" → "the turning point"
        t = re.sub(r'^\d+[\.\):]?\s*', '', t).strip()
        # Strip leading/trailing quote characters (catches OCR missing open/close quote)
        t = t.strip('"')
        # Collapse whitespace
        t = re.sub(r'\s+', ' ', t)
        return t

    # Build list of (position, page_num, tag, content, match_obj) for all h1/h2
    _dedup_entries = []
    _current_dedup_page = 1
    for m in re.finditer(r'<a id="page_(\d+)"></a>|<(h[12])>(.*?)</\2>', html):
        if m.group(1):  # page anchor
            _current_dedup_page = int(m.group(1))
        elif m.group(2):  # heading
            _dedup_entries.append({
                'pos': m.start(), 'page': _current_dedup_page,
                'tag': m.group(2), 'content': m.group(3),
                'norm': _normalize_heading_for_dedup(m.group(3)),
                'full': m.group(0)
            })

    # Find duplicates: for each normalized text, keep first occurrence,
    # demote subsequent ones within 50 pages to <p>
    _dedup_seen = {}  # norm_text → page of first occurrence
    _dedup_remove = set()  # positions to demote
    for entry in _dedup_entries:
        norm = entry['norm']
        if not norm:
            continue
        if norm in _dedup_seen:
            first_page = _dedup_seen[norm]
            if abs(entry['page'] - first_page) <= 50:
                _dedup_remove.add(entry['pos'])
            # else: > 50 pages apart, legitimate — don't update first_page
            # so future duplicates are compared against the original
        else:
            _dedup_seen[norm] = entry['page']

    if _dedup_remove:
        def _dedup_heading(m):
            if m.start() in _dedup_remove:
                content = m.group(2)
                return f'<p>{content}</p>'
            return m.group(0)
        html = re.sub(r'<(h[12])>(.*?)</\1>', _dedup_heading, html)
        log(f"  FIX 7: Deduplicated {len(_dedup_remove)} heading(s) (same text within 50 pages)")

    # ── FIX 8: Strip standalone page numbers ────────────────────────
    # Remove <p> elements that contain only a bare number (1-4 digits),
    # optionally with whitespace. These are extracted printed page numbers.
    # Don't touch numbers inside headings, footnotes, or longer paragraphs.
    _page_num_pattern = re.compile(r'<p>\s*\d{1,4}\s*</p>\n?')
    _page_num_count = len(_page_num_pattern.findall(html))
    if _page_num_count > 0:
        html = _page_num_pattern.sub('', html)
        log(f"  FIX 8: Stripped {_page_num_count} standalone page number paragraph(s)")

    # FIX 5: Insert synthetic Front Matter h1 for pre-Part h2s.
    has_part_h1 = bool(re.search(
        r'<h1>(?!(?:CONTENTS|Contents|Front Matter|NOTES|Notes|BIBLIOGRAPHY'
        r'|Bibliography|INDEX|Index|Epilogue|Further reading|Further Reading'
        r'|FURTHER READING|References|REFERENCES|Glossary|GLOSSARY'
        r'|Appendix|APPENDIX|Abbreviation|ABBREVIATION|Table of Contents))', html))
    if has_part_h1:
        # Check if an h2 appears before the first real h1
        first_h1 = re.search(r'<h1>', html)
        first_h2 = re.search(r'<h2>(.*?)</h2>', html)
        if first_h1 and first_h2 and first_h2.start() < first_h1.start():
            # Don't insert Front Matter if the first h2 is just the book subtitle
            # (appears very close before the title h1 and is in ALL CAPS)
            gap = first_h1.start() - first_h2.end()
            h2_text = first_h2.group(1).strip()
            if gap < 300 and h2_text == h2_text.upper() and len(h2_text) < 80:
                log(f"  FIX 5: Skipped — first h2 '{h2_text[:50]}' appears to be subtitle (gap={gap})")
            else:
                # Demote the CONTENTS h1 to styled paragraph if present
                html = re.sub(
                    r'<h1>(CONTENTS|Contents)</h1>',
                    r'<p style="font-size:1.4em;text-align:center;margin:2em 0;"><b>\1</b></p>',
                    html)
                # Insert Front Matter h1 before the first h2
                html = html.replace(first_h2.group(), '<h1>Front Matter</h1>\n' + first_h2.group(), 1)
                h1_count += 1
                log(f"  FIX 5: Inserted Front Matter h1 (pre-Part h2s need parent)")

    # Capitalize first letter of first paragraph after chapter headings
    # (drop-cap extraction artifact: pdfminer loses the large initial letter)
    html = re.sub(
        r'(</h[12]>\s*\n<p>)([a-z])',
        lambda m: m.group(1) + m.group(2).upper(),
        html)

    return html


def clean_and_join(raw_text, log):
    """Fix hyphens, rejoin wrapped lines into flowing paragraphs."""
    log("  Fixing hyphenated line breaks...")

    text = raw_text.replace("\xa0", " ")  # non-breaking spaces

    # Soft hyphen line break -- common in scanned books
    text = re.sub(r"\u00ac\s*\n\s*", "", text)

    # Regular hyphenated line breaks: "word-\nword" -> "wordword"
    text = re.sub(r"(\w)-\s*\n(\w)", r"\1\2", text)

    lines = text.split("\n")

    # Measure typical body-line length for paragraph detection
    body_lens = [len(l) for l in lines if 30 < len(l.strip()) < 130]
    median_len = statistics.median(body_lens) if body_lens else 65
    short_threshold = median_len * 0.72
    log(f"  Median line length: {median_len:.0f} chars  |  Short threshold: {short_threshold:.0f}")

    # Words that signal mid-sentence continuation when they end a line
    _CONTINUATION_WORDS = {
        'a', 'an', 'the', 'of', 'in', 'to', 'for', 'and', 'or', 'but',
        'by', 'with', 'at', 'on', 'as', 'that', 'which', 'from', 'into',
        'is', 'was', 'are', 'were', 'be', 'been', 'being', 'has', 'had',
        'have', 'not', 'no', 'this', 'these', 'those', 'than', 'who',
        'whom', 'whose', 'its', 'their', 'his', 'her', 'our', 'your',
        'about', 'between', 'through', 'during', 'before', 'after',
        'above', 'below', 'under', 'over', 'against', 'among', 'upon',
    }

    output_lines = []
    heading_count = 0
    for line in lines:
        stripped = line.strip()

        # Blank lines in the source text are explicit paragraph breaks
        if not stripped:
            output_lines.append("")
            continue

        # Preserve page markers for bookmark mapping — always standalone
        if re.match(r'^<<PAGE:\d+>>$', stripped):
            output_lines.append("")    # break before marker
            output_lines.append(stripped)
            output_lines.append("")    # break after marker
            continue

        # Strip lone page numbers (2-3 digits only).
        # Single-digit numbers are too ambiguous (chapter refs, list items)
        # and get caught by the short-fragment filter later anyway.
        if re.match(r"^\d{2,3}$", stripped):
            continue

        # Preserve structural headings as standalone paragraphs
        if _looks_like_heading(stripped):
            output_lines.append(stripped)
            output_lines.append("")  # paragraph break
            heading_count += 1
            continue

        ends_sentence = bool(re.search(r"[.!?][\"'\u201d\u2019)}\]]*\s*$", stripped))
        is_short = len(stripped) < short_threshold

        # Check for continuation signals — line clearly continues on next line
        last_word = stripped.split()[-1].lower().rstrip('.,;:') if stripped.split() else ''
        ends_with_continuation = (
            last_word in _CONTINUATION_WORDS
            or stripped.endswith(',')
            or stripped.endswith(';')
            or stripped.endswith(':')
            or stripped.endswith('(')
            or stripped.endswith('\u2014')  # em-dash
            or stripped.endswith('\u2013')  # en-dash
        )

        # Paragraph break logic:
        # 1. Lines ending with continuation words/punctuation are NEVER breaks
        # 2. Short lines are breaks ONLY if they end with terminal punctuation
        #    (short lines without terminal punct are style fragments from pypdf)
        # 3. Medium lines (< 92% of median) that end a sentence are breaks
        # 4. Everything else is a continuation (join to next line)
        if ends_with_continuation:
            output_lines.append(stripped + " ")
        elif is_short and ends_sentence:
            output_lines.append(stripped)
            output_lines.append("")          # paragraph break
        elif is_short and not ends_sentence:
            # Short line without terminal punctuation — likely a style fragment
            # or the last short word before a font change. Join it.
            output_lines.append(stripped + " ")
        elif ends_sentence and len(stripped) < median_len * 0.92:
            output_lines.append(stripped)
            output_lines.append("")          # paragraph break
        else:
            output_lines.append(stripped + " ")

    if heading_count:
        log(f"  Preserved {heading_count} heading-like lines")

    # Merge into paragraphs
    paragraphs = []
    current = []
    for ol in output_lines:
        if ol == "":
            if current:
                paragraphs.append("".join(current).strip())
                current = []
        else:
            current.append(ol)
    if current:
        paragraphs.append("".join(current).strip())

    # Drop very short artifact fragments (< 4 words), but protect:
    # - <<PAGE:N>> markers
    # - Short lines immediately AFTER a page marker (chapter title fragments)
    filtered = []
    for i, p in enumerate(paragraphs):
        if re.match(r'^<<PAGE:\d+>>$', p.strip()):
            filtered.append(p)
            continue
        if len(p.split()) >= 4:
            filtered.append(p)
            continue
        # Protect short lines that follow a page marker — these are chapter titles
        # (e.g., "Genesis before Darwin", "Why Scripture Needed Liberating")
        if i > 0 and re.match(r'^<<PAGE:\d+>>$', paragraphs[i - 1].strip()):
            filtered.append(p)
            continue
        # Also protect short lines within 8 paragraphs of a page marker.
        # Chapter title pages have: marker → number → title1 → title2 → subtitle → author → body
        # That's 6-7 short fragments. Window of 8 covers the full pattern.
        if any(re.match(r'^<<PAGE:\d+>>$', paragraphs[j].strip())
               for j in range(max(0, i - 8), i)):
            filtered.append(p)
            continue
        # Drop the artifact
    paragraphs = filtered

    # Post-processing: merge false paragraph breaks
    # If a paragraph starts with a lowercase letter or closing punctuation,
    # it's almost certainly a continuation of the previous paragraph.
    # But NEVER merge into or across <<PAGE:N>> markers or title fragments after them.
    merged = []
    for p in paragraphs:
        # Continuation signals: starts with lowercase, closing paren/bracket,
        # or a comma/semicolon (styled text fragments)
        is_continuation = (
            merged and p and (
                p[0].islower()
                or p[0] in ')]\u201d\u2019'  # closing parens, brackets, quotes
                or (p[0] == ',' or p[0] == ';')  # comma/semicolon fragments
            )
        )
        if not is_continuation:
            merged.append(p)
            continue

        # Find the actual previous content paragraph (skip past page markers)
        prev_idx = len(merged) - 1
        while prev_idx >= 0 and re.match(r'^<<PAGE:\d+>>$', merged[prev_idx].strip()):
            prev_idx -= 1

        if prev_idx < 0:
            merged.append(p)
            continue

        # Don't merge short fragments near page markers — these are likely
        # title/subtitle elements on chapter title pages.
        # But longer paragraphs (40+ chars) starting lowercase are body text
        # continuations that should ALWAYS be merged, even near page markers.
        if len(p) < 40:
            near_marker = any(re.match(r'^<<PAGE:\d+>>$', merged[j].strip())
                              for j in range(max(0, len(merged) - 8), len(merged)))
            if near_marker:
                merged.append(p)
                continue

        merged[prev_idx] = merged[prev_idx].rstrip() + " " + p

    before = len(paragraphs)
    paragraphs = merged
    if before != len(paragraphs):
        log(f"  Merged {before - len(paragraphs)} false paragraph breaks")

    log(f"  Built {len(paragraphs):,} paragraphs")
    return paragraphs


# Back-matter keywords
BACK_MATTER_PATTERNS = re.compile(
    r"^(notes?|endnotes?|footnotes?|bibliography|references?|index|"
    r"works\s+cited|further\s+reading|selected\s+bibliography|"
    r"acknowledgements?|appendix|abbreviations?)$",
    re.IGNORECASE,
)

# Front-matter skip patterns (title page, TOC, copyright)
FRONT_MATTER_PATTERNS = re.compile(
    r"(all rights reserved|printed in|library of congress|"
    r"isbn|copyright|published by|digitized by|"
    r"table of contents|contents\b|translator'?s? note)",
    re.IGNORECASE,
)

# Scholarly/footnote indicator words used to reject numbered footnotes
# that would otherwise match the "1. Title" chapter heading pattern.
# E.g. "8. LXX reads 'to all the house of Israel.'" is a footnote, not a chapter.
_FOOTNOTE_INDICATORS = (
    'LXX', 'MT', 'BHS', 'Cf.', 'cf.', 'See ', 'see ', 'Note ', 'note ',
    'Thus ', 'Read ', 'reads ', 'Greenberg', 'Zimmerli', 'NRSV', 'HALOT',
    'BDB', 'GKC', 'RSV', 'NIV', 'NASB', 'ESV', 'TDOT', 'ANET', 'ABD',
    'AHW', 'CAD', 'DNWSI',
)


def is_heading_candidate(para):
    """Return True if a paragraph looks like a chapter/section heading."""
    stripped = para.strip()
    words = stripped.split()
    n = len(words)

    if n < 1 or n > 20:
        return False
    # Must start with a capital letter or digit (numbered chapters)
    if not (stripped[0].isupper() or stripped[0].isdigit()):
        return False
    # Reject if it ends with a weak trailing word (mid-sentence fragment)
    if words[-1].lower() in {"a","an","the","of","in","to","for","and","or","but","by","with","at","was","is","are","were","has","had"}:
        return False
    # Reject page-number suffixed headings like "A Hundred Years After 293"
    # but allow them if preceded by a comma (TOC-style "Title, 293")
    if re.search(r"[^,]\s\d{1,4}$", stripped):
        return False
    # Title-case ratio check (relax for numbered headings)
    alpha_words = [w for w in words if w[0].isalpha()]
    if alpha_words:
        upper_ratio = sum(1 for w in alpha_words if w[0].isupper()) / len(alpha_words)
        if upper_ratio < 0.40:
            return False
    return True


def is_strong_chapter_heading(para):
    """
    Stronger signal: paragraph IS a standalone chapter/section label.
    Matches:
      - "Chapter 1", "Part II: Title", "Prologue", "Appendix A"
      - Numbered entries: "1. Title", "12. Title"
      - Roman numerals: "I. Title", "XIV. Title"
    """
    stripped = para.strip()
    if len(stripped.split()) > 20:
        return False
    # Traditional chapter/part/section keywords
    if re.match(
        r"^(chapter|part|section|prologue|epilogue|preface|introduction|"
        r"foreword|afterword|conclusion|appendix|excursus)\b",
        stripped, re.IGNORECASE
    ):
        return True
    # Numbered heading: "1. Title" or "12. Title"
    # Require: max 2 digits (no book has 100+ chapters), period after number,
    # and at least 3 words total (to exclude footnote refs like "246 C. Ar. 1. 3.")
    m = re.match(r"^(\d{1,2})\.\s*[A-Z]", stripped)
    if m and len(stripped.split()) >= 3:
        # Reject if it looks like a citation: contains dots/numbers after the title start
        # e.g., "95 Alexander, Ep. Alex. 47." vs "1. Points of Departure"
        rest = stripped[m.end()-1:]  # text after the number
        # Real chapter titles don't have multiple periods in them
        if rest.count('.') <= 2:
            # Reject numbered footnotes containing scholarly indicator words.
            # E.g. "8. LXX reads..." or "19. Note the cynicism..." are footnotes;
            # "2. Yahweh's Design for Israel (28:24-26)" is a real chapter heading.
            if any(ind in rest for ind in _FOOTNOTE_INDICATORS):
                return False
            return True
    # Roman numeral heading: "I. Title", "XIV. Title"
    # Require period and at least 3 words to avoid running header fragments
    # like "I.  A CONTROVERSY" or "II.  OF PRO-NICENE THEOLOGY"
    if re.match(r"^[IVXLC]+\.\s+[A-Z]", stripped) and len(stripped.split()) >= 4:
        return True
    return False


def is_part_heading(para):
    """Detect Part-level (top-level) headings like 'Part I: Title'."""
    stripped = para.strip()
    if len(stripped.split()) > 15:
        return False
    return bool(re.match(
        r"^part\s+[IVXLC\d]+",
        stripped, re.IGNORECASE
    ))


def detect_front_matter_end(paragraphs, log):
    """
    Find the index where real prose begins.
    Strategy: skip until we find the first long paragraph (> 60 words)
    that does NOT look like front-matter boilerplate.
    We also require we're past any obvious TOC / copyright block.
    """
    for i, p in enumerate(paragraphs):
        words = p.split()
        if len(words) < 50:
            continue
        # Check the surrounding context (last few paras) for TOC/copyright signals
        context = " ".join(paragraphs[max(0, i-5):i])
        if FRONT_MATTER_PATTERNS.search(context):
            continue
        # If we're > para 5 and hit a long paragraph without TOC context -> body start
        if i > 3:
            log(f"  Body text starts at paragraph {i}")
            return i
    log("  Could not auto-detect front matter end -- using paragraph 0")
    return 0


def detect_back_matter_start(paragraphs, log):
    """
    Find the index where back matter (Notes, Bibliography, Index) begins.
    Look for standalone short paragraphs matching known back-matter keywords,
    followed by content that looks like footnotes/references (short, numbered).
    """
    n = len(paragraphs)
    # Only search the final 40% of the book
    search_start = int(n * 0.60)

    for i in range(search_start, n):
        p = paragraphs[i].strip()
        if BACK_MATTER_PATTERNS.match(p):
            # Confirm: check that the next several paragraphs are short/reference-like
            lookahead = paragraphs[i+1:i+8]
            short_count = sum(1 for x in lookahead if len(x.split()) < 25)
            if short_count >= 4:
                log(f"  Back matter starts at paragraph {i} -- '{p}'")
                return i

    # Fallback: look for dense footnote-like content (many short paras with digits)
    for i in range(search_start, n - 10):
        window = paragraphs[i:i+10]
        short = sum(1 for p in window if len(p.split()) < 20)
        numbered = sum(1 for p in window if re.match(r"^\d{1,3}[\.\s]", p.strip()))
        if short >= 8 and numbered >= 3:
            log(f"  Back matter (footnote block) detected at paragraph {i}")
            return i

    log("  No back matter detected -- keeping full text")
    return n


def detect_toc_section(paragraphs, log):
    """Detect the printed Table of Contents section and return the index range.

    Returns a set of paragraph indices that belong to the printed TOC.
    These should be skipped by chapter detection to avoid false headings.

    Detection: find a "Contents" heading, then mark all subsequent short
    paragraphs until the first long prose paragraph (50+ words).
    """
    toc_indices = set()
    toc_start = None

    # Find the "Contents" heading
    for i, p in enumerate(paragraphs[:100]):  # only check first 100 paragraphs
        stripped = p.strip()
        stripped_lower = stripped.lower()
        # Exact matches
        if stripped_lower in ('contents', 'table of contents', 'detailed contents',
                       'brief contents', 'contents in detail'):
            toc_start = i
            break
        # Starts with "Contents" (e.g., "Contents xv", "Contents Abbreviations xv")
        if re.match(r'^(table of )?contents\b', stripped_lower):
            toc_start = i
            break
        # Also detect TOC by structure: a cluster of short paragraphs with trailing
        # page numbers, preceded by a heading-like paragraph
        # Look for 5+ consecutive short paragraphs with trailing numbers
        if i < 50 and len(stripped.split()) < 15 and re.search(r'\d{1,3}\s*$', stripped):
            # Check if next 5 paragraphs also look like TOC entries
            lookahead = paragraphs[i:i+8]
            toc_like = sum(1 for p2 in lookahead
                          if len(p2.split()) < 15 and re.search(r'\d{1,3}\s*$', p2.strip()))
            if toc_like >= 5:
                toc_start = i
                log(f"  Printed TOC detected by structure at paragraph {i}")
                break

    if toc_start is None:
        return set()

    log(f"  Printed TOC detected starting at paragraph {toc_start}")
    toc_indices.add(toc_start)

    # Walk forward from Contents heading -- mark short paragraphs as TOC entries
    # Stop when we hit a long prose paragraph (body text)
    consecutive_short = 0
    for i in range(toc_start + 1, min(len(paragraphs), toc_start + 300)):
        p = paragraphs[i].strip()
        words = p.split()
        word_count = len(words)

        # Long paragraph = body text, stop
        if word_count >= 50:
            break

        # "This page intentionally left blank" -- skip but don't break
        if 'intentionally left blank' in p.lower():
            toc_indices.add(i)
            continue

        # Short paragraph -- likely a TOC entry
        if word_count < 20:
            toc_indices.add(i)
            consecutive_short += 1
            continue

        # Medium paragraph (20-50 words) -- could be a subtitle cluster in the TOC
        # or could be the start of a preface/introduction
        # If we've seen many short paras already, keep going
        if consecutive_short >= 5 and word_count < 40:
            toc_indices.add(i)
            continue

        # Otherwise, this might be the start of body text
        break

    log(f"  Marked {len(toc_indices)} paragraphs as printed TOC (paras {toc_start}-{max(toc_indices)})")
    return toc_indices


def detect_chapters(paragraphs, log, toc_indices=None):
    """
    Identify chapter heading paragraphs.
    Returns a dict with two keys:
      'parts'    -- indices of Part-level (top) headings
      'chapters' -- indices of chapter-level headings
    For backward compatibility, also works as a flat list via detect_chapters_flat().

    Args:
        toc_indices: Set of paragraph indices that belong to the printed TOC.
                     These are skipped to avoid detecting TOC entries as chapter headings.
    """
    n = len(paragraphs)
    parts    = []
    chapters = []
    skip = toc_indices or set()

    for i, p in enumerate(paragraphs):
        if i in skip:
            continue
        stripped = p.strip()

        # Part-level headings (highest priority)
        if is_part_heading(stripped):
            parts.append(i)
            continue

        # Strong chapter markers (numbered, keyword-prefixed)
        if is_strong_chapter_heading(stripped):
            chapters.append(i)
            continue

    # If we found chapters via strong detection, validate the count
    if len(chapters) >= 2:
        # Sanity check: most books have < 40 chapters. If we found way more,
        # footnotes/citations are probably matching. Keep only numbered headings
        # with numbers that form a reasonable sequence.
        if len(chapters) > 50:
            log(f"  {len(chapters)} chapter headings detected -- likely false positives, filtering...")
            filtered = []
            seen_titles = set()

            for idx in chapters:
                p = paragraphs[idx].strip()

                # Skip long paragraphs -- real chapter titles are short
                if len(p) > 100:
                    continue

                # Skip duplicates (running headers appear many times)
                # Normalize: lowercase, collapse whitespace
                norm = re.sub(r'\s+', ' ', p.lower().strip())
                if norm in seen_titles:
                    continue
                seen_titles.add(norm)

                # Skip citation-style entries: "C. Ar. 1. 9", "C. Th. 16. 5"
                if re.match(r'^[A-Z]\.\s', p):
                    continue

                # Skip running header fragments: all caps with incomplete text
                # e.g., "1.  A CONTROVERSY", "II.  OF PRO-NICENE THEOLOGY"
                if re.match(r'^[\dIVXLC]+\.\s{2,}', p):
                    continue

                # For numbered entries (1., 2., etc.), require they look like real titles
                m = re.match(r'^(\d{1,2})\.\s', p)
                if m:
                    # Real chapter title: short, title-case, not a full sentence
                    if len(p) > 80 or p.rstrip().endswith(('.', ',', ';')):
                        continue  # too long or ends like a sentence -- not a heading
                    if int(m.group(1)) > 20:
                        continue  # chapter number too high
                    filtered.append(idx)
                    continue

                # For Roman numeral entries, require proper title
                if re.match(r'^[IVXLC]+\.\s+[A-Z]', p):
                    if len(p) > 80 or p.rstrip().endswith(('.', ',', ';')):
                        continue
                    filtered.append(idx)
                    continue

                # Keyword-based headings (Introduction, Conclusion, Epilogue, etc.)
                if re.match(r'^(chapter|part|section|prologue|epilogue|preface|introduction|foreword|afterword|conclusion|appendix|excursus)\b', p, re.IGNORECASE):
                    if len(p) > 80 or p.rstrip().endswith(('.', ',', ';')):
                        continue
                    filtered.append(idx)
                    continue

            log(f"  Filtered to {len(filtered)} likely real chapters")
            chapters = filtered

        # Content-based validation: separate TOC entries from real body headings.
        # TOC entries cluster together with almost no body text between them.
        # Real chapters have substantial prose after them.
        all_headings_sorted = sorted(parts + chapters)
        thin_headings = []     # headings with < 50 words after them (likely TOC)
        content_validated = [] # headings with real body text after them

        for idx in chapters:
            # Find the next heading after this one
            next_heading = None
            for h in all_headings_sorted:
                if h > idx:
                    next_heading = h
                    break
            if next_heading is None:
                next_heading = len(paragraphs)

            # Count words between this heading and the next
            body_words = 0
            for k in range(idx + 1, next_heading):
                if paragraphs[k] and paragraphs[k].strip():
                    body_words += len(paragraphs[k].split())

            if body_words >= 50:
                content_validated.append(idx)
            else:
                thin_headings.append(idx)

        # For thin headings in the first 300 paragraphs (TOC area), try to find
        # where that same title appears later in the body text as a paragraph.
        # This turns the printed TOC into a chapter-finding tool.
        toc_rescued = 0
        if thin_headings:
            for idx in thin_headings:
                title = paragraphs[idx].strip()
                # Normalize the title for matching
                title_norm = re.sub(r'\s+', ' ', title.lower()).strip()
                # Remove trailing page numbers that might be in the TOC entry
                title_norm = re.sub(r'\s+\d{1,3}\s*$', '', title_norm).strip()
                # Normalize numbering: "1. Title" -> "1 title", "I. Title" -> "i title"
                title_norm = re.sub(r'^(\d{1,2})\.\s*', r'\1 ', title_norm)
                title_norm = re.sub(r'^([ivxlc]+)\.\s*', r'\1 ', title_norm)

                if len(title_norm) < 5:
                    continue

                # Search for this title in body paragraphs (after the TOC area)
                search_start = max(idx + 20, 120)  # skip past front matter
                for j in range(search_start, len(paragraphs)):
                    if j in content_validated or j in parts:
                        continue
                    candidate = paragraphs[j].strip()
                    candidate_norm = re.sub(r'\s+', ' ', candidate.lower()).strip()
                    # Normalize numbering the same way
                    candidate_norm = re.sub(r'^(\d{1,2})\.\s*', r'\1 ', candidate_norm)
                    candidate_norm = re.sub(r'^([ivxlc]+)\.\s*', r'\1 ', candidate_norm)

                    # Exact or close match (also try first 80% of title for truncated headings)
                    title_prefix = title_norm[:int(len(title_norm) * 0.8)] if len(title_norm) > 10 else title_norm
                    if (candidate_norm == title_norm or
                        candidate_norm.startswith(title_norm) or
                        (len(title_prefix) > 10 and candidate_norm.startswith(title_prefix))):
                        # Verify this body occurrence has real content after it
                        next_h = None
                        for h in all_headings_sorted:
                            if h > j:
                                next_h = h
                                break
                        if next_h is None:
                            next_h = len(paragraphs)
                        bw = sum(len(paragraphs[k].split()) for k in range(j+1, min(j+20, next_h))
                                 if paragraphs[k] and paragraphs[k].strip())

                        if bw >= 30:
                            content_validated.append(j)
                            toc_rescued += 1
                            log(f"  TOC rescue: '{title[:50]}' -> body para {j}")
                            break

            log(f"  Dropped {len(thin_headings)} thin headings, rescued {toc_rescued} from body text")

        chapters = sorted(content_validated)

        if len(chapters) != len(content_validated):
            log(f"  Content validation: {len(chapters)} chapters after TOC rescue")

        log(f"  Found {len(parts)} part headings + {len(chapters)} chapter headings")
        return {'parts': parts, 'chapters': chapters}

    # Fallback: heuristic -- short title-case paras surrounded by prose
    for i in range(1, n - 1):
        p = paragraphs[i]
        if i in parts or i in skip:
            continue
        if not is_heading_candidate(p):
            continue

        prev_words = len(paragraphs[i-1].split())
        next_words = len(paragraphs[i+1].split()) if i+1 < n else 0

        if prev_words > 25 and next_words > 25:
            chapters.append(i)

    chapters = sorted(set(chapters))
    log(f"  Detected {len(parts)} part headings + {len(chapters)} chapter/section headings")
    return {'parts': parts, 'chapters': chapters}


def detect_chapters_flat(paragraphs, log, toc_indices=None):
    """Return a flat list of all heading indices (for Balabolka mode)."""
    result = detect_chapters(paragraphs, log, toc_indices=toc_indices)
    return sorted(result['parts'] + result['chapters'])


# Common heading keywords for single-word validation (lowercase)
_HEADING_KEYWORDS = {
    'chapter', 'part', 'epilogue', 'prologue', 'introduction',
    'conclusion', 'appendix', 'bibliography', 'notes', 'index',
    'preface', 'foreword', 'acknowledgments',
}
_ROMAN_NUMERAL_RE = re.compile(r'^[IVXLC]+$', re.IGNORECASE)


def validate_heading_indices(paragraphs, heading_indices, log, bookmark_indices=None):
    """
    Post-processing validation: demote false-positive headings.

    Rules:
    1. < 4 words AND ends with period/comma -> demote
    2. Starts with lowercase letter -> demote
    3. Single word not a number, Roman numeral, or common keyword -> demote
    4. Previous paragraph ends without sentence-ending punctuation -> likely continuation -> demote
       (skipped for bookmark-sourced headings — bookmarks are authoritative for position)

    Returns a new list with false positives removed.
    """
    if bookmark_indices is None:
        bookmark_indices = set()
    demoted = []
    validated = []

    for idx in heading_indices:
        if idx >= len(paragraphs):
            continue
        text = paragraphs[idx].strip()
        # Strip Markdown heading markers for analysis
        clean = re.sub(r'^#{1,3}\s*', '', text).strip()
        if not clean:
            demoted.append((idx, text, "empty"))
            continue

        words = clean.split()
        word_count = len(words)

        # Rule 2: starts with lowercase letter
        if clean[0].islower():
            demoted.append((idx, text, "starts with lowercase"))
            continue

        # Rule 1: < 4 words AND ends with period or comma
        if word_count < 4 and clean[-1] in '.,':
            demoted.append((idx, text, "short heading ends with period/comma"))
            continue

        # Rule 3: single word not a number, Roman numeral, or common keyword
        if word_count == 1:
            word_lower = clean.lower().rstrip(':.')
            if (not clean.isdigit()
                    and not _ROMAN_NUMERAL_RE.match(clean)
                    and word_lower not in _HEADING_KEYWORDS):
                demoted.append((idx, text, "single non-keyword word"))
                continue

        # Rule 4: previous paragraph ends without sentence-ending punctuation
        # Skip for bookmark-sourced headings — PDF bookmarks are authoritative
        if idx > 0 and idx not in bookmark_indices:
            prev = paragraphs[idx - 1].strip() if (idx - 1) < len(paragraphs) else ''
            if prev and not re.search(r'[.!?]["\u201d\u2019)]*\s*$', prev):
                demoted.append((idx, text, "previous para lacks sentence-ending punctuation"))
                continue

        validated.append(idx)

    if demoted:
        log(f"  Heading validation: demoted {len(demoted)} false-positive heading(s)")
        for idx, text, reason in demoted:
            log(f"    - [{reason}] \"{text[:60]}\"")

    return validated


def validate_heading_dict(paragraphs, heading_dict, log, bookmark_indices=None):
    """Validate heading_dict (parts + chapters), demoting false positives."""
    all_indices = sorted(heading_dict['parts'] + heading_dict['chapters'])
    validated = set(validate_heading_indices(paragraphs, all_indices, log,
                                            bookmark_indices=bookmark_indices))
    return {
        'parts': [i for i in heading_dict['parts'] if i in validated],
        'chapters': [i for i in heading_dict['chapters'] if i in validated],
    }


def apply_chapter_hints(paragraphs, hints, log):
    """
    Locate chapter headings using pre-detected hints (from Claude API).

    Uses quality-scored matching with monotonic ordering enforcement:
      - Q4: Exact normalized match, proper casing
      - Q3: Exact normalized match, ALL-CAPS (or near-exact prefix >= 75%)
      - Q2: Near-exact prefix match, ALL-CAPS
      - Q1: Substring match in short paragraph (<= 150 chars)
      - Q0: Substring match embedded in long paragraph (> 150 chars)

    Each hint must match at a paragraph index strictly after the previous
    hint's match, ensuring chapter order mirrors reading order.

    Matched paragraphs are replaced with the Claude hint title text to
    preserve proper casing and numbering.

    Returns (new_paragraphs, heading_dict) where heading_dict has the same
    format as detect_chapters(): {'parts': [indices], 'chapters': [indices]}.
    """
    paras    = list(paragraphs)   # mutable copy
    parts    = []
    chapters = []
    matched  = 0
    min_idx  = 0                  # monotonic ordering constraint

    # -- Normalisation helpers ------------------------------------
    def _norm(text):
        """Normalise for comparison: strip numbering, normalise chars, lowercase."""
        t = text.strip()
        # Strip markdown heading markers from earlier processing
        t = re.sub(r'^#{1,3}\s*', '', t)
        # Unicode dashes to ASCII hyphen
        t = t.replace('\u2013', '-').replace('\u2014', '-')
        # Unicode quotes to ASCII
        t = t.replace('\u2018', "'").replace('\u2019', "'")
        t = t.replace('\u201c', '"').replace('\u201d', '"')
        # Strip leading digit number: "1. " or "1) " or "1 "
        t = re.sub(r'^\d{1,2}[\.\)]\s*', '', t)
        t = re.sub(r'^\d{1,2}\s+(?=[A-Za-z])', '', t)
        # Strip leading roman numeral: "I. ", "III) ", "IV "
        t = re.sub(r'^[IVXLC]+[\.\)]\s*', '', t)
        t = re.sub(r'^[ivxlc]+[\.\)]\s*', '', t)
        t = re.sub(r'^[IVXLC]+\s+(?=[A-Za-z])', '', t)
        # Strip "Chapter X:" prefix
        t = re.sub(r'^(?:chapter|chap\.?)\s+\w+[:\.\s]+', '', t, flags=re.IGNORECASE)
        # Collapse whitespace
        t = re.sub(r'\s+', ' ', t).strip()
        return t.lower()

    def _body_words(idx, limit=120):
        """Count words in the paragraphs following *idx*, up to *limit*."""
        total = 0
        for k in range(idx + 1, min(idx + 60, len(paras))):
            p = paras[k].strip()
            if p:
                total += len(p.split())
            if total >= limit:
                return total
        return total

    # -- Main loop: one hint at a time, in reading order ----------
    for hint in hints:
        title = hint.get('title', '').strip()
        level = hint.get('level', 2)
        if not title:
            continue

        title_norm = _norm(title)
        if not title_norm:
            log(f"  [hint] empty after normalisation: {title[:70]}")
            continue

        # Gather every candidate paragraph from min_idx onward
        candidates = []          # (para_idx, quality, body_words)

        for i in range(min_idx, len(paras)):
            p = paras[i].strip()
            if not p:
                continue

            p_norm = _norm(p)
            if not p_norm:
                continue
            p_len  = len(p)
            is_caps = p.isupper()

            quality = -1

            # -- Q4 / Q3: exact normalised match -----------------
            if p_norm == title_norm:
                quality = 4 if not is_caps else 3

            # -- Q3 / Q2: near-exact (prefix >= 75 %) -----------
            if quality < 0 and p_len <= 200:
                shorter = p_norm if len(p_norm) <= len(title_norm) else title_norm
                longer  = title_norm if shorter == p_norm else p_norm
                if longer.startswith(shorter) and len(shorter) >= len(longer) * 0.60:
                    quality = 3 if not is_caps else 2

            # -- Q1: substring in short paragraph ----------------
            if quality < 0 and p_len <= 150:
                if title_norm in p_norm:
                    quality = 1

            # -- Q0: embedded in long paragraph ------------------
            if quality < 0 and p_len > 150:
                if title_norm in p_norm:
                    quality = 0

            if quality >= 0:
                bw = _body_words(i)
                candidates.append((i, quality, bw))

        if not candidates:
            log(f"  [hint] not found: {title[:70]}")
            continue

        # Sort: best quality first, then prefer has body text, then earliest
        def _score(c):
            pi, q, bw = c
            has_body = 1 if bw >= 50 else 0
            return (q, has_body, -pi)

        candidates.sort(key=_score, reverse=True)
        best_pi, best_q, best_bw = candidates[0]

        matched += 1
        log(f"  [hint] matched (q={best_q}, body={best_bw}, para={best_pi}): {title[:60]}")

        # -- Apply the match --------------------------------------
        if best_q >= 1:
            # Exact, near-exact, or substring in short para:
            # replace paragraph text with properly formatted hint title
            paras[best_pi] = title
            target_idx = best_pi
        else:
            # Embedded (Q0): insert hint title as a new paragraph
            # before the matching paragraph, preserving original text
            paras.insert(best_pi, title)
            target_idx = best_pi
            # Shift all previously recorded indices at or above best_pi
            parts    = [x + 1 if x >= best_pi else x for x in parts]
            chapters = [x + 1 if x >= best_pi else x for x in chapters]

        if level == 1:
            parts.append(target_idx)
        else:
            chapters.append(target_idx)

        # Enforce monotonic ordering: next hint must be after this one
        min_idx = target_idx + 1

    log(f"  Chapter hints: matched {matched}/{len(hints)} titles")
    return paras, {'parts': sorted(parts), 'chapters': sorted(chapters)}


def detect_scene_breaks(paragraphs, heading_indices_set, log):
    """Identify scene-break paragraphs (***, ---, ###, etc.)."""
    scene_break_pattern = re.compile(
        r'^\s*'
        r'(?:'
        r'[\*]{3,}'            # ***
        r'|[\*]\s[\*]\s[\*]'   # * * *
        r'|\u2042'             # asterism ⁂
        r'|[#]{3,}'            # ###
        r'|[#]\s[#]\s[#]'      # # # #
        r'|[-]{3,}'            # ---
        r'|[\u2013]\s[\u2013]\s[\u2013]'   # en-dash spaced
        r'|[\u2014]{1,3}'      # em-dashes
        r'|[\u2014]\s[\u2014]\s[\u2014]'   # em-dash spaced
        r')'
        r'\s*$'
    )
    breaks = set()
    for i, p in enumerate(paragraphs):
        if i in heading_indices_set:
            continue
        stripped = p.strip()
        if not stripped:
            continue
        if scene_break_pattern.match(stripped):
            breaks.add(i)
        elif len(stripped) <= 5 and all(c in ' \t*#\u2014\u2013-~\u2022\u00b7' for c in stripped):
            breaks.add(i)
    if breaks:
        log(f"  Found {len(breaks)} scene breaks")
    return breaks


def detect_emphatic_closers(paragraphs, heading_indices_set, scene_breaks, log):
    """Find short declarative sentences at paragraph ends for rate adjustment."""
    closers = []
    for i, p in enumerate(paragraphs):
        if i in heading_indices_set or i in scene_breaks:
            continue
        stripped = p.strip()
        if not stripped:
            continue

        # Must end with . or !
        if not (stripped.endswith('.') or stripped.endswith('!')):
            continue

        # Find the last sentence boundary
        last_break = -1
        for match in re.finditer(r'[.!?]\s+(?=[A-Z"\u201c])', stripped):
            last_break = match.end()

        if last_break == -1:
            # Single-sentence paragraph — skip
            continue

        final_sentence = stripped[last_break:].strip()

        word_count = len(final_sentence.split())
        if word_count < EMPHATIC_MIN_WORDS or word_count > EMPHATIC_MAX_WORDS:
            continue

        # No quotation marks (skip dialogue)
        if any(c in final_sentence for c in '"""\u201c\u201d'):
            continue

        # Not ALL CAPS
        alpha_chars = [c for c in final_sentence if c.isalpha()]
        if alpha_chars and all(c.isupper() for c in alpha_chars):
            continue

        closers.append({'para_index': i, 'sentence_start': last_break})

    if closers:
        log(f"  Found {len(closers)} emphatic closers")
    return closers


def _silence_tag(ms, syntax):
    if syntax == 'universal':
        return f'{{{{Pause={ms}}}}}'
    return f'<silence msec="{ms}"/>'


def _rate_wrap(text, speed, syntax):
    if syntax == 'universal':
        return text  # Universal syntax has no rate tag
    return f'<rate speed="{speed}">{text}</rate>'


def _voice_wrap(text, voice_name, syntax):
    """Wrap text in a voice tag for Balabolka/SAPI TTS."""
    if syntax == 'universal':
        return text  # Universal syntax doesn't support voice switching
    return f'<voice required="Name={voice_name}">{text}</voice>'


def detect_dialogue_spans(paragraph):
    """Detect quoted speech spans in a paragraph.

    Returns a list of (start, end, quote_text) tuples for each dialogue span.
    Handles double-quoted, smart-quoted dialogue. Filters out short quotes
    (< 3 words), number-only quotes, and citations in parentheses.
    """
    spans = []

    patterns = [
        re.compile(r'"([^"]{10,})"'),
        re.compile(r'\u201c([^\u201d]{10,})\u201d'),
    ]

    for pattern in patterns:
        for m in pattern.finditer(paragraph):
            quote_text = m.group(1).strip()
            if len(quote_text.split()) < 3:
                continue
            if re.match(r'^[\d\s.,]+$', quote_text):
                continue
            spans.append((m.start(), m.end(), quote_text))

    if len(spans) > 1:
        spans.sort(key=lambda s: s[0])
        deduped = [spans[0]]
        for s in spans[1:]:
            if s[0] >= deduped[-1][1]:
                deduped.append(s)
            elif (s[1] - s[0]) > (deduped[-1][1] - deduped[-1][0]):
                deduped[-1] = s
        spans = deduped

    return spans


def _build_voiced_paragraph(paragraph, spans, voice_name, silence_before, silence_after, tag_syntax):
    """Reconstruct a paragraph with voice tags wrapped around dialogue spans."""
    parts = []
    last_end = 0

    for start, end, _ in spans:
        if start > last_end:
            parts.append(paragraph[last_end:start])

        quote_with_marks = paragraph[start:end]
        parts.append(_silence_tag(silence_before, tag_syntax))
        parts.append(_voice_wrap(quote_with_marks, voice_name, tag_syntax))
        parts.append(_silence_tag(silence_after, tag_syntax))

        last_end = end

    if last_end < len(paragraph):
        parts.append(paragraph[last_end:])

    return ''.join(parts)


def _apply_dialogue_voices(paragraphs, tag_syntax, options, log):
    """Apply voice tags to detected dialogue and blockquote paragraphs.

    Narrator text (Steffan) is untagged. Dialogue gets Guy Online.
    Blockquotes (lines starting with >) get Aria Online.
    """
    try:
        _cfg_path = Path(__file__).resolve().parent.parent / 'config' / 'settings.json'
        if _cfg_path.exists():
            with open(_cfg_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f).get('voice_tags', {})
        else:
            cfg = {}
    except Exception:
        cfg = {}

    dialogue_voice = cfg.get('dialogue_voice', 'Microsoft Guy Online')
    blockquote_voice = cfg.get('blockquote_voice', 'Microsoft Aria Online')
    dlg_silence_before = cfg.get('dialogue_silence_before_ms', 150)
    dlg_silence_after = cfg.get('dialogue_silence_after_ms', 200)
    bq_silence_before = cfg.get('blockquote_silence_before_ms', 200)
    bq_silence_after = cfg.get('blockquote_silence_after_ms', 300)

    tagged_count = 0
    blockquote_count = 0
    result = []

    for p in paragraphs:
        if not p or p.startswith('<silence') or p.startswith('{{Pause'):
            result.append(p)
            continue

        stripped = p.strip()
        if stripped.startswith('>') or stripped.startswith('\t>'):
            bq_text = re.sub(r'^>\s*', '', stripped)
            tagged = (_silence_tag(bq_silence_before, tag_syntax) +
                      _voice_wrap(bq_text, blockquote_voice, tag_syntax) +
                      _silence_tag(bq_silence_after, tag_syntax))
            result.append(tagged)
            blockquote_count += 1
            continue

        spans = detect_dialogue_spans(p)
        if not spans:
            result.append(p)
            continue

        tagged_para = _build_voiced_paragraph(
            p, spans, dialogue_voice, dlg_silence_before, dlg_silence_after,
            tag_syntax
        )
        result.append(tagged_para)
        tagged_count += len(spans)

    if tagged_count or blockquote_count:
        log(f"  Voice tags: {tagged_count} dialogue spans, {blockquote_count} blockquotes")

    return result


def apply_voice_tags(paragraphs, chapter_structure, tag_syntax='sapi', options=None, log=lambda m: None):
    """Apply structural (Tier 1) and dialogue (Tier 2) voice tags to paragraphs."""
    if options is None:
        options = {'chapter_silence': True, 'scene_break_silence': True, 'emphatic_closers': True,
                   'dialogue_voices': False}

    part_set = set(chapter_structure.get('parts', []))
    chapter_set = set(chapter_structure.get('chapters', []))
    heading_set = part_set | chapter_set

    scene_breaks = set()
    if options.get('scene_break_silence', True):
        scene_breaks = detect_scene_breaks(paragraphs, heading_set, log)

    closer_map = {}
    if options.get('emphatic_closers', True):
        closers = detect_emphatic_closers(paragraphs, heading_set, scene_breaks, log)
        closer_map = {c['para_index']: c for c in closers}

    output = []
    for i, p in enumerate(paragraphs):
        if i in part_set:
            output.append(p.upper())
            if options.get('chapter_silence', True):
                output.append(_silence_tag(PART_SILENCE_MS, tag_syntax))

        elif i in chapter_set:
            output.append(p.upper())
            if options.get('chapter_silence', True):
                output.append(_silence_tag(CHAPTER_SILENCE_MS, tag_syntax))

        elif i in scene_breaks:
            output.append(_silence_tag(SCENE_BREAK_SILENCE_MS, tag_syntax))

        elif i in closer_map:
            info = closer_map[i]
            before = p[:info['sentence_start']]
            final = p[info['sentence_start']:].strip()
            tagged_final = _rate_wrap(final, EMPHATIC_RATE, tag_syntax)
            output.append(before + tagged_final)
            next_is_break = (i + 1 in scene_breaks) or (i + 1 in heading_set)
            if not next_is_break:
                output.append(_silence_tag(EMPHATIC_SILENCE_MS, tag_syntax))

        else:
            output.append(p)

    # ── Tier 2: Dialogue voice tags ──────────────────────────────────
    if options.get('dialogue_voices', False):
        output = _apply_dialogue_voices(output, tag_syntax, options, log)

    return output


def format_output(paragraphs, chapter_structure, log, tts_enhance=False, tag_syntax='sapi',
                  dialogue_voices=False):
    """Build the final text with ALL-CAPS headings and optional TTS voice tags."""
    if tts_enhance:
        options = {
            'chapter_silence': True,
            'scene_break_silence': True,
            'emphatic_closers': True,
            'dialogue_voices': dialogue_voices,
        }
        tagged = apply_voice_tags(paragraphs, chapter_structure, tag_syntax=tag_syntax,
                                  options=options, log=log)
        return "\n\n".join(tagged)

    heading_set = set(chapter_structure.get('parts', []) + chapter_structure.get('chapters', []))
    parts = []
    for i, p in enumerate(paragraphs):
        parts.append(p.upper() if i in heading_set else p)
    return "\n\n".join(parts)


def format_kindle_html(paragraphs, headings, log, theme='classic', book_title='', book_author=''):
    """
    Build styled HTML output for Kindle/EPUB conversion via Calibre.

    Unlike format_output() which produces plain text with Markdown headings,
    this produces a full HTML document with embedded CSS theming, proper
    semantic markup (h1/h2/h3, blockquote, p), and professional typography.

    Args:
        paragraphs: List of paragraph strings (cleaned text)
        headings: Dict with 'parts' and 'chapters' index lists
        log: Logging function
        theme: Theme name ('classic', 'modern', 'minimal') or path to custom CSS
        book_title: Book title for the half-title page
        book_author: Author name for the half-title page

    Returns:
        Complete HTML string ready for Calibre conversion
    """
    part_set = set(headings.get('parts', []))
    chapter_set = set(headings.get('chapters', []))
    all_headings = part_set | chapter_set

    # -- Theme CSS ------------------------------------------------
    themes = {
        'classic': """
            body {
                font-family: Georgia, 'Times New Roman', serif;
                font-size: 1em;
                line-height: 1.6;
                color: #1a1a1a;
                margin: 0;
                padding: 0;
            }
            h1 {
                font-family: Georgia, 'Times New Roman', serif;
                font-size: 1.8em;
                font-weight: bold;
                text-align: center;
                margin-top: 2em;
                margin-bottom: 0.5em;
                page-break-before: always;
                letter-spacing: 0.02em;
            }
            h2 {
                font-family: Georgia, 'Times New Roman', serif;
                font-size: 1.4em;
                font-weight: bold;
                margin-top: 2em;
                margin-bottom: 0.3em;
                page-break-before: always;
            }
            h3 {
                font-family: Georgia, 'Times New Roman', serif;
                font-size: 1.1em;
                font-weight: normal;
                font-style: italic;
                margin-top: 1.5em;
                margin-bottom: 0.3em;
            }
            p {
                text-indent: 1.5em;
                margin: 0;
                padding: 0;
            }
            p.first-para {
                text-indent: 0;
            }
            p.first-para::first-letter {
                font-size: 2.8em;
                float: left;
                line-height: 0.8;
                margin-right: 0.08em;
                margin-top: 0.05em;
                font-weight: bold;
            }
            blockquote {
                margin: 1em 2em;
                padding: 0;
                font-style: italic;
                font-size: 0.95em;
            }
            blockquote p {
                text-indent: 0;
            }
            .dialogue {
                margin-left: 2em;
                margin-top: 0.3em;
                margin-bottom: 0.3em;
            }
            .half-title {
                text-align: center;
                page-break-after: always;
                padding-top: 30%;
            }
            .half-title h1 {
                page-break-before: auto;
                margin-top: 0;
            }
            .half-title .author {
                font-size: 1.1em;
                font-style: italic;
                margin-top: 1em;
                color: #444;
            }
            .subtitle {
                font-size: 1em;
                font-weight: normal;
                font-style: italic;
                display: block;
                margin-top: 0.3em;
            }
            hr.footnote-separator {
                border: none;
                border-top: 1px solid #999;
                width: 30%;
                margin: 1.5em 0 0.5em 0;
            }
            .footnotes {
                font-size: 0.85em;
                line-height: 1.4;
                color: #555;
            }
            .footnotes p {
                text-indent: 0;
                margin: 0.3em 0;
            }
        """,
        'modern': """
            body {
                font-family: Georgia, 'Times New Roman', serif;
                font-size: 1em;
                line-height: 1.7;
                color: #222;
                margin: 0;
                padding: 0;
            }
            h1 {
                font-family: Helvetica, Arial, sans-serif;
                font-size: 2em;
                font-weight: 300;
                text-align: left;
                margin-top: 2em;
                margin-bottom: 0.8em;
                page-break-before: always;
                border-bottom: 1px solid #ccc;
                padding-bottom: 0.3em;
            }
            h2 {
                font-family: Helvetica, Arial, sans-serif;
                font-size: 1.5em;
                font-weight: 400;
                margin-top: 2em;
                margin-bottom: 0.5em;
                page-break-before: always;
            }
            h3 {
                font-family: Helvetica, Arial, sans-serif;
                font-size: 1.1em;
                font-weight: 400;
                color: #555;
                margin-top: 1.5em;
                margin-bottom: 0.3em;
            }
            p {
                text-indent: 0;
                margin-top: 0.6em;
                margin-bottom: 0;
            }
            p.first-para::first-letter {
                font-size: 2.5em;
                float: left;
                line-height: 0.8;
                margin-right: 0.08em;
                margin-top: 0.05em;
                font-weight: 300;
                font-family: Helvetica, Arial, sans-serif;
            }
            blockquote {
                margin: 1em 1.5em;
                padding-left: 1em;
                border-left: 3px solid #ddd;
                font-style: italic;
                color: #444;
            }
            blockquote p { text-indent: 0; margin-top: 0.4em; }
            .dialogue { margin-left: 2em; margin-top: 0.3em; margin-bottom: 0.3em; }
            .half-title { text-align: center; page-break-after: always; padding-top: 30%; }
            .half-title h1 { page-break-before: auto; margin-top: 0; border: none; }
            .half-title .author { font-size: 1.1em; font-style: italic; margin-top: 1em; color: #666; }
            hr.footnote-separator { border: none; border-top: 1px solid #ddd; width: 30%; margin: 1.5em 0 0.5em 0; }
            .footnotes { font-size: 0.85em; line-height: 1.4; color: #666; }
            .footnotes p { text-indent: 0; margin: 0.3em 0; }
        """,
        'minimal': """
            body {
                font-family: Georgia, 'Times New Roman', serif;
                font-size: 1em;
                line-height: 1.6;
                color: #1a1a1a;
                margin: 0;
                padding: 0;
            }
            h1 { font-size: 1.6em; font-weight: bold; margin-top: 2em; margin-bottom: 0.5em; page-break-before: always; }
            h2 { font-size: 1.3em; font-weight: bold; margin-top: 2em; margin-bottom: 0.3em; page-break-before: always; }
            h3 { font-size: 1.05em; font-weight: bold; margin-top: 1.2em; margin-bottom: 0.3em; }
            p { text-indent: 1.5em; margin: 0; }
            p.first-para { text-indent: 0; }
            blockquote { margin: 0.8em 2em; font-style: italic; }
            blockquote p { text-indent: 0; }
            .dialogue { margin-left: 2em; }
            .half-title { text-align: center; page-break-after: always; padding-top: 30%; }
            .half-title h1 { page-break-before: auto; margin-top: 0; }
            .half-title .author { font-style: italic; margin-top: 1em; }
            hr.footnote-separator { border: none; border-top: 1px solid #999; width: 30%; margin: 1.5em 0 0.5em 0; }
            .footnotes { font-size: 0.85em; line-height: 1.4; color: #555; }
            .footnotes p { text-indent: 0; margin: 0.3em 0; }
        """,
    }

    # Load theme CSS
    if theme in themes:
        css = themes[theme]
    elif os.path.isfile(theme):
        with open(theme, 'r', encoding='utf-8') as f:
            css = f.read()
    else:
        log(f"  [WARN] Unknown theme '{theme}', falling back to 'classic'")
        css = themes['classic']

    # -- Build HTML -----------------------------------------------
    html_parts = []
    html_parts.append('<!DOCTYPE html>')
    html_parts.append('<html lang="en">')
    html_parts.append('<head>')
    html_parts.append('<meta charset="utf-8">')
    html_parts.append(f'<title>{_html_escape(book_title or "Untitled")}</title>')
    html_parts.append(f'<style>{css}</style>')
    html_parts.append('</head>')
    html_parts.append('<body>')

    # Half-title page
    if book_title:
        html_parts.append('<div class="half-title">')
        html_parts.append(f'<h1>{_html_escape(book_title)}</h1>')
        if book_author:
            html_parts.append(f'<div class="author">{_html_escape(book_author)}</div>')
        html_parts.append('</div>')

    # Body content
    after_heading = False
    for i, p in enumerate(paragraphs):
        if not p or not p.strip():
            continue

        stripped = p.strip()

        # Part heading (h1)
        if i in part_set:
            html_parts.append(f'<h1>{_html_escape(stripped)}</h1>')
            after_heading = True
            continue

        # Chapter heading (h2)
        if i in chapter_set:
            html_parts.append(f'<h2>{_html_escape(stripped)}</h2>')
            after_heading = True
            continue

        # Dialogue lines (tabbed)
        if stripped.startswith('\t'):
            html_parts.append(f'<p class="dialogue">{_html_escape(stripped.strip())}</p>')
            after_heading = False
            continue

        # Section subtitle detection (short, title-case, not a sentence)
        if (len(stripped) < 80 and
            not stripped.endswith(('.', '!', '?', ':', ',')) and
            not stripped[0].islower() and
            len(stripped.split()) <= 10 and
            i not in all_headings and
            not stripped.startswith('"')):
            # Check if it looks title-case-ish
            words = stripped.split()
            alpha_words = [w for w in words if w[0:1].isalpha()]
            if alpha_words:
                cap_ratio = sum(1 for w in alpha_words if w[0].isupper()) / len(alpha_words)
                if cap_ratio >= 0.5 and len(words) >= 2:
                    html_parts.append(f'<h3>{_html_escape(stripped)}</h3>')
                    after_heading = True
                    continue

        # Block quote detection (starts and ends with quotes, or preceded by attribution)
        is_block_quote = False
        if ((stripped.startswith('"') and stripped.endswith('"')) or
            (stripped.startswith('\u201c') and stripped.endswith('\u201d'))):
            if len(stripped) > 100:
                is_block_quote = True

        if is_block_quote:
            html_parts.append(f'<blockquote><p>{_html_escape(stripped)}</p></blockquote>')
            after_heading = False
            continue

        # Regular paragraph
        css_class = ' class="first-para"' if after_heading else ''
        html_parts.append(f'<p{css_class}>{_html_escape(stripped)}</p>')
        after_heading = False

    html_parts.append('</body>')
    html_parts.append('</html>')

    result = '\n'.join(html_parts)
    log(f"  Generated HTML output ({len(result):,} chars, theme: {theme})")
    return result


def _html_escape(text):
    """Escape HTML special characters, preserving <sup>/<em>/<strong> tags."""
    # Temporarily replace allowed tags with placeholders
    preserved = {
        '<sup>': '\x00SUP_OPEN\x00', '</sup>': '\x00SUP_CLOSE\x00',
        '<em>': '\x00EM_OPEN\x00', '</em>': '\x00EM_CLOSE\x00',
        '<strong>': '\x00STRONG_OPEN\x00', '</strong>': '\x00STRONG_CLOSE\x00',
    }
    for tag, placeholder in preserved.items():
        text = text.replace(tag, placeholder)
    text = (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;'))
    for tag, placeholder in preserved.items():
        text = text.replace(placeholder, tag)
    return text


def inject_missing_hints(paras, missing_hints, raw_text, heading_dict, log):
    """
    Insert missing chapter headings at evenly distributed positions.

    Since Claude returns chapters in reading order and apply_chapter_hints
    already placed some correctly, we distribute the remaining ones evenly
    across the full paragraph range.
    """
    total_paras = len(paras)
    if total_paras == 0 or not missing_hints:
        return paras, heading_dict

    _ = raw_text  # unused in this implementation; kept for call-site compatibility

    # We need to figure out where in the FULL chapter sequence each missing hint belongs.
    # missing_hints is a subset — we need to know the total chapter count and each hint's
    # ordinal position. Use a simple even spread across the paragraph range.
    # Reserve first 2% for front matter, last 5% for epilogue-area content.
    start_para = int(total_paras * 0.02)
    end_para = int(total_paras * 0.95)
    usable_range = end_para - start_para

    # Spread missing hints evenly across the usable range
    count = len(missing_hints)
    injections = []

    for i, hint in enumerate(missing_hints):
        title = hint.get('title', '').strip()
        level = hint.get('level', 2)
        if not title:
            continue

        # Check if this is an epilogue/conclusion (place near the end)
        is_epilogue = bool(re.match(r'(?i)^(epilogue|conclusion|afterword)', title))

        if is_epilogue:
            target_idx = int(total_paras * 0.93)
        else:
            # Distribute evenly across the usable range
            position_fraction = i / count if count > 1 else 0.5
            target_idx = start_para + int(position_fraction * usable_range)

        target_idx = max(0, min(target_idx, total_paras))
        injections.append((target_idx, title, level))
        log(f"  [inject] placing at para {target_idx} ({target_idx*100//total_paras}%): {title[:60]}")

    # Sort descending to insert bottom-up (avoids index shifting)
    injections.sort(key=lambda x: x[0], reverse=True)

    injected = 0
    for target_idx, title, level in injections:
        paras.insert(target_idx, title)
        heading_dict['parts'] = [x + 1 if x >= target_idx else x for x in heading_dict['parts']]
        heading_dict['chapters'] = [x + 1 if x >= target_idx else x for x in heading_dict['chapters']]
        if level == 1:
            heading_dict['parts'].append(target_idx)
        else:
            heading_dict['chapters'].append(target_idx)
        injected += 1

    heading_dict['parts'] = sorted(heading_dict['parts'])
    heading_dict['chapters'] = sorted(heading_dict['chapters'])
    log(f"  Injected {injected}/{len(missing_hints)} chapter headings via even distribution")
    return paras, heading_dict


def format_output_with_levels(paragraphs, heading_dict):
    """Build text with ALL-CAPS headings and extra whitespace for parts."""
    part_set    = set(heading_dict.get('parts', []))
    chapter_set = set(heading_dict.get('chapters', []))
    parts = []

    for i, p in enumerate(paragraphs):
        if i in part_set:
            # Extra blank lines around part headings for TTS pauses
            parts.append("\n\n" + p.upper() + "\n")
        elif i in chapter_set:
            parts.append(p.upper())
        else:
            parts.append(p)

    return "\n\n".join(parts)


def map_bookmarks_to_paragraphs(paragraphs, bookmarks, log):
    """Map PDF bookmarks to paragraph positions using page markers."""
    if not bookmarks:
        return paragraphs, {'parts': [], 'chapters': []}

    # Build page -> paragraph index mapping from markers
    page_to_para = {}
    marker_indices = []
    for i, p in enumerate(paragraphs):
        m = re.match(r'^<<PAGE:(\d+)>>$', p.strip())
        if m:
            page_num = int(m.group(1))
            page_to_para[page_num] = i
            marker_indices.append(i)

    log(f"  Page markers found: {len(page_to_para)} (pages {min(page_to_para.keys()) if page_to_para else '?'}-{max(page_to_para.keys()) if page_to_para else '?'})")

    # Remove page markers from paragraph list (work backwards to preserve indices)
    for i in sorted(marker_indices, reverse=True):
        paragraphs.pop(i)

    # Adjust page_to_para indices after marker removal
    # Each removed marker before a given index shifts it down by 1
    sorted_markers = sorted(marker_indices)
    adjusted_page_to_para = {}
    for page, para_idx in page_to_para.items():
        offset = sum(1 for m_idx in sorted_markers if m_idx < para_idx)
        adjusted_page_to_para[page] = para_idx - offset
    page_to_para = adjusted_page_to_para

    # Also strip any page markers that got merged into paragraph text
    for i in range(len(paragraphs)):
        if '<<PAGE:' in paragraphs[i]:
            paragraphs[i] = re.sub(r'\s*<<PAGE:\d+>>\s*', ' ', paragraphs[i]).strip()

    # Place bookmarks at their page positions
    heading_dict = {'parts': [], 'chapters': []}
    insertions = []  # (para_index, title, level)

    sorted_pages = sorted(page_to_para.keys())

    for bm in bookmarks:
        page = bm['page']
        title = bm['title']
        level = bm['level']

        # Find the closest page marker at or before this page
        target_para = None
        for p in sorted(sorted_pages, reverse=True):
            if p <= page:
                target_para = page_to_para[p]
                break

        # If the bookmark's exact page has no marker, it may be an image-only
        # title page (decorative chapter opener). Check the NEXT page(s) for
        # a marker — the actual chapter text starts on the following page.
        if page not in page_to_para:
            for next_p in sorted_pages:
                if next_p > page:
                    next_para = page_to_para[next_p]
                    if target_para is None or next_para > target_para:
                        target_para = next_para
                        log(f"    (page {page} has no marker — using next page {next_p} -> para {target_para})")
                    break

        if target_para is None:
            target_para = 0

        insertions.append((target_para, title, level, bm['page']))
        log(f"  [bookmark] page {page} -> para {target_para}: {title[:60]}")

    # Content-alignment pass: adjust insertion positions by searching forward
    # from the page-start paragraph to find where the actual section begins.
    # PDF bookmarks point to pages, not paragraphs. When a chapter starts
    # mid-page, the page-start position is still in the previous chapter's text.

    def _norm_bm(text):
        """Normalize bookmark/paragraph text for fuzzy comparison."""
        t = text.strip()
        # Strip markdown heading markers
        t = re.sub(r'^#+\s*', '', t)
        # Strip leading roman numerals with separators: "I.—", "IV. ", "III--"
        t = re.sub(r'^[IVXLC]+[\.\-\—\–:]+\s*', '', t)
        # Strip leading arabic numbers: "1. ", "10) ", "33. "
        t = re.sub(r'^\d+[\.\)\-:]+\s*', '', t)
        # Strip "Chapter " prefix
        t = re.sub(r'^Chapter\s+\d*[\.\s]*', '', t, flags=re.IGNORECASE)
        # Normalize unicode dashes/quotes to ASCII
        t = t.replace('\u2014', '-').replace('\u2013', '-')
        t = t.replace('\u2018', "'").replace('\u2019', "'")
        t = t.replace('\u201c', '"').replace('\u201d', '"')
        # Unify all quote types to a single form for comparison
        t = t.replace('"', "'").replace('`', "'")
        return t.lower().strip()

    # Build sorted page list for search window calculation
    sorted_pages = sorted(page_to_para.keys())

    aligned = []
    for orig_para, title, level, page in insertions:
        # Calculate search window: from page start to next page start
        page_idx = sorted_pages.index(page) if page in sorted_pages else -1
        if page_idx >= 0 and page_idx + 1 < len(sorted_pages):
            next_page = sorted_pages[page_idx + 1]
            window_end = page_to_para[next_page]
        else:
            window_end = min(orig_para + 40, len(paragraphs))

        # Extend window one more page for bookmarks near page boundaries
        if page_idx >= 0 and page_idx + 2 < len(sorted_pages):
            next_next_page = sorted_pages[page_idx + 2]
            window_end = max(window_end, page_to_para[next_next_page])

        norm_title = _norm_bm(title)
        best_idx = None
        best_quality = -1

        if len(norm_title) >= 3:
            for k in range(orig_para, min(window_end, len(paragraphs))):
                para_text = paragraphs[k].strip()
                if not para_text or len(para_text) > 200:
                    continue

                norm_para = _norm_bm(para_text)
                if len(norm_para) < 3:
                    continue

                # Exact match after normalization
                if norm_para == norm_title:
                    best_idx = k
                    best_quality = 4
                    break

                # ALL-CAPS version: normalize the CAPS paragraph and compare
                if para_text.upper() == para_text and len(para_text) > 5:
                    norm_caps = _norm_bm(para_text)
                    if norm_caps == norm_title:
                        best_idx = k
                        best_quality = 3
                        break

                # Prefix match: paragraph starts with 60%+ of normalized title
                min_prefix = max(3, int(len(norm_title) * 0.6))
                if len(norm_title) >= 5 and norm_para.startswith(norm_title[:min_prefix]):
                    if best_quality < 2:
                        best_idx = k
                        best_quality = 2

                # Title starts with paragraph (short heading in body)
                if len(norm_para) >= 5 and norm_title.startswith(norm_para[:min_prefix]):
                    if best_quality < 1:
                        best_idx = k
                        best_quality = 1

                # Containment: title's key words found in a short paragraph
                # Handles "its relation to creation" in "the relation of the godhead to creation"
                if len(norm_title) >= 8 and len(norm_para) < 120:
                    title_words = set(norm_title.split())
                    para_words = set(norm_para.split())
                    # At least 60% of title words must appear in the paragraph
                    overlap = len(title_words & para_words)
                    if len(title_words) >= 3 and overlap >= len(title_words) * 0.6:
                        if best_quality < 1:
                            best_idx = k
                            best_quality = 1

        if best_idx is not None and best_idx != orig_para:
            log(f"    -> aligned to para {best_idx} (was {orig_para}, Q{best_quality})")
            # Replace matched paragraph with the bookmark title (proper casing)
            paragraphs[best_idx] = title
            aligned.append((best_idx, title, level))
        else:
            aligned.append((orig_para, title, level))

    # Separate aligned (in-place replacement) from unaligned (need insertion)
    aligned_in_place = []   # (para_idx, title, level) — body para already replaced
    need_insert = []        # (para_idx, title, level, orig_order) — need insertion
    align_count = 0

    for i, ((orig_para, title, level, page), (final_para, _, _)) in enumerate(zip(insertions, aligned)):
        if final_para != orig_para:
            # Aligned: body paragraph at final_para already has the title text
            aligned_in_place.append((final_para, title, level))
            align_count += 1
        else:
            need_insert.append((orig_para, title, level, i))

    if align_count:
        log(f"  Content-aligned {align_count} bookmarks to body paragraph positions")

    # Record aligned headings directly (no insertion needed)
    for para_idx, title, level in aligned_in_place:
        if level == 1:
            heading_dict['parts'].append(para_idx)
        else:
            heading_dict['chapters'].append(para_idx)

    # --- Collision resolution ---
    # When page markers are sparse, multiple bookmarks map to the same paragraph.
    # Resolve by searching forward from the collision point to find each bookmark's
    # actual chapter start in the body text.
    if need_insert:
        # Sort by target para then original PDF order for collision detection
        need_insert.sort(key=lambda x: (x[0], x[3]))
        collision_resolved = 0

        # Group by target paragraph to find collisions
        i = 0
        while i < len(need_insert):
            group = [need_insert[i]]
            while i + 1 < len(need_insert) and abs(need_insert[i + 1][0] - need_insert[i][0]) <= 2:
                i += 1
                group.append(need_insert[i])
            i += 1

            if len(group) < 2:
                continue

            # First bookmark in the group keeps its position
            search_from = group[0][0] + 1
            for g_idx in range(1, len(group)):
                target, title, level, orig_order = group[g_idx]
                best_match = None

                # Search forward for a paragraph matching this bookmark's title.
                # Use BOTH full title and normalized title (some PDFs strip "Chapter").
                full_title_lower = title.strip().lower()
                norm_title = _norm_bm(title)
                search_limit = min(search_from + 500, len(paragraphs))

                for k in range(search_from, search_limit):
                    para_text = paragraphs[k].strip()
                    if not para_text or len(para_text) > 200:
                        continue

                    para_lower = para_text.lower()

                    # Full title match (case-insensitive) — catches "Chapter Two"
                    if para_lower == full_title_lower:
                        best_match = k
                        break

                    # Full title contained in short paragraph
                    if len(para_text) < 80 and full_title_lower in para_lower:
                        best_match = k
                        break

                    # Normalized match
                    norm_para = _norm_bm(para_text)
                    if len(norm_para) >= 3 and len(norm_title) >= 3:
                        if norm_para == norm_title:
                            best_match = k
                            break
                        min_prefix = max(3, int(len(norm_title) * 0.6))
                        if len(norm_title) >= 5 and norm_para.startswith(norm_title[:min_prefix]):
                            best_match = k
                            break
                        # Word overlap
                        if len(norm_title) >= 8 and len(norm_para) < 120:
                            title_words = set(norm_title.split())
                            para_words = set(norm_para.split())
                            if len(title_words) >= 3 and len(title_words & para_words) >= len(title_words) * 0.6:
                                best_match = k
                                break

                if best_match is not None and best_match != target:
                    # Replace the matched paragraph with the title
                    paragraphs[best_match] = title
                    # Move from need_insert to aligned_in_place
                    if level == 1:
                        heading_dict['parts'].append(best_match)
                    else:
                        heading_dict['chapters'].append(best_match)
                    need_insert[need_insert.index(group[g_idx])] = None  # mark for removal
                    search_from = best_match + 1
                    collision_resolved += 1
                    log(f"    [collision fix] '{title[:50]}' relocated to para {best_match} (was {target})")
                else:
                    # No title match found — keep original position, log warning
                    log(f"    [collision warn] '{title[:50]}' — no body match found, keeping at {target}")
                    search_from = target + 1

        # Remove resolved entries (marked as None)
        need_insert = [x for x in need_insert if x is not None]

        if collision_resolved:
            log(f"  Resolved {collision_resolved} bookmark collision(s)")

    # Sort unaligned insertions descending by para index for bottom-up insertion.
    # For same-index bookmarks: include original PDF outline order (i) in the sort
    # key so that higher-i items are inserted first, and subsequent lower-i items
    # push them down, restoring the correct PDF outline sequence.
    need_insert.sort(key=lambda x: (x[0], x[3]), reverse=True)

    for target_para, title, level, _ in need_insert:
        paragraphs.insert(target_para, title)
        # Shift ALL existing heading indices (both aligned and inserted)
        heading_dict['parts'] = [x + 1 if x >= target_para else x for x in heading_dict['parts']]
        heading_dict['chapters'] = [x + 1 if x >= target_para else x for x in heading_dict['chapters']]
        if level == 1:
            heading_dict['parts'].append(target_para)
        else:
            heading_dict['chapters'].append(target_para)

    heading_dict['parts'] = sorted(heading_dict['parts'])
    heading_dict['chapters'] = sorted(heading_dict['chapters'])

    # Enforce original bookmark page-order: if content alignment caused two
    # bookmarks to swap order (earlier-page bookmark got a later paragraph index),
    # swap their paragraph contents to restore the original sequence.
    all_heading_indices = sorted(heading_dict['parts'] + heading_dict['chapters'])
    # Build page-order list of (bookmark_title, bookmark_page) from the original bookmarks
    bm_by_title = {}
    for bm in bookmarks:
        bm_by_title[bm['title'].strip()] = bm['page']
    # Check each consecutive pair of headings for order violations
    for h in range(len(all_heading_indices) - 1):
        idx_a = all_heading_indices[h]
        idx_b = all_heading_indices[h + 1]
        if idx_a >= len(paragraphs) or idx_b >= len(paragraphs):
            continue
        title_a = paragraphs[idx_a].strip()
        title_b = paragraphs[idx_b].strip()
        page_a = bm_by_title.get(title_a)
        page_b = bm_by_title.get(title_b)
        if page_a is not None and page_b is not None and page_a > page_b:
            # title_a has a later page but earlier paragraph — swap content
            paragraphs[idx_a], paragraphs[idx_b] = paragraphs[idx_b], paragraphs[idx_a]
            log(f"  [order fix] swapped '{title_a[:40]}' and '{title_b[:40]}' to match page order")

    # Heuristic L2 -> L1 promotion for major work divisions.
    # In some PDFs (e.g., CCEL digitizations), major sections like
    # "Introduction", "The Divine Names" are L2 alongside their sub-chapters.
    # Promote an L2 bookmark to L1 when ALL conditions are met:
    #   - 20+ total bookmarks (complex book with likely nested structure)
    #   - title doesn't start with a number or "Chapter"
    #   - title doesn't match front/back matter patterns
    #   - followed by 3+ consecutive L2 bookmarks before the next candidate
    total_bookmarks = len(bookmarks)
    if total_bookmarks > 20:
        _fm_bm_patterns = re.compile(
            r'^(Cover|Contents|Table of Contents|Index|Bibliography|Preface|'
            r'Acknowledgm|Title Page|About|Copyright|Dedication|Appendix|'
            r'Glossar|Abbreviat|Foreword|List of|Notes|Endnotes)',
            re.IGNORECASE
        )
        _numbered_start = re.compile(r'^(\d+[\.\):]?\s|Chapter\s)', re.IGNORECASE)

        # Work on ordered bookmark list to check "followed by 3+ L2" condition
        l2_indices_in_bm = []  # indices into bookmarks[] that are L2
        for bi, bm in enumerate(bookmarks):
            if bm['level'] != 1:
                l2_indices_in_bm.append(bi)

        # Build set of L1 "Part" bookmark indices for the guard below
        _part_bm_indices = set()
        _first_part_bi = None
        for bi2, bm2 in enumerate(bookmarks):
            if bm2['level'] == 1 and re.match(r'^Part\b', bm2['title'].strip(), re.IGNORECASE):
                _part_bm_indices.add(bi2)
                if _first_part_bi is None:
                    _first_part_bi = bi2

        promoted = []
        for pos, bi in enumerate(l2_indices_in_bm):
            title = bookmarks[bi]['title'].strip()
            # Skip numbered/chapter headings
            if _numbered_start.match(title):
                continue
            # Skip front/back matter
            if _fm_bm_patterns.match(title):
                continue
            # Guard: NEVER promote an L2 that appears BEFORE the first Part heading.
            # Bookmarks before the first Part are introductory material, not Part-level.
            if _first_part_bi is not None and bi < _first_part_bi:
                continue
            # Guard: NEVER promote an L2 that follows a Part heading.
            # An L2 after a Part is correctly nested as a chapter within that part.
            preceding_l1 = None
            for check_bi in range(bi - 1, -1, -1):
                if bookmarks[check_bi]['level'] == 1:
                    preceding_l1 = check_bi
                    break
            if preceding_l1 is not None and preceding_l1 in _part_bm_indices:
                continue
            # Count consecutive L2 bookmarks following this one
            followers = 0
            for next_pos in range(pos + 1, len(l2_indices_in_bm)):
                next_bi = l2_indices_in_bm[next_pos]
                next_title = bookmarks[next_bi]['title'].strip()
                # Stop counting if we hit another promotion candidate
                if (not _numbered_start.match(next_title) and
                    not _fm_bm_patterns.match(next_title) and
                    next_bi == l2_indices_in_bm[next_pos]):
                    # Check if this next item also qualifies as a section head
                    # by having 3+ followers itself — if so, it's the next group
                    remaining = len(l2_indices_in_bm) - next_pos - 1
                    if remaining >= 3:
                        break
                followers += 1
            if followers >= 3:
                promoted.append((bi, title))

        # Apply promotions
        if promoted:
            for bi, title in promoted:
                # Find the heading index in paragraphs for this bookmark
                for idx in heading_dict['chapters'][:]:
                    if idx < len(paragraphs) and paragraphs[idx].strip() == title.strip():
                        heading_dict['chapters'].remove(idx)
                        heading_dict['parts'].append(idx)
                        log(f"  [promote L2->L1] '{title[:60]}' (followed by 3+ sub-items)")
                        break
            heading_dict['parts'] = sorted(heading_dict['parts'])

    # Heuristic L1 -> L2 demotion for numbered bookmarks that belong in a sequence.
    # Some PDFs (e.g., CCEL) wrongly mark one numbered item as L1 when siblings
    # are L2. E.g., "10. Bibliography" at L1 while "1. The Author" through
    # "9. Conclusion" are all L2. Demote if:
    #   - Title starts with a number (like "10." or "10)")
    #   - Other numbered titles in the sequence exist at L2
    if heading_dict['parts']:
        _num_prefix = re.compile(r'^(\d+)[\.\):\s]')
        # Collect numbered parts and numbered chapters
        numbered_parts = []  # (paragraph_index, number, title)
        for idx in heading_dict['parts']:
            if idx < len(paragraphs):
                title = paragraphs[idx].strip()
                m = _num_prefix.match(title)
                if m:
                    numbered_parts.append((idx, int(m.group(1)), title))

        numbered_chapters = set()
        for idx in heading_dict['chapters']:
            if idx < len(paragraphs):
                title = paragraphs[idx].strip()
                m = _num_prefix.match(title)
                if m:
                    numbered_chapters.add(int(m.group(1)))

        demoted = []
        for idx, num, title in numbered_parts:
            # Check if other numbers in the sequence exist as L2 chapters
            nearby_in_chapters = sum(1 for n in numbered_chapters if abs(n - num) <= num)
            if nearby_in_chapters >= 2:
                demoted.append((idx, title))

        for idx, title in demoted:
            heading_dict['parts'].remove(idx)
            heading_dict['chapters'].append(idx)
            log(f"  [demote L1->L2] '{title[:60]}' (other numbered items in sequence are L2)")
        if demoted:
            heading_dict['chapters'] = sorted(heading_dict['chapters'])

    total = len(heading_dict['parts']) + len(heading_dict['chapters'])
    log(f"  Placed {total} bookmarks as chapter headings")
    return paragraphs, heading_dict


def ai_detect_subheadings(paragraphs, log, api_key=None, bookmark_titles=None, heading_indices=None, has_bookmarks=True):
    """
    AI Quality Pass Phase 3 — Sub-heading Detection.

    Identifies section sub-headings extracted as plain paragraphs and
    promotes them to ### (h3) format for Kindle TOC third-level nesting.
    Only activates for books WITHOUT PDF bookmarks.
    """
    _empty_stats = {}
    if has_bookmarks:
        log("  AI Sub-headings: skipped (book has PDF bookmarks — using bookmark TOC structure)")
        return paragraphs, _empty_stats

    import os as _os

    key = api_key or _os.environ.get('ANTHROPIC_API_KEY', '')
    _empty_stats = {}
    if not key:
        log("  AI Sub-headings: skipped (no API key)")
        return paragraphs, _empty_stats
    try:
        import requests as _requests
    except ImportError:
        log("  AI Sub-headings: skipped (requests library not installed)")
        return paragraphs, _empty_stats

    _h_indices = heading_indices or set()
    _bm_titles = set()
    if bookmark_titles:
        for t in bookmark_titles:
            _bm_titles.add(t.strip().lower())

    # Citation/bibliography pattern to exclude
    _cite_pattern = re.compile(
        r'\b(pp?\.\s*\d|vol\.\s*\d|\d{4}[a-z]?\)|eds?\.\s|trans\.\s|'
        r'University Press|Cambridge:|Oxford:|New York:)', re.IGNORECASE
    )

    # --- Step 1: Heuristic pre-filter ---
    candidates = []
    for i, p in enumerate(paragraphs):
        text = p.strip()
        if not text or len(text) < 10 or len(text) > 100:
            continue
        if text.startswith('#'):
            continue
        if i in _h_indices:
            continue
        # Skip if it's a known bookmark title
        if text.lower() in _bm_titles:
            continue
        # Skip if ends with sentence-ending punctuation
        if text[-1] in '.!?;':
            continue
        # Skip bibliography/citation patterns
        if _cite_pattern.search(text):
            continue

        # Must be followed by a body paragraph (100+ chars)
        has_body_after = False
        for j in range(i + 1, min(i + 3, len(paragraphs))):
            nxt = paragraphs[j].strip()
            if nxt and not nxt.startswith('#') and len(nxt) > 100:
                has_body_after = True
                break
        if not has_body_after:
            continue

        # Priority signals
        is_all_caps = text == text.upper() and any(c.isalpha() for c in text)
        is_title_case = text == text.title() or (text[0].isupper() and sum(1 for w in text.split() if w[0].isupper()) > len(text.split()) * 0.6)
        has_colon = ':' in text and len(text.split(':')[0]) < 40
        # Preceded by sentence-ending punctuation (natural break)
        preceded_by_break = False
        if i > 0:
            prev = paragraphs[i - 1].strip()
            if prev and prev[-1] in '.!?"\u201d':
                preceded_by_break = True

        priority = sum([is_all_caps, is_title_case, has_colon, preceded_by_break])

        candidates.append({
            'index': i,
            'text': text,
            'priority': priority,
            'context_before': paragraphs[i - 1].strip()[-100:] if i > 0 else '',
            'context_after': paragraphs[i + 1].strip()[:100] if i + 1 < len(paragraphs) else '',
        })

    if not candidates:
        log("  AI Sub-headings: no candidates detected")
        return paragraphs, _empty_stats

    # Sort by priority descending, cap at 100 candidates (5 API calls × 20)
    candidates.sort(key=lambda c: c['priority'], reverse=True)
    total_candidates = len(candidates)
    max_candidates = 100
    if len(candidates) > max_candidates:
        candidates = candidates[:max_candidates]

    _model = _load_api_model("haiku")
    log(f"  AI Sub-headings: using model={_model}")
    log(f"  AI Sub-headings: {total_candidates} candidates detected"
        + (f" (processing top {len(candidates)})" if total_candidates > max_candidates else ""))

    # --- Step 2: Send to Claude API for verification ---
    batch_size = 20
    confirmed_headings = []

    for batch_start in range(0, len(candidates), batch_size):
        batch = candidates[batch_start:batch_start + batch_size]
        batch_text = "\n\n".join(
            f"[Candidate {j}] (paragraph {c['index']})\n"
            f"PRECEDING: ...{c['context_before']}\n"
            f">>> {c['text']}\n"
            f"FOLLOWING: {c['context_after']}..."
            for j, c in enumerate(batch)
        )

        prompt = f"""Analyze these {len(batch)} candidate paragraphs from a book. For each, determine if it is a section sub-heading (introducing a new topic or section) or regular body text.

{batch_text}

A section heading is typically:
- Short and descriptive (like a title)
- ALL CAPS or Title Case
- Followed by body text on a new topic
- NOT a sentence fragment, quote, or citation

Return a JSON object with:
- "headings": array of objects, each with:
  - "index": candidate index (0-based in this batch)
  - "is_heading": boolean
  - "confidence": "high", "medium", or "low"
  - "heading_text": the cleaned heading text (only if is_heading is true)"""

        try:
            resp = _requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "content-type": "application/json",
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": _model,
                    "max_tokens": 1500,
                    "temperature": 0,
                    "system": (
                        "You are analyzing paragraphs from a book to identify section "
                        "sub-headings extracted as plain text. Return ONLY valid JSON, "
                        "no markdown or explanation."
                    ),
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=30,
            )
            resp.raise_for_status()
            body = resp.json()
            content_text = body['content'][0]['text'].strip()
            if content_text.startswith('```'):
                content_text = content_text.split('\n', 1)[1] if '\n' in content_text else content_text[3:]
                if content_text.endswith('```'):
                    content_text = content_text[:-3]
                content_text = content_text.strip()
            result = json.loads(content_text)

            for h in result.get('headings', []):
                idx = h.get('index', -1)
                if 0 <= idx < len(batch) and h.get('is_heading') and h.get('confidence') in ('high', 'medium'):
                    candidate = batch[idx]
                    heading_text = h.get('heading_text', candidate['text'])
                    confirmed_headings.append({
                        'para_index': candidate['index'],
                        'heading_text': heading_text,
                        'confidence': h['confidence'],
                    })

        except Exception as e:
            log(f"  AI Sub-headings: API call failed ({e}) — skipping batch")
            continue

    # --- Step 3: Apply heading promotion ---
    subheadings_detected = 0
    for h in confirmed_headings:
        idx = h['para_index']
        if idx < len(paragraphs):
            paragraphs[idx] = f"### {h['heading_text']}"
            subheadings_detected += 1
            log(f"  [subheading] para {idx}: '{h['heading_text']}'")

    subheadings_skipped = total_candidates - subheadings_detected
    log(f"  AI Sub-headings: {subheadings_detected}/{total_candidates} headings promoted to h3 "
        f"({subheadings_skipped} skipped)")

    subheading_stats = {
        'subheading_candidates': total_candidates,
        'subheadings_detected': subheadings_detected,
        'subheadings_skipped': subheadings_skipped,
    }

    return paragraphs, subheading_stats


def ai_rejoin_fragments(paragraphs, log, api_key=None, heading_indices=None):
    """
    AI-powered paragraph rejoining for page-boundary truncation.

    Detects candidate fragment pairs (truncated paragraph + continuation),
    sends to Claude API for verification, and joins confirmed pairs.
    Runs AFTER fix_ocr_artifacts() but BEFORE chapter heading detection.
    """
    import os as _os
    import statistics

    key = api_key or _os.environ.get('ANTHROPIC_API_KEY', '')
    _empty_stats = {}
    if not key:
        log("  AI Rejoin: skipped (no API key)")
        return paragraphs, _empty_stats
    try:
        import requests as _requests
    except ImportError:
        log("  AI Rejoin: skipped (requests library not installed)")
        return paragraphs, _empty_stats

    _h_indices = heading_indices or set()

    # --- Step 1: Detect candidate fragment pairs ---
    # Calculate median paragraph length for relative-length check
    para_lengths = [len(p.strip()) for p in paragraphs if p.strip() and not p.strip().startswith('#') and len(p.strip()) > 30]
    if len(para_lengths) < 10:
        log("  AI Rejoin: skipped (too few paragraphs)")
        return paragraphs, _empty_stats
    median_len = statistics.median(para_lengths)

    # Continuation-start words
    _cont_words = {
        'and', 'or', 'but', 'which', 'that', 'who', 'whom', 'where', 'when',
        'because', 'however', 'therefore', 'moreover', 'furthermore', 'thus',
        'nevertheless', 'although', 'though', 'while', 'since', 'unless',
        'yet', 'so', 'nor', 'for', 'as', 'than', 'whether', 'after',
        'before', 'until', 'once', 'whereas', 'whereby', 'therein',
    }

    candidates = []
    for i in range(len(paragraphs) - 1):
        para_a = paragraphs[i].strip()
        para_b = paragraphs[i + 1].strip()

        # Skip headings, empty, very short
        if not para_a or not para_b or len(para_a) < 10 or len(para_b) < 10:
            continue
        if para_a.startswith('#') or para_b.startswith('#'):
            continue
        if i in _h_indices or (i + 1) in _h_indices:
            continue

        # Check if para_a looks truncated
        is_truncated = False
        reason = ''

        # Ends mid-word (letter with no punctuation)
        if para_a[-1].isalpha() and not para_a.endswith(('etc', 'Jr', 'Sr', 'Dr', 'Mr', 'Mrs', 'Ms', 'St', 'vs')):
            last_word = para_a.split()[-1] if para_a.split() else ''
            if len(last_word) < 12:  # short last word = likely truncated
                is_truncated = True
                reason = 'ends mid-word'

        # Ends with opening quote never closed
        if not is_truncated and para_a.count('"') % 2 == 1 and para_a.rstrip()[-1] == '"':
            is_truncated = True
            reason = 'unclosed quote'

        # Ends with conjunction/comma/semicolon
        if not is_truncated:
            last_token = para_a.rstrip().rstrip('"\'').rstrip()
            if last_token and last_token[-1] in (',', ';'):
                is_truncated = True
                reason = f'ends with {last_token[-1]}'
            last_word_lower = para_a.split()[-1].lower().rstrip('.,;:') if para_a.split() else ''
            if last_word_lower in ('and', 'or', 'but', 'that', 'which', 'the', 'a', 'an', 'of', 'in', 'to', 'for'):
                is_truncated = True
                reason = f'ends with "{last_word_lower}"'

        # Short paragraph without terminal punctuation
        if not is_truncated and len(para_a) < median_len * 0.4:
            if para_a[-1] not in '.!?:"\u201d':
                is_truncated = True
                reason = 'short + no terminal punct'

        # Ends with hyphen
        if not is_truncated and para_a.rstrip()[-1] == '-':
            is_truncated = True
            reason = 'ends with hyphen'

        if not is_truncated:
            continue

        # Check if para_b looks like a continuation
        is_continuation = False
        first_char = para_b[0] if para_b else ''
        first_word = para_b.split()[0].lower().rstrip('.,;:') if para_b.split() else ''

        if first_char.islower():
            is_continuation = True
        elif first_word in _cont_words:
            is_continuation = True
        elif first_char in (')', ']', '\u201d', '"'):
            is_continuation = True
        # If para_a ends mid-word, any continuation is valid
        elif reason == 'ends mid-word':
            is_continuation = True

        if is_continuation:
            candidates.append({
                'index_a': i,
                'index_b': i + 1,
                'end_a': para_a[-200:],
                'start_b': para_b[:200],
                'reason': reason,
            })

    if not candidates:
        log("  AI Rejoin: no candidate fragment pairs detected")
        return paragraphs, _empty_stats

    # Cap at 150 candidates (10 API calls × 15 pairs)
    total_candidates = len(candidates)
    max_candidates = 150
    remaining_beyond_cap = max(0, total_candidates - max_candidates)
    if len(candidates) > max_candidates:
        candidates = candidates[:max_candidates]

    _model = _load_api_model("haiku")
    log(f"  AI Rejoin: using model={_model}")
    log(f"  AI Rejoin: {total_candidates} candidate pairs detected"
        + (f" (processing first {len(candidates)}, {remaining_beyond_cap} beyond cap)" if remaining_beyond_cap else ""))

    # --- Step 2: Send candidates to Claude API for verification ---
    batch_size = 15
    all_joins = []

    for batch_start in range(0, len(candidates), batch_size):
        batch = candidates[batch_start:batch_start + batch_size]
        batch_text = "\n\n".join(
            f"[Pair {j}] (reason: {c['reason']})\n"
            f"END OF PARAGRAPH {c['index_a']}:\n...{c['end_a']}\n"
            f"START OF PARAGRAPH {c['index_b']}:\n{c['start_b']}..."
            for j, c in enumerate(batch)
        )

        prompt = f"""These {len(batch)} paragraph pairs were split at PDF page boundaries during text extraction. For each pair, determine if Paragraph B is a continuation of Paragraph A (they should be joined) or if they are intentionally separate paragraphs.

{batch_text}

Return a JSON object with:
- "joins": array of objects, each with:
  - "pair_index": integer (0-based index in this batch)
  - "should_join": boolean
  - "confidence": "high", "medium", or "low"

Only mark should_join as true when you are confident the paragraphs were split mid-sentence or mid-thought by a page break. Separate paragraphs that happen to have related content should NOT be joined."""

        try:
            resp = _requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "content-type": "application/json",
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": _model,
                    "max_tokens": 1500,
                    "temperature": 0,
                    "system": (
                        "You are a text extraction repair tool. Determine if paragraph "
                        "pairs were split at page boundaries and should be rejoined. "
                        "Return ONLY valid JSON, no markdown or explanation."
                    ),
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=30,
            )
            resp.raise_for_status()
            body = resp.json()
            content_text = body['content'][0]['text'].strip()
            if content_text.startswith('```'):
                content_text = content_text.split('\n', 1)[1] if '\n' in content_text else content_text[3:]
                if content_text.endswith('```'):
                    content_text = content_text[:-3]
                content_text = content_text.strip()
            result = json.loads(content_text)
            joins = result.get('joins', [])

            for join_info in joins:
                pair_idx = join_info.get('pair_index', -1)
                if 0 <= pair_idx < len(batch):
                    candidate = batch[pair_idx]
                    candidate['should_join'] = join_info.get('should_join', False)
                    candidate['confidence'] = join_info.get('confidence', 'low')
                    all_joins.append(candidate)

        except Exception as e:
            log(f"  AI Rejoin: API call failed ({e}) — skipping batch")
            continue

    # --- Step 3: Apply joins (bottom to top) ---
    joins_to_apply = [
        c for c in all_joins
        if c.get('should_join') and c.get('confidence') in ('high', 'medium')
    ]
    # Sort by index_b descending so joining doesn't shift remaining indices
    joins_to_apply.sort(key=lambda c: c['index_b'], reverse=True)

    # Prevent overlapping joins (if para X is in two pairs, only join the first)
    used_indices = set()
    filtered_joins = []
    for c in joins_to_apply:
        if c['index_a'] not in used_indices and c['index_b'] not in used_indices:
            filtered_joins.append(c)
            used_indices.add(c['index_a'])
            used_indices.add(c['index_b'])
    joins_to_apply = filtered_joins

    rejoin_applied = 0
    for c in joins_to_apply:
        idx_a = c['index_a']
        idx_b = c['index_b']
        para_a = paragraphs[idx_a].rstrip()
        para_b = paragraphs[idx_b].lstrip()

        # Join: strip hyphen if para_a ends with one, otherwise space-join
        if para_a.endswith('-'):
            joined = para_a[:-1] + para_b
        else:
            joined = para_a + ' ' + para_b

        paragraphs[idx_a] = joined
        paragraphs[idx_b] = ''  # empty the continuation paragraph
        rejoin_applied += 1
        end_preview = para_a[-40:].replace('\n', ' ')
        start_preview = para_b[:40].replace('\n', ' ')
        log(f"  [rejoin] para {idx_a}+{idx_b}: '...{end_preview}' + '{start_preview}...'")

    rejoin_skipped = len(all_joins) - rejoin_applied
    log(f"  AI Rejoin: {rejoin_applied}/{total_candidates} fragments rejoined "
        f"({rejoin_skipped} skipped"
        + (f", {remaining_beyond_cap} beyond cap)" if remaining_beyond_cap else ")"))

    rejoin_stats = {
        'rejoin_candidates': total_candidates,
        'rejoin_applied': rejoin_applied,
        'rejoin_skipped': rejoin_skipped,
        'rejoin_beyond_cap': remaining_beyond_cap,
    }

    return paragraphs, rejoin_stats


def ai_quality_pass(paragraphs, log, api_key=None, apply_fixes=False):
    """
    AI Quality Pass — detection and optional fix application.

    Samples paragraphs, sends to Claude API for quality analysis.
    Returns (paragraphs, quality_report_dict).

    When apply_fixes=False (default): detection only — scores and reports
    issues but does NOT modify paragraphs.
    When apply_fixes=True: applies fixes with guardrails (length check,
    word-overlap check) to prevent content substitution.
    """
    import os as _os

    # Resolve API key
    key = api_key or _os.environ.get('ANTHROPIC_API_KEY', '')
    if not key:
        log("  AI Quality Pass: skipped (no API key)")
        return paragraphs, {}

    try:
        import requests as _requests
    except ImportError:
        log("  AI Quality Pass: skipped (requests library not installed)")
        return paragraphs, {}

    # --- Sampling ---
    # Collect non-empty, non-heading paragraphs with original indices
    candidates = []
    for i, p in enumerate(paragraphs):
        s = p.strip()
        if s and not s.startswith('#') and len(s) > 30:
            candidates.append((i, s))

    if len(candidates) < 5:
        log("  AI Quality Pass: skipped (fewer than 5 eligible paragraphs)")
        return paragraphs, {}

    sample_size = min(20, max(5, int(len(candidates) * 0.10)))

    # Must-include indices within candidates list
    sampled_set = set()
    # First and last
    sampled_set.add(0)
    sampled_set.add(len(candidates) - 1)
    # Longest paragraph
    longest_idx = max(range(len(candidates)), key=lambda x: len(candidates[x][1]))
    sampled_set.add(longest_idx)
    # Shortest over 50 chars
    short_candidates = [x for x in range(len(candidates)) if len(candidates[x][1]) > 50]
    if short_candidates:
        shortest_idx = min(short_candidates, key=lambda x: len(candidates[x][1]))
        sampled_set.add(shortest_idx)

    # 3 from first 5%
    first_5pct = max(1, len(candidates) // 20)
    for j in range(0, min(first_5pct, len(candidates)), max(1, first_5pct // 3)):
        sampled_set.add(j)
        if len(sampled_set) >= 4:
            break

    # 3 from last 5%
    last_start = len(candidates) - first_5pct
    for j in range(max(0, last_start), len(candidates), max(1, first_5pct // 3)):
        sampled_set.add(j)

    # Fill remaining from evenly spaced middle
    remaining = sample_size - len(sampled_set)
    if remaining > 0:
        middle_start = first_5pct
        middle_end = len(candidates) - first_5pct
        if middle_end > middle_start:
            step = max(1, (middle_end - middle_start) // remaining)
            for j in range(middle_start, middle_end, step):
                sampled_set.add(j)
                if len(sampled_set) >= sample_size:
                    break

    # Build sample list with original paragraph indices
    samples = []
    for ci in sorted(sampled_set):
        if ci < len(candidates):
            para_idx, text = candidates[ci]
            samples.append({'paragraph_index': para_idx, 'text': text[:500]})

    _model = _load_api_model("haiku")
    log(f"  AI Quality Pass: using model={_model}")
    log(f"  AI Quality Pass: sampling {len(samples)} of {len(candidates)} paragraphs")

    # --- Rules-based quality gate ---
    # Check sampled paragraphs for known extraction artifacts.
    # If zero regex issues detected, skip the AI call entirely.
    _artifact_patterns = [
        (re.compile(r'(?<=[a-z])(?=[A-Z][a-z])'), 'missing_space'),       # camelCase mid-word splits
        (re.compile(r'\b\w+\s-\s\n?\s*\w+\b'), 'hyphen_split'),           # hyphenated line breaks kept
        (re.compile(r'[\ufb01\ufb02\ufb00\ufb03\ufb04]'), 'ligature_chars'),  # unresolved ligatures
        (re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]'), 'control_chars'),  # control characters
        (re.compile(r'[^\x00-\x7f]{3,}'), 'encoding_garble'),             # 3+ consecutive non-ASCII (potential garble)
        (re.compile(r'\b(\w)\s(\w)\s(\w)\s(\w)\b'), 'spaced_letters'),    # s p a c e d out letters
        (re.compile(r'(\w)\1{4,}'), 'repeated_chars'),                     # 5+ repeated characters
    ]

    _gate_issues = 0
    for s in samples:
        for _pat, _name in _artifact_patterns:
            if _pat.search(s['text']):
                _gate_issues += 1
                break  # one issue per paragraph is enough to count

    if _gate_issues == 0 and not apply_fixes:
        log(f"  AI Quality Pass: rules-based gate passed (0/{len(samples)} sampled paragraphs "
            f"had regex artifacts) — skipping API call")
        return paragraphs, {"gate_skipped": True, "gate_checked": len(samples), "gate_issues": 0}
    elif _gate_issues > 0:
        log(f"  AI Quality Pass: rules-based gate found {_gate_issues}/{len(samples)} paragraphs "
            f"with potential artifacts — proceeding to AI analysis")

    # --- Build API request ---
    sample_text = "\n\n".join(
        f"[Paragraph {s['paragraph_index']}]\n{s['text']}"
        for s in samples
    )

    system_prompt = (
        "You are a PDF text extraction quality checker. Analyze sampled paragraphs "
        "from a book and identify extraction artifacts. Return ONLY valid JSON, "
        "no markdown formatting, code fences, or explanation. "
        "When scoring, focus on body text paragraphs only. Index entries, "
        "bibliographic citations, and footnote references are expected to have "
        "irregular formatting — do not count these as extraction issues. "
        "For orphaned_fragment issues, only suggest fixes that complete a clearly "
        "truncated word (e.g., 'the r' → 'the rock'). NEVER add words or phrases "
        "that aren't clearly implied by the truncation. If you cannot determine "
        "the exact missing characters with high confidence, set fix to null and "
        "flag for manual review."
    )

    user_prompt = f"""Analyze these {len(samples)} paragraphs sampled from a PDF-extracted book. Identify any text extraction artifacts.

{sample_text}

For each issue found in the samples, estimate how many total occurrences likely exist in the full text (the book has {len(candidates)} body paragraphs total, you are seeing {len(samples)} samples). A pattern appearing in multiple samples is likely systematic — estimate higher total occurrences proportionally.

Classify each issue severity:
- "critical": makes text unreadable (garbled text, major content loss, sentences that make no sense)
- "moderate": readable but noticeable (split words like "aft er", orphaned headers, running headers bleeding into text, truncated words)
- "minor": cosmetic only (extra whitespace, minor formatting inconsistencies)

Note: split_word and running_header issues are ALWAYS at least "moderate" severity.

Return a JSON object with:
- "issues": array of objects, each with:
  - "type": one of "split_word", "orphaned_fragment", "footnote_number", "running_header", "garbled_text", "encoding_artifact"
  - "severity": one of "critical", "moderate", "minor"
  - "text": the problematic text (short excerpt)
  - "fix": suggested correction (or null if unclear)
  - "paragraph_index": the paragraph number from the sample
  - "estimated_total_occurrences": integer estimate for the full text
- "recommendations": array of strings with overall suggestions

Do NOT include a "quality_score" field — the score will be calculated separately.
Remember: index entries, bibliographic citations, and footnote references have inherently irregular formatting — do NOT flag these as issues.
Only flag clear extraction artifacts in body text, not the author's original formatting choices."""

    # --- Send API request ---
    try:
        resp = _requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "content-type": "application/json",
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": _model,
                "max_tokens": 2000,
                "temperature": 0,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            },
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        log(f"  AI Quality Pass: API request failed ({e}) — skipping")
        return paragraphs, {}

    # --- Parse response ---
    try:
        body = resp.json()
        content_text = body['content'][0]['text']
        # Strip markdown code fences if present
        content_text = content_text.strip()
        if content_text.startswith('```'):
            content_text = content_text.split('\n', 1)[1] if '\n' in content_text else content_text[3:]
            if content_text.endswith('```'):
                content_text = content_text[:-3]
            content_text = content_text.strip()
        report = json.loads(content_text)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        log(f"  AI Quality Pass: failed to parse API response ({e}) — skipping")
        return paragraphs, {}

    # --- Calculate original score deterministically ---
    import math
    issues = report.get('issues', [])
    recommendations = report.get('recommendations', [])

    def _calc_score(issue_list):
        """Deterministic quality score from issue list."""
        severity_penalty = {'critical': 10, 'moderate': 3, 'minor': 1}
        s = 100.0
        for iss in issue_list:
            sev = iss.get('severity', 'moderate')
            base = severity_penalty.get(sev, 3)
            est = iss.get('estimated_total_occurrences', 1)
            mult = 1.0 + min(0.5, math.log10(max(est, 1)) * 0.25)
            s -= base * mult
        return max(0, min(100, int(round(s))))

    original_score = _calc_score(issues)
    log(f"  AI Quality Pass: original score {original_score}/100, {len(issues)} issue(s)")

    # --- Log scan results ---
    for issue in issues[:20]:
        itype = issue.get('type', '?')
        isev = issue.get('severity', '?')
        itext = issue.get('text', '')[:60]
        ifix = issue.get('fix', '')
        ipara = issue.get('paragraph_index', '?')
        iest = issue.get('estimated_total_occurrences', '?')
        fix_str = f" -> {ifix}" if ifix else ""
        log(f"    [{isev}/{itype}] para {ipara}: \"{itext}\"{fix_str} (est. {iest} total)")
    if len(issues) > 20:
        log(f"    ... and {len(issues) - 20} more issues")
    for rec in recommendations:
        log(f"    [rec] {rec}")

    # --- Detection-only mode: return score and report without modifying text ---
    if not apply_fixes:
        log("  AI Quality Pass: detection only (use --apply-ai-fixes to enable fix application)")
        report['original_score'] = original_score
        report['quality_score'] = original_score
        report['final_score'] = original_score
        report['total_fixes'] = 0
        report['fixes_applied'] = 0
        report['fixes_flagged'] = 0
        return paragraphs, report

    # --- Fix validation guardrails ---
    def _validate_fix(issue_text, fix_text, paragraph_text, log_prefix=""):
        """
        Validate a proposed fix against guardrails to prevent content substitution.

        Returns (is_valid, rejection_reason).
        Guardrails:
        - Length difference: fix must be within 20% of original length
        - Word overlap: at least 60% of fix words must appear in original text
          or surrounding paragraph context
        """
        # Length guardrail: reject if fix length differs by more than 20%
        orig_len = len(issue_text)
        fix_len = len(fix_text)
        if orig_len > 0:
            length_ratio = abs(fix_len - orig_len) / orig_len
            if length_ratio > 0.20:
                return False, f"length change {length_ratio:.0%} exceeds 20% limit ({orig_len} -> {fix_len} chars)"

        # Word-overlap guardrail: at least 60% of fix words must appear
        # in the original issue text or the surrounding paragraph
        fix_words = set(fix_text.lower().split())
        context_words = set(issue_text.lower().split()) | set(paragraph_text.lower().split())
        if fix_words:
            overlap = len(fix_words & context_words) / len(fix_words)
            if overlap < 0.60:
                return False, f"word overlap {overlap:.0%} below 60% threshold"

        return True, ""

    # --- Phase 2: Apply fixes ---
    log("  Phase 2: applying fixes with guardrails (20% length, 60% word overlap)...")
    fixes_applied = 0
    fixes_flagged = 0

    for issue in issues:
        fix_text = issue.get('fix')
        issue_text = issue.get('text', '')
        para_idx = issue.get('paragraph_index')

        if not fix_text or para_idx is None:
            # No fix available — flag for manual review
            issue['applied'] = False
            issue['needs_review'] = True
            fixes_flagged += 1
            itype = issue.get('type', '?')
            log(f"  [AI flag] para {para_idx}: {itype} — needs manual review")
            continue

        # BUG 1 guard: prevent AI hallucination on orphaned_fragment fixes.
        # If the fix adds more than 3 characters beyond the original text,
        # the AI is likely guessing/inventing content rather than completing
        # a clearly truncated word.
        if issue.get('type') == 'orphaned_fragment':
            added_chars = len(fix_text) - len(issue_text)
            if added_chars > 3:
                issue['applied'] = False
                issue['needs_review'] = True
                fixes_flagged += 1
                log(f"  [AI skip] para {para_idx}: orphaned_fragment fix adds {added_chars} chars "
                    f"(>{3} limit) — likely hallucinated, flagging for review")
                continue

        # Safety check: verify the issue text exists in the paragraph
        if para_idx < 0 or para_idx >= len(paragraphs):
            issue['applied'] = False
            issue['needs_review'] = True
            fixes_flagged += 1
            log(f"  [AI flag] para {para_idx}: out of range — skipped")
            continue

        para = paragraphs[para_idx]

        # Guardrail: validate fix before applying (length + word overlap)
        is_valid, rejection_reason = _validate_fix(issue_text, fix_text, para)
        if not is_valid:
            issue['applied'] = False
            issue['needs_review'] = True
            issue['rejection_reason'] = rejection_reason
            fixes_flagged += 1
            log(f"  [AI reject] para {para_idx}: {rejection_reason} "
                f"— '{issue_text[:40]}' → '{fix_text[:40]}'")
            continue

        if issue_text not in para:
            # Try case-insensitive match as fallback
            lower_para = para.lower()
            lower_issue = issue_text.lower()
            if lower_issue in lower_para:
                # Find the actual-case version in the paragraph
                start = lower_para.index(lower_issue)
                actual_text = para[start:start + len(issue_text)]
                paragraphs[para_idx] = para[:start] + fix_text + para[start + len(issue_text):]
                issue['applied'] = True
                issue['needs_review'] = False
                fixes_applied += 1
                log(f"  [AI fix] para {para_idx}: '{actual_text}' → '{fix_text}'")
            else:
                issue['applied'] = False
                issue['needs_review'] = True
                fixes_flagged += 1
                log(f"  [AI flag] para {para_idx}: text '{issue_text[:40]}' not found — skipped")
        else:
            paragraphs[para_idx] = para.replace(issue_text, fix_text, 1)
            issue['applied'] = True
            issue['needs_review'] = False
            fixes_applied += 1
            log(f"  [AI fix] para {para_idx}: '{issue_text}' → '{fix_text}'")

    sample_fixes = fixes_applied
    log(f"  Phase 2 sample fixes: {sample_fixes} applied, {fixes_flagged} flagged for review")

    # --- Phase 2a: Global pattern propagation ---
    # Collect successful split_word / encoding_artifact fixes as patterns
    global_patterns = {}
    for issue in issues:
        if issue.get('applied') and issue.get('type') in ('split_word', 'encoding_artifact'):
            issue_text = issue.get('text', '')
            fix_text = issue.get('fix', '')
            if issue_text and fix_text and issue_text != fix_text:
                global_patterns[issue_text] = fix_text

    global_fixes = 0
    if global_patterns:
        log(f"  Global fix: propagating {len(global_patterns)} pattern(s) across all {len(paragraphs)} paragraphs")
        # Track which paragraphs were already fixed by the sample pass
        sample_fixed_paras = {}
        for issue in issues:
            if issue.get('applied'):
                idx = issue.get('paragraph_index')
                txt = issue.get('text', '')
                sample_fixed_paras.setdefault(idx, set()).add(txt)

        for pattern, replacement in global_patterns.items():
            for i in range(len(paragraphs)):
                # Re-read current paragraph text (may have been modified by
                # a previous pattern — BUG 2 fix: prevents double-application)
                para = paragraphs[i]
                if pattern not in para:
                    continue
                # Skip if this exact paragraph+pattern was already fixed
                if i in sample_fixed_paras and pattern in sample_fixed_paras[i]:
                    continue
                # BUG 2 guard: verify the replacement won't create a stutter
                # by checking if replacement text already exists at the match site.
                # e.g., "Ultimate" → "Ultimately" on text that already has "Ultimately"
                # would produce "Ultimatelyly".
                if replacement in para and pattern in replacement:
                    # The replacement text is already present AND the pattern
                    # is a substring of the replacement — skip to prevent stutter
                    continue
                count = para.count(pattern)
                paragraphs[i] = para.replace(pattern, replacement)
                global_fixes += count
                # Track this paragraph as modified to prevent re-application
                sample_fixed_paras.setdefault(i, set()).add(pattern)
                log(f"  [AI global fix] para {i}: '{pattern}' → '{replacement}'"
                    + (f" ({count}x)" if count > 1 else ""))

        log(f"  Global fix complete: {global_fixes} additional replacement(s)")
    else:
        log("  Global fix: no propagatable patterns found")

    # --- Phase 2b: Targeted verification pass (Call 3) ---
    if fixes_applied > 0:
        log("  AI Quality Pass: verifying fixes (Call 3)...")
        # Collect fixed paragraphs with surrounding context
        fixed_indices = set()
        for issue in issues:
            if issue.get('applied'):
                fixed_indices.add(issue['paragraph_index'])

        verify_samples = []
        for idx in sorted(fixed_indices):
            context_before = paragraphs[idx - 1][:200] if idx > 0 else ""
            context_after = paragraphs[idx + 1][:200] if idx < len(paragraphs) - 1 else ""
            verify_samples.append({
                'paragraph_index': idx,
                'context_before': context_before,
                'text': paragraphs[idx][:600],
                'context_after': context_after,
            })

        verify_text = "\n\n".join(
            f"[Paragraph {s['paragraph_index']}]\n"
            f"BEFORE: {s['context_before']}\n"
            f">>> {s['text']}\n"
            f"AFTER: {s['context_after']}"
            for s in verify_samples
        )

        verify_prompt = f"""These {len(verify_samples)} paragraphs had text extraction fixes applied. Verify the fixes look correct and flag any remaining issues in these specific paragraphs.

{verify_text}

Return a JSON object with:
- "verification": "pass" or "fail"
- "remaining_issues": array of objects (same format as before: type, severity, text, fix, paragraph_index, estimated_total_occurrences), only for NEW issues not already reported
- "notes": array of strings with any observations"""

        try:
            verify_resp = _requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "content-type": "application/json",
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": _model,
                    "max_tokens": 2000,
                    "temperature": 0,
                    "system": (
                        "You are a PDF text extraction quality checker verifying "
                        "that automated fixes were applied correctly. Return ONLY "
                        "valid JSON, no markdown formatting, code fences, or explanation. "
                        "Focus on body text only — ignore index entries, bibliographic "
                        "citations, and footnote references."
                    ),
                    "messages": [{"role": "user", "content": verify_prompt}],
                },
                timeout=30,
            )
            verify_resp.raise_for_status()
            vbody = verify_resp.json()
            vcontent = vbody['content'][0]['text'].strip()
            if vcontent.startswith('```'):
                vcontent = vcontent.split('\n', 1)[1] if '\n' in vcontent else vcontent[3:]
                if vcontent.endswith('```'):
                    vcontent = vcontent[:-3]
                vcontent = vcontent.strip()
            verify_report = json.loads(vcontent)

            verification = verify_report.get('verification', '?')
            remaining = verify_report.get('remaining_issues', [])
            notes = verify_report.get('notes', [])
            log(f"  Verification: {verification}, {len(remaining)} remaining issue(s)")
            for note in notes:
                log(f"    [verify] {note}")

            # Apply any additional fixes from verification
            for issue in remaining:
                fix_text = issue.get('fix')
                issue_text = issue.get('text', '')
                para_idx = issue.get('paragraph_index')
                if fix_text and para_idx is not None and 0 <= para_idx < len(paragraphs):
                    para = paragraphs[para_idx]
                    if issue_text in para:
                        paragraphs[para_idx] = para.replace(issue_text, fix_text, 1)
                        issue['applied'] = True
                        issue['needs_review'] = False
                        fixes_applied += 1
                        log(f"  [AI fix] para {para_idx}: '{issue_text}' → '{fix_text}'")
                    else:
                        issue['applied'] = False
                        issue['needs_review'] = True
                        fixes_flagged += 1
                else:
                    issue['applied'] = False
                    issue['needs_review'] = True
                    fixes_flagged += 1
                issues.append(issue)

            report['verification'] = verify_report

        except Exception as e:
            log(f"  Verification pass failed ({e}) — continuing with fixes already applied")

    # --- Calculate final score (only counting unfixed issues) ---
    unfixed_issues = [i for i in issues if not i.get('applied', False)]
    final_score = _calc_score(unfixed_issues)

    # --- Build final report ---
    total_fixes = sample_fixes + global_fixes
    report['original_score'] = original_score
    report['quality_score'] = final_score
    report['final_score'] = final_score
    report['sample_fixes'] = sample_fixes
    report['global_fixes'] = global_fixes
    report['total_fixes'] = total_fixes
    report['fixes_applied'] = total_fixes
    report['fixes_flagged'] = fixes_flagged

    log(f"  AI Quality Pass complete: {original_score} → {final_score}/100 "
        f"({sample_fixes} sample + {global_fixes} global = {total_fixes} fixed, "
        f"{fixes_flagged} flagged)")

    return paragraphs, report


def strip_footnotes_from_paragraphs(paragraphs, log):
    """
    Remove trailing footnote text from body paragraphs.

    Academic PDFs place page-bottom footnotes after the last body paragraph
    extracted from each page, producing paragraphs where body text ends with
    a sentence, then one or more footnote entries are appended.

    Conservative rules:
    - Only strips footnotes at paragraph END (after sentence-ending punct)
    - Skips paragraphs that START with a number (could be list items)
    - Skips Markdown heading paragraphs (start with '#')
    - Logs stripped count and approximate word count removed
    """
    _FN_TAIL_RE = re.compile(
        r'([.!?])\s*'
        r'(\d{1,3}\s+'
        r'(?:See\s|Cf\.\s|On\s+this\s|For\s+[A-Z]|According\s+to\s|Ibid[.\s]|[A-Z][a-z]+[,.])\s*'
        r'.*)$',
        re.DOTALL
    )

    stripped_count = 0
    stripped_words = 0

    for i, para in enumerate(paragraphs):
        text = para.strip()
        if not text:
            continue
        if text.startswith('#'):
            continue
        # Skip paragraphs that start with a number — could be numbered list items
        if re.match(r'^\d', text):
            continue

        m = _FN_TAIL_RE.search(text)
        if m:
            # Keep everything up through the sentence-ending punctuation; drop the rest
            kept = text[:m.start(2)].rstrip()
            removed = m.group(2)
            stripped_words += len(removed.split())
            paragraphs[i] = kept
            stripped_count += 1

    if stripped_count:
        log(f"  Stripped trailing footnotes from {stripped_count} paragraph(s) "
            f"(~{stripped_words} words removed)")

    return paragraphs


def process_pdf(input_path, output_path, log, chapter_hints_path=None,
                use_ocr=None, tesseract_path=None, poppler_path=None, ocr_dpi=300,
                calibre_path=None, force_columns=False,
                tts_enhance=False, tag_syntax='sapi', dialogue_voices=False):
    """Full pipeline: ebook -> clean text -> chapter-formatted Balabolka file.

    use_ocr: True = force OCR, False = force standard, None = auto-detect (PDF only)
    """
    ext_upper = Path(input_path).suffix.lstrip('.').upper()
    is_pdf = ext_upper == 'PDF'

    bookmarks = []
    if is_pdf:
        log("\n-- STEP 0: Checking for PDF bookmarks -----------------")
        bookmarks = extract_bookmarks(input_path, log)

    log(f"\n-- STEP 1: Extracting text from {ext_upper} --")

    # --- PDF type detection and extraction routing ---
    do_ocr = False

    if is_pdf:
        if use_ocr is True:
            do_ocr = True
            log("  OCR: Forced by --ocr flag")
        elif use_ocr is False:
            do_ocr = False
            log("  OCR: Disabled by --no-ocr flag")
        else:
            # Auto-detect: check if PDF is image-only
            detection = detect_pdf_type(input_path, log)
            if detection['pdf_type'] == 'image':
                do_ocr = True
                log(f"  OCR: Auto-detected image-only PDF "
                    f"(avg {detection['avg_chars_per_page']:.0f} chars/page)")

    if do_ocr:
        raw = extract_text_ocr(input_path, log,
                               tesseract_path=tesseract_path,
                               poppler_path=poppler_path,
                               dpi=ocr_dpi)
        if not raw or not raw.strip():
            log("  OCR extraction returned no text -- aborting")
            return
    else:
        raw = extract_text_auto(input_path, log, calibre_path=calibre_path,
                                force_columns=force_columns)

        # ── Zero-text OCR escalation for large PDFs (SCRUM-148) ──────
        if is_pdf and raw:
            raw_word_count = len(raw.split())
            file_size_mb = os.path.getsize(input_path) / (1024 * 1024)
            if file_size_mb > 5 and raw_word_count < 200:
                log(f"  Zero-text escalation: {file_size_mb:.1f}MB PDF, only {raw_word_count} words")
                log(f"  Trying OCR...")
                try:
                    ocr_raw = extract_text_ocr(
                        input_path, log,
                        tesseract_path=tesseract_path,
                        poppler_path=poppler_path,
                        dpi=ocr_dpi
                    )
                    if ocr_raw and len(ocr_raw.split()) > raw_word_count * 2:
                        log(f"  OCR wins ({len(ocr_raw.split())} words vs {raw_word_count})")
                        raw = ocr_raw
                    else:
                        log(f"  OCR didn't improve — keeping original")
                except Exception as e:
                    log(f"  OCR escalation failed (non-blocking): {e}")

    # Encoding normalization
    log("  Encoding normalization...")
    raw, enc_stats = normalize_encoding(raw, log=log)

    log("\n-- STEP 2: Cleaning and joining paragraphs --")
    paragraphs = clean_and_join(raw, log)

    if bookmarks:
        log("\n-- STEP 2b: Mapping bookmarks to paragraphs ----------")
        paragraphs, heading_dict = map_bookmarks_to_paragraphs(paragraphs, bookmarks, log)

        # Check if bookmarks include any Part-level headings
        has_parts = len(heading_dict['parts']) > 0
        if not has_parts and len(heading_dict['chapters']) >= 4:
            log("  No Part-level bookmarks found — checking if chapter titles suggest Parts...")
            for bm in bookmarks:
                title = bm.get('title', '')
                if re.match(r'^(?:Part|PART)\s+[IVXLC\d]+', title, re.IGNORECASE):
                    for ch_idx in list(heading_dict['chapters']):
                        if ch_idx < len(paragraphs) and paragraphs[ch_idx].strip() == title:
                            heading_dict['chapters'].remove(ch_idx)
                            heading_dict['parts'].append(ch_idx)
                            log(f"  Promoted to Part: {title[:60]}")
                            break
            heading_dict['parts'] = sorted(heading_dict['parts'])

        heading_indices = sorted(heading_dict['parts'] + heading_dict['chapters'])

        log("\n-- STEP 2c: Fixing OCR artifacts ---------------------")
        bm_titles = [bm['title'] for bm in bookmarks] if bookmarks else []
        h_indices = set(heading_dict.get('parts', []) + heading_dict.get('chapters', []))
        paragraphs, _fix_stats = fix_ocr_artifacts(paragraphs, log, bookmark_titles=bm_titles, heading_indices=h_indices)

        log("\n-- STEP 2d: Stripping trailing footnotes ---------------")
        paragraphs = strip_footnotes_from_paragraphs(paragraphs, log)

        # Skip front/back matter detection and regex chapter detection
        # -- bookmarks already tell us the full structure
        log("\n-- STEP 3: Skipping front/back matter detection (bookmarks provide structure) --")

        # For TTS mode, skip front matter entirely
        content_heading_indices = [heading_indices[j] for j, bm in enumerate(bookmarks)
                                   if not bm.get('front_matter', False) and j < len(heading_indices)]
        if content_heading_indices:
            body_start = content_heading_indices[0]
        elif heading_indices:
            body_start = heading_indices[0]
        else:
            body_start = 0

        # For TTS mode, trim back matter (Notes, Bibliography, Index are not useful for audio)
        back_matter_indices = [heading_indices[j] for j, bm in enumerate(bookmarks)
                              if bm.get('back_matter', False) and j < len(heading_indices)]
        if back_matter_indices:
            body_end = back_matter_indices[0]  # Cut at first back matter heading
            body = paragraphs[body_start:body_end]
            # Remove back matter headings from the heading indices
            heading_indices = [h - body_start for h in heading_indices
                             if h >= body_start and h < body_end]
            log(f"  Trimmed back matter at paragraph {body_end} (TTS mode)")
        else:
            body = paragraphs[body_start:]
            heading_indices = [h - body_start for h in heading_indices if h >= body_start]

        log(f"  Body: {len(body):,} paragraphs (starting from bookmark-based position {body_start})")

        log("\n-- STEP 2e: Validating heading indices ----------------")
        heading_indices = validate_heading_indices(body, heading_indices, log,
                                                   bookmark_indices=set(heading_indices))

        if tts_enhance:
            log("\n-- STEP 6: Applying TTS voice tags -------------------")
        else:
            log("\n-- STEP 6: Formatting and saving ---------------------")
        _cs = {'parts': [], 'chapters': heading_indices}
        final_text = format_output(body, _cs, log, tts_enhance=tts_enhance, tag_syntax=tag_syntax, dialogue_voices=dialogue_voices)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_text)

        word_count = len(final_text.split())
        log(f"\nDone! Saved to: {output_path}")
        log(f"  Words: {word_count:,}")
        log(f"  Sections/chapters: {len(heading_indices)}")
        if tts_enhance:
            log(f"  Tag syntax: {tag_syntax}")
            log(f"  TTS enhancements applied (chapter silence, scene breaks, emphatic closers)")
        if heading_indices:
            log("\n  Detected headings:")
            for idx in heading_indices:
                log(f"    - {body[idx][:70]}")
        return  # Skip the rest of process_pdf

    log("\n-- STEP 2c: Fixing OCR artifacts ---------------------")
    paragraphs, _fix_stats = fix_ocr_artifacts(paragraphs, log)

    log("\n-- STEP 2d: Stripping trailing footnotes ---------------")
    paragraphs = strip_footnotes_from_paragraphs(paragraphs, log)

    log("\n-- STEP 3: Detecting front matter --")
    body_start = detect_front_matter_end(paragraphs, log)

    log("\n-- STEP 4: Detecting back matter --")
    body_end = detect_back_matter_start(paragraphs, log)

    body = paragraphs[body_start:body_end]
    log(f"  Body: {len(body):,} paragraphs  ({body_start}-{body_end})")

    # Strip page markers — bookmark path uses them in map_bookmarks_to_paragraphs,
    # but the non-bookmark path (hints or heuristic) doesn't need them.
    marker_count = 0
    for i in range(len(body)):
        if body[i].strip().startswith('<<PAGE:'):
            # Standalone marker — replace with empty string (will be filtered)
            if re.match(r'^<<PAGE:\d+>>$', body[i].strip()):
                body[i] = ''
                marker_count += 1
            else:
                # Marker embedded in text — strip it
                body[i] = re.sub(r'<<PAGE:\d+>>\s*', '', body[i]).strip()
                marker_count += 1
        elif '<<PAGE:' in body[i]:
            body[i] = re.sub(r'\s*<<PAGE:\d+>>\s*', ' ', body[i]).strip()
            marker_count += 1
    # Remove empty paragraphs left by marker removal
    body = [p for p in body if p.strip()]
    if marker_count:
        log(f"  Stripped {marker_count} page markers from text")

    log("\n-- STEP 5: Detecting chapter headings --")
    toc_indices = detect_toc_section(body, log)

    # If chapter hints are provided (from Claude API), use them
    if chapter_hints_path:
        try:
            with open(chapter_hints_path, "r", encoding="utf-8") as hf:
                hints = json.load(hf)
            log(f"  Using {len(hints)} chapter hint(s) from: {chapter_hints_path}")
            body, heading_dict = apply_chapter_hints(body, hints, log)
            # Collect hints that weren't found in cleaned text
            matched_titles = set()
            for idx in heading_dict['parts'] + heading_dict['chapters']:
                if idx < len(body):
                    matched_titles.add(body[idx].lower().strip())
            missing = [h for h in hints
                       if h.get('title', '').strip().lower() not in matched_titles
                       and h.get('title', '').strip().upper() not in
                           {body[i].upper().strip() for i in heading_dict['parts'] + heading_dict['chapters'] if i < len(body)}]
            if missing:
                log(f"  {len(missing)} chapter hints could not be located in cleaned text (skipped)")
                for m in missing:
                    log(f"    - {m.get('title', '')[:70]}")
            heading_indices = sorted(heading_dict['parts'] + heading_dict['chapters'])
        except (json.JSONDecodeError, OSError) as e:
            log(f"  [warn] Failed to load chapter hints: {e} -- falling back to regex")
            heading_indices = detect_chapters_flat(body, log, toc_indices=toc_indices)
            heading_dict = None
    else:
        heading_indices = detect_chapters_flat(body, log, toc_indices=toc_indices)
        heading_dict = None

    log("\n-- STEP 5b: Validating heading indices -----------------")
    if heading_dict:
        heading_dict = validate_heading_dict(body, heading_dict, log,
                                             bookmark_indices=set())
        heading_indices = sorted(heading_dict['parts'] + heading_dict['chapters'])
    else:
        heading_indices = validate_heading_indices(body, heading_indices, log,
                                                   bookmark_indices=set())

    if tts_enhance:
        log("\n-- STEP 6: Applying TTS voice tags --")
    else:
        log("\n-- STEP 6: Formatting and saving --")
    if heading_dict and not tts_enhance:
        final_text = format_output_with_levels(body, heading_dict)
    else:
        _cs = heading_dict if heading_dict else {'parts': [], 'chapters': heading_indices}
        final_text = format_output(body, _cs, log, tts_enhance=tts_enhance, tag_syntax=tag_syntax, dialogue_voices=dialogue_voices)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_text)

    word_count = len(final_text.split())
    log(f"\nDone! Saved to: {output_path}")
    log(f"  Words: {word_count:,}")
    log(f"  Sections/chapters: {len(heading_indices)}")
    if tts_enhance:
        log(f"  Tag syntax: {tag_syntax}")
        log(f"  TTS enhancements applied (chapter silence, scene breaks, emphatic closers)")
    if heading_indices:
        log("\n  Detected headings:")
        for idx in heading_indices:
            log(f"    - {body[idx][:70]}")


def _link_endnotes(html, log):
    """
    Link <sup> footnote references in body text to endnotes/footnotes.
    Handles three styles:
      1. Collected endnotes: single "Notes" heading at the back
      2. Per-chapter endnotes: note clusters after each chapter (numbering restarts)
      3. Per-page footnotes: inline note paragraphs near their references
    Creates bidirectional links: body → endnote and endnote → body.
    """
    if '<sup>' not in html:
        log("  No <sup> tags found — skipping endnote linking")
        return html

    total_sups = len(re.findall(r'<sup>\d{1,4}</sup>', html))

    # Try strategies 1 and 2 (collected / per-chapter endnotes)
    result = _link_endnotes_collected(html, log)

    # Check if enough superscripts were linked
    remaining = len(re.findall(r'<sup>\d{1,4}</sup>', result))
    linked_count = total_sups - remaining
    if total_sups == 0 or linked_count / total_sups > 0.2:
        return result

    # Strategies 1/2 linked <20% — try per-page footnotes on original HTML
    log(f"  Strategies 1-2 linked only {linked_count}/{total_sups} (<20%)"
        f" — trying per-page footnotes")
    return _link_per_page_footnotes(html, total_sups, log)


def _link_endnotes_collected(html, log):
    """
    Strategies 1 and 2 for endnote linking: collected or per-chapter endnotes.
    Returns the (possibly modified) HTML.
    """
    if '<sup>' not in html:
        log("  No <sup> tags found — skipping endnote linking")
        return html

    # ── Strategy 1: Collected endnotes under a "Notes" heading ────────
    notes_match = re.search(
        r'<h[12]>([^<]*(?:Notes|Endnotes|NOTES|ENDNOTES)[^<]*)</h[12]>',
        html)
    if notes_match:
        notes_start = notes_match.end()
        log(f"  Notes section found: '{notes_match.group(1).strip()}'")
        notes_end_match = re.search(r'<h[12]>', html[notes_start:])
        notes_end = notes_start + notes_end_match.start() if notes_end_match else len(html)

        body_html = html[:notes_match.start()]
        notes_section = html[notes_start:notes_end]
        after_notes = html[notes_end:]

        endnote_numbers = set()
        def _add_anchor(m):
            num = m.group(1)
            endnote_numbers.add(num)
            return f'<p><a id="endnote_{num}"></a><a href="#noteref_{num}">{num}.</a>{m.group(2)}'

        notes_linked = re.sub(r'<p>(\d{1,4})\.\s*(.)', _add_anchor, notes_section)

        def _add_anchor2(m):
            num = m.group(1)
            if num in endnote_numbers:
                return m.group(0)
            endnote_numbers.add(num)
            return f'<p><a id="endnote_{num}"></a><a href="#noteref_{num}">{num}.</a> {m.group(2)}'
        notes_linked = re.sub(r'<p>(\d{1,4})\s+([A-Z"\u201c])', _add_anchor2, notes_linked)

        if not endnote_numbers:
            log("  No endnote entries parsed in Notes section")
            return html

        linked = [0]
        def _link_sup(m):
            num = m.group(1)
            if num in endnote_numbers:
                linked[0] += 1
                return f'<sup><a id="noteref_{num}" href="#endnote_{num}">{num}</a></sup>'
            return m.group(0)

        body_linked = re.sub(r'<sup>(\d{1,4})</sup>', _link_sup, body_html)
        log(f"  Endnotes parsed: {len(endnote_numbers)}, linked: {linked[0]}")
        return body_linked + html[notes_match.start():notes_start] + notes_linked + after_notes

    # ── Strategy 2: Per-chapter endnotes (detect note clusters) ───────
    log("  No Notes heading found — scanning for per-chapter endnote clusters")

    # Split into chapter sections at CHAPTER-LEVEL headings only.
    # Numbered chapters ("1 The State...", "Chapter 2..."), Introduction, Conclusion,
    # Epilogue, Appendix, Bibliography, Index — but NOT sub-section headings like
    # "How Civil Society..." which are mid-chapter h2/h3 breaks.
    _chapter_pat = re.compile(
        r'<h[12]>([^<]*(?:\d+\s|Chapter|Introduction|Conclusion|Epilogue|'
        r'Appendix|Bibliography|Index|Abbreviation|Acknowledgment|CONTENTS|Contents)[^<]*)</h[12]>',
        re.IGNORECASE)
    chapter_splits = list(_chapter_pat.finditer(html))
    if not chapter_splits:
        log("  No chapter headings — skipping endnote linking")
        return html

    sections = []
    for i, m in enumerate(chapter_splits):
        sec_end = chapter_splits[i + 1].start() if i + 1 < len(chapter_splits) else len(html)
        heading = re.sub(r'<[^>]+>', '', m.group()).strip()
        sections.append((m.start(), sec_end, heading))

    total_notes = 0
    total_linked = 0
    result_parts = []
    last_end = 0

    for sec_start, sec_end, heading in sections:
        section_html = html[sec_start:sec_end]

        # Find note paragraphs: <p> starting with number + period
        note_matches = list(re.finditer(r'<p>(\d{1,4})\.\s', section_html))
        if len(note_matches) < 3:
            result_parts.append(html[last_end:sec_end])
            last_end = sec_end
            continue

        # Find start of note cluster: 3+ sequential numbered paragraphs
        cluster_start = None
        for j in range(len(note_matches) - 2):
            n1 = int(note_matches[j].group(1))
            n2 = int(note_matches[j + 1].group(1))
            n3 = int(note_matches[j + 2].group(1))
            if n1 < n2 <= n1 + 3 and n2 < n3 <= n2 + 3:
                cluster_start = note_matches[j].start()
                break
        if cluster_start is None:
            result_parts.append(html[last_end:sec_end])
            last_end = sec_end
            continue

        body_part = section_html[:cluster_start]
        notes_part = section_html[cluster_start:]

        # Make chapter-scoped unique IDs (sanitize heading for use in id)
        ch_id = re.sub(r'[^a-zA-Z0-9]', '', heading[:15])
        chapter_notes = set()

        def _make_anchor(m, _ch_id=ch_id, _notes=chapter_notes):
            num = m.group(1)
            _notes.add(num)
            uid = f'{_ch_id}_{num}'
            return f'<p><a id="endnote_{uid}"></a><a href="#noteref_{uid}">{num}.</a>{m.group(2)}'

        notes_linked = re.sub(r'<p>(\d{1,4})\.\s*(.)', _make_anchor, notes_part)

        ch_linked = [0]
        def _link_ch(m, _ch_id=ch_id, _notes=chapter_notes, _cnt=ch_linked):
            num = m.group(1)
            if num in _notes:
                _cnt[0] += 1
                uid = f'{_ch_id}_{num}'
                return f'<sup><a id="noteref_{uid}" href="#endnote_{uid}">{num}</a></sup>'
            return m.group(0)

        body_linked = re.sub(r'<sup>(\d{1,4})</sup>', _link_ch, body_part)

        total_notes += len(chapter_notes)
        total_linked += ch_linked[0]

        result_parts.append(html[last_end:sec_start])
        result_parts.append(body_linked + notes_linked)
        last_end = sec_end

    if last_end < len(html):
        result_parts.append(html[last_end:])

    if total_notes == 0:
        log("  No endnote clusters found — skipping")
        return html

    log(f"  Per-chapter endnotes: {total_notes} notes, {total_linked} superscripts linked")
    return ''.join(result_parts)


def _link_per_page_footnotes(html, total_sups, log):
    """
    Strategy 3: Link per-page footnotes where note text appears inline near
    the body reference, formatted as <p><sup>N</sup> or <p><em><sup>N</sup>.

    Each footnote number typically appears twice: once as a body reference
    (inline <sup>N</sup>) and once as the footnote text paragraph
    (<p><sup>N</sup> note text).  Numbers restart per page.
    """
    log("  Trying per-page footnote linking (Strategy 3)")

    # Find all unlinked <sup>N</sup>
    sup_pat = re.compile(r'<sup>(\d{1,4})</sup>')
    all_sups = list(sup_pat.finditer(html))
    if not all_sups:
        log("  No unlinked superscripts found")
        return html

    # Classify each <sup> as body-ref or footnote-text.
    # A footnote paragraph starts with <p><sup> or <p><em><sup>.
    # Multiple footnotes can be crammed into one paragraph:
    #   <p><sup>9</sup> ref text <sup>10</sup> ref text</p>
    # All <sup> inside such paragraphs are footnote texts.
    fn_para_starts = re.compile(r'<p>(?:<em>)?\s*<sup>\d{1,4}</sup>')
    fn_para_ranges = []
    for pm in fn_para_starts.finditer(html):
        p_end = html.find('</p>', pm.end())
        if p_end >= 0:
            fn_para_ranges.append((pm.start(), p_end + 4))

    body_refs = []
    footnote_texts = []
    for m in all_sups:
        in_fn_para = any(s <= m.start() < e for s, e in fn_para_ranges)
        if in_fn_para:
            footnote_texts.append(m)
        else:
            body_refs.append(m)

    log(f"  Found {len(body_refs)} body references, {len(footnote_texts)} footnote texts")

    if not footnote_texts:
        log("  No footnote text paragraphs found — skipping")
        return html

    # Match each body ref to nearest forward footnote text with same number
    counter = 0
    replacements = []
    used_footnotes = set()

    for br in body_refs:
        num = br.group(1)
        br_pos = br.start()
        best = None
        for ft in footnote_texts:
            if ft.start() in used_footnotes:
                continue
            if ft.group(1) == num and ft.start() > br_pos \
                    and ft.start() - br_pos <= 5000:
                best = ft
                break
        if best is None:
            continue

        counter += 1
        used_footnotes.add(best.start())
        uid = f"fn_{counter}"

        # Body ref: <sup>N</sup> → <sup><a id=... href=...>N</a></sup>
        replacements.append((br.start(), br.end(),
            f'<sup><a id="noteref_{uid}" href="#footnote_{uid}">'
            f'{num}</a></sup>'))

        # Footnote text: <sup>N</sup> → <sup><a id=...></a><a href=...>N</a></sup>
        replacements.append((best.start(), best.end(),
            f'<sup><a id="footnote_{uid}"></a>'
            f'<a href="#noteref_{uid}">{num}</a></sup>'))

    if counter == 0:
        log("  No footnote pairs matched — skipping")
        return html

    # Apply replacements in reverse position order to preserve indices
    replacements.sort(key=lambda x: x[0], reverse=True)
    result = html
    for start, end, new_text in replacements:
        result = result[:start] + new_text + result[end:]

    log(f"  Per-page footnotes: {counter} pairs linked")
    return result


def _fix_ligature_splits(para_dicts, log):
    """
    Fix ligature decomposition splits in paragraph text.
    Reusable by both pdfminer HTML path and legacy pypdf path.
    Handles: fi/fl splits, ffi/ffl triple splits, Th+word splits, hyphen-splits.
    """
    try:
        from spellchecker import SpellChecker
        spell = SpellChecker()
    except ImportError:
        log("  pyspellchecker not installed — skipping ligature fixes")
        return

    total_fixes = 0

    for p in para_dicts:
        if p.get('is_page_marker') or not p.get('text', '').strip():
            continue
        text = p['text']
        original = text

        # Multi-space normalization
        text = re.sub(r'  +', ' ', text)

        # Phase 3c: "Th e" → "The", "Th is" → "This"
        def _th_repl(m):
            merged = 'Th' + m.group(1)
            return merged if merged.lower() in spell else m.group(0)
        text = re.sub(r'\bTh (\w+)', _th_repl, text)

        # Phase 3d: fi/fl ligature splits — "fi gures" → "figures"
        def _fifl_repl(m):
            prefix, suffix = m.group(1), m.group(2)
            merged = prefix + suffix
            if merged.lower() in spell:
                return merged
            for suf in ('ing', 'ed', 'tion', 'sion', 'ly', 'er', 'ment', 'ness', 'ous',
                        'ive', 'al', 'ence', 'ance', 'ity', 'able', 'ible'):
                if merged.lower().endswith(suf):
                    root = merged[:len(merged)-len(suf)].lower()
                    if root in spell or root + 'e' in spell:
                        return merged
            return m.group(0)
        text = re.sub(r'\b(\w*f[il]) (\w+)', _fifl_repl, text)

        # Phase 3d extended: ffi/ffl triple ligature — "tra ffi cking" → "trafficking"
        def _ffi_repl(m):
            prefix = m.group(1) or ''
            lig, suffix = m.group(2), m.group(3)
            merged = prefix + lig + suffix
            if merged.lower() in spell:
                return merged[0].upper() + merged[1:] if prefix and prefix[0].isupper() else merged
            for suf in ('ing', 'ed', 'tion', 'ly', 'er', 'ers', 'ment', 'es',
                        'ence', 'ance', 'al', 'le', 'les'):
                if merged.lower().endswith(suf):
                    root = merged[:len(merged)-len(suf)].lower()
                    if root in spell or root + 'e' in spell:
                        return merged[0].upper() + merged[1:] if prefix and prefix[0].isupper() else merged
            return m.group(0)
        text = re.sub(r'\b(\w*?)[\s]?(ff[il]) (\w+)', _ffi_repl, text)

        # Phase 3b: Hyphen-split rejoining — "sym bolic" → "symbolic"
        # Also handles multi-fragment splits: "att en tion" → "attention"
        # Pre-split: detach ligature fragments glued to em dashes/hyphens
        # e.g., "death—fi tt ing" → "death— fi tt ing" so "fi tt ing" merges
        text = re.sub(r'(\u2014|\u2013)([a-z]{1,4})\b', r'\1 \2', text)
        words = text.split(' ')
        j = 0
        while j < len(words) - 1:
            left = words[j]
            # Skip words containing HTML tags entirely as merge starters
            if '<' in left or '>' in left:
                j += 1
                continue
            lc = re.sub(r'^[^A-Za-z]*', '', re.sub(r'[^A-Za-z]*$', '', left))
            if not lc:
                j += 1
                continue
            # Try merging 2, 3, or 4 consecutive fragments
            merged_match = None
            for span in range(2, min(5, len(words) - j + 1)):
                fragments = []
                all_ok = True
                trailing_remainder = ''
                for k in range(j, j + span):
                    # Skip words containing HTML tags — merging tag fragments
                    # with text produces false positives (e.g. <em>+End→"emend")
                    # and destroys the tag structure, causing unclosed <em>/<strong>.
                    if '<' in words[k] or '>' in words[k]:
                        all_ok = False
                        break
                    frag = re.sub(r'^[^A-Za-z]*', '', re.sub(r'[^A-Za-z]*$', '', words[k]))
                    if not frag:
                        all_ok = False
                        break
                    # Use only the first alpha run if the fragment contains
                    # internal punctuation (e.g., "y-three" → "y", remainder="-three")
                    alpha_m = re.match(r'^([A-Za-z]+)', frag)
                    if alpha_m and alpha_m.group(1) != frag:
                        trailing_remainder = frag[len(alpha_m.group(1)):]
                        frag = alpha_m.group(1)
                    else:
                        trailing_remainder = ''
                    fragments.append(frag)
                if not all_ok:
                    break
                # Skip all-uppercase fragment pairs — these are headings
                # where word spacing is intentional (e.g., "SUPER MAN"
                # should NOT become "SUPERMAN" since bookmark matching
                # depends on exact text).
                if all(f.isupper() for f in fragments):
                    continue
                # Skip if all fragments are valid words — these are separate
                # words, not ligature-split fragments.
                # Exception: allow merge when the last fragment looks like a
                # suffix (e.g., "kidnap" + "ping" → "kidnapping" via -ing)
                # AND no fragment is a common function word (articles,
                # prepositions, pronouns, auxiliaries).  Without the function-
                # word guard, "as"+"a"→"asa", "in"+"a"→"ina",
                # "to"+"live"→"tolive" all become false positives.
                _suffix_patterns = ('ing', 'tion', 'sion', 'ment', 'ness', 'ous',
                                    'ive', 'ence', 'ance', 'ity', 'ible', 'able',
                                    'ful', 'less', 'ings', 'ments', 'ly', 'ed',
                                    'er', 'ers', 'est', 'ies', 'es', 'ised', 'ized')
                _func_words = {
                    'a', 'an', 'as', 'at', 'be', 'by', 'do', 'go',
                    'he', 'i', 'if', 'in', 'is', 'it', 'me', 'my',
                    'no', 'of', 'on', 'or', 'so', 'to', 'up', 'us',
                    'we', 'am', 'has', 'had', 'the', 'and', 'but',
                    'for', 'not', 'was', 'are', 'his', 'her', 'its',
                    'can', 'did', 'get', 'let', 'our', 'own', 'per',
                    'she', 'too', 'two', 'use', 'who', 'why', 'yet',
                    'you', 'may', 'all', 'any', 'few', 'how', 'new',
                    'now', 'old', 'one', 'out', 'say', 'see', 'way',
                }
                if all(f.lower() in spell for f in fragments):
                    if any(f.lower() in _func_words for f in fragments):
                        continue  # function word — never merge
                    last_is_suffix = any(fragments[-1].lower().endswith(s)
                                         for s in _suffix_patterns)
                    if all(len(f) > 3 for f in fragments) and not last_is_suffix:
                        continue
                # Skip if total merged length would be unreasonably long
                joined = ''.join(f.lower() for f in fragments)
                if len(joined) > 20:
                    break
                if joined in spell:
                    merged_match = (span, fragments, joined, trailing_remainder)
                    # Keep looking — a longer merge might also work (prefer longest)
                    continue
                # Also check with common suffixes for inflected forms
                for suf in ('ing', 'ed', 'tion', 'sion', 'ly', 'er', 'ers', 'ment',
                            'ness', 'ous', 'ive', 'al', 'ence', 'ance', 'ity',
                            'able', 'ible', 'es', 's', 'ies', 'ful'):
                    if joined.endswith(suf):
                        root = joined[:len(joined)-len(suf)]
                        if root in spell or root + 'e' in spell:
                            merged_match = (span, fragments, joined, trailing_remainder)
                            break

            if merged_match:
                span, fragments, joined, trailing_remainder = merged_match
                # Preserve leading punctuation from first word and trailing from last
                lp = re.match(r'^([^A-Za-z]*)', words[j]).group(1)
                rs = re.search(r'([^A-Za-z]*)$', words[j + span - 1]).group(1)
                # Preserve original case of first letter
                merged_word = ''.join(fragments)
                # Append any trailing remainder from truncated last fragment
                # (e.g., "y-three" truncated to "y" → remainder "-three")
                words[j] = lp + merged_word + trailing_remainder + rs
                for _ in range(span - 1):
                    words.pop(j + 1)
                continue
            j += 1
        text = ' '.join(words)

        if text != original:
            p['text'] = text
            total_fixes += 1

    if total_fixes:
        log(f"  Ligature fixes applied to {total_fixes} paragraphs")


def process_kindle_html(pdf_path, output_path, log, api_key=None, force_columns=False,
                        skip_footnotes=False, apply_ai_fixes=False,
                        tesseract_path=None, poppler_path=None, ocr_dpi=300,
                        no_cache=False, use_vision=False, vision_cost_limit=15.0,
                        use_gemini=False, gemini_remediate=False,
                        gemini_cost_limit=5.0, gemini_model=None,
                        compare_extractors_enabled=False):
    """
    HTML-based Kindle extraction using pdfminer font metadata.
    Produces semantic HTML with heading levels, blockquotes, and attributions
    derived from font size/bold/italic properties in the source PDF.

    If Tier 1 text quality is poor (score <= 70), auto-escalates to Tesseract 5
    OCR (Tier 2) and keeps whichever result scores higher.

    If use_vision=True, skips Tier 1/2 entirely and uses Claude Vision (Tier 3).
    """
    import time as _time_mod
    _extraction_start = _time_mod.time()
    # Resolve gemini_model from config if not explicitly provided
    if gemini_model is None:
        gemini_model = _load_api_model("gemini_flash")
    tier_used = 1
    extraction_method = 'pdfminer_html'
    if force_columns:
        extraction_method = 'column_aware'
    vision_cost = 0
    quality = None
    _pdf_producer = None
    _pdf_creator = None

    # Capture PDF producer metadata for pattern recognition
    try:
        from pypdf import PdfReader as _PdfReader
        _meta_reader = _PdfReader(pdf_path)
        _meta = _meta_reader.metadata
        if _meta:
            _pdf_producer = str(_meta.producer)[:200] if _meta.producer else None
            _pdf_creator = str(_meta.creator)[:200] if _meta.creator else None
            if _pdf_producer:
                log(f"  PDF producer: {_pdf_producer}")
            if _pdf_creator:
                log(f"  PDF creator: {_pdf_creator}")
    except Exception:
        pass

    # ── Vision extraction (Tier 3) — explicit opt-in only ──────────
    if use_vision:
        log("\n-- STEP 0: Checking for PDF bookmarks -----------------")
        bookmarks = extract_bookmarks(pdf_path, log)

        log("\n-- STEP 1 (VISION): Claude Vision transcription -------")
        log("  Tier 3 extraction — premium AI transcription")

        vision_result = extract_text_vision(
            pdf_path, log,
            api_key=api_key,
            poppler_path=poppler_path,
            dpi=200,
            batch_size=3,
            cost_limit=vision_cost_limit,
        )

        if vision_result and vision_result.get('text'):
            vision_text, _ = normalize_encoding(vision_result['text'], log=log)
            para_dicts, body_size = vision_text_to_para_dicts(vision_text, log)
            tier_used = 3
            extraction_method = 'claude_vision'
            vision_cost = vision_result.get('cost_usd', 0)

            vision_text_flat = '\n'.join(d.get('text', '') for d in para_dicts)
            try:
                quality = score_text_layer_quality(vision_text_flat, log=log)
                log(f"  Vision text quality: {quality.get('score', 0)}/100")
            except Exception:
                quality = {'score': 85, 'recommendation': 'accept',
                           'tier_suggestion': 1, 'details': {}}
            log(f"  Vision cost: ${vision_cost:.4f}")
        else:
            log("  Vision extraction failed or returned no text — "
                "falling back to standard extraction")
            use_vision = False

    # ── Gemini extraction (Tier 2.5) — explicit opt-in only ──────
    gemini_cost = 0
    if use_gemini and not use_vision:
        log("\n-- STEP 0: Checking for PDF bookmarks -----------------")
        bookmarks = extract_bookmarks(pdf_path, log)

        log("\n-- STEP 1 (GEMINI): Gemini Flash transcription ---------")
        log("  Tier 2.5 extraction — Gemini Flash OCR")

        try:
            from gemini_ocr import extract_text_gemini

            gemini_result = extract_text_gemini(
                pdf_path, log,
                poppler_path=poppler_path,
                dpi=200,
                batch_size=5,
                cost_limit=gemini_cost_limit,
                model=gemini_model,
            )

            if gemini_result and gemini_result.get('text'):
                gemini_text, _ = normalize_encoding(gemini_result['text'], log=log)
                para_dicts, body_size = vision_text_to_para_dicts(
                    gemini_text, log)
                tier_used = 2
                extraction_method = 'gemini_flash'
                gemini_cost = gemini_result.get('cost_usd', 0)

                gemini_text_flat = '\n'.join(
                    d.get('text', '') for d in para_dicts)
                try:
                    quality = score_text_layer_quality(gemini_text_flat, log=log)
                    log(f"  Gemini text quality: {quality.get('score', 0)}/100")
                except Exception:
                    quality = {'score': 85, 'recommendation': 'accept',
                               'tier_suggestion': 1, 'details': {}}
                log(f"  Gemini cost: ${gemini_cost:.4f}")
            else:
                log("  Gemini extraction failed — falling back to standard extraction")
                use_gemini = False

        except RuntimeError as e:
            log(f"  Gemini not available: {e}")
            log(f"  Falling back to standard extraction")
            use_gemini = False
        except Exception as e:
            log(f"  Gemini error (non-blocking): {e}")
            use_gemini = False

    _timing = {}  # FU-3: duration breakdown

    if not use_vision and not use_gemini:
        # ── Standard Tier 1/2 extraction ──────────────────────────
        log("\n-- STEP 0: Checking for PDF bookmarks -----------------")
        bookmarks = extract_bookmarks(pdf_path, log)

        _t_extract = _time_mod.time()
        log("\n-- STEP 1: Extracting text with font metadata --")
        para_dicts, body_size = extract_with_pdfminer_html(pdf_path, log,
                                                            force_columns=force_columns)

        # ── Text layer quality scoring ──────────────────────────────────
        all_text_for_scoring = ' '.join(
            p['text'] for p in para_dicts
            if p.get('text') and not p.get('is_page_marker')
        )
        quality = score_text_layer_quality(all_text_for_scoring, log)
        log(f"  Text layer quality score: {quality['score']}/100 — "
            f"{quality['recommendation']}")
        if quality['score'] < 75:
            log(f"  Warning: Quality below threshold. Details:")
            for check, detail in quality['details'].items():
                if isinstance(detail, dict) and 'score' in detail:
                    log(f"    {check}: {detail['score']}/100")

        log("\n-- STEP 1a: Fixing word merges in extraction output ----")
        _fix_word_merges_html(para_dicts, log)

        log("\n-- STEP 1b: Rejoining page-boundary fragments ----------")
        para_dicts = rejoin_html_fragments(para_dicts, body_size, log)

        log("\n-- STEP 1c: Fixing ligature splits --------------------")
        _fix_ligature_splits(para_dicts, log)

        # ── STEP 1c2: Encoding normalization (SCRUM-165) ────────────
        log("\n-- STEP 1c2: Encoding normalization --------------------")
        total_encoding_fixes = 0
        for pd in para_dicts:
            if pd.get('text'):
                cleaned, enc_stats = normalize_encoding(pd['text'], log=None)  # Silent per-para
                if enc_stats['replacements_made'] > 0:
                    pd['text'] = cleaned
                    total_encoding_fixes += enc_stats['replacements_made']
        if total_encoding_fixes > 0:
            log(f"  Fixed {total_encoding_fixes} encoding issues across {len(para_dicts)} paragraphs")
        else:
            log(f"  No encoding issues found")

        # ── STEP 1d: Zero-text OCR escalation (SCRUM-148) ──────────
        # If Tier 1 extraction produced very little text from a large PDF,
        # the text layer is probably empty/corrupted. Try OCR on page images.
        tier1_text = '\n'.join(d.get('text', '') for d in para_dicts)
        tier1_word_count = len(tier1_text.split()) if tier1_text else 0
        file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
        _escalation_info = None  # FU-2: capture escalation comparison

        if file_size_mb > 5 and tier1_word_count < 200:
            log(f"\n-- STEP 1d: Zero-text OCR escalation -------------------")
            log(f"  Trigger: {file_size_mb:.1f}MB PDF produced only {tier1_word_count} words")
            log(f"  Attempting Tesseract OCR on page images...")

            try:
                ocr_text = extract_text_ocr(
                    pdf_path, log,
                    tesseract_path=tesseract_path,
                    poppler_path=poppler_path,
                    dpi=ocr_dpi
                )

                if ocr_text and len(ocr_text.strip()) > len(tier1_text.strip()):
                    ocr_word_count = len(ocr_text.split())
                    log(f"  OCR produced {ocr_word_count} words (was {tier1_word_count})")

                    if ocr_word_count > tier1_word_count * 2 or (tier1_word_count < 50 and ocr_word_count > 100):
                        log(f"  OCR wins — switching to Tier 2 output")
                        ocr_text, _ = normalize_encoding(ocr_text, log=log)
                        para_dicts, body_size = ocr_text_to_para_dicts(ocr_text, log)
                        tier_used = 2
                        extraction_method = 'tesseract5'
                        # Re-score with OCR text
                        quality = score_text_layer_quality(ocr_text, log=log)
                        ocr_score = quality.get('score', 0) if quality else 0
                        _escalation_info = json.dumps({
                            'trigger': 'zero_text',
                            'tier1_score': 0,
                            'tier2_score': ocr_score,
                            'tier1_words': tier1_word_count,
                            'tier2_words': ocr_word_count,
                            'improvement_pct': 100,
                        })
                    else:
                        log(f"  OCR didn't produce enough improvement — keeping Tier 1")
                else:
                    log(f"  OCR produced no usable text — this PDF likely needs Vision (Tier 3)")

            except RuntimeError as e:
                log(f"  OCR escalation failed: {e}")
                log(f"  Continuing with Tier 1 output (may be empty)")
            except Exception as e:
                log(f"  OCR escalation error (non-blocking): {e}")

        # ── STEP 1d2: Multi-extractor comparison for borderline quality ──
        _extractor_comparison = None
        if (tier_used == 1 and compare_extractors_enabled
                and quality and 60 <= quality.get('score', 0) <= 80):
            _tier1_pre = quality.get('score', 0)
            log(f"\n-- STEP 1d2: Multi-extractor comparison ----------------")
            log(f"  Borderline score ({_tier1_pre}/100) — comparing extractors")

            current_plain = '\n'.join(d.get('text', '') for d in para_dicts)

            _cmp = compare_extractors(
                pdf_path, log,
                current_text=current_plain,
                current_score=_tier1_pre,
                current_extractor='pdfminer',
            )
            _extractor_comparison = _cmp.get('comparison')

            if _cmp['improved'] and _cmp['score'] > _tier1_pre:
                _winner = _cmp['winner']
                log(f"  Switching to {_winner} (score: {_tier1_pre} -> {_cmp['score']})")

                if _winner in ('pypdf', 'pymupdf'):
                    plain_text = _cmp['text']
                    plain_text, _ = normalize_encoding(plain_text, log=log)
                    para_dicts, body_size = _plain_text_to_para_dicts(plain_text, log)
                    extraction_method = f'{_winner}_comparison_winner'

                quality = score_text_layer_quality(_cmp['text'], log=log)
            else:
                log(f"  Original pdfminer extraction wins — no change")

        # ── STEP 1e: Auto-escalation to Tier 2 (Re-OCR) if quality is poor ──
        tier1_score = quality.get('score', 0) if quality else 0
        tier_suggestion = quality.get('tier_suggestion', 1) if quality else 1

        if tier_used == 1 and tier1_score <= 70 and tier_suggestion >= 2:
            log(f"\n-- STEP 1e: Auto-escalating to Tier 2 (Re-OCR) --------")
            log(f"  Reason: Tier 1 quality score {tier1_score} <= 70")

            try:
                ocr_text = extract_text_ocr(
                    pdf_path, log,
                    tesseract_path=tesseract_path,
                    poppler_path=poppler_path,
                    dpi=ocr_dpi
                )

                if ocr_text and len(ocr_text.strip()) >= 100:
                    ocr_quality = score_text_layer_quality(ocr_text, log=log)
                    ocr_score = ocr_quality.get('score', 0)
                    log(f"  OCR quality score: {ocr_score}/100 "
                        f"(Tier 1 was: {tier1_score}/100)")

                    if ocr_score > tier1_score:
                        log(f"  OCR wins: {ocr_score} > {tier1_score} — "
                            f"switching to Tier 2 output")
                        ocr_text, _ = normalize_encoding(ocr_text, log=log)
                        ocr_word_count = len(ocr_text.split())
                        _escalation_info = json.dumps({
                            'trigger': 'quality_score',
                            'tier1_score': tier1_score,
                            'tier2_score': ocr_score,
                            'tier1_words': tier1_word_count,
                            'tier2_words': ocr_word_count,
                            'improvement_pct': round(
                                (ocr_score - tier1_score) / max(tier1_score, 1) * 100, 1),
                        })
                        para_dicts, body_size = ocr_text_to_para_dicts(ocr_text, log)
                        tier_used = 2
                        extraction_method = 'tesseract5'
                        tier1_score = ocr_score
                        quality = ocr_quality
                    else:
                        log(f"  Tier 1 wins: {tier1_score} >= {ocr_score} — "
                            f"keeping pdfminer output")
                else:
                    log(f"  OCR produced insufficient text — keeping Tier 1")

            except RuntimeError as e:
                log(f"  OCR escalation failed (non-blocking): {e}")
                log(f"  Continuing with Tier 1 output")
            except Exception as e:
                log(f"  OCR escalation error (non-blocking): {e}")
                log(f"  Continuing with Tier 1 output")

    _timing['extraction_s'] = round(_time_mod.time() - _t_extract, 1) if '_t_extract' in dir() else 0
    _t_format = _time_mod.time()
    log("\n-- STEP 2: Formatting as semantic HTML ----------------")
    # Extract title from bookmarks or filename
    title = 'Untitled'
    stem = os.path.splitext(os.path.basename(pdf_path))[0]
    if bookmarks:
        # Use first non-front-matter bookmark as title hint
        for bm in bookmarks:
            if not bm.get('front_matter'):
                title = stem[:80]
                break
    else:
        title = stem[:80]

    html = format_paragraphs_as_html(para_dicts, body_size, bookmarks, log, title=title,
                                     skip_footnotes=skip_footnotes)

    # ── Fix double spaces from inline tag boundaries ──────────────
    # pdfminer wraps individual italic/bold words in separate <em>/<strong>
    # tags: <em>The </em> <em>New </em> <em>York</em>.  When tags are stripped,
    # trailing space + inter-tag space = double space.  Merge consecutive
    # same-type tags and collapse any remaining text-content double spaces.
    html = re.sub(r'\s*</em>\s*<em>\s*', ' ', html)
    html = re.sub(r'\s*</strong>\s*<strong>\s*', ' ', html)
    # Normalize trailing whitespace inside closing inline tags to prevent
    # double spaces at tag boundaries: "word </em> next" → "word</em> next"
    html = re.sub(r'\s+(</em>)\s*', r'\1 ', html)
    html = re.sub(r'\s+(</strong>)\s*', r'\1 ', html)
    # Belt-and-suspenders: collapse double spaces in text content between tags
    html = re.sub(r'(?<=>)([^<]*)', lambda m: re.sub(r'  +', ' ', m.group(0)), html)

    if not skip_footnotes:
        log("\n-- STEP 2b: Linking footnote references to endnotes ---")
        html = _link_endnotes(html, log)
    else:
        log("\n-- STEP 2b: Skipping endnote linking (--skip-footnotes) ---")

    # Detect scripts for routing intelligence
    _detected_scripts = {}
    try:
        _plain = re.sub(r'<[^>]+>', '', html)
        _detected_scripts = detect_scripts(_plain)
        _non_latin = {k: v for k, v in _detected_scripts.items()
                      if k not in ('latin', 'other')}
        if _non_latin:
            log(f"  Scripts detected: {_detected_scripts}")
            log(f"  Non-Latin content: {_non_latin} — consider -UseVision for best results")
        else:
            log(f"  Scripts: Latin only")
    except Exception:
        pass

    _timing['formatting_s'] = round(_time_mod.time() - _t_format, 1) if '_t_format' in dir() else 0
    if _timing.get('extraction_s') or _timing.get('formatting_s'):
        log(f"  Timing: extraction={_timing.get('extraction_s', 0)}s, "
            f"formatting={_timing.get('formatting_s', 0)}s")

    # Write HTML output
    html_path = re.sub(r'\.(txt|html?)$', '.html', output_path)
    if not html_path.endswith('.html'):
        html_path = output_path + '.html'

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)

    word_count = len(re.sub(r'<[^>]+>', '', html).split())
    log(f"\nDone! Saved to: {html_path}")
    log(f"  Words: {word_count:,}")
    log(f"  HTML size: {len(html):,} chars")

    # ── Gemini page remediation (Mode B) — post-extraction ───────
    if gemini_remediate and not use_gemini and not use_vision:
        log("\n-- STEP 3: Gemini page remediation --------------------")

        pages_to_fix = []

        # Check multi-sample quality variance for problem regions
        if quality:
            try:
                _plain_for_var = re.sub(r'<[^>]+>', '', html)
                _var_result = score_text_layer_quality(
                    _plain_for_var, log=log, multi_sample=True)
                _multi = _var_result.get('details', {}).get('multi_sample', {})
                _problems = _multi.get('problem_regions', [])

                if _problems:
                    _total_pg = 0
                    try:
                        from pypdf import PdfReader as _RemPdfReader
                        _total_pg = len(_RemPdfReader(pdf_path).pages)
                    except Exception:
                        pass
                    if _total_pg > 0:
                        for region in _problems:
                            pos = region.get('position', 0.5)
                            page_est = max(1, int(pos * _total_pg))
                            for p in range(max(1, page_est - 1),
                                           min(_total_pg + 1, page_est + 2)):
                                if p not in pages_to_fix:
                                    pages_to_fix.append(p)
                        log(f"  Quality variance identified {len(pages_to_fix)} "
                            f"candidate pages: {pages_to_fix}")
            except Exception:
                pass

        if pages_to_fix:
            try:
                from gemini_ocr import remediate_pages_gemini

                _rem_result = remediate_pages_gemini(
                    pdf_path, pages_to_fix, log,
                    poppler_path=poppler_path,
                    dpi=200,
                    model=gemini_model,
                )

                if _rem_result and _rem_result.get('pages'):
                    _rem_count = 0
                    for page_num, new_text in _rem_result['pages'].items():
                        page_num = int(page_num)
                        old_indices = [j for j, p in enumerate(para_dicts)
                                       if p.get('page') == page_num]
                        if old_indices:
                            insert_pos = old_indices[0]
                            for idx in reversed(old_indices):
                                para_dicts.pop(idx)
                            para_dicts.insert(insert_pos, {
                                'text': new_text, 'sz': body_size,
                                'bold': False, 'italic': False,
                                'page': page_num, 'tag': None,
                            })
                            _rem_count += 1

                    if _rem_count > 0:
                        _rem_cost = _rem_result.get('cost_usd', 0)
                        gemini_cost += _rem_cost
                        log(f"  Gemini remediated {_rem_count} pages, "
                            f"cost: ${_rem_cost:.4f}")

                        # Re-format HTML with remediated content
                        html = format_paragraphs_as_html(
                            para_dicts, body_size, bookmarks, log, title=title,
                            skip_footnotes=skip_footnotes)
                        html = re.sub(r'\s*</em>\s*<em>\s*', ' ', html)
                        html = re.sub(r'\s*</strong>\s*<strong>\s*', ' ', html)
                        html = re.sub(r'\s+(</em>)\s*', r'\1 ', html)
                        html = re.sub(r'\s+(</strong>)\s*', r'\1 ', html)
                        html = re.sub(r'(?<=>)([^<]*)',
                                      lambda m: re.sub(r'  +', ' ', m.group(0)), html)
                        if not skip_footnotes:
                            html = _link_endnotes(html, log)

                        with open(html_path, 'w', encoding='utf-8') as f:
                            f.write(html)
                        word_count = len(re.sub(r'<[^>]+>', '', html).split())
                        log(f"  Remediated HTML written: {word_count:,} words")

            except RuntimeError as e:
                log(f"  Gemini remediation not available: {e}")
            except Exception as e:
                log(f"  Gemini remediation error (non-blocking): {e}")
        else:
            log("  No pages identified for remediation — quality is uniform")

    # --- Store extraction in cache ---
    if not no_cache:
        try:
            _tools_dir = os.path.dirname(os.path.abspath(__file__))
            if _tools_dir not in sys.path:
                sys.path.insert(0, _tools_dir)
            from pattern_db import (store_extraction, compute_file_hash,
                                    get_or_create_book)

            _src_hash = compute_file_hash(pdf_path)
            _extraction_duration = _time_mod.time() - _extraction_start
            _chapter_count = len(re.findall(r'<h[12]>', html))

            _book_id = get_or_create_book(
                filename=os.path.basename(pdf_path),
                format=os.path.splitext(pdf_path)[1].lstrip('.'),
                source_file_path=pdf_path,
                source_file_hash=_src_hash,
                pdf_producer=_pdf_producer,
                pdf_creator=_pdf_creator,
                detected_scripts=_detected_scripts if _detected_scripts else None,
            )

            _quality_score = quality.get('score') if quality else None

            store_extraction(
                book_id=_book_id,
                source_file_hash=_src_hash,
                tier=tier_used,
                method=extraction_method,
                extracted_html=html,
                quality_score=_quality_score,
                word_count=word_count,
                chapter_count=_chapter_count,
                cost_usd=vision_cost + gemini_cost,
                duration_seconds=round(_extraction_duration, 1),
                escalation_details=_escalation_info if '_escalation_info' in dir() else None,
            )
            log(f"Extraction cached: hash={_src_hash[:12]}..., tier={tier_used}, "
                f"method={extraction_method}, score={_quality_score}")
        except Exception as _ce:
            log(f"Extraction cache write failed (non-blocking): {_ce}")

    # Build result dict with extraction metadata for CLI JSON output
    _result = {"html_path": html_path}
    if '_escalation_info' in dir() and _escalation_info:
        try:
            _result["escalation_details"] = json.loads(_escalation_info)
        except (json.JSONDecodeError, TypeError):
            _result["escalation_details"] = _escalation_info
    if '_extractor_comparison' in dir() and _extractor_comparison:
        _result["extractor_comparison"] = _extractor_comparison
    return _result


def process_kindle(input_path, output_path, log, chapter_hints_path=None, api_key=None,
                   calibre_path=None, force_columns=False, apply_ai_fixes=False):
    """
    Kindle-optimised extraction: ebook -> clean text with FULL content preserved.

    Unlike process_pdf() (Balabolka mode), this keeps:
      - Front matter (title page, TOC, copyright)
      - Back matter (notes, bibliography, index)
      - Chapter headings in original case (not ALL CAPS)

    The text is still cleaned (hyphen fixes, paragraph joining, page number
    removal) so Calibre can produce a readable KFX/AZW3 from it.
    """
    ext_upper = Path(input_path).suffix.lstrip('.').upper()
    is_pdf = ext_upper == 'PDF'

    bookmarks = []
    if is_pdf:
        log("\n-- STEP 0: Checking for PDF bookmarks -----------------")
        bookmarks = extract_bookmarks(input_path, log)

    log(f"\n-- STEP 1: Extracting text from {ext_upper} --")
    raw = extract_text_auto(input_path, log, calibre_path=calibre_path,
                            force_columns=force_columns)

    # Encoding normalization
    log("  Encoding normalization...")
    raw, enc_stats = normalize_encoding(raw, log=log)

    log("\n-- STEP 2: Cleaning and joining paragraphs --")
    paragraphs = clean_and_join(raw, log)
    log(f"  Keeping ALL {len(paragraphs):,} paragraphs (Kindle mode -- no stripping)")

    if bookmarks:
        # NEW PIPELINE ORDER: cleanup and rejoin BEFORE bookmark mapping,
        # so heading indices are calculated on the final paragraph state.

        log("\n-- STEP 2b: Fixing OCR artifacts ---------------------")
        bm_titles = [bm['title'] for bm in bookmarks]
        # No heading_indices yet — bookmarks haven't been placed
        paragraphs, _fix_stats = fix_ocr_artifacts(paragraphs, log, bookmark_titles=bm_titles)

        log("\n-- STEP 2b2: Stripping trailing footnotes ------------")
        paragraphs = strip_footnotes_from_paragraphs(paragraphs, log)

        # AI Paragraph Rejoin (page-boundary fragment repair)
        # Runs BEFORE bookmark mapping — no heading_indices needed,
        # uses startswith('#') guard for any pre-existing markdown headings.
        _rejoin_stats = {}
        _subheading_stats = {}
        if api_key:
            log("\n-- STEP 2c: AI Paragraph Rejoin ----------------------")
            paragraphs, _rejoin_stats = ai_rejoin_fragments(paragraphs, log, api_key=api_key)

            log("\n-- STEP 2c2: AI Sub-heading Detection ----------------")
            paragraphs, _subheading_stats = ai_detect_subheadings(
                paragraphs, log, api_key=api_key,
                bookmark_titles=bm_titles,
                has_bookmarks=bool(bookmarks))

        log("\n-- STEP 2d: Mapping bookmarks to paragraphs ----------")
        paragraphs, heading_dict = map_bookmarks_to_paragraphs(paragraphs, bookmarks, log)

        # Check if bookmarks include any Part-level headings
        has_parts = len(heading_dict['parts']) > 0
        if not has_parts and len(heading_dict['chapters']) >= 4:
            log("  No Part-level bookmarks found — checking if chapter titles suggest Parts...")
            for bm in bookmarks:
                title = bm.get('title', '')
                if re.match(r'^(?:Part|PART)\s+[IVXLC\d]+', title, re.IGNORECASE):
                    for ch_idx in list(heading_dict['chapters']):
                        if ch_idx < len(paragraphs) and paragraphs[ch_idx].strip() == title:
                            heading_dict['chapters'].remove(ch_idx)
                            heading_dict['parts'].append(ch_idx)
                            log(f"  Promoted to Part: {title[:60]}")
                            break
            heading_dict['parts'] = sorted(heading_dict['parts'])

        # Synthetic Front Matter — only for books with sparse bookmarks (<5)
        has_front_matter = any(bm.get('front_matter', False) for bm in bookmarks)
        if has_front_matter and len(bookmarks) < 5:
            first_fm_idx = None
            for bm in bookmarks:
                if bm.get('front_matter', False):
                    for idx in sorted(heading_dict['parts'] + heading_dict['chapters']):
                        if idx < len(paragraphs) and paragraphs[idx].strip() == bm['title'].strip():
                            first_fm_idx = idx
                            break
                    if first_fm_idx is not None:
                        break
            if first_fm_idx is not None:
                paragraphs.insert(first_fm_idx, "Front Matter")
                heading_dict['parts'] = [x + 1 if x >= first_fm_idx else x for x in heading_dict['parts']]
                heading_dict['chapters'] = [x + 1 if x >= first_fm_idx else x for x in heading_dict['chapters']]
                heading_dict['parts'].append(first_fm_idx)
                heading_dict['parts'] = sorted(heading_dict['parts'])
                log(f"  Inserted 'Front Matter' heading at paragraph {first_fm_idx}")

        # AI Quality Pass (detection only by default; fixes require apply_ai_fixes=True)
        if api_key:
            log("\n-- STEP 2e: AI Quality Pass --------------------------")
            h_indices = set(heading_dict.get('parts', []) + heading_dict.get('chapters', []))
            paragraphs, _quality_report = ai_quality_pass(paragraphs, log, api_key=api_key, apply_fixes=apply_ai_fixes)
            _quality_report.update(_rejoin_stats)
            _quality_report.update(_subheading_stats)
        else:
            _quality_report = {}
            _quality_report.update(_rejoin_stats)
            _quality_report.update(_subheading_stats)

        # Strip printed TOC content: dot-leader paragraphs with page numbers
        # that duplicate the sidebar TOC and clutter the body text.
        # Scan the first 15% of the document (TOC is always near the start).
        # Only strip non-heading paragraphs that match dot-leader / page-number patterns.
        toc_dot_pattern = re.compile(r'\.\s*\.\s*\.\s*\.|p\.\s*\d+|\.{4,}')
        # Also match numbered TOC entries: "1. Oh, No! 3" or "12. James the Legend 177"
        # Pattern: starts with digit(s)+period, has title text, ends with digit(s) (page number)
        toc_numbered_pattern = re.compile(r'^\d{1,3}[\.\)]\s+.+\s+\d{1,4}\s*$')
        all_headings = set(heading_dict['parts'] + heading_dict['chapters'])
        toc_strip_count = 0

        # Find TOC region: between a "Contents" heading and the first content chapter
        toc_region_start = 0
        toc_region_end = 0
        for k in sorted(all_headings):
            if k < len(paragraphs):
                title = paragraphs[k].strip().lstrip('#').strip()
                if re.match(r'^(Contents|Table of Contents)$', title, re.IGNORECASE):
                    toc_region_start = k + 1
                elif toc_region_start > 0 and toc_region_end == 0:
                    toc_region_end = k  # first heading after Contents
                    break
        if toc_region_start and not toc_region_end:
            toc_region_end = min(toc_region_start + 80, len(paragraphs))

        toc_scan_limit = max(80, len(paragraphs) // 7)  # ~15% of doc
        for k in range(min(toc_scan_limit, len(paragraphs))):
            if k in all_headings:
                continue  # don't strip heading paragraphs
            para = paragraphs[k].strip()
            if not para:
                continue
            if toc_dot_pattern.search(para):
                paragraphs[k] = ''
                toc_strip_count += 1
            # Strip numbered TOC entries only within the detected TOC region
            elif (toc_region_start and toc_region_start <= k < toc_region_end
                  and toc_numbered_pattern.match(para)):
                paragraphs[k] = ''
                toc_strip_count += 1
        if toc_strip_count:
            log(f"  Stripped {toc_strip_count} printed TOC paragraphs (dot leaders/numbered entries)")

        # If book has front matter but no Part bookmarks, promote content chapters
        # to h1 so they sit alongside Front Matter, not nested under it.
        # Build exclusion set from actual paragraph text at heading positions
        # (not bookmark titles, which may differ after OCR correction)
        fm_bm_indices = set()
        for j, bm in enumerate(bookmarks):
            if bm.get('front_matter', False) or bm.get('back_matter', False):
                fm_bm_indices.add(j)

        fm_bm_titles = {'Front Matter'}  # synthetic heading
        all_heading_indices = sorted(heading_dict['parts'] + heading_dict['chapters'])
        for j, idx in enumerate(all_heading_indices):
            if idx < len(paragraphs):
                # Check if this heading corresponds to a front/back matter bookmark
                title = paragraphs[idx].strip()
                for bm in bookmarks:
                    if bm.get('front_matter', False) or bm.get('back_matter', False):
                        # Match by position: bookmark titles may have been OCR-corrected
                        if title.lower().startswith(bm['title'][:10].lower()) or bm['title'].lower().startswith(title[:10].lower()):
                            fm_bm_titles.add(title)
                            break

        content_parts = [idx for idx in heading_dict['parts']
                         if idx < len(paragraphs) and paragraphs[idx].strip() not in fm_bm_titles]
        has_real_parts = len(content_parts) > 0

        if not has_real_parts and has_front_matter:
            # Promote all content chapters (not front matter, not back matter) to h1
            front_matter_titles = set()
            back_matter_titles = set()
            for bm in bookmarks:
                if bm.get('front_matter', False):
                    front_matter_titles.add(bm['title'].strip())
                if bm.get('back_matter', False):
                    back_matter_titles.add(bm['title'].strip())

            promote_indices = []
            for idx in heading_dict['chapters'][:]:
                if idx < len(paragraphs):
                    title = paragraphs[idx].strip()
                    if title not in front_matter_titles and title not in back_matter_titles:
                        promote_indices.append(idx)

            for idx in promote_indices:
                heading_dict['chapters'].remove(idx)
                heading_dict['parts'].append(idx)

            heading_dict['parts'] = sorted(heading_dict['parts'])
            if promote_indices:
                log(f"  Promoted {len(promote_indices)} content chapters to h1 (no Parts in book)")

        log("\n-- STEP 2f: Validating heading indices ----------------")
        bm_idx_set = set(heading_dict['parts'] + heading_dict['chapters'])
        heading_dict = validate_heading_dict(paragraphs, heading_dict, log,
                                             bookmark_indices=bm_idx_set)

        part_set = set(heading_dict['parts'])
        chapter_set = set(heading_dict['chapters'])

        log("\n-- STEP 3: Formatting with Markdown headings ---------")
        # Detect ALL CAPS section breaks: short, ALL CAPS paragraphs between
        # chapter headings. Add blank line before them for visual separation
        # without adding them to the Kindle TOC.
        all_heading_set = part_set | chapter_set
        caps_breaks = 0
        for i, p in enumerate(paragraphs):
            s = p.strip()
            if (s and 10 < len(s) < 60
                    and s == s.upper()
                    and any(c.isalpha() for c in s)
                    and i not in all_heading_set
                    and not s.startswith('#')
                    and not s.endswith('.')
                    and not re.match(r'^\d', s)):
                # Verify followed by body text (not another heading or short line)
                if i + 1 < len(paragraphs):
                    nxt = paragraphs[i + 1].strip()
                    if nxt and len(nxt) > 80 and not nxt.startswith('#'):
                        paragraphs[i] = f"\n{s}"  # extra blank line before
                        caps_breaks += 1
        if caps_breaks:
            log(f"  Visual separation added for {caps_breaks} ALL-CAPS section breaks")

        # Detect epigraph attributions near chapter headings and add visual separation.
        # Pattern: short paragraph starting with em-dash/dash within 10 paragraphs of
        # a heading, or a short paragraph containing "—Author" attribution pattern.
        epigraph_seps = 0
        _attrib_re = re.compile(
            r'^[\u2014\u2013\-\u2015]\s*[A-Z]'  # starts with dash + capital letter
            r'|^[A-Z][a-z]+\s+[A-Z][a-z]+'       # "FirstName LastName" pattern
        )
        for i, p in enumerate(paragraphs):
            s = p.strip()
            if not s or len(s) > 80 or i in all_heading_set or s.startswith('#'):
                continue
            # Check if this is an attribution line near a heading
            is_attrib = bool(_attrib_re.match(s))
            if not is_attrib:
                continue
            # Must be within 10 paragraphs of a heading
            near_heading = any(
                j in all_heading_set
                for j in range(max(0, i - 10), i)
            )
            if not near_heading:
                continue
            # Must be followed by a longer body paragraph
            if i + 1 < len(paragraphs):
                nxt = paragraphs[i + 1].strip()
                if nxt and len(nxt) > 100 and not nxt.startswith('#'):
                    paragraphs[i] = f"{s}\n"  # extra blank line after
                    epigraph_seps += 1
        if epigraph_seps:
            log(f"  Visual separation added after {epigraph_seps} epigraph attributions")

        parts = []
        for i, p in enumerate(paragraphs):
            if i in part_set:
                parts.append(f"# {p}")
            elif i in chapter_set:
                parts.append(f"## {p}")
            else:
                parts.append(p)

        final_text = "\n\n".join(parts)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_text)

        total_headings = len(heading_dict['parts']) + len(heading_dict['chapters'])
        word_count = len(final_text.split())
        log(f"\nDone! Saved to: {output_path}")
        log(f"  Words: {word_count:,}")
        log(f"  Parts: {len(heading_dict['parts'])}  |  Chapters: {len(heading_dict['chapters'])}")
        if heading_dict['parts']:
            log("\n  Part headings:")
            for idx in heading_dict['parts']:
                log(f"    -> {paragraphs[idx][:70]}")
        if heading_dict['chapters']:
            log("\n  Chapter headings:")
            for idx in heading_dict['chapters']:
                log(f"    - {paragraphs[idx][:70]}")

        # Save quality report alongside output
        if _quality_report:
            _report_dir = os.path.dirname(output_path)
            _report_stem = os.path.basename(output_path).replace('.txt', '')[:80]
            report_path = os.path.join(_report_dir, _report_stem + '_quality_report.json')
            try:
                with open(report_path, 'w', encoding='utf-8') as rf:
                    json.dump(_quality_report, rf, indent=2, ensure_ascii=False)
                log(f"  Quality report saved to: {report_path}")
            except Exception as e:
                log(f"  [warn] Failed to save quality report: {e}")

        return  # Skip regex/hints path

    log("\n-- STEP 2c: Fixing OCR artifacts ---------------------")
    paragraphs, _fix_stats = fix_ocr_artifacts(paragraphs, log)

    log("\n-- STEP 2c2: Stripping trailing footnotes ------------")
    paragraphs = strip_footnotes_from_paragraphs(paragraphs, log)

    # AI Paragraph Rejoin (page-boundary fragment repair)
    _rejoin_stats = {}
    _subheading_stats = {}
    if api_key:
        log("\n-- STEP 2d: AI Paragraph Rejoin ----------------------")
        paragraphs, _rejoin_stats = ai_rejoin_fragments(paragraphs, log, api_key=api_key)

        log("\n-- STEP 2d2: AI Sub-heading Detection ----------------")
        paragraphs, _subheading_stats = ai_detect_subheadings(
            paragraphs, log, api_key=api_key, has_bookmarks=False)

    # AI Quality Pass (detection only by default; fixes require apply_ai_fixes=True)
    _quality_report = {}
    if api_key:
        log("\n-- STEP 2e: AI Quality Pass --------------------------")
        paragraphs, _quality_report = ai_quality_pass(paragraphs, log, api_key=api_key, apply_fixes=apply_ai_fixes)
        _quality_report.update(_rejoin_stats)
        _quality_report.update(_subheading_stats)
    else:
        _quality_report.update(_rejoin_stats)
        _quality_report.update(_subheading_stats)

    # Strip page markers — bookmark path uses them in map_bookmarks_to_paragraphs,
    # but the non-bookmark path (hints or heuristic) doesn't need them.
    marker_count = 0
    for i in range(len(paragraphs)):
        if paragraphs[i].strip().startswith('<<PAGE:'):
            # Standalone marker — replace with empty string (will be filtered)
            if re.match(r'^<<PAGE:\d+>>$', paragraphs[i].strip()):
                paragraphs[i] = ''
                marker_count += 1
            else:
                # Marker embedded in text — strip it
                paragraphs[i] = re.sub(r'<<PAGE:\d+>>\s*', '', paragraphs[i]).strip()
                marker_count += 1
        elif '<<PAGE:' in paragraphs[i]:
            paragraphs[i] = re.sub(r'\s*<<PAGE:\d+>>\s*', ' ', paragraphs[i]).strip()
            marker_count += 1
    # Remove empty paragraphs left by marker removal
    paragraphs = [p for p in paragraphs if p.strip()]
    if marker_count:
        log(f"  Stripped {marker_count} page markers from text")

    log("\n-- STEP 3: Detecting chapter headings --")
    # Detect printed TOC section so chapter detection skips it
    toc_indices = detect_toc_section(paragraphs, log)
    if chapter_hints_path:
        try:
            with open(chapter_hints_path, 'r', encoding='utf-8') as f:
                hints = json.load(f)
            log(f"  Using {len(hints)} chapter hint(s) from: {chapter_hints_path}")
            paragraphs, heading_dict = apply_chapter_hints(paragraphs, hints, log)
            # Collect hints that weren't found
            matched_titles = set()
            for idx in heading_dict['parts'] + heading_dict['chapters']:
                if idx < len(paragraphs):
                    matched_titles.add(paragraphs[idx].lower().strip())
            missing = [h for h in hints if h.get('title', '').strip().lower() not in matched_titles
                       and h.get('title', '').strip().upper() not in
                           {paragraphs[i].upper().strip() for i in heading_dict['parts'] + heading_dict['chapters'] if i < len(paragraphs)}]
            if missing:
                log(f"  {len(missing)} chapter hints could not be located in cleaned text (skipped)")
                for m in missing:
                    log(f"    - {m.get('title', '')[:70]}")
            headings = heading_dict

            # -- Front matter detection for non-bookmark books --------
            # If there are paragraphs before the first chapter heading,
            # insert a synthetic "Front Matter" h1 and detect sub-sections.
            all_heading_indices = sorted(heading_dict['parts'] + heading_dict['chapters'])
            first_heading = all_heading_indices[0] if all_heading_indices else len(paragraphs)

            if first_heading > 5:
                log(f"  Detecting front matter before first heading (para {first_heading})...")
                fm_sub_headings = []

                # Scan paragraphs before the first chapter heading for front matter sections
                fm_patterns = {
                    'title': re.compile(r'^.{3,80}$'),  # short paragraph near start = likely title
                    'copyright': re.compile(r'copyright|©|all rights reserved|published by|press|isbn', re.IGNORECASE),
                    'dedication': re.compile(r'^(for |to |in memory|dedicated)', re.IGNORECASE),
                    'acknowledgements': re.compile(r'acknowledg|acknowledgment', re.IGNORECASE),
                    'preface': re.compile(r'^preface', re.IGNORECASE),
                    'foreword': re.compile(r'^foreword', re.IGNORECASE),
                }

                # Detect title: first non-empty short paragraph
                title_idx = None
                for fi in range(min(first_heading, 10)):
                    p = paragraphs[fi].strip()
                    if p and 3 < len(p) < 100 and not fm_patterns['copyright'].search(p):
                        title_idx = fi
                        fm_sub_headings.append((fi, 'Title'))
                        break

                # Detect copyright block
                for fi in range(min(first_heading, 30)):
                    p = paragraphs[fi].strip()
                    if fm_patterns['copyright'].search(p):
                        fm_sub_headings.append((fi, 'Copyright'))
                        break

                # Detect dedication, acknowledgements, preface, foreword
                for label, pattern in [('Dedication', fm_patterns['dedication']),
                                       ('Acknowledgements', fm_patterns['acknowledgements']),
                                       ('Preface', fm_patterns['preface']),
                                       ('Foreword', fm_patterns['foreword'])]:
                    for fi in range(min(first_heading, 80)):
                        p = paragraphs[fi].strip()
                        if pattern.search(p):
                            fm_sub_headings.append((fi, label))
                            break

                if fm_sub_headings:
                    # Sort by paragraph index
                    fm_sub_headings.sort(key=lambda x: x[0])

                    # Insert "Front Matter" h1 at the very beginning
                    paragraphs.insert(0, "Front Matter")
                    # Shift everything by 1
                    heading_dict['parts'] = [x + 1 for x in heading_dict['parts']]
                    heading_dict['chapters'] = [x + 1 for x in heading_dict['chapters']]
                    fm_sub_headings = [(idx + 1, label) for idx, label in fm_sub_headings]

                    # Add Front Matter as h1
                    heading_dict['parts'].append(0)

                    # Add sub-sections as h2
                    for idx, label in fm_sub_headings:
                        # Insert label as a heading paragraph before the content
                        paragraphs.insert(idx, label)
                        # Shift indices above this insertion
                        heading_dict['parts'] = [x + 1 if x >= idx else x for x in heading_dict['parts']]
                        heading_dict['chapters'] = [x + 1 if x >= idx else x for x in heading_dict['chapters']]
                        # Shift remaining fm_sub_headings
                        fm_sub_headings = [(i + 1 if i >= idx else i, l) for i, l in fm_sub_headings]
                        heading_dict['chapters'].append(idx)

                    heading_dict['parts'] = sorted(heading_dict['parts'])
                    heading_dict['chapters'] = sorted(heading_dict['chapters'])

                    log(f"  Inserted Front Matter with {len(fm_sub_headings)} sub-sections: {', '.join(l for _, l in fm_sub_headings)}")

                    # Update headings reference
                    headings = heading_dict

        except (json.JSONDecodeError, OSError) as e:
            log(f"  [warn] Failed to load chapter hints: {e} -- falling back to regex")
            headings = detect_chapters(paragraphs, log, toc_indices=toc_indices)
    else:
        headings = detect_chapters(paragraphs, log, toc_indices=toc_indices)

    log("\n-- STEP 3b: Validating heading indices -----------------")
    headings = validate_heading_dict(paragraphs, headings, log,
                                     bookmark_indices=set())

    part_set    = set(headings['parts'])
    chapter_set = set(headings['chapters'])

    log("\n-- STEP 4: Formatting and saving --")
    # Mark headings with Markdown-style markers so Calibre can build a TOC.
    #   # Part Title      -> level 1 (Calibre h1)
    #   ## Chapter Title  -> level 2 (Calibre h2)
    parts = []
    for i, p in enumerate(paragraphs):
        if i in part_set:
            parts.append(f"# {p}")
        elif i in chapter_set:
            parts.append(f"## {p}")
        else:
            parts.append(p)

    final_text = "\n\n".join(parts)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(final_text)

    word_count = len(final_text.split())
    log(f"\nDone! Saved to: {output_path}")
    log(f"  Words: {word_count:,}")
    log(f"  Parts: {len(headings['parts'])}  |  Chapters: {len(headings['chapters'])}")
    if headings['parts']:
        log("\n  Part headings:")
        for idx in headings['parts']:
            log(f"    -> {paragraphs[idx][:70]}")
    if headings['chapters']:
        log("\n  Chapter headings:")
        for idx in headings['chapters']:
            log(f"    - {paragraphs[idx][:70]}")

    # Save quality report alongside output
    if _quality_report:
        report_path = re.sub(r'\.txt$', '_quality_report.json', output_path)
        try:
            with open(report_path, 'w', encoding='utf-8') as rf:
                json.dump(_quality_report, rf, indent=2, ensure_ascii=False)
            log(f"  Quality report saved to: {report_path}")
        except Exception as e:
            log(f"  [warn] Failed to save quality report: {e}")


# ───────────────────────────────────────────────────────────
#  CLI MODE
# ───────────────────────────────────────────────────────────

def run_cli():
    """Headless CLI for pipeline / PowerShell automation."""
    # Force UTF-8 output on Windows to avoid 'charmap' codec errors
    # when stdout/stderr is captured by PowerShell (cp1252 can't handle
    # Unicode box-drawing chars and symbols in progress output)
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8', errors='replace') # type: ignore
        sys.stderr.reconfigure(encoding='utf-8', errors='replace') # type: ignore

    ap = argparse.ArgumentParser(
        description="Ebook to Balabolka Converter -- extract and format ebook text for TTS or Kindle",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  balabolka  Strip front/back matter, ALL-CAPS chapter headings (default)
  kindle     Keep full content, Markdown chapter headings for Calibre TOC

Examples:
  python pdf_to_balabolka.py --input book.pdf --output-dir output/balabolka-txt
  python pdf_to_balabolka.py --input book.epub --output-dir output/balabolka-txt
  python pdf_to_balabolka.py --input book.mobi --mode kindle --calibre-path "C:\\Program Files\\Calibre2\\ebook-convert.exe"
  python pdf_to_balabolka.py --input book.pdf --mode kindle --output-dir output/kindle
  python pdf_to_balabolka.py --input book.pdf --mode kindle --suffix _kindle.txt
  python pdf_to_balabolka.py          (no args -- launches GUI)
        """,
    )
    ap.add_argument("--input", required=True,
                    help="Path to the input ebook file (supported: pdf, epub, mobi, azw, azw3, djvu)")
    ap.add_argument("--output-dir", default=None,
                    help="Folder for the output .txt file (default: same folder as input)")
    ap.add_argument("--mode", choices=["balabolka", "kindle"], default="balabolka",
                    help="Extraction mode: 'balabolka' strips front/back matter; "
                         "'kindle' keeps full content for Calibre (default: balabolka)")
    ap.add_argument("--suffix", default=None,
                    help="Suffix for output filename (default: _balabolka.txt or _kindle.txt)")
    ap.add_argument("--quiet", action="store_true",
                    help="Suppress progress output (only errors)")
    ap.add_argument("--api-key", default=None,
                    help="Anthropic API key for AI Quality Pass. "
                         "Falls back to ANTHROPIC_API_KEY environment variable.")
    ap.add_argument("--apply-ai-fixes", action="store_true",
                    help="Enable AI Quality Pass fix application. Without this flag, "
                         "the quality pass only detects and scores issues without "
                         "modifying text. Use with caution — AI fixes can alter content.")
    ap.add_argument("--chapter-hints", default=None,
                    help="Path to a JSON file with pre-detected chapter titles and levels "
                         "(from Claude API).  Format: [{\"level\":1,\"title\":\"Part One\"}, "
                         "{\"level\":2,\"title\":\"Chapter 1: Name\"}].  "
                         "When provided, overrides the built-in regex chapter detection.")
    ap.add_argument("--html-extraction", action="store_true",
                    help="Use pdfminer HTML-aware extraction with font metadata. "
                         "Produces semantic HTML instead of plain text.")
    ap.add_argument("--ocr", action="store_true",
                    help="Force Tesseract OCR extraction (for scanned/image-only PDFs)")
    ap.add_argument("--no-ocr", action="store_true",
                    help="Disable OCR auto-detection, force standard text extraction")
    ap.add_argument("--skip-footnotes", action="store_true",
                    help="Skip footnote/endnote linking (used when profile strips footnotes)")
    ap.add_argument("--tesseract-path", default=None,
                    help="Path to tesseract.exe (auto-detected from PATH if not set)")
    ap.add_argument("--poppler-path", default=None,
                    help="Path to poppler bin directory (for pdf2image page rendering)")
    ap.add_argument("--ocr-dpi", type=int, default=300,
                    help="DPI for OCR page rendering (default: 300)")
    ap.add_argument("--calibre-path", default=None,
                    help="Path to Calibre's ebook-convert.exe (auto-detected if not specified)")
    ap.add_argument("--epub-html", action="store_true",
                    help="For EPUB input: extract and merge chapter HTML instead of plain text. "
                         "Preserves formatting (bold, italic, headings, links).")
    ap.add_argument("--force-columns", action="store_true",
                    help="Force PyMuPDF column-aware extraction even if detection confidence is low")
    ap.add_argument("--no-cache", action="store_true", default=False,
                    help="Skip extraction cache lookup, force fresh extraction")
    ap.add_argument("--use-gemini", action="store_true",
                    help="Use Gemini Flash for full book transcription (Tier 2.5). "
                         "More capable than Tesseract, 10-20x cheaper than Claude Vision. "
                         "Cost: ~$0.50/book. Requires GEMINI_API_KEY.")
    ap.add_argument("--gemini-remediate", action="store_true",
                    help="Use Gemini Flash to remediate specific low-quality pages "
                         "identified by quality variance. Only re-extracts flagged pages. "
                         "Cost: ~$0.002/page. Requires GEMINI_API_KEY.")
    ap.add_argument("--gemini-cost-limit", type=float, default=5.0,
                    help="Maximum allowed cost for Gemini extraction in USD (default: $5.00)")
    ap.add_argument("--gemini-model", default=None,
                    help="Gemini model to use (default: from settings.json or gemini-2.5-flash)")
    ap.add_argument("--use-vision", action="store_true",
                    help="Use Claude Vision API for page-by-page transcription (Tier 3). "
                         "Highest quality — handles multi-script, custom fonts, degraded scans. "
                         "Cost: ~$0.02-0.04/page. Requires ANTHROPIC_API_KEY.")
    ap.add_argument("--vision-cost-limit", type=float, default=15.0,
                    help="Maximum allowed cost for Vision extraction in USD (default: $15.00). "
                         "Aborts if estimated cost exceeds this limit.")
    ap.add_argument("--tts-enhance", action="store_true",
                    help="Apply TTS voice tags (silence, pacing, emphatic closers)")
    ap.add_argument("--tag-syntax", choices=["sapi", "universal"], default="sapi",
                    help="Tag format: 'sapi' for <voice>/<silence> XML tags, "
                         "'universal' for {{Voice=}}/{{Pause=}} tags (default: sapi)")
    ap.add_argument("--dialogue-voices", action="store_true", default=False,
                    help="Tag detected dialogue with alternate TTS voice (Guy Online)")
    ap.add_argument("--compare-extractors", action="store_true", default=False,
                    help="For borderline PDFs (score 60-80), try all 3 extractors and pick the best")
    ap.add_argument("--ocr-table", default=None,
                    help="Path to custom OCR substitution JSON (merged on top of config/ocr_substitutions.json)")
    ap.add_argument("--dump-ocr-table", action="store_true",
                    help="Print the effective OCR substitution table and exit")

    args = ap.parse_args()

    # --dialogue-voices implies --tts-enhance
    if args.dialogue_voices and not args.tts_enhance:
        args.tts_enhance = True

    # Handle --dump-ocr-table diagnostic flag
    if args.dump_ocr_table:
        _subs = load_ocr_substitutions(custom_path=args.ocr_table if args.ocr_table else None)
        print(json.dumps(_subs, indent=2, ensure_ascii=False))
        sys.exit(0)

    # Fallback to settings.json for tool paths if not provided via CLI
    if not args.tesseract_path or not args.poppler_path:
        _cfg_path = Path(__file__).resolve().parent.parent / "config" / "settings.json"
        if _cfg_path.exists():
            try:
                with open(_cfg_path, 'r', encoding='utf-8') as _cf:
                    _cfg_paths = json.load(_cf).get("paths", {})
                if not args.tesseract_path and _cfg_paths.get("tesseract"):
                    _tpath = _cfg_paths["tesseract"]
                    if os.path.isfile(_tpath):
                        args.tesseract_path = _tpath
                if not args.poppler_path and _cfg_paths.get("poppler"):
                    _ppath = _cfg_paths["poppler"]
                    if not os.path.isabs(_ppath):
                        _ppath = str(Path(__file__).resolve().parent.parent / _ppath)
                    if os.path.isdir(_ppath):
                        # Check if pdftoppm.exe is directly in this dir
                        if os.path.isfile(os.path.join(_ppath, "pdftoppm.exe")):
                            args.poppler_path = _ppath
                        else:
                            # Walk into nested release dirs (e.g. Release-X/poppler-X/Library/bin)
                            for root, dirs, files in os.walk(_ppath):
                                if "pdftoppm.exe" in files:
                                    args.poppler_path = root
                                    break
            except Exception:
                pass

    # Validate input
    input_path = os.path.abspath(args.input)
    if not os.path.isfile(input_path):
        print(f"[error] Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    ext = Path(input_path).suffix.lstrip('.').lower()
    if ext not in SUPPORTED_FORMATS:
        print(f"[error] Unsupported format: .{ext} (supported: {', '.join(SUPPORTED_FORMATS)})", file=sys.stderr)
        sys.exit(1)

    # Resolve output directory
    if args.output_dir:
        out_dir = os.path.abspath(args.output_dir)
    else:
        out_dir = str(Path(input_path).parent)

    if not os.path.isdir(out_dir):
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError as e:
            print(f"[error] Cannot create output directory: {out_dir} -- {e}", file=sys.stderr)
            sys.exit(1)

    # Build output filename
    stem = Path(input_path).stem
    safe_stem = re.sub(r"[^\w\s\-]", "", stem).strip().replace(" ", "_")
    default_suffix = "_kindle.txt" if args.mode == "kindle" else "_balabolka.txt"
    suffix = args.suffix if args.suffix else default_suffix
    output_path = os.path.join(out_dir, safe_stem + suffix)

    # Set up logging
    if args.quiet:
        log_fn = lambda msg: None
    else:
        def log_fn(msg):
            print(msg)

    # Run
    log_fn(f"[cli] Mode:   {args.mode}")
    log_fn(f"[cli] Input:  {input_path}")
    log_fn(f"[cli] Output: {output_path}")

    try:
        hints_path = None
        if args.chapter_hints:
            hints_path = os.path.abspath(args.chapter_hints)
            if not os.path.isfile(hints_path):
                print(f"[error] Chapter hints file not found: {hints_path}", file=sys.stderr)
                sys.exit(1)
            log_fn(f"[cli] Hints: {hints_path}")

        if args.epub_html and ext == 'epub':
            html_output = os.path.join(out_dir, safe_stem + '_kindle.html')
            log_fn(f"[cli] EPUB HTML extraction -> {html_output}")
            result = extract_html_from_epub(input_path, log_fn, output_dir=out_dir)
            raw_html = result['html']
            with open(html_output, 'w', encoding='utf-8') as f:
                f.write(raw_html)
            log_fn(f"Done! Saved EPUB HTML to: {html_output}")
            log_fn(f"  Size: {len(raw_html):,} chars")
            # Emit JSON result with paths for the PowerShell caller
            cli_result = {"html_path": html_output, "size": len(raw_html)}
            if result.get('cover_image') and os.path.isfile(result['cover_image']):
                cli_result["cover_image"] = result['cover_image']
            print(json.dumps(cli_result))
        elif args.html_extraction and args.mode == "kindle":
            html_output = re.sub(r'\.(txt|html?)$', '.html', output_path)
            if not html_output.endswith('.html'):
                html_output = output_path + '.html'

            # --- Extraction cache check ---
            _cache_hit = False
            if not args.no_cache:
                try:
                    _tools_dir = os.path.dirname(os.path.abspath(__file__))
                    if _tools_dir not in sys.path:
                        sys.path.insert(0, _tools_dir)
                    from pattern_db import get_cached_extraction, compute_file_hash
                    _src_hash = compute_file_hash(input_path)
                    _cached = get_cached_extraction(source_file_hash=_src_hash, min_score=60)
                    if _cached and _cached.get('extracted_html'):
                        log_fn(f"EXTRACTION CACHE HIT: tier {_cached['extraction_tier']}, "
                               f"method {_cached['extraction_method']}, "
                               f"quality {_cached['quality_score']}, "
                               f"served {_cached['times_served']} times")
                        with open(html_output, 'w', encoding='utf-8') as _cf:
                            _cf.write(_cached['extracted_html'])
                        _word_count = len(re.sub(r'<[^>]+>', '', _cached['extracted_html']).split())
                        log_fn(f"Done! Served from cache: {html_output}")
                        log_fn(f"  Words: {_word_count:,}")
                        log_fn(f"  HTML size: {len(_cached['extracted_html']):,} chars")
                        _cache_hit = True
                    else:
                        log_fn(f"Extraction cache miss for {_src_hash[:12]}... — running fresh extraction")
                except Exception as _ce:
                    log_fn(f"Extraction cache check failed (continuing normally): {_ce}")
            elif args.no_cache:
                log_fn("Extraction cache bypassed (--no-cache)")

            if not _cache_hit:
                _html_result = process_kindle_html(input_path, html_output, log_fn, api_key=args.api_key,
                                    force_columns=args.force_columns,
                                    skip_footnotes=args.skip_footnotes,
                                    apply_ai_fixes=args.apply_ai_fixes,
                                    tesseract_path=args.tesseract_path,
                                    poppler_path=args.poppler_path,
                                    ocr_dpi=args.ocr_dpi,
                                    no_cache=args.no_cache,
                                    use_vision=args.use_vision,
                                    vision_cost_limit=args.vision_cost_limit,
                                    use_gemini=args.use_gemini,
                                    gemini_remediate=args.gemini_remediate,
                                    gemini_cost_limit=args.gemini_cost_limit,
                                    gemini_model=args.gemini_model,
                                    compare_extractors_enabled=args.compare_extractors)
                # Emit JSON result for PSM1 caller (FU-2: includes escalation_details)
                if isinstance(_html_result, dict):
                    _cli_json = {"html_path": _html_result.get("html_path", html_output)}
                    if _html_result.get("escalation_details"):
                        _cli_json["escalation_details"] = _html_result["escalation_details"]
                    _html_size = 0
                    _hp = _cli_json["html_path"]
                    if _hp and os.path.isfile(_hp):
                        _html_size = os.path.getsize(_hp)
                    _cli_json["size"] = _html_size
                    print(json.dumps(_cli_json))
        elif args.mode == "kindle":
            process_kindle(input_path, output_path, log_fn, chapter_hints_path=hints_path,
                           api_key=args.api_key, calibre_path=args.calibre_path,
                           force_columns=args.force_columns,
                           apply_ai_fixes=args.apply_ai_fixes)
        else:
            # Determine OCR mode from CLI flags
            if args.ocr:
                use_ocr = True
            elif args.no_ocr:
                use_ocr = False
            else:
                use_ocr = None  # auto-detect

            process_pdf(input_path, output_path, log_fn,
                        chapter_hints_path=hints_path,
                        use_ocr=use_ocr,
                        tesseract_path=args.tesseract_path,
                        poppler_path=args.poppler_path,
                        ocr_dpi=args.ocr_dpi,
                        calibre_path=args.calibre_path,
                        force_columns=args.force_columns,
                        tts_enhance=args.tts_enhance,
                        tag_syntax=args.tag_syntax,
                        dialogue_voices=args.dialogue_voices)
        sys.exit(0)
    except Exception as exc:
        print(f"[error] Conversion failed: {exc}", file=sys.stderr)
        sys.exit(1)


# ───────────────────────────────────────────────────────────
#  GUI
# ───────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Ebook to Balabolka Converter")
        self.resizable(True, True)
        self.minsize(620, 520)
        self._build_ui()
        self._center_window(660, 580)

    def _center_window(self, w, h):
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        BG      = "#1e1e2e"
        PANEL   = "#2a2a3e"
        ACCENT  = "#7c6af7"
        ACCENT2 = "#56cfb2"
        TEXT    = "#e0e0f0"
        MUTED   = "#888aaa"
        BTN_FG  = "#ffffff"

        self.configure(bg=BG)
        self.option_add("*Font", "Segoe\\ UI 10")

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame",         background=BG)
        style.configure("Card.TFrame",    background=PANEL, relief="flat")
        style.configure("TLabel",         background=BG,    foreground=TEXT,  font=("Segoe UI", 10))
        style.configure("Title.TLabel",   background=BG,    foreground=ACCENT, font=("Segoe UI", 14, "bold"))
        style.configure("Sub.TLabel",     background=BG,    foreground=MUTED,  font=("Segoe UI", 9))
        style.configure("Card.TLabel",    background=PANEL, foreground=TEXT,   font=("Segoe UI", 10))
        style.configure("CardSub.TLabel", background=PANEL, foreground=MUTED,  font=("Segoe UI", 9))
        style.configure("TEntry",         fieldbackground=PANEL, foreground=TEXT,
                         insertcolor=TEXT, borderwidth=0)
        style.configure("Convert.TButton",
                         background=ACCENT, foreground=BTN_FG,
                         font=("Segoe UI", 11, "bold"),
                         borderwidth=0, focusthickness=0, padding=(20, 10))
        style.map("Convert.TButton",
                  background=[("active", "#6a58e8"), ("disabled", "#444466")],
                  foreground=[("disabled", "#888")])
        style.configure("Browse.TButton",
                         background=PANEL, foreground=TEXT,
                         font=("Segoe UI", 9),
                         borderwidth=1, padding=(8, 4))
        style.map("Browse.TButton",
                  background=[("active", "#3a3a54")])

        # Header
        hdr = ttk.Frame(self)
        hdr.pack(fill="x", padx=20, pady=(18, 4))
        ttk.Label(hdr, text="Ebook \u2192 Balabolka Converter", style="Title.TLabel").pack(anchor="w")
        ttk.Label(hdr, text="Extracts, cleans, and chapter-formats ebooks for Balabolka TTS",
                  style="Sub.TLabel").pack(anchor="w")

        sep = tk.Frame(self, height=1, bg=ACCENT)
        sep.pack(fill="x", padx=20, pady=(6, 14))

        # Input file card
        card1 = ttk.Frame(self, style="Card.TFrame", padding=14)
        card1.pack(fill="x", padx=20, pady=(0, 10))

        ttk.Label(card1, text="INPUT FILE", style="CardSub.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))

        self.input_var = tk.StringVar()
        input_entry = tk.Entry(card1, textvariable=self.input_var,
                              bg=PANEL, fg=TEXT, insertbackground=TEXT,
                              relief="flat", font=("Segoe UI", 10),
                              highlightthickness=1, highlightbackground="#444466",
                              highlightcolor=ACCENT)
        input_entry.grid(row=1, column=0, columnspan=2, sticky="ew", padx=(0, 8), ipady=5)

        ttk.Button(card1, text="Browse...", style="Browse.TButton",
                   command=self._browse_input).grid(row=1, column=2)
        card1.columnconfigure(0, weight=1)

        # Output folder card
        card2 = ttk.Frame(self, style="Card.TFrame", padding=14)
        card2.pack(fill="x", padx=20, pady=(0, 10))

        ttk.Label(card2, text="OUTPUT FOLDER", style="CardSub.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))

        self.out_var = tk.StringVar()
        out_entry = tk.Entry(card2, textvariable=self.out_var,
                              bg=PANEL, fg=TEXT, insertbackground=TEXT,
                              relief="flat", font=("Segoe UI", 10),
                              highlightthickness=1, highlightbackground="#444466",
                              highlightcolor=ACCENT)
        out_entry.grid(row=1, column=0, columnspan=2, sticky="ew", padx=(0, 8), ipady=5)

        ttk.Button(card2, text="Browse...", style="Browse.TButton",
                   command=self._browse_output).grid(row=1, column=2)
        card2.columnconfigure(0, weight=1)

        # TTS Enhancements card
        card3 = ttk.Frame(self, style="Card.TFrame", padding=14)
        card3.pack(fill="x", padx=20, pady=(0, 10))

        ttk.Label(card3, text="TTS ENHANCEMENTS", style="CardSub.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))

        self.tts_enhance_var = tk.BooleanVar(value=True)
        tts_cb = tk.Checkbutton(card3, text="Apply voice tags (silence, pacing, emphatic closers)",
                                variable=self.tts_enhance_var,
                                bg=PANEL, fg=TEXT, selectcolor="#1e1e2e",
                                activebackground=PANEL, activeforeground=TEXT,
                                font=("Segoe UI", 10))
        tts_cb.grid(row=1, column=0, sticky="w")

        self.tag_syntax_var = tk.StringVar(value="sapi")
        syntax_frame = ttk.Frame(card3, style="Card.TFrame")
        syntax_frame.grid(row=2, column=0, sticky="w", pady=(4, 0))

        ttk.Label(syntax_frame, text="Tag syntax:", style="Card.TLabel").pack(side="left")
        for val, label in [("sapi", "SAPI XML"), ("universal", "Universal")]:
            rb = tk.Radiobutton(syntax_frame, text=label, variable=self.tag_syntax_var,
                                value=val, bg=PANEL, fg=TEXT, selectcolor="#1e1e2e",
                                activebackground=PANEL, activeforeground=TEXT,
                                font=("Segoe UI", 9))
            rb.pack(side="left", padx=(8, 0))

        # Log area
        log_frame = ttk.Frame(self, style="Card.TFrame", padding=12)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        ttk.Label(log_frame, text="PROCESSING LOG", style="CardSub.TLabel").pack(anchor="w", pady=(0, 6))

        self.log_text = tk.Text(
            log_frame, height=10,
            bg="#12121e", fg=ACCENT2,
            font=("Consolas", 9),
            relief="flat", wrap="word",
            state="disabled",
            highlightthickness=1, highlightbackground="#333355",
        )
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Bottom bar
        bot = ttk.Frame(self)
        bot.pack(fill="x", padx=20, pady=(0, 16))

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(bot, textvariable=self.status_var, style="Sub.TLabel").pack(side="left")

        self.convert_btn = ttk.Button(
            bot, text="Convert",
            style="Convert.TButton",
            command=self._start_conversion,
        )
        self.convert_btn.pack(side="right")

    # File dialogs
    def _browse_input(self):
        path = filedialog.askopenfilename(
            title="Select Ebook",
            filetypes=[
                ("Ebook files", "*.pdf *.epub *.mobi *.azw *.azw3 *.djvu"),
                ("PDF files", "*.pdf"),
                ("EPUB files", "*.epub"),
                ("MOBI files", "*.mobi"),
                ("AZW files", "*.azw *.azw3"),
                ("DJVU files", "*.djvu"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.input_var.set(path)
            # Auto-set output to same folder if not yet set
            if not self.out_var.get():
                self.out_var.set(str(Path(path).parent))

    def _browse_output(self):
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self.out_var.set(folder)

    # Logging helpers
    def _append_log(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    # Conversion
    def _start_conversion(self):
        input_path = self.input_var.get().strip()
        out_dir    = self.out_var.get().strip()

        if not input_path:
            messagebox.showerror("Missing input", "Please select an ebook file.")
            return
        if not os.path.isfile(input_path):
            messagebox.showerror("File not found", f"Cannot find:\n{input_path}")
            return
        ext = Path(input_path).suffix.lstrip('.').lower()
        if ext not in SUPPORTED_FORMATS:
            messagebox.showerror("Unsupported format",
                f"Format .{ext} is not supported.\n\nSupported: {', '.join(SUPPORTED_FORMATS)}")
            return
        if not out_dir:
            messagebox.showerror("Missing output", "Please select an output folder.")
            return
        if not os.path.isdir(out_dir):
            messagebox.showerror("Invalid folder", f"Output folder does not exist:\n{out_dir}")
            return

        stem = Path(input_path).stem
        # Sanitise filename
        safe_stem = re.sub(r"[^\w\s\-]", "", stem).strip().replace(" ", "_")
        output_path = os.path.join(out_dir, safe_stem + "_balabolka.txt")

        self._clear_log()
        self._append_log(f"Converting: {Path(input_path).name}")
        self._append_log(f"Output:     {output_path}\n")
        self.status_var.set("Processing...")
        self.convert_btn.state(["disabled"])

        def worker():
            try:
                process_pdf(input_path, output_path, self._append_log,
                            tts_enhance=self.tts_enhance_var.get(),
                            tag_syntax=self.tag_syntax_var.get())
                self.after(0, lambda: self.status_var.set("Conversion complete"))
                self.after(0, lambda: messagebox.showinfo(
                    "Done",
                    f"File saved:\n{output_path}\n\n"
                    "In Balabolka: Tools -> Split and Convert to Audio Files\n"
                    "Split method: 'by lines where all letters are capital'"
                ))
            except Exception as exc:
                self.after(0, lambda: self._append_log(f"\nERROR: {exc}"))
                self.after(0, lambda: self.status_var.set("Error -- see log"))
                self.after(0, lambda: messagebox.showerror("Error", str(exc)))
            finally:
                self.after(0, lambda: self.convert_btn.state(["!disabled"]))

        threading.Thread(target=worker, daemon=True).start()


# ───────────────────────────────────────────────────────────
#  ENTRY POINT
# ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    # If --input is present on the command line, run in headless CLI mode.
    # Otherwise, launch the Tkinter GUI.
    if "--input" in sys.argv:
        run_cli()
    else:
        app = App()
        app.mainloop()
