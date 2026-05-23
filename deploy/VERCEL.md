# Vercel Frontend Deployment — leafbind.io

This document covers the production deployment of the Next.js frontend at
`web_service/frontend/` to Vercel. The FastAPI backend continues to run on the
Hetzner VM at `api.leafbind.io`; only the frontend is on Vercel.

Companion artifacts:
- `web_service/frontend/vercel.json` — declares `framework: nextjs` so deploys
  don't silently change shape if Vercel's auto-detection heuristics drift.
- `deploy/nginx.conf` — accepts requests on `api.leafbind.io` (added in EB-232 Phase 1).
- `deploy/README.md` — backend deployment + CORS configuration.

---

## Architecture

```
Browser ───https://leafbind.io──> Vercel (Next.js, static + SSR)
                                     │
                                     │ NEXT_PUBLIC_API_URL
                                     ▼
Browser ───https://api.leafbind.io──> Cloudflare ──> Hetzner VM (nginx → FastAPI :8001)
```

`leafbind.io` and `www.leafbind.io` resolve to Vercel. `api.leafbind.io` resolves
to the Hetzner VM through Cloudflare. The frontend makes browser-side `fetch`
calls to `NEXT_PUBLIC_API_URL`; CORS is enforced by Starlette on the backend.

---

## First-time project setup

### Prerequisites

- Vercel account with the GitHub repo accessible to it.
- Vercel CLI logged in: `npx vercel whoami` returns your username.
- API subdomain reachable: `curl -I https://api.leafbind.io/health` returns 200.

### Project creation (Vercel dashboard)

The dashboard path is preferred for the first-time setup because the **Root
Directory** field — the single most failure-prone setting — is more visible
than via CLI.

1. Vercel Dashboard → **Add New** → **Project** → **Import Git Repository** →
   select `jlfowler1084/EbookAutomation`.
2. Configure Project:
   - **Project Name:** `leafbind` (or whatever the team chooses; the URL slug
     will be `leafbind-<scope>.vercel.app`).
   - **Framework Preset:** Next.js (auto-detected).
   - **Root Directory:** `web_service/frontend` — **CLICK EDIT AND SET THIS.**
     If you leave it blank or as `.`, Vercel will look for `package.json` at
     the repo root, find none, and create silent `[0ms]` ghost builds that
     pass GitHub status checks while the production alias stays stale. See
     "Why this matters" below.
   - **Build & Output Settings:** leave defaults (`npm ci`, `next build`,
     `.next`) — `vercel.json` and auto-detection handle these.
   - **Environment Variables — Production scope:**
     - `NEXT_PUBLIC_API_URL=https://api.leafbind.io`
   - **Environment Variables — Preview scope:**
     - Leave `NEXT_PUBLIC_API_URL` unset. Preview deployments use
       `*-<scope>.vercel.app` origins, which the production backend rejects
       at the CORS layer (Starlette does strict-equality on origins, not
       regex). Preview deploys are useful for UI review only — they cannot
       hit the production API. If you need preview-API integration, point
       preview at a staging FastAPI instance with its own CORS allow-list.
3. **Deploy.** The first build runs immediately.
4. Run the post-deploy verification ritual below **before** declaring the
   project healthy.

### Production domain attachment

After the first successful deploy:

1. Project → **Settings** → **Domains** → **Add**.
2. Add `leafbind.io` (apex). Vercel will provide DNS instructions — you'll
   need to change the `A` record at Cloudflare from the Hetzner IP
   (`5.161.228.1`) to Vercel's anycast IP, **with Cloudflare proxy OFF**
   (orange-cloud → gray). Vercel needs to see real client IPs and serves its
   own TLS, so the Cloudflare proxy must not sit in front for this hostname.
3. Add `www.leafbind.io`. Configure as redirect to `leafbind.io` (or vice
   versa — choose one as canonical).
4. `api.leafbind.io` stays pointed at the Hetzner VM with Cloudflare proxy ON.

### VM-side prerequisite

Before the production cutover (step 3 above), confirm the FastAPI backend
accepts `https://leafbind.io` and `https://www.leafbind.io` as CORS origins.
These are the values documented in `deploy/README.md`, but a live check is
cheap insurance:

```bash
ssh <hetzner-host>
sudo grep WEB_SERVICE_ALLOWED_ORIGINS /etc/web_service.env
# Expected: WEB_SERVICE_ALLOWED_ORIGINS=https://leafbind.io,https://www.leafbind.io
sudo systemctl status ebookweb | grep Active
# Expected: Active: active (running)
curl -I https://api.leafbind.io/health
# Expected: HTTP/2 200
```

If `WEB_SERVICE_ALLOWED_ORIGINS` is absent or wrong, update `/etc/web_service.env`
and `sudo systemctl restart ebookweb` before the Vercel domain cutover.

---

## Post-deploy verification ritual

Lifted from CareerPilot's CAR-209/210/211 ghost-deploy incident (May 2026),
which discovered that the GitHub `Vercel: success` status check is unreliable
on its own — it only confirms the deployment object reached `Ready`, which a
`[0ms]` empty deploy also does. Run all five checks on every production deploy
until at least three consecutive deploys pass cleanly.

If your project lives in a team scope, add `--scope <team-slug>` to each
`vercel` command. `vercel teams ls` lists available scopes.

```powershell
# 1. Find the new deployment.
npx vercel ls leafbind | Select-Object -First 10

# 2. Confirm build duration > 30s. A 3-5s build is a ghost / empty deploy.
#    The "Duration" column in `vercel ls` output reports build time.

# 3. Inspect the build. The Builds section must show real Lambda functions
#    or Next.js routes -- not just ". [0ms]".
npx vercel inspect <deployment-url>

# 4. Confirm production aliases point at the new build.
#    The Aliases section of `vercel inspect` must include leafbind.io.

# 5. Gold standard: HTML fetch against the production URL, grep for a marker
#    string from the new commit. For EB-230 Phase 3 work, the sitemap is a
#    convenient marker -- if the SEO landing pages are live, sitemap.xml will
#    list them.
$marker = (Invoke-WebRequest https://leafbind.io/sitemap.xml).Content
$marker | Select-String -Pattern "pdf-to-kfx|academic-pdf-to-kindle|pdf-footnotes-kindle|multi-column-pdf-kindle"
# Expected: at least 4 matches.
```

A green GitHub `Vercel: success` check **without** these five passing means
nothing. The 43-hour CareerPilot stall happened because every CI check
reported success while the production alias served an empty `[0ms]` build.

---

## Subsequent deploys

GitHub auto-deploy on push to `master` is the default. No manual `vercel
deploy` is needed. Each push to `master` triggers a production build; each
push to any other branch (including worktree branches) triggers a preview
build.

To force a manual production deploy from the working tree:

```powershell
cd web_service\frontend
npx vercel deploy --prod
```

The first time you do this, `vercel link` will prompt for the project — pick
the existing `leafbind` project. This writes `.vercel/project.json` locally
(already gitignored by the Vercel CLI). Run from `web_service/frontend/`, not
the repo root, or the Root Directory will be wrong.

---

## Rollback

Vercel keeps every prior production deployment. To roll back:

1. Vercel Dashboard → Project → **Deployments**.
2. Find the last known-good deployment.
3. Click the deployment → **... menu** → **Promote to Production**.

This is instant (DNS doesn't change — only the production alias pointer
moves). Use this if the verification ritual catches a bad deploy that already
landed.

---

## Why the Root Directory trap matters

The CareerPilot incident (CAR-209, CAR-210, CAR-211) in May 2026: a Next.js
app at `dashboard/` in a monorepo. Both PRs merged with green CI. The
production alias was 43 hours stale before anyone noticed. Root cause: the
Root Directory was left blank instead of `dashboard/`. Vercel scanned the
repo root for `package.json`, found none, and created `[0ms]` empty
deployments that immediately reached `Ready` — which the GitHub status check
reports as `Vercel: success`. The production alias stayed pointed at an
older deployment because Vercel won't promote a zero-output build.

`web_service/frontend/` is the same shape. The vercel.json in that directory
won't save you — vercel.json is read **after** Root Directory resolution,
not before, so a blank Root Directory means Vercel never sees the
vercel.json at all.

The dashboard setting is the only defense. Verify it with `vercel inspect`
on every first deploy of a new project.
