"""Tests for web_service/templates/shell.py — EB-248 Unit 2.

Verifies header_html() and footer_html() produce well-formed HTML
with the expected brand anchors and an inline SVG logo.
"""

from __future__ import annotations

from html.parser import HTMLParser

import pytest


class _LinkCollector(HTMLParser):
    """Collect all <a href="..."> targets and all <svg> occurrences."""

    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []
        self.svg_count: int = 0
        self.aria_labels: dict[str, str] = {}  # href → aria-label

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "a":
            href = d.get("href", "")
            self.hrefs.append(href)
            if "aria-label" in d:
                self.aria_labels[href] = d["aria-label"]
        elif tag == "svg":
            self.svg_count += 1


def _parse(html: str) -> _LinkCollector:
    p = _LinkCollector()
    p.feed(html)
    return p


class TestHeaderHtml:
    """header_html() — minimal payment-flow header."""

    def test_returns_string(self):
        from web_service.templates.shell import header_html
        assert isinstance(header_html(), str)

    def test_contains_home_link(self):
        from web_service.templates.shell import header_html
        p = _parse(header_html())
        assert "/" in p.hrefs

    def test_home_link_aria_label(self):
        from web_service.templates.shell import header_html
        p = _parse(header_html())
        assert p.aria_labels.get("/") == "leafbind home"

    def test_contains_svg_logo(self):
        from web_service.templates.shell import header_html
        p = _parse(header_html())
        assert p.svg_count >= 1

    def test_no_marketing_nav_links(self):
        """Payment-flow header must NOT include Convert/Pricing/Quality nav."""
        from web_service.templates.shell import header_html
        html = header_html()
        assert "/convert" not in html
        assert "/quality" not in html

    def test_parseable_html(self):
        from web_service.templates.shell import header_html
        errors = []

        class _ErrorCollector(HTMLParser):
            def handle_starttag(self, tag, attrs): ...
            def handle_error(self, message):
                errors.append(message)

        _ErrorCollector().feed(header_html())
        assert errors == []


class TestFooterHtml:
    """footer_html() — minimal payment-flow footer."""

    def test_returns_string(self):
        from web_service.templates.shell import footer_html
        assert isinstance(footer_html(), str)

    def test_contains_pricing_link(self):
        from web_service.templates.shell import footer_html
        p = _parse(footer_html())
        assert "/pricing" in p.hrefs

    def test_contains_recover_link(self):
        from web_service.templates.shell import footer_html
        p = _parse(footer_html())
        assert "/recover" in p.hrefs

    def test_parseable_html(self):
        from web_service.templates.shell import footer_html
        errors = []

        class _ErrorCollector(HTMLParser):
            def handle_starttag(self, tag, attrs): ...
            def handle_error(self, message):
                errors.append(message)

        _ErrorCollector().feed(footer_html())
        assert errors == []
