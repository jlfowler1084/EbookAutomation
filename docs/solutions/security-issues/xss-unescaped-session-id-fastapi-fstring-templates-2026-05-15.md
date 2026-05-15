---
title: XSS via Unescaped session_id in FastAPI F-String Templates
date: 2026-05-15
category: docs/solutions/security-issues/
module: web_service/routes/payment.py
problem_type: security_issue
component: payments
severity: high
symptoms:
  - "session_id query parameter reflected directly into HTML via Python f-string without html.escape()"
  - "Four _render_* helpers in payment.py all affected simultaneously"
  - "Stripe prefix check (cs_) passes crafted payloads like cs_<script>alert(1)</script>"
root_cause: missing_validation
resolution_type: code_fix
related_components:
  - authentication
tags:
  - xss
  - fastapi
  - html-escape
  - session-id
  - payment-flow
  - input-validation
  - security-issue
---

# XSS via Unescaped session_id in FastAPI F-String Templates

## Problem

4 `_render_*` helpers in `web_service/routes/payment.py` reflected the `session_id` query parameter directly into HTML f-strings without escaping. The parameter arrives from the URL after Stripe redirects the user back to the site. Because it came from Stripe and was prefixed with `cs_`, it was implicitly treated as trusted structured data. It is not.

The vulnerability was discovered by the security-lens reviewer during the EB-248 brainstorm (confidence 0.82), before any implementation began — not during code review after the fact. (session history [claude])

```python
# BEFORE (vulnerable) — in _render_success_page, _render_expired_page,
#                        _render_pending_page, _render_retry_page
f'<p class="lb-session-id">Session: {session_id}</p>'
```

## Symptoms

- session_id from URL query param interpolated as raw HTML in 4 render helpers
- A malicious URL like `/payment/success?session_id=cs_<script>alert(1)</script>` executes arbitrary JavaScript in the victim's browser
- The Stripe prefix check (`session_id.startswith("cs_")`) passes this payload — the string begins with `cs_`
- All 4 payment-flow states that display session ID were affected simultaneously

## What Didn't Work

**Prefix-only validation** is not a substitute for output escaping.

Checking `session_id.startswith("cs_")` serves a legitimate purpose: it rejects strings that cannot be valid Stripe Checkout Session IDs before making an API call. But it does not constrain the character set of the remainder of the string. A payload of `cs_<script>alert(1)</script>` passes the prefix check and is forwarded to Stripe (which returns a 404), but the HTML is rendered before the Stripe response matters.

Validation and escaping solve orthogonal problems. Both are required:
- Prefix validation → prevents wasted Stripe API calls on invalid IDs
- `html.escape()` → prevents XSS in HTML reflection

## Solution

```python
from html import escape

# AFTER (safe) — applied to all 4 f-string occurrences atomically via replace_all
f'<p class="lb-session-id">Session: {escape(session_id, quote=True)}</p>'
```

The `quote=True` argument was specifically identified during the brainstorm as essential: it additionally escapes `"` and `'`, preventing attribute context injection where `session_id` is placed inside an HTML attribute value. (session history [claude])

Three regression tests were written test-first, confirming the vulnerability existed before the fix landed:

```python
def test_xss_in_session_id_is_escaped_on_success_page(client):
    resp = client.get("/payment/success?session_id=cs_<script>alert(1)</script>")
    assert "<script>" not in resp.text
    assert "&lt;script&gt;" in resp.text  # confirm escaping, not suppression

def test_xss_in_session_id_is_escaped_on_expired_page(client):
    resp = client.get("/payment/success?session_id=cs_<script>alert(1)</script>")
    assert "<script>" not in resp.text

def test_xss_payload_not_reflected_on_pending_page(client):
    resp = client.get("/payment/success?session_id=cs_<img+onerror=alert(1)>")
    assert "onerror" not in resp.text
```

## Why This Works

`html.escape()` converts HTML-significant characters before the browser's HTML parser sees them:

| Character | Escaped form |
|-----------|-------------|
| `<` | `&lt;` |
| `>` | `&gt;` |
| `&` | `&amp;` |
| `"` | `&quot;` (with `quote=True`) |
| `'` | `&#x27;` (with `quote=True`) |

The fix is additive: no routing logic, validation logic, or Stripe API interaction changes. Prefix validation is preserved and complemented by output escaping.

## Prevention

**Rule 1: Always `escape()` user-supplied values before HTML interpolation in FastAPI f-strings.**

```python
# Always
f"<p>{escape(user_value, quote=True)}</p>"

# Never
f"<p>{user_value}</p>"
```

This applies to query params, path params, form fields, and third-party redirect values (Stripe, OAuth callbacks, email links).

**Rule 2: Structured-looking values are still untrusted.** Stripe session IDs, UUIDs, and token strings feel structured. They are not trusted until validated against their full format — and even then, they must be escaped before HTML reflection. Validation and escaping are orthogonal defenses.

**Rule 3: Fix all occurrences atomically.** When the same pattern appears in multiple helpers, fix all in one operation using `replace_all: true` in Edit calls. Partial fixes create false confidence and leave remaining instances for a later attacker to discover.

**Rule 4: Write XSS regression tests at the template rendering level.** Integration tests using real session IDs will never generate angle-bracket payloads. Template-level tests must construct explicit XSS payloads and assert on the rendered HTML output — not just the HTTP status.

**Rule 5: Add a CI grep for future additions.**

```bash
# Fails if any new f-string reflects session_id without escape()
grep -n 'f".*{session_id' web_service/routes/*.py | grep -v 'escape(' && exit 1 || true
```

This catches a developer adding a new `_render_*` helper who forgets the escaping pattern.

## Related Issues

- `web_service/routes/payment.py` — all 4 affected `_render_*` helpers (success, expired, pending, retry)
- Python stdlib `html.escape()` docs — `quote=True` parameter
- OWASP XSS Prevention Cheat Sheet — Rule 1 (HTML body) and Rule 2 (HTML attribute context)
- `docs/solutions/best-practices/fastapi-nextjs-css-token-sharing-python-shell-2026-05-15.md` — knowledge doc from the same EB-248 brand pass
