---
ticket: EB-241
phase: Phase 1 — Discovery (keyword research only)
date: 2026-05-15
author: Joe Fowler (research dispatched to compound-engineering:research:best-practices-researcher)
status: partial — keyword research complete; SERP analysis and competitor audit deferred to follow-up sub-tickets
related:
  - EB-230 (SEO landing pages — predecessor)
  - EB-233 (design system — visual brand)
  - EB-238 (LCP regression — affects ranking; tackle before Phase 2 on-page audit)
  - EB-242 (marketing positioning — shares this audience research)
---

# leafbind.io — SEO Phase 1 Keyword Research

## Scope and limitations

This document covers **only the keyword research portion of EB-241 Phase 1**. The two remaining Phase 1 deliverables are deferred:

- **SERP analysis** (screenshot top 10 per priority keyword, featured-snippet eligibility, AI Overview presence) — defer to a follow-up sub-ticket once primary keywords are confirmed.
- **Competitor audit** (Smallpdf, iLovePDF, PDFCandy, Calibre docs, Amazon help pages content depth) — defer to a follow-up sub-ticket.

### Data-quality constraints

- **No paid SEO tools.** No Ahrefs, no SEMRush, no Ubersuggest paid tier, no Google Keyword Planner (no Ads account).
- **Google Search Console not yet verified for `leafbind.io`** — domain ownership not established, so no first-party query data.
- **Volume signals are qualitative.** No keyword volume numbers below. "Demand" is inferred from forum thread frequency and SERP density, not measured.
- **Reddit direct-fetch blocked.** Reddit's bot blocking prevented direct surveying of `r/kindlescribe`, `r/kindle`, `r/calibre`, `r/GradSchool`. **MobileRead.com became the proxy authority** — it is the dominant Kindle Scribe technical forum, frequently cross-linked from those subreddits and durably indexed by Google. Reddit phrasing surfaced through Google-indexed Reddit titles. A manual Reddit pass (browser or Playwright) is a worthwhile follow-up if it changes any primary-keyword decisions.

## Audience hierarchy (priority order)

From EB-241 ticket and validated by forum surveying:

1. **Kindle Scribe owners reading academic PDFs** — primary. Grad students, postdocs, researchers. Concentrated on MobileRead, indirectly on r/kindlescribe / r/kindle / r/academia.
2. **Casual Kindle owners converting non-Amazon ebooks** — secondary. EPUB → KFX use case.
3. **Writers/publishers handing off manuscripts** — tertiary. DOCX → KFX with metadata.

## 1. Seed phrase validation

| Seed | SERP populated? | Apparent intent | Difficulty signal | Notes |
|---|---|---|---|---|
| kindle scribe kfx conversion | Yes, full SERP | Commercial-Investigation | **Low** — top 3: dedoimedo.com, epubor.com, MobileRead wiki. No retailer/aggregator dominance. | Strong opportunity; SERP is forum/tutorial heavy and recent (2023+). |
| pdf to kfx without amazon | Yes, full SERP | Transactional | **Medium** — top: PDFMate, Any-eBook-Converter, convert.guru, jedok.com, UPDF, Smallpdf | Real intent but crowded by generic converter farms. Differentiation = "without losing footnotes/columns". |
| academic papers on kindle scribe | Yes, full SERP | Informational | **Low** — top: Quora, personal blogs (galpotha.wordpress, meyerperin.org), Medium posts. Techlicious is the only Tier-1 publisher. | Pillar-page gold. SERP is opinion/blog, no SaaS competitor. |
| kfx footnote linking | Yes, sparse | Informational | **Low** — top: blogspot personal blog, MobileRead, KDP community, epubor | Very niche but exactly leafbind's differentiator. Few results = low competition AND low volume — feature page support, not pillar. |
| multi-column pdf to kindle | Yes, full SERP | Commercial-Investigation | **Low-Medium** — top: K2pdfopt (willus.com — Tier-2 personal), eshapard.github.io, MobileRead, kboards | Pillar/landing-page candidate. K2pdfopt's "must install + CLI" friction is the moat. |
| convert pdf to kfx for kindle scribe | Yes, full SERP | Transactional | **Low** — top: MobileRead forum threads (2x), UPDF, Any-eBook-Converter, blog.the-ebook-reader, goodereader. No major retailer. | Highest-intent transactional + Scribe-qualified + soft SERP. Primary landing-page target. |
| kindle scribe academic reading | Yes, full SERP | Informational | **Low** — top: personal blogs (Wordpress, Medium), Quora, Techlicious. No SaaS product. | Pillar-page or blog. Audience-perfect, low difficulty. |
| best kfx converter for academic papers | Sparse, generic | Commercial-Investigation | **Low** — SERP doesn't really exist for this phrase. Top results pivot to generic "best KFX converter" lists. | Term is too long-tail for direct rank but rich for "best X for Y" listicle blog. |
| kfx vs epub for kindle scribe | Yes, partial | Informational | **Low-Medium** — top: epubor (3 listings), Kindlepreneur, Amazon forum, MobileRead | Useful blog topic; epubor's three listings = brand-authority lock-in risk. |
| kindle scribe reflowable text | Yes | Informational | **Low** — top: ereadersforum, podcast pages, Amazon FAQ, MobileRead, pdf2go. No SaaS. | Blog topic — strong "why our service exists" framing. |
| calibre alternative kfx | Misleading SERP | Informational | **High (wrong framing)** — every top result reframes to "Calibre + KFX plugin", not "alternatives to Calibre" | **Skip.** Users don't think this way; SERP refuses to serve it. |
| send to kindle pdf bad formatting | Yes, full SERP | Informational / Commercial-Investigation | **Low-Medium** — top: Quora, epubor, KDP help, Amazon forum, Calibre FAQ, JustAnswer, MobileRead | High-pain query, perfect blog target. "Send to Kindle's PDF conversion is bad — here's why and how we fix it." |

## 2. Discovered long-tail variants (forum surveying)

Reddit was unreachable; MobileRead surfaced verbatim user-pain language. Representative source threads:

1. **MobileRead t=360212** ("PDF to KFX on Kindle Scribe"): *"I'm converting PDFs to print replica KFX files for my Kindle Scribe and I am having an odd issue with covers showing up..."*
2. **MobileRead t=360285** ("PDFs to KFX on Kindle Scribe issue"): *"Only some links in the resulting kfx file work... I also cannot highlight text on some pages, while other pages work fine..."*
3. **MobileRead t=354841** ("column mode w/ kindle scribe"): *"the scribes landscape column mode not working... I believe that multiple columns and sticky notes both require KFX format on a Scribe."*
4. **MobileRead t=358222** ("Troubleshooting Kindle Scribe — How to upload PDF with annotations enabled?")
5. **MobileRead t=361401** ("Kindle Scribe: Page Turns on PDFs")
6. **MobileRead t=110139** ("Converting academic PDF journal articles for Kindle") — indexed for 10+ years, durable phrasing
7. **MobileRead t=357168** ("Fixed page KPS to KFX or blank PDF to KFX conversion?")
8. **Quora indexed**: *"Is the new Kindle Oasis good for reading PDF academic articles with footnotes on each page?"* — the exact user vocabulary
9. **Quora indexed**: *"Do PhD students use Amazon Kindle for reading lots of papers?"*

**Long-tail candidates extracted from this language:**

- `kindle scribe pdf links not working`
- `kindle scribe pdf highlights some pages only`
- `kindle scribe column mode pdf`
- `kindle scribe sideload pdf annotations`
- `kindle scribe pdf cover not showing`
- `kindle scribe send to kindle vs sideload`
- `print replica kfx kindle scribe`
- `convert journal article to kindle scribe`
- `phd reading papers on kindle scribe`
- `kindle scribe ieee paper conversion`
- `kindle scribe arxiv pdf`
- `kindle scribe textbook footnotes`
- `kindle scribe two column landscape`
- `pdf chapter navigation kindle scribe`
- `kindle scribe pdf reflow`
- `convert pdf footnotes to kindle popup`
- `academic pdf to epub kindle`
- `dissertation to kindle scribe`
- `kindle scribe alternative to calibre kfx plugin`
- `kindle scribe print replica vs reflowable`

## 3. Ranked keyword table

Ranking logic: high intent + low difficulty + primary-audience match = top. Difficulty justifications cite top-3 ranking domains from §1.

| # | Keyword | Intent | Difficulty | Audience match | Recommended use |
|---|---|---|---|---|---|
| 1 | convert pdf to kfx for kindle scribe | Transactional | **Low** — top 3: MobileRead, UPDF, Any-eBook-Converter | Primary | `/convert/pdf-to-kfx` landing — primary |
| 2 | kindle scribe kfx conversion | Commercial-Investigation | **Low** — top 3: dedoimedo, epubor, MobileRead wiki | Primary | `/convert/pdf-to-kfx` LSI / blog pillar |
| 3 | academic pdf to kindle | Commercial-Investigation | **Low-Medium** — top 3 are generic SaaS (Aspose, Adobe, pdf2kindle) but none mention footnotes/columns | Primary | `/convert/academic-pdf-to-kindle` landing — primary |
| 4 | multi-column pdf to kindle | Commercial-Investigation | **Low-Medium** — top: K2pdfopt (open-source CLI), eshapard, MobileRead. CLI friction = SaaS opportunity. | Primary | `/convert/multi-column-pdf-kindle` landing — primary |
| 5 | kindle scribe academic reading | Informational | **Low** — top: galpotha.wordpress, meyerperin.org, Quora | Primary | Pillar page or blog post |
| 6 | academic papers on kindle scribe | Informational | **Low** — top: Quora, personal blogs, Medium | Primary | Pillar page (same as #5 — pick one canonical) |
| 7 | pdf footnotes kindle | Commercial-Investigation | **Low** — top: AtoZ ebook conversion, Jutoh KB, KDP forum, Adobe community | Primary | `/convert/pdf-footnotes-kindle` landing — primary |
| 8 | convert pdf footnotes to kindle popup | Transactional | **Low** — SERP near-empty for exact phrase | Primary | `/convert/pdf-footnotes-kindle` LSI |
| 9 | send to kindle pdf bad formatting | Informational | **Low-Medium** — top: Quora, epubor, KDP help, Calibre FAQ | Primary | Blog post (highest emotional-trigger keyword for the target audience) |
| 10 | pdf to kfx without amazon | Transactional | **Medium** — crowded by generic converters | Primary/Secondary | Blog post + `/convert/pdf-to-kfx` LSI |
| 11 | k2pdfopt alternative | Commercial-Investigation | **Low** — SERP doesn't yet exist; willus.com has no direct competitors with comparison content | Primary | Blog post (positioning vs the dominant freeware) |
| 12 | kfx footnote linking | Informational | **Low** — top: blogspot, MobileRead, KDP forum | Primary | `/convert/pdf-footnotes-kindle` LSI / blog support |
| 13 | print replica kfx kindle scribe | Commercial-Investigation | **Low** — phrase from MobileRead; sparse SERP | Primary | Blog post on print-replica vs reflowable tradeoff |
| 14 | kindle scribe column mode pdf | Informational | **Low** — top: MobileRead, xda-developers, ereadersforum | Primary | `/convert/multi-column-pdf-kindle` LSI / blog |
| 15 | kindle scribe pdf reflow | Informational | **Low-Medium** — top: blog.the-ebook-reader, kboards, mobileread | Primary | Blog post (educates on why reflow needs conversion) |
| 16 | kfx vs epub for kindle scribe | Informational | **Low-Medium** — epubor dominates with 3 listings | Secondary | Blog post (comparison piece) |
| 17 | convert journal article to kindle scribe | Transactional | **Low** — extremely sparse SERP | Primary | Blog post or `/convert/academic-pdf-to-kindle` LSI |
| 18 | kindle scribe textbook conversion | Commercial-Investigation | **Low** — Techlicious is the only Tier-1 ranker | Primary | Blog post |
| 19 | calibre kfx plugin too complex | Informational | **Low** — sparse SERP; user-pain framing | Primary | Blog post (positioning vs Calibre+plugin friction) |
| 20 | dissertation to kindle scribe | Transactional | **Low** — sparse SERP | Primary | Blog post |
| 21 | best kfx converter for academic papers | Commercial-Investigation | **Low** (no real SERP) | Primary | Blog listicle (low ROI — better as supporting copy on #3) |
| 22 | kfx converter | Transactional | **High** — Epubor, UPDF, PDFMate, convert.guru, jedok, Calibre — paid SEO real estate | Tertiary | **Skip** — too crowded, audience mismatch (DRM-removal intent) |
| 23 | calibre alternative kfx | Informational | **High (wrong framing)** — SERP refuses to serve | — | **Skip** |
| 24 | kindle scribe reflowable text | Informational | **Low** — podcast/blog ranking | Primary/Secondary | Blog support, not a pillar |
| 25 | epub to kfx converter | Transactional | **Medium-High** — generic converter farms | Secondary | **Skip for v1** (secondary audience, crowded) |

## 4. Per-landing-page primary keyword recommendations

Verified against the live slugs in `web_service/frontend/app/(marketing)/convert/`.

### `/convert/pdf-to-kfx`

- **Current title**: "Convert PDF to KFX for Kindle — leafbind"
- **Primary keyword**: `convert pdf to kfx for kindle scribe` (rank #1)
- **LSI variants**:
  - `kindle scribe kfx conversion` (rank #2)
  - `pdf to kfx without amazon` (rank #10) — differentiator framing
  - `print replica kfx kindle scribe` (rank #13) — power-user term
- **Action**: Add "Kindle Scribe" to the H1 and title tag. Current title omits the highest-intent qualifier.

### `/convert/academic-pdf-to-kindle`

- **Current title**: "Convert Academic PDFs to Kindle — leafbind"
- **Primary keyword**: `academic pdf to kindle` (rank #3)
- **LSI variants**:
  - `academic papers on kindle scribe` (rank #6)
  - `convert journal article to kindle scribe` (rank #17)
  - `kindle scribe academic reading` (rank #5) — supports E-E-A-T framing
- **Action**: Title well-anchored. Add H2 sections targeting "IEEE / arXiv / journal article" sub-intents discovered in Reddit phrasing.

### `/convert/multi-column-pdf-kindle`

- **Current title**: "Convert Multi-Column PDFs to Kindle — leafbind"
- **Primary keyword**: `multi-column pdf to kindle` (rank #4)
- **LSI variants**:
  - `kindle scribe column mode pdf` (rank #14)
  - `two column pdf kindle conversion`
  - `k2pdfopt alternative` (rank #11) — explicitly position against the dominant freeware
- **Action**: Strong as-is. Add a comparison section vs. K2pdfopt — the CLI-friction wedge is the conversion driver.

### `/convert/pdf-footnotes-kindle`

- **Current title**: "PDF Footnotes on Kindle — Keep Them Linked | leafbind"
- **Primary keyword**: `pdf footnotes kindle` (rank #7)
- **LSI variants**:
  - `convert pdf footnotes to kindle popup` (rank #8)
  - `kfx footnote linking` (rank #12)
  - `kindle popup footnotes`
- **Action**: Best-optimized of the four. Consider adding "Kindle Scribe" qualifier in H1 to inherit Scribe-audience traffic.

## 5. Cross-cutting strategic findings

- **The Kindle Scribe qualifier matters.** Adding "scribe" to a query shrinks the SERP from "generic KFX converter farms" to "MobileRead forums + personal blogs". Every primary keyword should include or accompany the Scribe qualifier where natural.
- **MobileRead is the gateway authority.** It outranks Reddit for technical Kindle Scribe queries because Reddit's bot-blocking limits Google's crawl. **Earning a single MobileRead mention or link in a knowledgeable thread would meaningfully boost both referral traffic and ranking signal.** This is a Phase 4 (off-page) lever, but worth flagging now.
- **Calibre + KFX-plugin friction is the wedge.** Forum data + SERP shape both confirm that the existing free path (Calibre + KFX Input/Output plugins + Kindle Previewer install) is real-pain technical setup. "We do what the Calibre plugin does, but in your browser, with footnotes that survive" is a defensible angle.
- **Generic "kfx converter" is a trap.** High volume, but the SERP is locked by Epubor/UPDF/PDFMate's content farms and the searcher intent is mostly DRM-removal (KFX → other), not PDF → KFX. Audience mismatch — skip.

## 6. Recommended next steps (for follow-up sub-tickets)

This Phase 1 deliverable is **partial**. Remaining work for EB-241:

1. **Phase 1b — SERP analysis** (new sub-ticket recommended):
   - Screenshot top 10 for keywords #1, #3, #4, #7 (the four landing-page primaries)
   - Featured-snippet eligibility per query
   - AI Overview presence and citation patterns
   - Estimated 1 session
2. **Phase 1c — Competitor audit** (new sub-ticket recommended):
   - Smallpdf, iLovePDF, PDFCandy content depth on KFX queries
   - Calibre docs + KFX-plugin MobileRead threads
   - Amazon Send-to-Kindle help-page coverage
   - Estimated 1 session
3. **Manual Reddit pass** (optional, only if Phase 1b/1c flag anomalies): Playwright or browser-driven survey of r/kindlescribe, r/kindle, r/calibre to confirm MobileRead-as-proxy was representative.
4. **Phase 2 — On-page audit**: Apply the per-landing-page recommendations above. **Blocked on EB-238** (LCP regression must be resolved first so the audit reflects production-truth).
5. **Phase 3 — Pillar content production**: Begin with rank #1 transactional + rank #5/6 pillar (academic Kindle Scribe). See EB-241 ticket Phase 3 brief for the 6 proposed pillar pieces.
6. **Feed EB-242** (marketing positioning): The audience hierarchy and pain phrasing here directly support EB-242 Phase 1 (positioning + messaging pillars). Share this doc.

## Sources

Forum threads cited for verbatim user phrasing and SERP difficulty assessment:

- [PDF to KFX on Kindle Scribe — MobileRead t=360212](https://www.mobileread.com/forums/showthread.php?t=360212)
- [PDFs to KFX on Kindle Scribe issue — MobileRead t=360285](https://www.mobileread.com/forums/showthread.php?t=360285)
- [column mode w/ kindle scribe — MobileRead t=354841](https://www.mobileread.com/forums/showthread.php?t=354841)
- [Troubleshooting Kindle Scribe annotations — MobileRead t=358222](https://www.mobileread.com/forums/showthread.php?t=358222)
- [Converting academic PDF journal articles for Kindle — MobileRead t=110139](https://www.mobileread.com/forums/showthread.php?t=110139)
- [Page Turns on PDFs — MobileRead t=361401](https://www.mobileread.com/forums/showthread.php?t=361401)
- [Fixed page KPS to KFX — MobileRead t=357168](https://www.mobileread.com/forums/showthread.php?t=357168)
- [K2pdfopt for academic papers — functor.tokyo](https://functor.tokyo/blog/2017-07-21-k2pdfopt-for-academic-papers)
- [Willus.com K2pdfopt](https://www.willus.com/k2pdfopt/)
- [Reading Science Papers on Your Kindle — Silversmith / Medium](https://willsilversmith.medium.com/reading-science-papers-on-your-kindle-4d7633f6ec4c)
- [Kindle Scribe review — galpotha.wordpress](https://galpotha.wordpress.com/2023/12/29/kindle-scribe-a-review/)
- [Replacing reMarkable with Kindle Scribe — MeyerPerin](https://meyerperin.org/posts/2024-01-12-kindle-scribe.html)
- [Kindle Scribe and PDF complete guide — todoereaders](https://en.todoereaders.com/Kindle-Scribe-and-PDF-Complete-Reading-Guide--Notes--and-Export.html)
- [Kindle Scribe update — XDA Developers](https://www.xda-developers.com/kindle-scribe-update-layout-pdf/)
- [PDF academic articles footnotes Kindle — Quora](https://www.quora.com/Is-the-new-Kindle-Oasis-good-for-reading-PDF-academic-articles-with-footnotes-on-each-page)
- [Send-to-Kindle PDF errors — Amazon forum](https://www.amazonforum.com/s/question/0D54P00008OqWzOSAV/when-amazon-converts-my-pdf-to-kindle-format-i-completely-lose-the-toc)
- [How to fix EPUB formatting issues — Epubor](https://www.epubor.com/how-to-fix-formatting-issues-on-epubs-sent-to-kindles.html)
- [KFX Wiki — MobileRead](https://wiki.mobileread.com/wiki/KFX)
- [KFX Input plugin — MobileRead t=291290](https://www.mobileread.com/forums/showthread.php?t=291290)
- [Annotating PDFs and EPUBs on Kindle Scribe — eReadersForum](https://www.ereadersforum.com/blog/annotating-pdfs-and-epubs-on-the-kindle-scribe-what-transfers-what-doesnt-and-why-it-matters/)
- [eWritable — Why you can't write on some PDFs on Kindle Scribe](https://ewritable.net/why-you-cant-write-on-some-pdf-files-on-the-kindle-scribe/)
- [Kindle Personal Documents in KFX — blog.the-ebook-reader](https://blog.the-ebook-reader.com/2023/09/26/kindle-personal-documents-now-getting-delivered-in-kfx-format/)
- [Kindle Scribe textbook replacement — Techlicious](https://www.techlicious.com/blog/kindle-scribe-great-textbook-replacement/)
- [Kindle Scribe FAQ — Amazon](https://www.aboutamazon.com/news/devices/kindle-scribe)
