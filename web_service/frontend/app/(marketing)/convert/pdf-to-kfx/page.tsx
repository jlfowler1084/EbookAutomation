import type { Metadata } from "next";
import Link from "next/link";
import JsonLd from "../../../../components/JsonLd";
import {
  buildSoftwareApplicationSchema,
  type FAQPageSchema,
  type HowToSchema,
} from "../../../../lib/structured-data";

export const metadata: Metadata = {
  title: "Convert PDF to KFX for Kindle Scribe — leafbind",
  description:
    "Convert PDF to KFX for Kindle Scribe with smart heading detection, footnote linking, " +
    "and multi-column layout support. Premium pipeline. No account required.",
  alternates: { canonical: "/convert/pdf-to-kfx" },
  openGraph: {
    title: "Convert PDF to KFX for Kindle Scribe — leafbind",
    description:
      "Smart PDF to KFX conversion for Kindle Scribe — heading structure, footnotes, and " +
      "multi-column layouts handled correctly.",
    type: "website",
    url: "https://leafbind.io/convert/pdf-to-kfx",
    images: [{ url: "https://leafbind.io/quality/pipeline-columns.png", width: 800, height: 600 }],
  },
  twitter: {
    card: "summary",
    title: "Convert PDF to KFX for Kindle Scribe — leafbind",
    description: "Smart PDF to KFX conversion for Kindle Scribe.",
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

export default function PdfToKfxPage() {
  return (
    <>
      <JsonLd schema={buildSoftwareApplicationSchema()} />
      <JsonLd schema={faqSchema} />
      <JsonLd schema={howToSchema} />

      {/* Page header */}
      <div className="py-12 md:py-16 border-b border-border mb-16">
        <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-5">
          Conversion guide
        </p>
        <h1 className="font-serif text-5xl md:text-6xl leading-tight text-text-base mb-6 max-w-3xl">
          Convert PDF to KFX for Kindle Scribe — Smart Formatting Preserved
        </h1>
        <p className="font-sans text-lg text-text-muted leading-relaxed max-w-2xl">
          KFX is Kindle&rsquo;s native enhanced typesetting format. Getting a PDF
          into KFX without losing headings, footnotes, or column order requires
          more than a one-step conversion — this guide explains what goes wrong and
          how leafbind handles it differently.
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
                  className="text-sm font-medium text-accent no-underline hover:underline"
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
                body: "When the conversion completes, download the KFX file. Transfer it to your Kindle via USB or email it to your Kindle’s personal document address. The file will appear in your Kindle library under Documents.",
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

        {/* ── Section 5: FAQ ── */}
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
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-2 hover:bg-accent/5"
            >
              Full guide: PDF to KFX for Kindle Scribe →
            </Link>
            <Link
              href="/convert/academic-pdf-to-kindle"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-2 hover:bg-accent/5"
            >
              Academic PDF to Kindle →
            </Link>
            <Link
              href="/quality"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-2 hover:bg-accent/5"
            >
              Quality comparison →
            </Link>
            <Link
              href="/pricing"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-2 hover:bg-accent/5"
            >
              Premium plans →
            </Link>
          </div>
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
