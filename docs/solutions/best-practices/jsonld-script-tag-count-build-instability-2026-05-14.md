---
title: JSON-LD script-tag count is unstable across Next.js builds — count @type, not <script>
date: 2026-05-14
category: best-practices
module: web_service/frontend
problem_type: best_practice
component: testing_framework
severity: medium
applies_when:
  - Writing audit pre-flight checks that verify structured data is present on a Next.js page
  - The page emits multiple JSON-LD schemas (SoftwareApplication + FAQPage + HowTo, etc.)
  - You want a stable assertion that survives Next.js/Turbopack/React-DOM upgrades
tags: [json-ld, structured-data, audit, regression-test, nextjs, seo, leafbind]
---

# JSON-LD script-tag count is unstable across Next.js builds — count @type, not <script>

## Context

The EB-230 Unit 9 audit prompt included a pre-flight check expecting **exactly 3** `<script type="application/ld+json">` tags on `/convert/pdf-to-kfx`. The first audit run (against the PR #67 build) found 6 regex matches (3 real script tags + 3 in the RSC serialization payload) and reported PASS by counting real tags. The post-Unit-9 build of the same page emits **1 combined** `<script type="application/ld+json">` tag containing all 3 schemas (SoftwareApplication + FAQPage + HowTo) inline — same payload, different wrapping. A naive `grep -c 'application/ld+json'` check would have flagged a regression where none existed.

## Guidance

Audit assertions on structured data should count **schema `@type` occurrences**, not `<script>` wrapper tags. The schema payload is what Google and Schema.org consume; the wrapper count is an implementation detail of whichever React-DOM / Next.js / hydration strategy is currently in use.

**Preferred check:**

```bash
curl -sS https://leafbind.io/convert/pdf-to-kfx \
  | grep -oE '"@type":"[^"]*"' \
  | sort -u
# Expected output (3 distinct top-level types):
# "@type":"FAQPage"
# "@type":"HowTo"
# "@type":"SoftwareApplication"
# Nested types (Question, Answer, HowToStep, Offer) are also present and OK to check.
```

**Avoid:**

```bash
# Unstable across builds — may match 1, 3, or 6 depending on
# how React-DOM serializes RSC payload alongside real script tags.
curl -sS https://leafbind.io/convert/pdf-to-kfx \
  | grep -c 'application/ld+json'
```

## Why This Matters

A pre-flight check that fails for a reason unrelated to the actual SEO health of the page wastes the audit run — it either stops a real audit cold or trains the auditor to ignore the check, both of which compound badly. Counting `@type` occurrences mirrors what the Schema.org validator and Google Rich Results Test actually inspect, so passing this check also predicts passing the downstream validators.

Next.js 16 + Turbopack happens to combine the three schemas into one `<script>` element. Earlier builds emitted three separate elements. Future builds may emit them differently again — possibly streamed in a separate document fragment, possibly emitted client-side via a `Head` component. The schema content stays stable; the wrapper count does not.

## When to Apply

- Writing a regression check that asserts structured data is present
- Updating an existing audit prompt that uses `grep -c 'application/ld+json'`
- Reviewing why a JSON-LD pre-flight check failed despite the live page rendering correctly in the Schema.org validator
- Building any test gate that fires on Next.js HTML output

## Examples

**Pre-flight check stanza for an audit prompt (markdown):**

```markdown
Structured data must include 3 top-level @type entries
(SoftwareApplication + FAQPage + HowTo). Use:

    curl -sS https://leafbind.io/convert/pdf-to-kfx \
      | grep -oE '"@type":"[^"]*"' | sort -u | wc -l

Expected: ≥ 3 distinct values. Verify the three listed above
appear in the sorted output.
```

**One-liner with named-type assertion in PowerShell:**

```powershell
$types = (Invoke-RestMethod "https://leafbind.io/convert/pdf-to-kfx") `
  -split "`n" `
  | Select-String -Pattern '"@type":"([^"]*)"' -AllMatches `
  | ForEach-Object { $_.Matches.Groups[1].Value } `
  | Sort-Object -Unique

$expected = @("SoftwareApplication", "FAQPage", "HowTo")
$missing = $expected | Where-Object { $_ -notin $types }
if ($missing) { throw "Missing schema types: $($missing -join ', ')" }
```

## Related

- EB-230 Unit 9 PR: https://github.com/jlfowler1084/EbookAutomation/pull/68
- EB-230 closeout comment, "Operational findings worth carrying forward" §3
- `prompts/EB-230-unit9-lighthouse-cwv.md` — the original prompt that used `grep -c 'application/ld+json'` and would benefit from this update on a re-run
