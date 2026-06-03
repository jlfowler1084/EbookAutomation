#!/usr/bin/env python3
"""Tests for visual_qa.find_poppler_path root-vs-bin resolution (EB-361).

The EB-361 determinism checker passed settings.json's poppler value
("tools\\poppler", a *root*) straight through to find_poppler_path, which
returned it unchanged. pdf2image needs the nested ``Library/bin`` that actually
holds ``pdftoppm.exe``, so rendering failed and the checker exited 2 before it
ever reached the provider — making the documented default command unreliable.

These tests pin the resolution contract:
  * a poppler *root* (binary nested under Library/bin) resolves to the bin dir,
  * a directory that already holds the binary is returned as-is,
  * an unrelated directory is never returned blindly.

Hermetic: fake poppler trees in a temp dir, no real Poppler install required.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import visual_qa as vqa  # noqa: E402


class TestFindPopplerPath(unittest.TestCase):
    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self._tmp, ignore_errors=True)

    def _make_bin(self, root: Path) -> Path:
        """Create root/Library/bin/pdftoppm.exe and return the bin dir."""
        bin_dir = root / "Library" / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "pdftoppm.exe").write_text("")
        return bin_dir

    def test_root_with_nested_bin_resolves_to_bin(self):
        # The exact EB-361 failure: passing the poppler root must yield the bin.
        root = self._tmp / "poppler"
        bin_dir = self._make_bin(root)
        self.assertEqual(vqa.find_poppler_path(str(root)), str(bin_dir))

    def test_direct_bin_dir_returned_as_is(self):
        # A path that already contains pdftoppm.exe is used directly (no regression).
        bin_dir = self._make_bin(self._tmp / "poppler")
        self.assertEqual(vqa.find_poppler_path(str(bin_dir)), str(bin_dir))

    def test_unrelated_dir_not_returned_blindly(self):
        # A directory with neither the binary nor a nested bin must not be returned.
        empty = self._tmp / "nothing_here"
        empty.mkdir()
        self.assertNotEqual(vqa.find_poppler_path(str(empty)), str(empty))


if __name__ == "__main__":
    unittest.main(verbosity=2)
