---
date: 2026-05-15
ticket: EB-252
module: web_service/frontend
tags: [analytics, plausible, next-plausible, next-16, app-router, frontend, vercel, proxy]
problem_type: third-party-integration
related:
  - EB-242 (parent marketing strategy; this was Phase 5)
  - EB-253 (deferred Stripe attribution follow-up)
---

# next-plausible × Next 16 App Router: two non-obvious failures + the fix

## Problem

`next-plausible@3.12.4` is the documented Plausible integration for Next.js. Its `withPlausibleProxy()` next.config.js wrapper claims to create same-origin rewrites for `/js/script.js` and `/api/event` (ad-blocker bypass). Its `<PlausibleProvider>` React component claims to inject the tracking script via `next/script`.

On **Next.js 16.2.6 with the App Router**, neither claim fully holds. The integration ships without errors, the Vercel build succeeds, the SSR HTML looks plausible (you see a `<link rel="preload">` for the tracker script), but **no pageviews are recorded**.

If you don't post-deploy-verify with curl, you ship apparently-working analytics that captures zero data.

## Symptoms

After running `npm install next-plausible`, configuring `withPlausibleProxy()` in `next.config.js`, and adding `<PlausibleProvider domain="leafbind.io" trackOutboundLinks />` (self-closing) inside `<head>` of `app/layout.tsx`:

1. **`POST https://yourdomain/api/event` returns 404** in production. Even though `GET https://yourdomain/js/script.outbound-links.js` returns 200 with the Plausible tracker JS body, the event-submission endpoint is unreachable. The browser script tries to POST events and silently fails.

2. **No `<script>` tag in the SSR HTML.** Only the `<link rel="preload" href="/js/script.outbound-links.js" as="script">` tag appears. The script preloads but never executes because nothing references it in a `<script src=...>`. Even if `/api/event` worked, no client-side code would call it.

3. **No errors in Vercel build logs, no errors at runtime.** Both failures are silent — they just don't fire pageviews.

## Root cause

### Failure 1 — `/api/event` 404

Next.js 16 App Router resolves file-based routing in `app/api/**/route.ts` **before** the `rewrites()` in `next.config.js`. Since there's no `app/api/event/route.ts` file in a default integration, Next returns a 404 for the path before the `withPlausibleProxy()` rewrite has a chance to fire.

`/js/script.outbound-links.js` survives because Next has no built-in `/js/*` namespace to short-circuit — the rewrite handles it normally. The asymmetry is the diagnostic: if one rewrite from the same `withPlausibleProxy()` call works and the other doesn't, the namespace is the variable.

(This was a regression in Next 16. The same `withPlausibleProxy()` setup reportedly worked on Next 14 and 15. The change in routing precedence isn't loudly documented in Next's release notes — the symptom shows up only when something else, like Plausible's proxy, depended on the old precedence.)

### Failure 2 — Missing `<script>` tag

`<PlausibleProvider />` with self-closing syntax inside `<head>` doesn't invoke next-plausible's internal `<Script>` component. The component renders only the `<link rel="preload">` hint when it has no children context, OR when placed in a context where `next/script` can't inject into the document body.

The documented pattern is to **wrap children** inside `<body>`:

```tsx
<body>
  <PlausibleProvider domain="yourdomain.com" trackOutboundLinks>
    {children}
  </PlausibleProvider>
</body>
```

When wrapping children, next-plausible renders both the preload AND the actual `<script>` execution tag via `next/script`, which Next.js then injects at the appropriate time (head after hydration, by default).

## Fix

Two changes:

### 1. `app/layout.tsx` — wrap children, don't self-close in head

```tsx
// BEFORE (broken)
export default function RootLayout({ children }) {
  return (
    <html>
      <head>
        <PlausibleProvider domain="leafbind.io" trackOutboundLinks />
      </head>
      <body>{children}</body>
    </html>
  );
}

// AFTER (works)
export default function RootLayout({ children }) {
  return (
    <html>
      <body>
        <PlausibleProvider domain="leafbind.io" trackOutboundLinks>
          {children}
        </PlausibleProvider>
      </body>
    </html>
  );
}
```

### 2. `app/api/event/route.ts` — explicit proxy handler

Manual route handler that bypasses the Next 16 rewrite precedence issue entirely:

```ts
import { type NextRequest } from "next/server";

const PLAUSIBLE_EVENT_ENDPOINT = "https://plausible.io/api/event";

export async function POST(request: NextRequest) {
  const body = await request.text();
  const userAgent = request.headers.get("user-agent") ?? "";
  const xForwardedFor =
    request.headers.get("x-forwarded-for") ??
    request.headers.get("x-real-ip") ??
    "";

  const upstream = await fetch(PLAUSIBLE_EVENT_ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": request.headers.get("content-type") ?? "text/plain",
      "User-Agent": userAgent,
      "X-Forwarded-For": xForwardedFor,
    },
    body,
  });

  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: {
      "Content-Type":
        upstream.headers.get("content-type") ?? "text/plain; charset=utf-8",
    },
  });
}
```

Critical: forward `X-Forwarded-For` so Plausible sees real client IPs instead of the Vercel server IP. Without that header, every pageview looks like it came from the same datacenter, and Plausible's IP-based geo and uniqueness logic breaks.

You can leave `withPlausibleProxy()` in `next.config.js` — it still handles `/js/script.outbound-links.js` correctly, and the file-based `app/api/event/route.ts` overrides the broken rewrite for the event path. Both rewrites in the same call, only the script one survives Next 16's routing precedence.

## Verification

After deploying both fixes, run these three checks against production:

```bash
# 1. Script endpoint returns Plausible tracker JS
curl -sI https://yourdomain.com/js/script.outbound-links.js
# Expect: HTTP/1.1 200 OK, Content-Type: application/javascript

# 2. Event endpoint accepts POSTs
curl -X POST -H "Content-Type: text/plain" \
  -d '{"n":"pageview","u":"https://yourdomain.com/","d":"yourdomain.com"}' \
  https://yourdomain.com/api/event
# Expect: HTTP 202 (Plausible's success code)

# 3. SSR HTML includes preload (script tag is added at hydration by next/script)
curl -s https://yourdomain.com/ | grep -oE '<link[^>]+script\.outbound-links[^>]+>'
# Expect: the <link rel="preload" ...> tag
```

All three should pass. If `/api/event` returns 404, your fix isn't deployed or the file path is wrong. If the script endpoint returns 404, the `withPlausibleProxy()` wrapper isn't applied.

## Lessons

1. **`next-plausible` integration tests pass even when pageviews aren't firing.** The library doesn't validate end-to-end at install time. Post-deploy curl verification of both endpoints is the only honest test.

2. **Next.js 16's App Router changed routing precedence vs Next 14/15.** Library wrappers that relied on rewrites taking precedence over file-based routing for `/api/*` paths can silently break on upgrade. Pattern to watch for: any third-party integration that creates rewrites in `/api/*` namespace and was working before a Next major-version upgrade.

3. **The diagnostic asymmetry — script rewrite works, event rewrite doesn't — is the smoking gun.** Both rewrites come from the same `withPlausibleProxy()` call. If you ever see one rewrite from a pair working and the other failing, the path namespace is the variable; the rewrite mechanism itself is intact.

4. **Self-closing React components can silently lose injection behavior.** `<PlausibleProvider />` and `<PlausibleProvider>{children}</PlausibleProvider>` are different components in next-plausible's behavior, even though TypeScript marks `children` as optional. The wrap-children pattern is the only documented one and the only one that injects the script tag.

5. **Forward `X-Forwarded-For` when proxying analytics requests through Next route handlers.** Without it, every pageview attributes to your serverless function's egress IP (Vercel's datacenter), not the user's real IP. Plausible's uniqueness, geo, and deduplication all break silently.
