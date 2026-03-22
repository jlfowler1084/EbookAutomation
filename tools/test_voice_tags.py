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

import pytest
from pdf_to_balabolka import (
    detect_scene_breaks,
    detect_emphatic_closers,
    apply_voice_tags,
    detect_chapters,
    detect_chapters_flat,
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
        assert out[0] == "CHAPTER ONE"

    def test_chapter_silence_inserted_after_heading(self):
        paras = ["Chapter One", "Some body text here."]
        out = apply_voice_tags(paras, self._cs(chapters=[0]), tag_syntax='sapi', log=nolog)
        assert out[1] == f'<silence msec="{CHAPTER_SILENCE_MS}"/>'

    def test_part_silence_longer_than_chapter(self):
        paras = ["Part One", "Chapter Two", "Body text here with words."]
        out = apply_voice_tags(paras, self._cs(parts=[0], chapters=[1]), tag_syntax='sapi', log=nolog)
        assert out[1] == f'<silence msec="{PART_SILENCE_MS}"/>'
        assert out[3] == f'<silence msec="{CHAPTER_SILENCE_MS}"/>'

    def test_scene_break_replaced_with_silence(self):
        paras = ["Body text.", "***", "More body text."]
        out = apply_voice_tags(paras, self._cs(), tag_syntax='sapi', log=nolog)
        assert out[1] == f'<silence msec="{SCENE_BREAK_SILENCE_MS}"/>'

    def test_emphatic_closer_wrapped_in_rate_tag(self):
        paras = ["He walked into the room. He was alone."]
        out = apply_voice_tags(paras, self._cs(), tag_syntax='sapi', log=nolog)
        combined = "\n\n".join(out)
        assert '<rate speed="-1">' in combined
        assert "He was alone." in combined

    def test_emphatic_silence_appended_after_closer(self):
        paras = ["He walked into the room. He was alone."]
        out = apply_voice_tags(paras, self._cs(), tag_syntax='sapi', log=nolog)
        assert f'<silence msec="{EMPHATIC_SILENCE_MS}"/>' in out

    def test_universal_syntax_chapter_pause(self):
        paras = ["Chapter One", "Body text."]
        out = apply_voice_tags(paras, self._cs(chapters=[0]), tag_syntax='universal', log=nolog)
        assert out[1] == f'{{{{Pause={CHAPTER_SILENCE_MS}}}}}'

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
        emphatic_silence = f'<silence msec="{EMPHATIC_SILENCE_MS}"/>'
        scene_silence = f'<silence msec="{SCENE_BREAK_SILENCE_MS}"/>'
        assert emphatic_silence not in out
        assert scene_silence in out

    def test_emphatic_silence_skipped_when_next_is_heading(self):
        paras = ["He walked. He was alone.", "Chapter Two"]
        out = apply_voice_tags(paras, self._cs(chapters=[1]), tag_syntax='sapi', log=nolog)
        emphatic_silence = f'<silence msec="{EMPHATIC_SILENCE_MS}"/>'
        assert emphatic_silence not in out

    def test_output_length_heading_plus_silence_plus_body(self):
        # 1 chapter heading → [heading, silence, body] = 3 items
        paras = ["Chapter One", "Body text here with enough words."]
        out = apply_voice_tags(paras, self._cs(chapters=[0]), tag_syntax='sapi', log=nolog)
        assert len(out) == 3

    def test_plain_paragraph_unchanged(self):
        paras = ["This is a long body paragraph with many words and does not qualify as emphatic."]
        out = apply_voice_tags(paras, self._cs(), tag_syntax='sapi', log=nolog)
        assert out == paras

    def test_heading_uppercase_no_xml_on_same_line(self):
        # ALL CAPS heading line must contain no XML tags (Balabolka split rule)
        paras = ["Chapter One", "Body."]
        out = apply_voice_tags(paras, self._cs(chapters=[0]), tag_syntax='sapi', log=nolog)
        assert out[0] == "CHAPTER ONE"
        assert "<" not in out[0]


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


if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-v"],
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    sys.exit(result.returncode)
