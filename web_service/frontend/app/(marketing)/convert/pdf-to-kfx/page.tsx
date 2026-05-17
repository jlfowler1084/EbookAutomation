import type { Metadata } from "next";
import Link from "next/link";
import JsonLd from "../../../../components/JsonLd";
import {
  buildArticleSchema,
  buildSoftwareApplicationSchema,
  type FAQPageSchema,
  type HowToSchema,
} from "../../../../lib/structured-data";

const CANONICAL = "https://leafbind.io/convert/pdf-to-kfx";

export const metadata: Metadata = {
  title: "Convert PDF to Kindle Format (KFX): Online Converter for Academic & Multi-Column PDFs — leafbind",
  description:
    "Convert PDF to Kindle format (KFX) online — built for academic papers, footnotes, and " +
    "multi-column layouts. leafbind handles what Send-to-Kindle and Calibre struggle with. No account required.",
  alternates: { canonical: "/convert/pdf-to-kfx" },
  openGraph: {
    title: "Convert PDF to Kindle Format (KFX) — leafbind",
    description:
      "Convert PDF to Kindle format (KFX) online — academic papers, footnotes, multi-column layouts handled correctly.",
    type: "article",
    url: CANONICAL,
    images: [{ url: "https://leafbind.io/quality/pipeline-columns.png", width: 800, height: 600 }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Convert PDF to Kindle Format (KFX) — leafbind",
    description: "Convert PDF to Kindle format (KFX) online — academic papers, multi-column, and footnotes handled correctly.",
    images: ["https://leafbind.io/quality/pipeline-columns.png"],
  },
};

const faqItems = [
  {
    q: "Is KFX output available in the free tier?",
    a: "No. KFX conversion is a premium feature because it requires the full pipeline: heading detection, footnote linking, and the Calibre KFX Output plugin with the additional KFX support files installed. The free tier produces EPUB, which works on Kindle but does not get the KFX-specific typography improvements. See the pricing page for details on premium plans.",
  },
  {
    q: "What types of PDF work best with KFX conversion?",
    a: "Text-based PDFs produce the best results — academic papers, technical manuals, non-fiction books, conference proceedings. The pipeline extracts text and coordinates from the PDF's internal representation, so it relies on actual text objects rather than rendered pixels. Scanned PDFs (image-only) fall back to OCR, which works for clean scans but cannot guarantee heading detection accuracy. Heavily image-dependent documents like textbooks with full-page illustrations are supported but images are placed inline rather than as floating figures.",
  },
  {
    q: "Will my footnotes survive the PDF to KFX conversion?",
    a: "Yes. leafbind's pipeline detects footnote markers — numeric superscripts, symbolic markers (*, †), and margin notes — and pairs each marker with its footnote body text. In the KFX output, footnote markers become tappable links that open the footnote as a Kindle popup. You can jump back to your reading position from the popup. This is one of the most significant improvements over Calibre's raw EPUB-to-KFX path, which typically strips footnote backreferences entirely.",
  },
  {
    q: "Which Kindle models support KFX format?",
    a: "All Kindle devices released from 2018 onward support KFX: Kindle Paperwhite (10th generation and later), Kindle (10th generation and later), Kindle Oasis (9th generation and later), and Kindle Scribe. KFX is Amazon's native enhanced typesetting format — it enables custom fonts, improved hyphenation, and enhanced typography features that EPUB and MOBI formats cannot provide. If you own an older Kindle (pre-2018), the converter can produce EPUB instead.",
  },
  // ── Unit 5 additions ─────────────────────────────────────────────────────
  {
    q: "Can I convert PDF to Kindle format for free?",
    a: "Yes, with limits. leafbind's free tier converts up to 3 files per day with a 20 MB file size cap, producing EPUB output. EPUB works on all Kindle devices and renders correctly for single-column PDFs. KFX output — which adds enhanced typography, tappable footnotes, and better heading navigation — is a premium feature that requires a one-time credit. See the pricing page for current credit pack options.",
  },
  {
    q: "Does leafbind work on Mac, Windows, and Linux?",
    a: "Yes. leafbind is entirely web-based — it runs in your browser with no software installation required. Upload your PDF from any device on any operating system. This is one of its advantages over Calibre, which requires a desktop install plus plugin management to produce KFX output.",
  },
  {
    q: "What's the difference between KFX and AZW3?",
    a: "KFX is Amazon's current native Kindle format (Kindle Format 10), introduced around 2014 and standard on all Kindle devices since 2018. It supports custom font embedding, advanced hyphenation, and the full Kindle typography stack. AZW3 (also called KF8) is the enhanced MOBI format that preceded KFX — still supported on modern Kindles, but without the full KFX typographic enhancements. For the best reading experience on a Kindle Scribe, Paperwhite, or Oasis, KFX is the right conversion target.",
  },
  {
    q: "I want to convert a Kindle book to PDF — does leafbind do that?",
    a: "No. leafbind only converts in the PDF → Kindle direction. For Kindle → PDF (personal backups of books you own), Calibre with the DeDRM plugin is the standard tool — but removing DRM is subject to the content's terms of service. leafbind does not handle that direction.",
  },
];

const faqSchema: FAQPageSchema = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: faqItems.map((item) => ({
    "@type": "Question",
    name: item.q,
    acceptedAnswer: { "@type": "Answer", text: item.a },
  })),
};

const howToSchema: HowToSchema = {
  "@context": "https://schema.org",
  "@type": "HowTo",
  name: "How to convert your PDF to KFX",
  step: [
    {
      "@type": "HowToStep",
      name: "Upload your PDF",
      text: "Drag your PDF onto the upload area or click to browse. Files up to 100 MB are supported on premium plans. The upload is encrypted in transit and stored only for the duration of the conversion job.",
    },
    {
      "@type": "HowToStep",
      name: "Select KFX as the output format",
      text: "After upload, choose KFX from the output format selector. This triggers the premium pipeline: column detection, heading classification, and footnote linking all run before the EPUB-to-KFX final step. You will be prompted to unlock a premium conversion if you have not already.",
    },
    {
      "@type": "HowToStep",
      name: "Download and send to your Kindle",
      text: "When the conversion completes, download the KFX file. Transfer it to your Kindle via USB or email it to your Kindle's personal document address. The file will appear in your Kindle library under Documents.",
    },
  ],
};

const articleSchema = buildArticleSchema({
  headline: "Convert PDF to Kindle Format (KFX): Online Converter for Academic & Multi-Column PDFs",
  description:
    "Convert PDF to Kindle format (KFX) online — built for academic papers, footnotes, and " +
    "multi-column layouts. leafbind handles what Send-to-Kindle and Calibre struggle with.",
  image: [
    "https://leafbind.io/quality/pipeline-columns.png",
    "https://leafbind.io/quality/pipeline-headings.png",
  ],
  datePublished: "2026-05-17",
  dateModified: "2026-05-17",
  url: CANONICAL,
});

export default function PdfToKfxPage() {
  return (
    <>
      <JsonLd schema={buildSoftwareApplicationSchema()} />
      <JsonLd schema={faqSchema} />
      <JsonLd schema={howToSchema} />
      <JsonLd schema={articleSchema} />

      {/* Page header */}
      <div className="py-12 md:py-16 border-b border-border mb-16">
        <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-5">
          Conversion guide
        </p>
        <h1 className="font-serif text-3xl sm:text-4xl md:text-5xl lg:text-6xl leading-tight text-text-base mb-6 max-w-3xl">
          Convert PDF to Kindle Format (KFX) — Academic Papers, Footnotes, and Multi-Column Layouts
        </h1>
        <p className="font-sans text-lg text-text-muted leading-relaxed max-w-2xl">
          leafbind converts PDF to Kindle format (KFX) online — built for academic papers, footnotes,
          and multi-column layouts that Send-to-Kindle and Calibre struggle with. Upload your PDF,
          get a KFX file that opens natively in your Kindle library. This guide covers the full
          pipeline, supported formats, and honest comparisons with Calibre and Send-to-Kindle.
        </p>
        <p className="font-sans text-sm text-text-muted leading-relaxed mt-4 max-w-2xl">
          Need the other direction?{" "}
          <a
            href="https://calibre-ebook.com"
            target="_blank"
            rel="noopener nofollow"
            className="text-accent no-underline hover:underline"
          >
            Calibre
          </a>{" "}
          with the DeDRM plugin handles Kindle&nbsp;&rarr;&nbsp;PDF for personal-use backups of books you own —
          leafbind only goes PDF&nbsp;&rarr;&nbsp;Kindle.
        </p>
      </div>

      {/* Main content */}
      <div className="py-0">

        {/* ── Section 1: What is KFX ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            What is KFX?
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              KFX is Amazon&rsquo;s proprietary Kindle Format 10 — the native ebook format
              shipped on every Kindle device sold since 2018. Where EPUB and MOBI treat text
              as a simple flow of paragraphs, KFX adds a layout layer: it supports custom
              font embedding, advanced hyphenation, enhanced paragraph spacing, and
              page-turn animation that respects the document&rsquo;s intended typographic weight.
            </p>
            <p>
              The difference is visible in reading comfort. A KFX file rendered on a Kindle
              Paperwhite uses the device&rsquo;s built-in Bookerly or Amazon Ember font with
              proper optical sizing. An EPUB or MOBI from the same source document will use
              the same fonts but without the Kindle typography stack — line spacing is less
              refined, hyphenation is cruder, and margin control is reduced.
            </p>
            <p>
              For academic and technical readers who spend hours on dense text — legal briefs,
              research papers, technical manuals — the KFX difference accumulates into noticeably
              less eye strain. KFX is also the format that Kindle&rsquo;s enhanced table of
              contents feature relies on: chapter navigation via swipe gestures and the reading
              progress bar at the bottom of the screen are more accurate in KFX than in legacy
              formats. If you are going to convert a PDF to read on Kindle, KFX is the format
              worth targeting.
            </p>
          </div>
        </section>

        {/* ── Section 2: Why most converters fail ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            Why most converters fail on PDF → KFX
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              Every converter that produces KFX from a PDF works in two steps: PDF → EPUB,
              then EPUB → KFX. The first step is where the quality is won or lost. Calibre,
              the most widely used open-source converter, handles the EPUB → KFX step well —
              but its PDF extraction is the weak link.
            </p>
            <p>
              Calibre&rsquo;s PDF extractor reads text in document order, which roughly corresponds
              to left-to-right, top-to-bottom page scanning. On a single-column PDF this is
              adequate. On a two-column academic paper, Calibre reads the first line of the
              left column, then the first line of the right column, then the second line of the
              left column — interleaving both columns into an unreadable stream. Heading
              detection is equally unreliable: Calibre applies heuristics based on font name
              rather than rendered font size, so a section title set in 14pt Bold Helvetica
              is treated identically to 14pt Bold body text.
            </p>
            <p>
              Footnotes compound the problem. A PDF footnote is a positional annotation at
              the bottom of a physical page. When Calibre converts to EPUB and strips the page
              model, footnotes either get appended to the end of the document with no navigation
              link, or they disappear entirely. The EPUB → KFX step then faithfully converts
              that broken EPUB — and the broken structure ends up in your Kindle library.
            </p>
          </div>
        </section>

        {/* ── Section 3: How leafbind does it differently ── */}
        <section className="mb-16 pb-16 border-b border-border">
          {/* 60/40 split: text left, proof link right */}
          <div className="grid grid-cols-1 md:grid-cols-5 gap-8 md:gap-12 items-start">
            <div className="md:col-span-3">
              <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
                How leafbind does it differently
              </h2>
              <div className="text-text-base leading-relaxed space-y-4 text-base">
                <p>
                  leafbind replaces Calibre&rsquo;s PDF extraction with a coordinate-aware
                  pipeline that reads the PDF at the object level rather than in page-scan order.
                  Each text object has an x/y position; the pipeline clusters objects into columns
                  by their horizontal bounding boxes, then reads each column top-to-bottom before
                  moving to the next. A two-column IEEE paper extracts as two clean columns, not
                  an interleaved mess.
                </p>
                <p>
                  Heading classification uses rendered font size as the primary signal. A text
                  run at 16pt in a document where body text averages 11pt is a heading candidate
                  regardless of the font family or weight name. The classifier computes a font-size
                  histogram across the document, identifies the body-text mode, and promotes text
                  runs that exceed the threshold by 30% or more. The result is a structured EPUB
                  with h2 and h3 tags that Calibre can then convert to KFX with a proper
                  navigable table of contents.
                </p>
                <p>
                  Footnote linking is explicit: the pipeline detects superscript markers in body
                  text, finds the corresponding footnote block at the bottom of the page region,
                  and generates a linked &lt;a&gt; pair — one anchor at the in-text citation, one at
                  the footnote body. In KFX, those links become Kindle&rsquo;s native footnote
                  popups.
                </p>
              </div>
            </div>

            <div className="md:col-span-2 mt-2 md:mt-12">
              <div className="bg-white border border-border rounded-md p-6 shadow-sm">
                <p className="font-mono text-xs font-medium text-text-muted uppercase tracking-widest mb-3">
                  See it in practice
                </p>
                <p className="text-base text-text-base leading-relaxed mb-4">
                  Side-by-side screenshots comparing Calibre raw output against
                  leafbind output for the same academic PDF — columns, footnotes,
                  and headings.
                </p>
                <Link
                  href="/quality"
                  className="inline-flex items-center min-h-[44px] text-sm font-medium text-accent no-underline hover:underline"
                >
                  View quality comparison →
                </Link>
              </div>
            </div>
          </div>
        </section>

        {/* ── Section 4: HowTo numbered list ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            How to convert your PDF to KFX
          </h2>
          <p className="text-base text-text-base leading-relaxed mb-8 max-w-2xl">
            KFX conversion is available on leafbind premium plans.{" "}
            <Link href="/pricing" className="text-accent no-underline hover:underline font-medium">
              See pricing →
            </Link>{" "}
            No account is required — premium access is unlocked per-conversion with a
            one-time credit.
          </p>
          <ol className="space-y-6 max-w-2xl">
            {[
              {
                n: "1",
                title: "Upload your PDF",
                body: "Drag your PDF onto the upload area or click to browse. Files up to 100 MB are supported on premium plans. The upload is encrypted in transit and stored only for the duration of the conversion job.",
              },
              {
                n: "2",
                title: "Select KFX as the output format",
                body: "After upload, choose KFX from the output format selector. This triggers the premium pipeline: column detection, heading classification, and footnote linking all run before the EPUB-to-KFX final step. You will be prompted to unlock a premium conversion if you have not already.",
              },
              {
                n: "3",
                title: "Download and send to your Kindle",
                body: "When the conversion completes, download the KFX file. Transfer it to your Kindle via USB or email it to your Kindle's personal document address. The file will appear in your Kindle library under Documents.",
              },
            ].map((step) => (
              <li key={step.n} className="flex gap-5">
                <div className="flex-shrink-0 w-8 h-8 rounded-sm bg-accent flex items-center justify-center">
                  <span className="text-sm font-medium text-white">{step.n}</span>
                </div>
                <div>
                  <h3 className="font-medium text-brand text-base mb-1">{step.title}</h3>
                  <p className="text-base text-text-base leading-relaxed">
                    {step.body}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        {/* ── Section 5: File formats (Unit 5) ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            File formats leafbind accepts
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              PDF is the primary input format. The pipeline reads text objects and their
              x/y coordinates directly from the PDF&rsquo;s internal structure using PyMuPDF,
              rather than rendering pages to pixels. Text-based PDFs — academic papers,
              technical manuals, legal documents, books exported from Word or InDesign —
              convert with full structure detection. Scanned PDFs (image-only pages) are
              also accepted; the pipeline triggers OCR via Gemini when no text layer is found.
            </p>
            <p>
              DRM-free EPUB files are accepted as input for conversion to KFX. Files from
              the Kindle or Apple Books store that carry DRM cannot be processed — the
              converter requires files you own outright or files without digital rights
              restrictions.
            </p>
            <p>
              Formats leafbind does not accept directly: MOBI (Amazon removed MOBI from
              Send-to-Kindle in 2022; leafbind follows the same policy), CBZ comic archives,
              ODT, or Apple Pages files. For those formats, export to PDF first, then convert.
            </p>
            <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-xl">
              <div className="border border-border rounded-sm p-4">
                <p className="font-mono text-xs font-medium text-text-muted uppercase tracking-widest mb-2">
                  Input
                </p>
                <ul className="space-y-1 text-sm text-text-base">
                  <li>PDF (text-based or scanned via OCR)</li>
                  <li>EPUB (DRM-free)</li>
                </ul>
              </div>
              <div className="border border-border rounded-sm p-4">
                <p className="font-mono text-xs font-medium text-text-muted uppercase tracking-widest mb-2">
                  Output
                </p>
                <ul className="space-y-1 text-sm text-text-base">
                  <li>KFX — premium, files up to 100&nbsp;MB</li>
                  <li>EPUB — free tier, files up to 20&nbsp;MB</li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        {/* ── Section 6: Multi-column PDFs — Calibre manual quote (EB-258 E-E-A-T) ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            What about multi-column PDFs?
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              Multi-column PDFs are the hardest class of document to convert correctly to
              Kindle format, and the most common source of garbled output. Calibre&rsquo;s own
              documentation is direct about the limitation:{" "}
              <em>&ldquo;Complex, multi-column, and image-based documents are not
              supported.&rdquo;</em>{" "}
              This refers specifically to Calibre&rsquo;s PDF input processing — the
              EPUB&nbsp;&rarr;&nbsp;KFX step works fine; PDF extraction is where multi-column
              layouts break down.
            </p>
            <p>
              Converting a two-column academic PDF to Kindle format requires a converter
              that understands the physical layout of the page, not just the document&rsquo;s
              text flow. Standard PDF-to-Kindle tools read text in document order, which
              roughly follows left-to-right, top-to-bottom page scanning. On a single-column
              PDF this produces correct output. On a two-column document such as an IEEE
              Transactions paper or a Nature article, document order interleaves the two
              columns: line one of column A, line one of column B, line two of column A,
              and so on. The result on your Kindle reads as alternating fragments from each
              column, making the text unreadable. The correct approach is coordinate-aware
              extraction: determine the x&nbsp;and y position of each text block, group
              blocks into columns by their horizontal bounding boxes, then read each complete
              column top-to-bottom before moving to the next. This is how leafbind&rsquo;s
              pipeline works.
            </p>
            <p>
              In practice, this handles IEEE, arXiv, ACM, and Nature two-column layouts
              correctly. Three-column layouts (common in newspaper-style PDFs) are also
              supported. Layouts where columns are unevenly sized or where sidebars break
              the column grid may require a manual review of the output.
            </p>
            <p>
              For a detailed walkthrough of the column-detection pipeline, see{" "}
              <Link
                href="/convert/multi-column-pdf-kindle"
                className="text-accent no-underline hover:underline"
              >
                Multi-column PDF to Kindle →
              </Link>
            </p>
          </div>
        </section>

        {/* ── Section 7: Academic papers with footnotes (Unit 5) ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            What about academic papers with footnotes?
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              Academic and legal documents rely on footnotes for citations,
              cross-references, and annotations. In the source PDF, a footnote is a
              positional annotation at the bottom of the physical page — the PDF format
              has no explicit structural link between the in-text superscript marker and
              the footnote body. That relationship is implied by position, not encoded.
            </p>
            <p>
              Most converters that produce EPUB from a PDF either append footnotes at
              the end of the document (losing the marker relationship) or drop them
              entirely. When Calibre then converts that EPUB to KFX, the broken structure
              carries through — you end up with a wall of unnumbered annotations at the
              back of the file with no way to navigate to them while reading.
            </p>
            <p>
              leafbind&rsquo;s pipeline detects superscript markers in body text — numeric
              superscripts, symbolic markers (*, †, ‡), and parenthetical citation numbers —
              and locates the corresponding footnote text by searching the bottom of the
              page region in which the marker appears. The pipeline then generates linked
              anchor pairs: one at the in-text marker, one at the footnote body. In the KFX
              output, those links become Kindle&rsquo;s native footnote popup overlays — tap
              the superscript, the footnote slides up without losing your reading position.
            </p>
            <p>
              For a full explanation with before/after rendering examples, see{" "}
              <Link
                href="/convert/pdf-footnotes-kindle"
                className="text-accent no-underline hover:underline"
              >
                PDF footnotes to Kindle →
              </Link>
            </p>
          </div>
        </section>

        {/* ── Section 8: Why not just use Calibre? (Unit 5) ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            Why not just use Calibre?
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              Calibre is excellent — it is the industry-standard open-source ebook manager
              and converter, and for most ebook formats it works well. If you have a simple
              single-column PDF and time to install a desktop application plus the KFX Output
              plugin, Calibre is a completely viable path to KFX at no cost.
            </p>
            <p>
              Where Calibre falls short is specifically on complex PDFs:
            </p>
            <ul className="list-disc list-inside space-y-2 ml-2">
              <li>
                <strong>Multi-column extraction</strong> — Calibre reads in document order
                and interleaves columns. Its own manual acknowledges that multi-column
                documents are not supported.
              </li>
              <li>
                <strong>Heading detection</strong> — Calibre&rsquo;s heading heuristics use
                font name rather than rendered font size. A title in Bold Helvetica is
                treated the same as bold body text. Table of contents in Calibre-converted
                academic papers is frequently flat or missing.
              </li>
              <li>
                <strong>Footnote backreferences</strong> — The EPUB Calibre produces from a
                PDF typically appends footnotes at the end of the document with no navigation
                link from the in-text marker. The EPUB&nbsp;&rarr;&nbsp;KFX step then converts
                this faithfully, preserving the broken structure in your Kindle library.
              </li>
            </ul>
            <p>
              The honest tradeoff: Calibre is free and handles the full ebook ecosystem.
              leafbind is a paid web service that solves a specific problem well. For a
              novel exported to PDF, a Word document, or any single-column text PDF,
              Calibre&rsquo;s output is adequate and there&rsquo;s no reason to pay. For
              academic papers, technical manuals, and legal documents with multi-column
              layouts, footnotes, and structured headings, leafbind produces noticeably
              better KFX output.
            </p>
            <p>
              One more thing worth knowing: leafbind&rsquo;s pipeline uses Calibre&rsquo;s
              own KFX Output plugin for the final EPUB&nbsp;&rarr;&nbsp;KFX step.
              Calibre&rsquo;s KFX conversion step is good — the weakness is in PDF
              extraction, not in the KFX assembly itself.
            </p>
          </div>
        </section>

        {/* ── Section 9: Why not just Send-to-Kindle? (Unit 5) ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            Why not just Send-to-Kindle?
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              Send-to-Kindle is convenient and free. For simple documents — a plain-text
              ebook, a DRM-free EPUB, a clean single-column PDF — it works well and is
              the easiest path to getting a file onto your Kindle.
            </p>
            <p>
              The problems arise when layout fidelity matters:
            </p>
            <ul className="list-disc list-inside space-y-2 ml-2">
              <li>
                <strong>Amazon re-converts your PDF on delivery.</strong> When you send a
                PDF via Send-to-Kindle, Amazon converts it on their servers. The conversion
                strips multi-column structure, drops footnote links, and flattens heading
                hierarchy. What arrives on your Kindle looks like a reflowed plain-text
                document, not the original PDF layout.
              </li>
              <li>
                <strong>File size limits.</strong> The Send-to-Kindle web uploader accepts
                files up to 200&nbsp;MB. For larger files, USB transfer is the alternative —
                it bypasses conversion entirely and loads the PDF into Kindle&rsquo;s native
                PDF reader as-is.
              </li>
              <li>
                <strong>Format restrictions.</strong> Send-to-Kindle no longer accepts MOBI
                (removed in 2022). Accepted formats include PDF, DOC, DOCX, TXT, RTF, HTML,
                EPUB, and common image formats. For other formats, convert to PDF first.
              </li>
            </ul>
            <p>
              For PDFs where formatting matters, the better alternatives are USB transfer
              (loads the PDF as-is into Kindle&rsquo;s PDF viewer — no conversion, all
              layout preserved) or leafbind (converts PDF to KFX with correct column order,
              tappable footnotes, and navigable headings).
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Link
                href="/guides/how-to-send-pdf-to-kindle"
                className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-3 hover:bg-accent/5"
              >
                All methods for getting files onto Kindle →
              </Link>
              <Link
                href="/guides/send-to-kindle-not-working"
                className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-3 hover:bg-accent/5"
              >
                Send to Kindle not working? 7 fixes →
              </Link>
            </div>
          </div>
        </section>

        {/* ── Section 10: FAQ ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-8 leading-snug">
            Frequently asked questions
          </h2>
          <div className="space-y-8 max-w-3xl">
            {faqItems.map((item) => (
              <div key={item.q}>
                <h3 className="font-serif text-xl text-brand mb-2 leading-snug">
                  {item.q}
                </h3>
                <p className="text-base text-text-base leading-relaxed">
                  {item.a.includes("/pricing") ? (
                    <>
                      {item.a.split(/(\bpricing page\b)/i).map((part, i) =>
                        /pricing page/i.test(part) ? (
                          <Link
                            key={i}
                            href="/pricing"
                            className="text-accent no-underline hover:underline font-medium"
                          >
                            pricing page
                          </Link>
                        ) : (
                          part
                        )
                      )}
                    </>
                  ) : (
                    item.a
                  )}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* ── Cross-links ── */}
        <section className="mb-16">
          <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-4">
            Related guides
          </p>
          <div className="flex flex-wrap gap-4">
            <Link
              href="/guides/pdf-to-kfx-for-kindle-scribe"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-3 hover:bg-accent/5"
            >
              Full guide: PDF to KFX for Kindle Scribe →
            </Link>
            <Link
              href="/guides/how-to-send-pdf-to-kindle"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-3 hover:bg-accent/5"
            >
              How to send PDFs to Kindle: every method →
            </Link>
            <Link
              href="/guides/send-to-kindle-not-working"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-3 hover:bg-accent/5"
            >
              Send to Kindle not working: 7 fixes →
            </Link>
            <Link
              href="/convert/academic-pdf-to-kindle"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-3 hover:bg-accent/5"
            >
              Academic PDF to Kindle →
            </Link>
            <Link
              href="/quality"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-3 hover:bg-accent/5"
            >
              Quality comparison →
            </Link>
            <Link
              href="/pricing"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-3 hover:bg-accent/5"
            >
              Premium plans →
            </Link>
          </div>
        </section>

        {/* ── Sources ── */}
        <section className="mb-16 pb-8 border-b border-border">
          <p className="font-mono text-xs font-medium text-text-muted uppercase tracking-widest mb-3">Sources</p>
          <ul className="space-y-1">
            <li className="font-sans text-sm text-text-muted">
              <a
                href="https://manual.calibre-ebook.com/"
                target="_blank"
                rel="noopener nofollow"
                className="text-accent no-underline hover:underline"
              >
                Calibre User Manual — PDF input limitations and conversion notes
              </a>{" "}(last verified 2026-05-17)
            </li>
            <li className="font-sans text-sm text-text-muted">
              <a
                href="https://www.amazon.com/sendtokindle"
                target="_blank"
                rel="noopener"
                className="text-accent no-underline hover:underline"
              >
                Amazon Send to Kindle — supported file types and web uploader
              </a>{" "}(last verified 2026-05-17)
            </li>
          </ul>
        </section>

        {/* Primary CTA */}
        <section className="mb-0 border-t border-border pt-16 pb-8">
          <h2 className="font-serif text-3xl text-text-base mb-4 leading-snug">
            Ready to convert your PDF to KFX?
          </h2>
          <p className="font-sans text-base text-text-muted leading-relaxed mb-3 max-w-xl">
            KFX output is a premium feature.{" "}
            <Link
              href="/pricing"
              className="text-brand font-medium no-underline hover:underline"
            >
              See pricing
            </Link>{" "}
            — plans start at a single conversion credit with no subscription required.
          </p>
          <p className="font-sans text-sm text-text-muted leading-relaxed mb-8">
            Free tier: 3 EPUB conversions per day, up to 20 MB. No account required.
          </p>
          <Link
            href="/"
            className="font-sans inline-block bg-brand text-white font-medium text-base px-8 py-3 rounded-sm no-underline hover:opacity-90"
          >
            Upload your PDF
          </Link>
        </section>
      </div>
    </>
  );
}
