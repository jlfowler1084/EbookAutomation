"""Payment-flow HTML shell — minimal header + footer for FastAPI-rendered pages.

Intentionally minimal: logo + footer copy only. Payment-flow users don't need
the marketing nav (Convert / Pricing / Quality) mid-payment.

Hand-mirrored from web_service/frontend/components/Header.tsx and Footer.tsx.
check-shell-drift.mjs (run in prebuild) compares text content + aria-labels
against the React components to catch drift.
"""

from __future__ import annotations

# ── Inline SVG logo — mirrored from web_service/frontend/components/Logo.tsx ──
# Unique SVG IDs (py suffix) avoid any future per-page collision.
_LOGO_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 380 100" role="img"
     aria-label="leafbind.io" fill="none" style="height:32px;width:auto;">
  <title>leafbind.io</title>
  <defs>
    <linearGradient id="lbCurlShade_py" x1="0.15" y1="0" x2="0.85" y2="1">
      <stop offset="0" stop-color="#fbf7ec"/>
      <stop offset="0.55" stop-color="#fbf7ec"/>
      <stop offset="1" stop-color="#e0d8c0"/>
    </linearGradient>
    <clipPath id="lbLeafClip_py">
      <path d="M50 6 C72 14,88 32,88 54 C88 76,72 92,50 94 C28 92,12 76,12 54 C12 32,28 14,50 6 Z"/>
    </clipPath>
  </defs>
  <path d="M50 6 C72 14,88 32,88 54 C88 76,72 92,50 94 C28 92,12 76,12 54 C12 32,28 14,50 6 Z" fill="#2f5d3a"/>
  <g clip-path="url(#lbLeafClip_py)">
    <path d="M50 12 Q49 50,47 92" stroke="#1f3f27" stroke-width="1.6" stroke-linecap="round" opacity="0.55"/>
    <g stroke="#1f3f27" stroke-width="0.9" stroke-linecap="round" opacity="0.32">
      <path d="M49 28 Q40 30,26 34"/>
      <path d="M48 44 Q38 48,22 54"/>
      <path d="M47 60 Q38 66,24 74"/>
      <path d="M46 76 Q38 82,28 86"/>
    </g>
    <path d="M50 12 L70 14 L84 28 L84 90 L50 94 Z" fill="#fbf7ec"/>
    <g stroke="#2f5d3a" stroke-width="1.4" stroke-linecap="round" opacity="0.82">
      <line x1="55" y1="38" x2="79" y2="38"/>
      <line x1="55" y1="46" x2="81" y2="46"/>
      <line x1="55" y1="54" x2="77" y2="54"/>
      <line x1="55" y1="62" x2="80" y2="62"/>
      <line x1="55" y1="70" x2="74" y2="70"/>
      <line x1="55" y1="78" x2="78" y2="78"/>
    </g>
    <path d="M70 14 L84 28 L70 28 Z" fill="url(#lbCurlShade_py)"/>
    <path d="M70 14 L84 28" stroke="#1f3f27" stroke-width="0.7" stroke-linecap="round" opacity="0.4"/>
    <path d="M70 14 L70 28 L84 28" stroke="#1f3f27" stroke-width="0.4" stroke-linejoin="round" opacity="0.18"/>
  </g>
  <text x="116" y="68" font-family="Newsreader,Georgia,serif" font-size="53"
        font-weight="500" fill="currentColor" letter-spacing="-0.8">leafbind<tspan fill="#c9a96e" font-style="italic">.io</tspan></text>
</svg>"""


def header_html() -> str:
    """Minimal payment-flow header: leafbind logo only, no marketing nav."""
    return (
        '<header class="lb-header">\n'
        '  <a href="/" aria-label="leafbind home">'
        + _LOGO_SVG
        + "</a>\n"
        "</header>"
    )


def footer_html() -> str:
    """Minimal payment-flow footer: tagline + pricing + recover links."""
    return (
        '<footer class="lb-footer">\n'
        "  <p>PDF to Kindle, the calm way.</p>\n"
        "  <p>\n"
        '    <a href="/pricing" class="lb-link">Pricing</a>\n'
        "    &nbsp;&middot;&nbsp;\n"
        '    <a href="/recover" class="lb-link">Recover tokens</a>\n'
        "  </p>\n"
        "  <p>&copy; 2025&ndash;2026 leafbind.</p>\n"
        "</footer>"
    )
