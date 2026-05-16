---
module: web_service/frontend
tags: [screenshots, pillar-page, kfx, calibre, toc, epub]
problem_type: content-production
date: 2026-05-15
ticket: EB-259
---

# Pillar Page Screenshot Workflow — KFX Before/After Demos

## Problem

Producing clean before/after screenshots for a KFX conversion guide requires
demonstrating garbled Calibre output vs. correct leafbind output across two
failure modes: column interleaving and stripped footnotes. Physical Kindle
photos and desktop screenshots (Calibre viewer / Kindle Previewer) are both
valid sources.

## What Worked

**Mix physical and desktop screenshots freely.** Phone photos of the Kindle
Scribe are best for showing the reading experience (columns, footnote popups).
Desktop screenshots from Calibre Book Viewer or Kindle Previewer are better for
TOC panels and endnote dumps — they're crisper and easier to capture repeatably.

**Book selection matters more than shot quality.** Choosing the right demo book
for each failure mode is the most important decision:
- Column interleaving → *Fate of Empires* (Glubb) — clearly garbled in Calibre
- Footnote stripping → *Mexico Illicit* (Jones) — 593 linked footnotes in
  leafbind, flat dump in Calibre; Oil Kings uses page-keyed endnotes with no
  inline superscripts, so it shows zero tappable footnotes in both versions

**Calibre Book Viewer needs an explicit `<nav epub:type="toc">` to generate a
TOC.** Auto-detection with `--level1-toc "//h:h1"` or `//h1` XPath returns 0
entries for single-file HTML input. Adding a hidden nav element before the body
content causes Calibre to find the 3 entries immediately:

```html
<nav epub:type="toc" id="toc" hidden="">
  <ol>
    <li><a href="#heading_0_introduction">Introduction</a></li>
    <li><a href="#heading_3_the-fate-of-empires">The Fate of Empires</a></li>
    <li><a href="#heading_4_search-for-survival">Search for Survival</a></li>
  </ol>
</nav>
```

## Title Page Heading Trap

PDFs with a visible book title (e.g., "THE FATE OF EMPIRES / And / SEARCH FOR
SURVIVAL" on the title page) cause the extraction engine to emit two `<h1>`
tags before the Introduction section, producing a TOC with the wrong order.

**Fix:** Demote title-page headings to styled paragraphs and insert proper `<h1>`
anchors at the true section boundaries in the body:

```python
# heading detection should skip title-page context
# (large bold text on page 1–2 within 5 lines of copyright notice)
```

Manual HTML fix pattern:
1. `<h1>TITLE</h1>` → `<p style="text-align:center;font-weight:bold;">TITLE</p>`
2. Insert `<h1 id="heading_0_introduction">Introduction</h1>` before the preface paragraph
3. Rename the misplaced h1 to the correct essay title
4. Insert `<h1>Search for Survival</h1>` at the second-essay boundary

## File Naming Convention

All pillar guide images go in:
`web_service/frontend/public/guides/<slug>/`

Use `.jpg` for all sources (Kindle photos + desktop screenshots) — Next.js
Image handles optimization at serve time regardless of source dimensions.
Converting PNG screenshots to JPG via `System.Drawing` at quality 90 works
cleanly from PowerShell.

## KFX Viewer Error

Opening a KFX in Calibre Book Viewer gives:
> "Destination does not exist; The file OEBPS/c0.xhtml does not exist"

This happens when front matter (cover + title page text) exists before the
first `<h1>` — Calibre generates a TOC entry for the pre-heading fragment
(`c0.xhtml`) but omits it from the manifest. **Workaround:** open the EPUB
variant instead of the KFX for TOC screenshots.
