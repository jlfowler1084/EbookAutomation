"""Unit tests for Gemini OCR integration (EB-218).

Tests cover _load_gemini_model, _get_gemini_client, extract_text_gemini,
and remediate_pages_gemini without making real API calls.
All Gemini SDK and PDF I/O is mocked via unittest.mock.

Usage:
    python tools/test_gemini_ocr.py
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import gemini_ocr

LOG = lambda msg: None  # silent logger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(text='Sample Gemini output.', in_tokens=100, out_tokens=50):
    """Build a mock generate_content response."""
    resp = MagicMock()
    resp.text = text
    usage = MagicMock()
    usage.prompt_token_count = in_tokens
    usage.candidates_token_count = out_tokens
    resp.usage_metadata = usage
    return resp


def _make_client(text='Sample Gemini output.', in_tokens=100, out_tokens=50):
    """Build a mock genai.Client whose generate_content returns one response."""
    client = MagicMock()
    client.models.generate_content.return_value = _make_response(text, in_tokens, out_tokens)
    return client


def _genai_sys_modules():
    """Return a sys.modules patch dict that satisfies 'from google.genai import types'."""
    types_mock = MagicMock()
    types_mock.Part.from_bytes.return_value = MagicMock()
    genai_mock = MagicMock()
    genai_mock.types = types_mock
    google_mock = MagicMock()
    google_mock.genai = genai_mock
    return {
        'google': google_mock,
        'google.genai': genai_mock,
        'google.genai.types': types_mock,
    }


# ---------------------------------------------------------------------------
# _load_gemini_model
# ---------------------------------------------------------------------------

class TestLoadGeminiModel(unittest.TestCase):

    def test_returns_default_when_config_file_absent(self):
        with patch.object(Path, 'exists', return_value=False):
            self.assertEqual(gemini_ocr._load_gemini_model(), 'gemini-2.5-flash')

    def test_reads_model_from_config(self):
        cfg = '{"api_models": {"gemini_flash": "gemini-2.0-flash-exp"}}'
        with patch.object(Path, 'exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=cfg)):
            self.assertEqual(gemini_ocr._load_gemini_model(), 'gemini-2.0-flash-exp')

    def test_falls_back_when_key_missing_in_config(self):
        cfg = '{"api_models": {}}'
        with patch.object(Path, 'exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=cfg)):
            self.assertEqual(gemini_ocr._load_gemini_model(), 'gemini-2.5-flash')

    def test_falls_back_on_invalid_json(self):
        with patch.object(Path, 'exists', return_value=True), \
             patch('builtins.open', mock_open(read_data='not-valid-json')):
            self.assertEqual(gemini_ocr._load_gemini_model(), 'gemini-2.5-flash')


# ---------------------------------------------------------------------------
# _get_gemini_client
# ---------------------------------------------------------------------------

class TestGetGeminiClient(unittest.TestCase):

    def test_raises_when_google_genai_not_installed(self):
        with patch.dict('sys.modules', {'google': None, 'google.genai': None}):
            with self.assertRaises(RuntimeError) as ctx:
                gemini_ocr._get_gemini_client(api_key='any-key')
        self.assertIn('google-genai', str(ctx.exception))

    def test_raises_when_no_api_key(self):
        genai_mock = MagicMock()
        google_mock = MagicMock()
        google_mock.genai = genai_mock
        with patch.dict('sys.modules', {'google': google_mock, 'google.genai': genai_mock}), \
             patch.dict('os.environ', {'GEMINI_API_KEY': ''}):
            with self.assertRaises(RuntimeError) as ctx:
                gemini_ocr._get_gemini_client(api_key=None)
        self.assertIn('GEMINI_API_KEY', str(ctx.exception))

    def test_uses_api_key_argument(self):
        genai_mock = MagicMock()
        google_mock = MagicMock()
        google_mock.genai = genai_mock
        with patch.dict('sys.modules', {'google': google_mock, 'google.genai': genai_mock}):
            gemini_ocr._get_gemini_client(api_key='explicit-key')
        genai_mock.Client.assert_called_once_with(api_key='explicit-key')

    def test_reads_api_key_from_environment(self):
        genai_mock = MagicMock()
        google_mock = MagicMock()
        google_mock.genai = genai_mock
        with patch.dict('sys.modules', {'google': google_mock, 'google.genai': genai_mock}), \
             patch.dict('os.environ', {'GEMINI_API_KEY': 'env-key'}):
            gemini_ocr._get_gemini_client(api_key=None)
        genai_mock.Client.assert_called_once_with(api_key='env-key')


# ---------------------------------------------------------------------------
# extract_text_gemini — cost limit
# ---------------------------------------------------------------------------

class TestExtractTextGeminiCostLimit(unittest.TestCase):

    def test_aborts_when_estimated_cost_exceeds_limit(self):
        # 1000 pages ~= $1.67 estimated; limit is $0.01
        with patch.object(gemini_ocr, '_get_gemini_client'), \
             patch.object(gemini_ocr, '_get_page_count', return_value=1000), \
             patch.object(gemini_ocr, '_ensure_safe_path', return_value=('f.pdf', None)), \
             patch.object(gemini_ocr, '_cleanup_safe_path'):
            result = gemini_ocr.extract_text_gemini(
                'f.pdf', LOG, api_key='key', cost_limit=0.01)
        self.assertIsNone(result)

    def test_proceeds_when_cost_under_limit(self):
        client = _make_client('Chapter One.')
        with patch.object(gemini_ocr, '_get_gemini_client', return_value=client), \
             patch.object(gemini_ocr, '_get_page_count', return_value=1), \
             patch.object(gemini_ocr, '_ensure_safe_path', return_value=('f.pdf', None)), \
             patch.object(gemini_ocr, '_cleanup_safe_path'), \
             patch.object(gemini_ocr, '_render_pages', return_value=[(1, b'png')]), \
             patch.dict('sys.modules', _genai_sys_modules()):
            result = gemini_ocr.extract_text_gemini(
                'f.pdf', LOG, api_key='key', cost_limit=100.0)
        self.assertIsNotNone(result)


# ---------------------------------------------------------------------------
# extract_text_gemini — happy path
# ---------------------------------------------------------------------------

class TestExtractTextGeminiHappyPath(unittest.TestCase):

    def _run(self, page_count=5, text='Hello world.', in_tokens=200, out_tokens=100):
        client = _make_client(text, in_tokens, out_tokens)
        pages = [(i, b'png') for i in range(1, page_count + 1)]
        with patch.object(gemini_ocr, '_get_gemini_client', return_value=client), \
             patch.object(gemini_ocr, '_get_page_count', return_value=page_count), \
             patch.object(gemini_ocr, '_ensure_safe_path', return_value=('f.pdf', None)), \
             patch.object(gemini_ocr, '_cleanup_safe_path'), \
             patch.object(gemini_ocr, '_render_pages', return_value=pages), \
             patch.dict('sys.modules', _genai_sys_modules()):
            return gemini_ocr.extract_text_gemini(
                'f.pdf', LOG, api_key='key', cost_limit=100.0, model='test-model')

    def test_returns_dict_with_required_keys(self):
        result = self._run()
        for key in ('text', 'pages_processed', 'total_pages', 'input_tokens',
                    'output_tokens', 'cost_usd'):
            self.assertIn(key, result)

    def test_text_is_non_empty(self):
        result = self._run(text='Chapter text here.')
        self.assertTrue(result['text'].strip())

    def test_total_pages_matches_page_count(self):
        result = self._run(page_count=3)
        self.assertEqual(result['total_pages'], 3)

    def test_pages_processed_equals_rendered_pages(self):
        result = self._run(page_count=3)
        self.assertEqual(result['pages_processed'], 3)

    def test_tokens_are_accumulated(self):
        # 5 pages, batch_size default 5 → 1 batch → 200 in, 100 out
        result = self._run(page_count=5, in_tokens=200, out_tokens=100)
        self.assertEqual(result['input_tokens'], 200)
        self.assertEqual(result['output_tokens'], 100)

    def test_cost_usd_is_non_negative_float(self):
        result = self._run()
        self.assertIsInstance(result['cost_usd'], float)
        self.assertGreaterEqual(result['cost_usd'], 0.0)


# ---------------------------------------------------------------------------
# extract_text_gemini — zero pages
# ---------------------------------------------------------------------------

class TestExtractTextGeminiZeroPages(unittest.TestCase):

    def test_returns_none_for_zero_page_pdf(self):
        with patch.object(gemini_ocr, '_get_gemini_client'), \
             patch.object(gemini_ocr, '_get_page_count', return_value=0):
            result = gemini_ocr.extract_text_gemini('f.pdf', LOG, api_key='key')
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# extract_text_gemini — API failure / graceful degradation
# ---------------------------------------------------------------------------

class TestExtractTextGeminiAPIFailure(unittest.TestCase):

    def test_returns_none_when_all_batches_fail(self):
        client = MagicMock()
        client.models.generate_content.side_effect = Exception('API down')
        with patch.object(gemini_ocr, '_get_gemini_client', return_value=client), \
             patch.object(gemini_ocr, '_get_page_count', return_value=2), \
             patch.object(gemini_ocr, '_ensure_safe_path', return_value=('f.pdf', None)), \
             patch.object(gemini_ocr, '_cleanup_safe_path'), \
             patch.object(gemini_ocr, '_render_pages', return_value=[(1, b'p'), (2, b'p')]), \
             patch.dict('sys.modules', _genai_sys_modules()):
            result = gemini_ocr.extract_text_gemini(
                'f.pdf', LOG, api_key='key', cost_limit=100.0)
        self.assertIsNone(result)

    def test_partial_success_returns_text_from_successful_batches(self):
        # Batch 1 succeeds, batch 2 raises — result should contain batch 1 text
        good = _make_response('Good batch.')
        client = MagicMock()
        client.models.generate_content.side_effect = [good, Exception('fail')]
        pages_b1 = [(i, b'p') for i in range(1, 6)]
        # _render_pages called twice; return pages for each batch
        with patch.object(gemini_ocr, '_get_gemini_client', return_value=client), \
             patch.object(gemini_ocr, '_get_page_count', return_value=10), \
             patch.object(gemini_ocr, '_ensure_safe_path', return_value=('f.pdf', None)), \
             patch.object(gemini_ocr, '_cleanup_safe_path'), \
             patch.object(gemini_ocr, '_render_pages', return_value=pages_b1), \
             patch.dict('sys.modules', _genai_sys_modules()):
            result = gemini_ocr.extract_text_gemini(
                'f.pdf', LOG, api_key='key', cost_limit=100.0, batch_size=5)
        self.assertIsNotNone(result)
        self.assertIn('Good batch.', result['text'])

    def test_render_failure_skips_batch_and_returns_none_if_all_skip(self):
        client = _make_client('text')
        with patch.object(gemini_ocr, '_get_gemini_client', return_value=client), \
             patch.object(gemini_ocr, '_get_page_count', return_value=1), \
             patch.object(gemini_ocr, '_ensure_safe_path', return_value=('f.pdf', None)), \
             patch.object(gemini_ocr, '_cleanup_safe_path'), \
             patch.object(gemini_ocr, '_render_pages', side_effect=Exception('render fail')), \
             patch.dict('sys.modules', _genai_sys_modules()):
            result = gemini_ocr.extract_text_gemini(
                'f.pdf', LOG, api_key='key', cost_limit=100.0)
        self.assertIsNone(result)

    def test_empty_render_result_skips_batch(self):
        client = _make_client('text')
        with patch.object(gemini_ocr, '_get_gemini_client', return_value=client), \
             patch.object(gemini_ocr, '_get_page_count', return_value=1), \
             patch.object(gemini_ocr, '_ensure_safe_path', return_value=('f.pdf', None)), \
             patch.object(gemini_ocr, '_cleanup_safe_path'), \
             patch.object(gemini_ocr, '_render_pages', return_value=[]), \
             patch.dict('sys.modules', _genai_sys_modules()):
            result = gemini_ocr.extract_text_gemini(
                'f.pdf', LOG, api_key='key', cost_limit=100.0)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# extract_text_gemini — model selection
# ---------------------------------------------------------------------------

class TestExtractTextGeminiModelSelection(unittest.TestCase):

    def _get_called_model(self, client):
        call = client.models.generate_content.call_args
        return (call.kwargs.get('model')
                if call and call.kwargs else
                call[1].get('model') if call and len(call) > 1 else None)

    def test_explicit_model_arg_is_used(self):
        client = _make_client('text')
        with patch.object(gemini_ocr, '_get_gemini_client', return_value=client), \
             patch.object(gemini_ocr, '_get_page_count', return_value=1), \
             patch.object(gemini_ocr, '_ensure_safe_path', return_value=('f.pdf', None)), \
             patch.object(gemini_ocr, '_cleanup_safe_path'), \
             patch.object(gemini_ocr, '_render_pages', return_value=[(1, b'p')]), \
             patch.dict('sys.modules', _genai_sys_modules()):
            gemini_ocr.extract_text_gemini(
                'f.pdf', LOG, api_key='key', cost_limit=100.0, model='explicit-model')
        self.assertEqual(self._get_called_model(client), 'explicit-model')

    def test_config_model_used_when_model_is_none(self):
        client = _make_client('text')
        with patch.object(gemini_ocr, '_get_gemini_client', return_value=client), \
             patch.object(gemini_ocr, '_get_page_count', return_value=1), \
             patch.object(gemini_ocr, '_ensure_safe_path', return_value=('f.pdf', None)), \
             patch.object(gemini_ocr, '_cleanup_safe_path'), \
             patch.object(gemini_ocr, '_render_pages', return_value=[(1, b'p')]), \
             patch.object(gemini_ocr, '_load_gemini_model', return_value='config-model'), \
             patch.dict('sys.modules', _genai_sys_modules()):
            gemini_ocr.extract_text_gemini(
                'f.pdf', LOG, api_key='key', cost_limit=100.0, model=None)
        self.assertEqual(self._get_called_model(client), 'config-model')


# ---------------------------------------------------------------------------
# remediate_pages_gemini — happy path
# ---------------------------------------------------------------------------

class TestRemediatePagesGeminiHappyPath(unittest.TestCase):

    def _run(self, page_numbers, response_text, in_tokens=50, out_tokens=30):
        client = _make_client(response_text, in_tokens, out_tokens)
        pages = [(n, b'p') for n in page_numbers]
        with patch.object(gemini_ocr, '_get_gemini_client', return_value=client), \
             patch.object(gemini_ocr, '_ensure_safe_path', return_value=('f.pdf', None)), \
             patch.object(gemini_ocr, '_cleanup_safe_path'), \
             patch.object(gemini_ocr, '_render_pages', return_value=pages), \
             patch.dict('sys.modules', _genai_sys_modules()):
            return gemini_ocr.remediate_pages_gemini(
                'f.pdf', page_numbers, LOG, api_key='key', model='test-model')

    def test_returns_dict_with_pages_key(self):
        result = self._run([3], '<<PAGE:3>>\nPage three content.')
        self.assertIsNotNone(result)
        self.assertIn('pages', result)

    def test_parses_single_page_marker(self):
        result = self._run([5], '<<PAGE:5>>\nFifth page text.')
        self.assertIn(5, result['pages'])
        self.assertIn('Fifth page text.', result['pages'][5])

    def test_parses_multiple_page_markers(self):
        response = '<<PAGE:10>>\nTenth page.\n<<PAGE:20>>\nTwentieth page.'
        result = self._run([10, 20], response)
        self.assertEqual(len(result['pages']), 2)
        self.assertIn('Tenth page.', result['pages'][10])
        self.assertIn('Twentieth page.', result['pages'][20])

    def test_text_before_first_marker_is_discarded(self):
        response = 'Preamble noise.\n<<PAGE:1>>\nReal content.'
        result = self._run([1], response)
        self.assertNotIn('Preamble', result['pages'].get(1, ''))
        self.assertIn('Real content.', result['pages'][1])

    def test_returns_token_counts(self):
        result = self._run([1], '<<PAGE:1>>\nHello.', in_tokens=50, out_tokens=30)
        self.assertEqual(result['input_tokens'], 50)
        self.assertEqual(result['output_tokens'], 30)

    def test_cost_usd_is_non_negative_float(self):
        result = self._run([1], '<<PAGE:1>>\nHello.')
        self.assertIsInstance(result['cost_usd'], float)
        self.assertGreaterEqual(result['cost_usd'], 0.0)


# ---------------------------------------------------------------------------
# remediate_pages_gemini — edge cases / failure modes
# ---------------------------------------------------------------------------

class TestRemediatePagesGeminiEdgeCases(unittest.TestCase):

    def test_empty_page_list_returns_none_immediately(self):
        with patch.object(gemini_ocr, '_get_gemini_client') as mock_client:
            result = gemini_ocr.remediate_pages_gemini('f.pdf', [], LOG, api_key='key')
        self.assertIsNone(result)
        mock_client.assert_not_called()

    def test_render_failure_returns_none(self):
        client = _make_client('text')
        with patch.object(gemini_ocr, '_get_gemini_client', return_value=client), \
             patch.object(gemini_ocr, '_ensure_safe_path', return_value=('f.pdf', None)), \
             patch.object(gemini_ocr, '_cleanup_safe_path'), \
             patch.object(gemini_ocr, '_render_pages', side_effect=Exception('render fail')):
            result = gemini_ocr.remediate_pages_gemini('f.pdf', [1], LOG, api_key='key')
        self.assertIsNone(result)

    def test_empty_render_result_returns_none(self):
        client = _make_client('text')
        with patch.object(gemini_ocr, '_get_gemini_client', return_value=client), \
             patch.object(gemini_ocr, '_ensure_safe_path', return_value=('f.pdf', None)), \
             patch.object(gemini_ocr, '_cleanup_safe_path'), \
             patch.object(gemini_ocr, '_render_pages', return_value=[]), \
             patch.dict('sys.modules', _genai_sys_modules()):
            result = gemini_ocr.remediate_pages_gemini('f.pdf', [1], LOG, api_key='key')
        self.assertIsNone(result)

    def test_api_error_returns_none(self):
        client = MagicMock()
        client.models.generate_content.side_effect = Exception('API error')
        with patch.object(gemini_ocr, '_get_gemini_client', return_value=client), \
             patch.object(gemini_ocr, '_ensure_safe_path', return_value=('f.pdf', None)), \
             patch.object(gemini_ocr, '_cleanup_safe_path'), \
             patch.object(gemini_ocr, '_render_pages', return_value=[(1, b'p')]), \
             patch.dict('sys.modules', _genai_sys_modules()):
            result = gemini_ocr.remediate_pages_gemini('f.pdf', [1], LOG, api_key='key')
        self.assertIsNone(result)

    def test_empty_api_response_produces_empty_pages_dict(self):
        resp = MagicMock()
        resp.text = ''
        resp.usage_metadata = MagicMock(prompt_token_count=0, candidates_token_count=0)
        client = MagicMock()
        client.models.generate_content.return_value = resp
        with patch.object(gemini_ocr, '_get_gemini_client', return_value=client), \
             patch.object(gemini_ocr, '_ensure_safe_path', return_value=('f.pdf', None)), \
             patch.object(gemini_ocr, '_cleanup_safe_path'), \
             patch.object(gemini_ocr, '_render_pages', return_value=[(1, b'p')]), \
             patch.dict('sys.modules', _genai_sys_modules()):
            result = gemini_ocr.remediate_pages_gemini('f.pdf', [1], LOG, api_key='key')
        self.assertEqual(result['pages'], {})


if __name__ == '__main__':
    unittest.main()
