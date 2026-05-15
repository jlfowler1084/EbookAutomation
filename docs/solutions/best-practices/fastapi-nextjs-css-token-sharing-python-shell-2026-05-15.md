---
title: Build-time CSS Token Sharing Between FastAPI and Next.js
date: 2026-05-15
category: docs/solutions/best-practices/
module: web_service/payment-flow
problem_type: best_practice
component: payments
severity: medium
related_components:
  - tooling
  - frontend_stimulus
applies_when:
  - "Hybrid FastAPI + Next.js app where Python templates and React components must share the same design token values"
  - "Build-time CSS committed to source control must stay in sync with TypeScript token definitions"
  - "Server-rendered payment pages need visual consistency with the Next.js frontend without runtime token lookup"
  - "Some routes need Cache-Control: private, no-store while static brand assets need aggressive caching"
tags:
  - fastapi
  - design-tokens
  - css-generation
  - drift-guard
  - nextjs
  - python-shell
  - brand-pass
---

# Build-time CSS Token Sharing Between FastAPI and Next.js

## Context

leafbind.io runs a hybrid architecture: a FastAPI backend handles the full payment flow (7 states: success, pending, expired, retry, not-found, invalid, cancel), while Next.js serves the public-facing pages. Design tokens — colors, type scale, spacing — live in `web_service/frontend/design-tokens.ts`. FastAPI-rendered payment HTML needed the same brand tokens without duplicating them in Python or generating CSS at runtime.

The core tension: TypeScript cannot be imported into Python, and runtime CSS generation adds latency and creates a second token system that can drift silently. Discovered during the EB-248 brand pass (2026-05-15), after confirming INFRA-392 (Figma MCP design-first workflow) should stay deferred until a concrete drift problem justifies it.

## Guidance

**1. Generate committed CSS from TypeScript tokens at build time.**

A Node.js build script (`gen-fastapi-css.mjs`) reads `design-tokens.ts`, extracts CSS custom property declarations, and writes `web_service/static/leafbind-tokens.css` as a committed file. This file is the contract between the two systems. It is not generated at runtime — it is checked in and versioned.

**2. Enforce token parity with a 3-way drift guard.**

`check-token-drift.mjs` validates that `design-tokens.ts`, `globals.css`, and `leafbind-tokens.css` agree on every token value. CI fails on any drift. This converts invisible brand inconsistency into a failing build.

**3. Hand-mirror shell components at language boundaries, then guard them with CI.**

`web_service/templates/shell.py` exposes `header_html()` and `footer_html()` — Python functions producing the same HTML structure as React `Header.tsx`/`Footer.tsx`. `check-shell-drift.mjs` compares aria-label text and footer links between `shell.py` and the React source.

**4. Use a `StaticFiles` subclass for surgical Cache-Control.**

Override `get_response()` — not middleware — to set `Cache-Control: public, max-age=3600, immutable` on brand CSS only. Payment HTML must remain `private, no-store`. Middleware-level Cache-Control cannot express per-route distinctions.

```python
class _BrandStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "public, max-age=3600, immutable"
        return response
```

**5. Extract multi-state rendering into named helpers.**

When a route handles N states, extract each into a named `_render_*` helper. Route handlers become routing-only. Template logic lives in helpers named after the state, not a sequence number.

```python
def _render_success_page(session_id: str, ...) -> str: ...
def _render_expired_page(session_id: str) -> str: ...

@router.get("/payment/success")
async def payment_success(session_id: str, ...):
    if is_expired:
        return HTMLResponse(_render_expired_page(session_id))
    return HTMLResponse(_render_success_page(session_id, ...))
```

## Why This Matters

Silent token drift is an invisible bug class. A color update in `design-tokens.ts` not reflected in FastAPI-served payment pages creates brand inconsistency that is invisible to unit tests and only visible to a human viewing the payment confirmation screen. The drift guard converts this from an invisible bug into a CI failure.

The `_BrandStaticFiles` subclass approach matters because payment HTML must never be cached — a `private, no-store` route and a `public, immutable` static file cannot coexist under a middleware-level Cache-Control policy. The subclass is the minimum surgical intervention.

## When to Apply

- A Python backend renders HTML directly (templating, f-strings) and must share design tokens with a TypeScript/JavaScript frontend
- Some routes need `Cache-Control: private, no-store` (payments, auth, personalized pages) while static assets need aggressive caching
- A React component (Header, Footer) must be mirrored into server-rendered HTML at a language boundary

Do not apply the `_BrandStaticFiles` approach if all static files can share the same cache policy — middleware is simpler and sufficient in that case.

## Examples

**gen-fastapi-css.mjs — use a global regex scan, not line-by-line**

```js
import { readFileSync, writeFileSync } from "fs";

const tokens = readFileSync("web_service/frontend/design-tokens.ts", "utf8");

// CORRECT: global scan captures all tokens, including multi-value lines
// e.g. `{ 1: "0.25rem", 2: "0.5rem", 3: "0.75rem" }` emits 3 entries per line
const cssVars = [];
const re = /(--[\w-]+):\s*([^,;\n}]+)/g;
let m;
while ((m = re.exec(tokens)) !== null) {
  cssVars.push(`  ${m[1]}: ${m[2].trim()};`);
}

// WRONG: line-by-line only captures first token per line
// tokens.split("\n").map(line => line.match(/--[\w-]+:\s*[^;]+/)?.[0])
// → misses 5 of 8 space tokens in the TypeScript space scale

writeFileSync(
  "web_service/static/leafbind-tokens.css",
  `:root {\n${cssVars.join("\n")}\n}\n\n${utilities}`
);
```

The multi-value line format `{ 1: "...", 2: "...", 3: "..." }` in TypeScript object literals means a single source line produces multiple CSS custom properties. Line-by-line matching only captures the first. (session history)

**check-shell-drift.mjs — target the `<a>` tag's aria-label, not any aria-label**

```js
// WRONG: too broad — matches the SVG logo's aria-label before the link's
const label = html.match(/aria-label="([^"]+)"/)?.[1];

// CORRECT: context-specific regex targets the nav link anchor
const label = html.match(/href="\/" aria-label="([^"]+)"/)?.[1];
```

The SVG logo in `Header.tsx` has its own `aria-label="leafbind logo"`. A context-free regex matches it first and returns the wrong value, causing the drift check to always fail. (session history)

**_BrandStaticFiles mount — use absolute path**

```python
from pathlib import Path
from starlette.staticfiles import StaticFiles

static_dir = Path(__file__).resolve().parent / "static"

class _BrandStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "public, max-age=3600, immutable"
        return response

# Mount brand CSS first so its handler takes precedence
app.mount("/static/brand", _BrandStaticFiles(directory=str(static_dir)), name="brand_static")
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
```

Use `Path(__file__).resolve().parent` rather than a relative path — uvicorn's CWD may differ from the repo root on the production VM.

## Related

- `web_service/routes/payment.py` — `_render_*` helpers and `_BrandStaticFiles`
- `web_service/templates/shell.py` — `header_html()` / `footer_html()`
- `web_service/static/leafbind-tokens.css` — committed generated CSS
- `web_service/frontend/design-tokens.ts` — canonical token source
- `docs/solutions/eb233-design-system-decisions.md` — covers `check-token-drift.mjs` within Next.js; this doc adds the cross-stack extension via `gen-fastapi-css.mjs`
- `docs/solutions/security-issues/xss-unescaped-session-id-fastapi-fstring-templates-2026-05-15.md` — XSS fix from the same EB-248 brand pass
