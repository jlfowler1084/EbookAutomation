"""
Tests for Tier 1 Voice Tags (TDD — written before implementation).

Run:
    python -m pytest tools/test_voice_tags.py -v
Or from the tools directory:
    python -m pytest test_voice_tags.py -v
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import re
import pytest
from pdf_to_balabolka import (
    detect_scene_breaks,
    detect_emphatic_closers,
    apply_voice_tags,
    detect_chapters,
    detect_chapters_flat,
    detect_dialogue_spans,
    _build_voiced_paragraph,
    _voice_wrap,
    CHAPTER_SILENCE_MS,
    PART_SILENCE_MS,
    SCENE_BREAK_SILENCE_MS,
    EMPHATIC_SILENCE_MS,
    EMPHATIC_RATE,
)

nolog = lambda m: None


# ─────────────────────────────────────────────────────────────
#  detect_scene_breaks
# ─────────────────────────────────────────────────────────────

class TestDetectSceneBreaks:
    def test_asterisk_triple(self):
        paras = ["Some text.", "***", "More text."]
        assert detect_scene_breaks(paras, set(), nolog) == {1}

    def test_asterisk_spaced(self):
        paras = ["Some text.", "* * *", "More text."]
        assert detect_scene_breaks(paras, set(), nolog) == {1}

    def test_hash_triple(self):
        paras = ["Some text.", "###", "More text."]
        assert detect_scene_breaks(paras, set(), nolog) == {1}

    def test_dash_triple(self):
        paras = ["Some text.", "---", "More text."]
        assert detect_scene_breaks(paras, set(), nolog) == {1}

    def test_em_dash_triple(self):
        paras = ["Some text.", "\u2014\u2014\u2014", "More text."]
        assert detect_scene_breaks(paras, set(), nolog) == {1}

    def test_em_dash_spaced(self):
        paras = ["Some text.", "\u2014 \u2014 \u2014", "More text."]
        assert detect_scene_breaks(paras, set(), nolog) == {1}

    def test_asterism_unicode(self):
        paras = ["Some text.", "\u2042", "More text."]
        assert detect_scene_breaks(paras, set(), nolog) == {1}

    def test_empty_paragraph_not_flagged(self):
        paras = ["Some text.", "", "More text."]
        assert detect_scene_breaks(paras, set(), nolog) == set()

    def test_heading_not_flagged(self):
        paras = ["Some text.", "***", "More text."]
        # index 1 is already in heading set — should be excluded
        assert detect_scene_breaks(paras, {1}, nolog) == set()

    def test_normal_paragraph_not_flagged(self):
        paras = ["This is a completely normal paragraph with lots of words and text in it."]
        assert detect_scene_breaks(paras, set(), nolog) == set()

    def test_short_symbol_only_tilde(self):
        paras = ["Text.", "~", "Text."]
        assert detect_scene_breaks(paras, set(), nolog) == {1}

    def test_multiple_scene_breaks(self):
        paras = ["Text.", "***", "Text.", "---", "Text."]
        assert detect_scene_breaks(paras, set(), nolog) == {1, 3}

    def test_logs_count(self):
        messages = []
        paras = ["Text.", "***", "Text."]
        detect_scene_breaks(paras, set(), lambda m: messages.append(m))
        assert any("1" in m and "scene break" in m.lower() for m in messages)

    def test_hash_spaced(self):
        paras = ["Text.", "# # #", "Text."]
        assert detect_scene_breaks(paras, set(), nolog) == {1}


# ─────────────────────────────────────────────────────────────
#  detect_emphatic_closers
# ─────────────────────────────────────────────────────────────

class TestDetectEmphaticClosers:
    def test_basic_closer(self):
        # Multi-sentence para ending with short declarative (3 words)
        paras = ["He walked into the room. The doors were closed. He was alone."]
        result = detect_emphatic_closers(paras, set(), set(), nolog)
        assert len(result) == 1
        assert result[0]['para_index'] == 0

    def test_single_sentence_skipped(self):
        # Only one sentence — too aggressive to tag all one-sentence paras
        paras = ["He was alone."]
        assert detect_emphatic_closers(paras, set(), set(), nolog) == []

    def test_question_mark_skipped(self):
        paras = ["He walked in. Was he alone?"]
        assert detect_emphatic_closers(paras, set(), set(), nolog) == []

    def test_dialogue_skipped_double_quotes(self):
        paras = ['He walked into the room and sat down. "He was alone."']
        assert detect_emphatic_closers(paras, set(), set(), nolog) == []

    def test_too_many_words_skipped(self):
        # Final sentence has 19 words — exceeds EMPHATIC_MAX_WORDS (18)
        final = "He was very much alone in the room with all the doors closed around him and no one nearby."
        paras = [f"He walked in. {final}"]
        assert detect_emphatic_closers(paras, set(), set(), nolog) == []

    def test_too_few_words_skipped(self):
        # Final sentence has 2 words — below EMPHATIC_MIN_WORDS (3)
        paras = ["He walked into the empty room and sat down. He froze."]
        # "He froze." = 2 words, should be skipped
        result = detect_emphatic_closers(paras, set(), set(), nolog)
        assert result == []

    def test_all_caps_skipped(self):
        paras = ["He walked into the room. HE WAS ALONE."]
        assert detect_emphatic_closers(paras, set(), set(), nolog) == []

    def test_heading_skipped(self):
        paras = ["He walked. He was alone."]
        assert detect_emphatic_closers(paras, {0}, set(), nolog) == []

    def test_scene_break_skipped(self):
        paras = ["He walked. He was alone."]
        assert detect_emphatic_closers(paras, set(), {0}, nolog) == []

    def test_exclamation_mark_accepted(self):
        paras = ["He walked into the empty room and looked around. He was free!"]
        result = detect_emphatic_closers(paras, set(), set(), nolog)
        assert len(result) == 1

    def test_sentence_start_offset_correct(self):
        p = "He walked into the room. He was alone."
        paras = [p]
        result = detect_emphatic_closers(paras, set(), set(), nolog)
        assert len(result) == 1
        start = result[0]['sentence_start']
        assert p[start:].strip() == "He was alone."

    def test_logs_count(self):
        messages = []
        paras = ["He walked. He was alone."]
        detect_emphatic_closers(paras, set(), set(), lambda m: messages.append(m))
        assert any("closer" in m.lower() for m in messages)


# ─────────────────────────────────────────────────────────────
#  apply_voice_tags
# ─────────────────────────────────────────────────────────────

class TestApplyVoiceTags:
    def _cs(self, chapters=None, parts=None):
        return {'parts': parts or [], 'chapters': chapters or []}

    def test_chapter_heading_uppercased(self):
        paras = ["Chapter One", "Some body text here."]
        out = apply_voice_tags(paras, self._cs(chapters=[0]), tag_syntax='sapi', log=nolog)
        assert out[0].startswith("CHAPTER ONE")

    def test_chapter_silence_inlined_with_heading(self):
        paras = ["Chapter One", "Some body text here."]
        out = apply_voice_tags(paras, self._cs(chapters=[0]), tag_syntax='sapi', log=nolog)
        assert out[0].startswith("CHAPTER ONE")
        assert out[0].endswith(f'<silence msec="{CHAPTER_SILENCE_MS}"/>')

    def test_part_silence_longer_than_chapter(self):
        paras = ["Part One", "Chapter Two", "Body text here with words."]
        out = apply_voice_tags(paras, self._cs(parts=[0], chapters=[1]), tag_syntax='sapi', log=nolog)
        assert f'<silence msec="{PART_SILENCE_MS}"/>' in out[0]
        assert f'<silence msec="{CHAPTER_SILENCE_MS}"/>' in out[1]
        assert PART_SILENCE_MS > CHAPTER_SILENCE_MS

    def test_scene_break_silence_inlined_with_preceding(self):
        paras = ["Body text.", "***", "More body text."]
        out = apply_voice_tags(paras, self._cs(), tag_syntax='sapi', log=nolog)
        # Scene break silence appended to preceding paragraph, *** removed
        assert out[0].endswith(f'<silence msec="{SCENE_BREAK_SILENCE_MS}"/>')
        assert "***" not in "\n\n".join(out)

    def test_emphatic_closer_wrapped_in_rate_tag(self):
        paras = ["He walked into the room. He was alone."]
        out = apply_voice_tags(paras, self._cs(), tag_syntax='sapi', log=nolog)
        combined = "\n\n".join(out)
        assert '<rate speed="-1">' in combined
        assert "He was alone." in combined

    def test_emphatic_silence_inlined_with_closer(self):
        paras = ["He walked into the room. He was alone."]
        out = apply_voice_tags(paras, self._cs(), tag_syntax='sapi', log=nolog)
        assert f'<silence msec="{EMPHATIC_SILENCE_MS}"/>' in out[0]

    def test_universal_syntax_chapter_pause_inlined(self):
        paras = ["Chapter One", "Body text."]
        out = apply_voice_tags(paras, self._cs(chapters=[0]), tag_syntax='universal', log=nolog)
        assert f'{{{{Pause={CHAPTER_SILENCE_MS}}}}}' in out[0]
        assert out[0].startswith("CHAPTER ONE")

    def test_universal_syntax_no_rate_tag(self):
        # Universal syntax has no rate support — text passes through unchanged
        paras = ["He walked into the room. He was alone."]
        out = apply_voice_tags(paras, self._cs(), tag_syntax='universal', log=nolog)
        combined = "\n\n".join(out)
        assert '<rate' not in combined

    def test_all_options_disabled_passes_through_unchanged(self):
        paras = ["Chapter One", "***", "Body text."]
        options = {'chapter_silence': False, 'scene_break_silence': False, 'emphatic_closers': False}
        out = apply_voice_tags(paras, self._cs(chapters=[0]), tag_syntax='sapi', options=options, log=nolog)
        # heading still uppercased, scene break not replaced, no silence
        assert out == ["CHAPTER ONE", "***", "Body text."]

    def test_emphatic_silence_skipped_when_next_is_scene_break(self):
        paras = ["He walked. He was alone.", "***"]
        out = apply_voice_tags(paras, self._cs(), tag_syntax='sapi', log=nolog)
        combined = "\n\n".join(out)
        assert f'<silence msec="{EMPHATIC_SILENCE_MS}"/>' not in combined
        assert f'<silence msec="{SCENE_BREAK_SILENCE_MS}"/>' in combined

    def test_emphatic_silence_skipped_when_next_is_heading(self):
        paras = ["He walked. He was alone.", "Chapter Two"]
        out = apply_voice_tags(paras, self._cs(chapters=[1]), tag_syntax='sapi', log=nolog)
        combined = "\n\n".join(out)
        assert f'<silence msec="{EMPHATIC_SILENCE_MS}"/>' not in combined

    def test_output_length_heading_with_inline_silence_plus_body(self):
        # 1 chapter heading → [heading+silence, body] = 2 items (silence inlined)
        paras = ["Chapter One", "Body text here with enough words."]
        out = apply_voice_tags(paras, self._cs(chapters=[0]), tag_syntax='sapi', log=nolog)
        assert len(out) == 2

    def test_plain_paragraph_unchanged(self):
        paras = ["This is a long body paragraph with many words and does not qualify as emphatic."]
        out = apply_voice_tags(paras, self._cs(), tag_syntax='sapi', log=nolog)
        assert out == paras

    def test_heading_uppercase_with_inline_silence_only(self):
        # Heading line: uppercase text + inline silence tag (no rate/voice tags)
        paras = ["Chapter One", "Body."]
        out = apply_voice_tags(paras, self._cs(chapters=[0]), tag_syntax='sapi', log=nolog)
        assert out[0].startswith("CHAPTER ONE")
        assert '<silence' in out[0]
        assert '<rate' not in out[0]
        assert '<voice' not in out[0]


# ─────────────────────────────────────────────────────────────
#  detect_chapters — structured dict return
# ─────────────────────────────────────────────────────────────

# The canonical detect_chapters requires >= 50 words between headings before
# accepting them as genuine chapters (vs TOC entries). Parts (Part I/II/etc.)
# are exempt from this check. Use _BODY60 (~60 words) to meet the threshold.
_BODY60 = (
    "This body paragraph has enough words to pass the canonical chapter detection "
    "validator. The algorithm requires at least fifty words of prose between "
    "headings before treating them as genuine chapter boundaries rather than "
    "table of contents entries. This ensures real chapters are distinguished "
    "from table of contents entries in the detection pipeline and counted correctly."
)


class TestDetectChaptersStructured:
    def test_returns_dict_with_parts_and_chapters_keys(self):
        # Just verify structure — even if headings aren't detected, keys must exist
        paras = ["Chapter 1", _BODY60, "Chapter 2", _BODY60]
        result = detect_chapters(paras, nolog)
        assert isinstance(result, dict)
        assert 'parts' in result
        assert 'chapters' in result

    def test_chapter_keyword_goes_in_chapters(self):
        # Canonical requires >= 50 body words between headings
        paras = ["Chapter 1", _BODY60, "Chapter 2", _BODY60]
        result = detect_chapters(paras, nolog)
        assert 0 in result['chapters']
        assert 0 not in result['parts']

    def test_part_keyword_goes_in_parts(self):
        # Canonical is_part_heading matches "Part <Roman/digit>" — not spelled-out numbers
        paras = ["Part I", _BODY60, "Part II", _BODY60]
        result = detect_chapters(paras, nolog)
        assert 0 in result['parts']
        assert 0 not in result['chapters']

    def test_parts_and_chapters_lists_are_disjoint(self):
        paras = ["Part I", "Chapter 1", _BODY60, "Chapter 2", _BODY60]
        result = detect_chapters(paras, nolog)
        part_set = set(result['parts'])
        chapter_set = set(result['chapters'])
        assert part_set.isdisjoint(chapter_set)


# ─────────────────────────────────────────────────────────────
#  detect_chapters_flat — backwards compatibility
# ─────────────────────────────────────────────────────────────

class TestDetectChaptersFlat:
    def test_returns_sorted_list(self):
        paras = [
            "Chapter One",
            "Body text with enough words to qualify as normal prose content.",
            "Chapter Two",
            "More body text with enough words to qualify as normal prose.",
        ]
        result = detect_chapters_flat(paras, nolog)
        assert isinstance(result, list)
        assert result == sorted(result)

    def test_contains_heading_indices(self):
        paras = ["Chapter 1", _BODY60, "Chapter 2", _BODY60]
        result = detect_chapters_flat(paras, nolog)
        assert 0 in result
        assert 2 in result

    def test_equivalent_to_union_of_structured(self):
        paras = [
            "Part One",
            "Body text with enough words.",
            "Chapter Two",
            "More body text with enough words to qualify as prose.",
            "Chapter Three",
            "Yet more body text here.",
        ]
        flat = detect_chapters_flat(paras, nolog)
        structured = detect_chapters(paras, nolog)
        expected = sorted(structured['parts'] + structured['chapters'])
        assert flat == expected


class TestDetectDialogueSpans:
    def test_detect_dialogue_basic(self):
        spans = detect_dialogue_spans('He said, "I never meant for this to happen." She nodded.')
        assert len(spans) == 1
        assert spans[0][2] == 'I never meant for this to happen.'

    def test_detect_dialogue_multiple(self):
        text = '"Where are you going?" she asked. "To the store for some groceries," he replied.'
        spans = detect_dialogue_spans(text)
        assert len(spans) == 2

    def test_detect_dialogue_short_ignored(self):
        """Quotes under 3 words are not dialogue — likely emphasis."""
        spans = detect_dialogue_spans('She said "no" firmly.')
        assert len(spans) == 0

    def test_detect_dialogue_smart_quotes(self):
        spans = detect_dialogue_spans('He whispered, \u201cThis changes everything between us.\u201d')
        assert len(spans) == 1

    def test_detect_dialogue_number_only_ignored(self):
        spans = detect_dialogue_spans('The sign read "1234, 5678, 9012."')
        assert len(spans) == 0


class TestBuildVoicedParagraph:
    def test_build_voiced_simple(self):
        para = 'He said, "I never meant for this to happen." She nodded.'
        spans = detect_dialogue_spans(para)
        result = _build_voiced_paragraph(para, spans, 'Microsoft Guy Online', 150, 200, 'sapi')
        assert '<voice required="Name=Microsoft Guy Online">' in result
        assert '<silence msec="150"/>' in result
        assert '<silence msec="200"/>' in result
        assert 'She nodded.' in result

    def test_voice_wrap_sapi(self):
        result = _voice_wrap('hello', 'Microsoft Guy Online', 'sapi')
        assert result == '<voice required="Name=Microsoft Guy Online">hello</voice>'

    def test_voice_wrap_universal_passthrough(self):
        result = _voice_wrap('hello', 'Microsoft Guy Online', 'universal')
        assert result == 'hello'


class TestApplyVoiceTagsDialogue:
    @staticmethod
    def _cs(parts=None, chapters=None):
        return {'parts': parts or [], 'chapters': chapters or []}

    def test_dialogue_tagged_when_enabled(self):
        paras = [
            '# Chapter One',
            'He walked into the room.',
            '"I have been waiting for you," she said quietly.',
            'The door closed behind him.',
        ]
        cs = self._cs(chapters=[0])
        options = {'chapter_silence': True, 'scene_break_silence': True,
                   'emphatic_closers': True, 'dialogue_voices': True}
        out = apply_voice_tags(paras, cs, tag_syntax='sapi', options=options, log=nolog)
        assert out[0].startswith('# CHAPTER ONE')
        tagged_para = [p for p in out if 'Microsoft Guy Online' in p]
        assert len(tagged_para) == 1

    def test_no_dialogue_by_default(self):
        """Dialogue voices off by default — no <voice> tags appear."""
        paras = ['"Hello there my good friend," he said warmly.']
        cs = self._cs()
        out = apply_voice_tags(paras, cs, tag_syntax='sapi', log=nolog)
        assert '<voice' not in out[0]

    def test_blockquote_gets_aria_voice(self):
        paras = ['> This is a formal citation from another source entirely.']
        cs = self._cs()
        options = {'chapter_silence': True, 'scene_break_silence': True,
                   'emphatic_closers': True, 'dialogue_voices': True}
        out = apply_voice_tags(paras, cs, tag_syntax='sapi', options=options, log=nolog)
        tagged = [p for p in out if 'Microsoft Aria Online' in p]
        assert len(tagged) == 1


# ─────────────────────────────────────────────────────────────
#  Em dash pause insertion (EB-77)
# ─────────────────────────────────────────────────────────────

class TestEmDashPause:
    def _cs(self):
        return {'parts': [], 'chapters': []}

    def test_em_dash_replaced_with_silence(self):
        paras = ["The king arrived\u2014his last refuge\u2014before nightfall."]
        out = apply_voice_tags(paras, self._cs(), tag_syntax='sapi', log=nolog)
        combined = "\n\n".join(out)
        assert '<silence msec="250"/>' in combined
        assert '\u2014' not in combined

    def test_double_hyphen_replaced(self):
        paras = ["The king arrived--his last refuge--before nightfall."]
        out = apply_voice_tags(paras, self._cs(), tag_syntax='sapi', log=nolog)
        combined = "\n\n".join(out)
        assert '<silence msec="250"/>' in combined
        assert '--' not in combined

    def test_en_dash_number_range_preserved(self):
        """En dashes between numbers (page ranges) should NOT get pauses."""
        paras = ["See pages 10\u201320 for details."]
        out = apply_voice_tags(paras, self._cs(), tag_syntax='sapi', log=nolog)
        combined = "\n\n".join(out)
        assert '<silence msec="150"/>' not in combined

    def test_en_dash_between_words_gets_pause(self):
        """En dashes between words should get a shorter pause."""
        paras = ["The Paris\u2013London express departed early."]
        out = apply_voice_tags(paras, self._cs(), tag_syntax='sapi', log=nolog)
        combined = "\n\n".join(out)
        assert '<silence msec="150"/>' in combined

    def test_em_dash_pause_disabled_by_option(self):
        paras = ["The king arrived\u2014his last refuge."]
        options = {'chapter_silence': True, 'scene_break_silence': True,
                   'emphatic_closers': True, 'em_dash_pause': False}
        out = apply_voice_tags(paras, self._cs(), tag_syntax='sapi', options=options, log=nolog)
        combined = "\n\n".join(out)
        assert '250' not in combined

    def test_universal_syntax_em_dash_pause(self):
        paras = ["The king arrived\u2014before nightfall."]
        out = apply_voice_tags(paras, self._cs(), tag_syntax='universal', log=nolog)
        combined = "\n\n".join(out)
        assert '{{Pause=250}}' in combined

    def test_xml_tags_not_mangled(self):
        """Existing silence tags should pass through unchanged."""
        paras = ['<silence msec="300"/>']
        out = apply_voice_tags(paras, self._cs(), tag_syntax='sapi', log=nolog)
        assert out[0] == '<silence msec="300"/>'

    def test_single_hyphen_preserved(self):
        """Regular hyphenated words should NOT be affected."""
        paras = ["The well-known author wrote a best-selling book."]
        out = apply_voice_tags(paras, self._cs(), tag_syntax='sapi', log=nolog)
        assert "well-known" in out[0]
        assert "best-selling" in out[0]

    def test_triple_hyphen_not_matched(self):
        """Triple hyphens (scene breaks) should not be partially replaced."""
        paras = ["Text before.", "---", "Text after."]
        out = apply_voice_tags(paras, self._cs(), tag_syntax='sapi', log=nolog)
        # Scene break gets its own silence, the --- itself shouldn't be em-dash-paused
        assert '<silence msec="250"/>' not in "\n\n".join(out)


# ─────────────────────────────────────────────────────────────
#  Voice tag format validation (EB-78)
# ─────────────────────────────────────────────────────────────

class TestVoiceTagFormat:
    def test_sapi_voice_tag_format(self):
        """Verify voice tags use the exact SAPI XML format balcon expects."""
        result = _voice_wrap('Hello world', 'Microsoft Guy Online', 'sapi')
        assert result == '<voice required="Name=Microsoft Guy Online">Hello world</voice>'

    def test_universal_voice_tag_no_switch(self):
        """Universal syntax doesn't support voice switching."""
        result = _voice_wrap('Hello world', 'Microsoft Guy Online', 'universal')
        assert result == 'Hello world'


# ─────────────────────────────────────────────────────────────
#  TTS regression guard: no standalone silence tags (EB-81)
# ─────────────────────────────────────────────────────────────

class TestNoStandaloneSilenceTags:
    """Regression guard: silence tags must never appear as standalone paragraphs.

    Balcon.exe only processes SAPI XML when inline with speakable text.
    A standalone <silence.../> on its own line produces zero audio.
    This test ensures apply_voice_tags() never produces that pattern.
    """

    SILENCE_ONLY_RE = re.compile(r'^\s*<silence\s+msec="\d+"\s*/>\s*$')
    PAUSE_ONLY_RE = re.compile(r'^\s*\{\{Pause=\d+\}\}\s*$')

    def _assert_no_standalone_silence(self, output, tag_syntax='sapi'):
        """Assert no item in output is a standalone silence/pause tag."""
        pattern = self.SILENCE_ONLY_RE if tag_syntax == 'sapi' else self.PAUSE_ONLY_RE
        for i, item in enumerate(output):
            assert not pattern.match(item), (
                f"Standalone silence tag at index {i}: {item!r} — "
                f"balcon will produce zero audio. Must be inlined with adjacent text."
            )

    def _cs(self, parts=None, chapters=None):
        return {'parts': parts or [], 'chapters': chapters or []}

    def test_chapter_heading_silence_inlined(self):
        paras = ["Chapter One", "Body text here with enough words."]
        out = apply_voice_tags(paras, self._cs(chapters=[0]),
                              tag_syntax='sapi', log=nolog)
        self._assert_no_standalone_silence(out)
        assert '<silence' in out[0]

    def test_part_heading_silence_inlined(self):
        paras = ["Part One", "Chapter One", "Body text here."]
        out = apply_voice_tags(paras, self._cs(parts=[0], chapters=[1]),
                              tag_syntax='sapi', log=nolog)
        self._assert_no_standalone_silence(out)

    def test_scene_break_silence_inlined(self):
        paras = ["Body text before.", "***", "Body text after."]
        out = apply_voice_tags(paras, self._cs(),
                              tag_syntax='sapi', log=nolog)
        self._assert_no_standalone_silence(out)

    def test_emphatic_closer_silence_inlined(self):
        paras = ["He walked into the room. He was alone."]
        out = apply_voice_tags(paras, self._cs(),
                              tag_syntax='sapi', log=nolog)
        self._assert_no_standalone_silence(out)

    def test_universal_syntax_no_standalone_pause(self):
        paras = ["Chapter One", "Body text."]
        out = apply_voice_tags(paras, self._cs(chapters=[0]),
                              tag_syntax='universal', log=nolog)
        self._assert_no_standalone_silence(out, tag_syntax='universal')

    def test_complex_document_no_standalone_silence(self):
        """Full document with all tag types — no standalone silence anywhere."""
        paras = [
            "Part One",
            "Chapter One",
            "The detective arrived at the scene.",
            "He examined the room. This was the end.",
            "***",
            "Chapter Two",
            "A new day dawned over the city.",
        ]
        structure = self._cs(parts=[0], chapters=[1, 5])
        out = apply_voice_tags(paras, structure, tag_syntax='sapi', log=nolog)
        self._assert_no_standalone_silence(out)

        # Verify silence tags ARE present (not just removed)
        combined = "\n".join(out)
        assert '<silence' in combined, "Silence tags should be present, just inlined"


# ─────────────────────────────────────────────────────────────
#  SecondBrain autobook SAPI XML contract (SB-6)
# ─────────────────────────────────────────────────────────────

# Fixtures: actual output from Format-SBAutobookSSML (patched) for each format
# using a 3-paragraph stub input. Locks in the fixed contract as a snapshot.

_SAMPLE_STUDYGUIDE = (
    '<voice required="Name=Microsoft Steffan Online"><rate speed="-2">'
    "This is a personalized study guide on Test Topic, generated for you on 2026-04-09."
    "</rate></voice>\n"
    '<voice required="Name=Microsoft Steffan Online">This is paragraph one about the main topic.</voice>\n'
    "\n"
    '<silence msec="500"/><voice required="Name=Microsoft Aria Online">'
    "Key Takeaway: The most important thing to remember is focus."
    '</voice><silence msec="500"/>\n'
    "\n"
    '<silence msec="500"/><voice required="Name=Microsoft Steffan Online">'
    "Chapter 1: Getting Started</voice>\n"
    '<voice required="Name=Microsoft Steffan Online">Here is the first chapter content.</voice>\n'
    '<silence msec="500"/><voice required="Name=Microsoft Jenny Online">'
    "Decision: We will proceed with the new approach."
    '</voice><silence msec="500"/>\n'
    '<voice required="Name=Microsoft Jenny Online">Another regular line here.</voice>\n'
    '<silence msec="500"/><voice required="Name=Microsoft Jenny Online">'
    "That's the end of this study guide. Happy learning, and remember -- you've got this."
    "</voice>"
)

_SAMPLE_REVIEW = (
    '<voice required="Name=Microsoft Jenny Online"><rate speed="-2">'
    "Here's your week in review for 2026-04-09. Let's look at what you've been up to."
    "</rate></voice>\n"
    '<voice required="Name=Microsoft Jenny Online">This is paragraph one about the main topic.</voice>\n'
    "\n"
    '<silence msec="500"/><voice required="Name=Microsoft Aria Online">'
    "Key Takeaway: The most important thing to remember is focus."
    '</voice><silence msec="500"/>\n'
    "\n"
    '<silence msec="500"/><voice required="Name=Microsoft Jenny Online">'
    "Chapter 1: Getting Started</voice>\n"
    '<voice required="Name=Microsoft Jenny Online">Here is the first chapter content.</voice>\n'
    '<silence msec="500"/><voice required="Name=Microsoft Steffan Online">'
    "Decision: We will proceed with the new approach."
    '</voice><silence msec="500"/>\n'
    '<voice required="Name=Microsoft Steffan Online">Another regular line here.</voice>\n'
    '<silence msec="500"/><voice required="Name=Microsoft Steffan Online">'
    "That's your week. You're making progress, even when it doesn't feel like it. See you next week."
    "</voice>"
)

_SAMPLE_REFLECTION = (
    '<voice required="Name=Microsoft Aria Online"><rate speed="-2">'
    "Let's explore some patterns emerging from your recent thinking. Generated on 2026-04-09."
    "</rate></voice>\n"
    '<voice required="Name=Microsoft Aria Online">This is paragraph one about the main topic.</voice>\n'
    "\n"
    '<silence msec="500"/><voice required="Name=Microsoft Steffan Online">'
    "Key Takeaway: The most important thing to remember is focus."
    '</voice><silence msec="500"/>\n'
    "\n"
    '<silence msec="500"/><voice required="Name=Microsoft Aria Online">'
    "Chapter 1: Getting Started</voice>\n"
    '<voice required="Name=Microsoft Aria Online">Here is the first chapter content.</voice>\n'
    '<silence msec="500"/><voice required="Name=Microsoft Jenny Online">'
    "Decision: We will proceed with the new approach."
    '</voice><silence msec="500"/>\n'
    '<voice required="Name=Microsoft Jenny Online">Another regular line here.</voice>\n'
    '<silence msec="500"/><voice required="Name=Microsoft Jenny Online">'
    "Those are the patterns I'm seeing. Sit with them. There's no rush to resolve everything at once."
    "</voice>"
)

_SAMPLE_SESSION = (
    '<voice required="Name=Microsoft Steffan Online"><rate speed="-2">'
    "Here's a synthesis of our conversation about Test Topic, from 2026-04-09."
    "</rate></voice>\n"
    '<voice required="Name=Microsoft Steffan Online">This is paragraph one about the main topic.</voice>\n'
    "\n"
    '<silence msec="500"/><voice required="Name=Microsoft Aria Online">'
    "Key Takeaway: The most important thing to remember is focus."
    '</voice><silence msec="500"/>\n'
    "\n"
    '<silence msec="500"/><voice required="Name=Microsoft Steffan Online">'
    "Chapter 1: Getting Started</voice>\n"
    '<voice required="Name=Microsoft Steffan Online">Here is the first chapter content.</voice>\n'
    '<silence msec="500"/><voice required="Name=Microsoft Jenny Online">'
    "Decision: We will proceed with the new approach."
    '</voice><silence msec="500"/>\n'
    '<voice required="Name=Microsoft Jenny Online">Another regular line here.</voice>\n'
    '<silence msec="500"/><voice required="Name=Microsoft Jenny Online">'
    "That covers our discussion. The key decisions are clear, and the action items are ready when you are."
    "</voice>"
)

_ALL_SAMPLES = {
    "StudyGuide": _SAMPLE_STUDYGUIDE,
    "Review": _SAMPLE_REVIEW,
    "Reflection": _SAMPLE_REFLECTION,
    "Session": _SAMPLE_SESSION,
}

_FORMAT_PRIMARY_VOICES = {
    "StudyGuide": "Microsoft Steffan Online",
    "Review": "Microsoft Jenny Online",
    "Reflection": "Microsoft Aria Online",
    "Session": "Microsoft Steffan Online",
}


class TestSecondBrainTagFormat:
    """Validate SecondBrain autobook output matches the SAPI XML contract."""

    def _all_sample_text(self):
        return "\n".join(_ALL_SAMPLES.values())

    def test_no_curly_voice_tags(self):
        """No {{Voice substring should appear in any sample output."""
        assert "{{Voice" not in self._all_sample_text()

    def test_no_curly_rate_tags(self):
        """No {{Rate substring should appear in any sample output."""
        assert "{{Rate" not in self._all_sample_text()

    def test_no_curly_pause_or_silence_tags(self):
        """No {{Pause or {{Silence substring should appear."""
        text = self._all_sample_text()
        assert "{{Pause" not in text
        assert "{{Silence" not in text

    def test_no_colon_tag_syntax(self):
        """No {{Voice:, {{Rate:, {{Silence:, or {{Pause: substrings."""
        text = self._all_sample_text()
        for tag in ("{{Voice:", "{{Rate:", "{{Silence:", "{{Pause:"):
            assert tag not in text, f"Found broken tag syntax: {tag}"

    def test_voice_tag_xml_format(self):
        """Every voice tag must match SAPI XML format with an approved voice."""
        text = self._all_sample_text()
        voice_tags = re.findall(r'<voice\s+required="Name=([^"]+)">', text)
        assert len(voice_tags) > 0, "No voice tags found at all"
        pattern = re.compile(r"^Microsoft (Steffan|Guy|Aria|Jenny) Online$")
        for voice_name in voice_tags:
            assert pattern.match(voice_name), (
                f"Voice tag has unapproved name: {voice_name}"
            )

    def test_no_standalone_control_tag_lines(self):
        """No line should contain *only* a control tag (no speakable text)."""
        bad_line_re = re.compile(
            r"^\s*<(voice|rate|silence|/voice|/rate)[^>]*/?>\s*$"
        )
        text = self._all_sample_text()
        for i, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            assert not bad_line_re.match(line), (
                f"Standalone control tag on line {i}: {line!r}"
            )

    def test_approved_voices_only(self):
        """No occurrence of legacy desktop voices or non-Online voices."""
        text = self._all_sample_text()
        for name in ("Zira", "Hazel", "David"):
            assert name not in text, f"Found forbidden voice: {name}"
        voice_names = re.findall(r'<voice\s+required="Name=([^"]+)">', text)
        for name in voice_names:
            assert name.endswith("Online"), (
                f"Voice name does not end with 'Online': {name}"
            )

    def test_all_four_formats_have_intro_voice(self):
        """Each format's first non-empty content line has its primary voice."""
        for fmt, sample in _ALL_SAMPLES.items():
            expected_voice = _FORMAT_PRIMARY_VOICES[fmt]
            first_line = ""
            for line in sample.splitlines():
                if line.strip():
                    first_line = line
                    break
            assert f'<voice required="Name={expected_voice}">' in first_line, (
                f"Format {fmt!r}: first content line missing primary voice "
                f"{expected_voice!r}. Got: {first_line!r}"
            )


if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-v"],
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    sys.exit(result.returncode)
