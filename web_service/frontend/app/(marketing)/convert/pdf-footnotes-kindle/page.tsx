import type { Metadata } from "next";
import Link from "next/link";
import JsonLd from "../../../../components/JsonLd";
import {
  buildSoftwareApplicationSchema,
  type FAQPageSchema,
  type HowToSchema,
} from "../../../../lib/structured-data";

export const metadata: Metadata = {
  title: "PDF footnotes on Kindle Scribe — keep them linked — leafbind",
  description:
    "Convert PDFs with footnotes to Kindle Scribe — leafbind links markers to footnote " +
    "text so citations stay tappable as popup links.",
  alternates: { canonical: "/convert/pdf-footnotes-kindle" },
  openGraph: {
    title: "PDF footnotes on Kindle Scribe — keep them linked — leafbind",
    description: "Footnote markers and text are linked — not stripped — in the Kindle output.",
    type: "website",
    url: "https://leafbind.io/convert/pdf-footnotes-kindle",
    images: [{ url: "https://leafbind.io/quality/pipeline-columns.png", width: 800, height: 600 }],
  },
  twitter: {
    card: "summary",
    title: "PDF footnotes on Kindle Scribe — keep them linked — leafbind",
    description: "Convert PDFs with footnotes to Kindle Scribe. Tappable popup links preserved.",
  },
};

const howToSteps = [
  {
    number: "01",
    title: "Upload your PDF",
    body: "Drag and drop your PDF or click to browse. Works with any text-based PDF — academic papers, history books, legal documents, annotated editions.",
  },
  {
    number: "02",
    title: "Select your output format",
    body: "Choose EPUB for broad device compatibility, or KFX for the richest Kindle experience. Both formats preserve footnote linking; KFX enables popup footnotes on modern Paperwhite and Scribe hardware.",
  },
  {
    number: "03",
    title: "Download and send to your Kindle",
    body: "Download the converted file and send it to your device via the Kindle app, USB cable, or your personal Kindle email address. Footnotes are immediately navigable on device.",
  },
];

const faqs = [
  {
    q: "Will footnote linking work in the free tier?",
    a: "Basic footnote linking — detecting numeric superscripts and connecting them to their footnote text — is available in the free tier. Full endnote backreference generation, which creates bidirectional jump links (marker-to-note and note-back-to-marker), is a premium feature. If your book has extensive footnotes or chapter-level endnotes that must be two-way navigable, the premium pipeline handles those correctly.",
  },
  {
    q: "What about books with 500 or more footnotes?",
    a: "There is no limit on footnote count. leafbind has been tested on Oswald Spengler's Decline of the West — a two-volume work with multi-chapter footnote sequences running into the hundreds — and the footnote pairing holds across all chapters. If anything, denser footnote structures benefit more from the pipeline: the more footnotes a book has, the worse the reading experience becomes when they are broken, and the more valuable correct linking is.",
  },
  {
    q: "Do footnotes become popups on Kindle?",
    a: "Yes, on Kindle Paperwhite, Kindle Scribe, and Kindle Colorsoft with KFX format output. When the footnote is tagged as an aside element in the KFX, modern Kindle firmware renders it as a dismissible popup overlay — the same behavior you see in professionally published Kindle books. EPUB format footnotes open as a linked page on older Kindles (pre-2018) and as a popup or bottom-sheet on newer ones, depending on firmware. If popup behavior matters to you, select KFX output in the premium tier.",
  },
];

const faqSchema: FAQPageSchema = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: faqs.map((item) => ({
    "@type": "Question",
    name: item.q,
    acceptedAnswer: { "@type": "Answer", text: item.a },
  })),
};

const howToSchema: HowToSchema = {
  "@context": "https://schema.org",
  "@type": "HowTo",
  name: "Three steps from PDF to Kindle-ready output",
  step: howToSteps.map((step) => ({
    "@type": "HowToStep",
    name: step.title,
    text: step.body,
  })),
};

export default function PdfFootnotesKindlePage() {
  return (
    <>
      <JsonLd schema={buildSoftwareApplicationSchema()} />
      <JsonLd schema={faqSchema} />
      <JsonLd schema={howToSchema} />

      {/* Page header */}
      <div className="py-12 md:py-16 border-b border-border mb-16">
        <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-5">
          Footnote conversion guide
        </p>
        <h1 className="font-serif text-3xl sm:text-4xl md:text-5xl lg:text-6xl leading-tight text-text-base mb-6 max-w-2xl">
          PDF Footnotes on Kindle Scribe — Keep Them Linked and Readable
        </h1>
        <p className="font-sans text-lg text-text-muted leading-relaxed max-w-xl">
          Most PDF converters break footnotes the moment the page model
          disappears. leafbind detects every marker, pairs it to the footnote
          body, and produces a navigable linked pair — so you can read
          footnote-heavy books on Kindle the way they were meant to be read.
        </p>
      </div>

      {/* Section 1 — The footnote problem on Kindle */}
      <section className="mb-16 pb-16 border-b border-border">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-8 md:gap-16 items-start">
          <div className="md:col-span-3">
            <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-4">
              The problem
            </p>
            <h2 className="font-serif text-3xl text-text-base mb-6 leading-snug">
              What a broken footnote actually looks like on Kindle
            </h2>
            <div className="space-y-4 font-sans text-base text-text-base leading-relaxed">
              <p>
                Open any Calibre-converted academic PDF on a Kindle
                Paperwhite and navigate to a footnoted passage. You will see
                a superscript number — say,{" "}
                <sup className="text-sm font-medium text-brand">14</sup> —
                sitting in the middle of the sentence, but tapping it does
                nothing. The number is rendered as plain text. Scroll to the
                end of the chapter and you may find the footnote body listed
                there as disconnected text: <em>"14. Cf. Weber, Economy and
                Society, §3, pp. 111–117."</em> There is no link back to
                the passage where the citation appeared. You lose your place
                every time you look something up.
              </p>
              <p>
                The root cause is structural. PDF footnotes are positional
                — the footnote body sits at the bottom of a physical page,
                tied to a location by coordinates, not by a semantic link.
                When a converter flattens the PDF into a reflow format, the
                page boundaries disappear and the positional relationship
                breaks. Unless the converter explicitly detects the
                superscript, locates its matching footnote body, and writes
                a bidirectional link into the EPUB or KFX output, the
                footnote is effectively destroyed.
              </p>
              <p>
                For novels and light non-fiction this is a minor annoyance.
                For academic history, philosophy, theology, law, or any
                heavily annotated scholarly text, broken footnotes make the
                book unusable. You cannot follow citations, verify claims,
                or read the scholarly apparatus that gives the text its
                authority.
              </p>
            </div>
          </div>
          <div className="md:col-span-2">
            <div className="bg-white rounded-md shadow-md border border-border p-6">
              <p className="font-mono text-xs font-medium text-text-muted uppercase tracking-widest mb-4">
                Typical Calibre output
              </p>
              <div className="font-serif text-sm text-text-base leading-relaxed space-y-3">
                <p>
                  The political legitimacy of the decree rested on three
                  precedents from the previous administration.
                  <sup className="text-xs text-text-muted">14</sup> None of these
                  precedents survived judicial review in the following decade.
                  <sup className="text-xs text-text-muted">15</sup>
                </p>
                <p className="font-sans text-xs text-text-muted italic border-t border-border pt-3">
                  [Superscripts 14, 15 are plain text — not tappable.
                  Footnote bodies appear 40 pages later with no
                  back-link.]
                </p>
              </div>
            </div>
            <p className="font-sans text-sm text-text-muted mt-4 leading-relaxed">
              See the{" "}
              <Link
                href="/quality"
                className="text-brand no-underline hover:underline"
              >
                quality comparison page
              </Link>{" "}
              for a screenshot of leafbind footnote output versus Calibre
              side by side.
            </p>
          </div>
        </div>
      </section>

      {/* Section 2 — How leafbind links footnotes */}
      <section className="mb-16 pb-16 border-b border-border">
        <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-4">
          The solution
        </p>
        <h2 className="font-serif text-3xl text-text-base mb-8 leading-snug max-w-2xl">
          How leafbind detects and links footnotes
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          <div className="space-y-3">
            <div className="w-10 h-10 rounded-sm bg-brand flex items-center justify-center">
              <span className="font-serif text-lg text-white">1</span>
            </div>
            <h3 className="font-sans font-semibold text-text-base text-base">
              Superscript detection
            </h3>
            <p className="font-sans text-base text-text-muted leading-relaxed">
              The pipeline reads the rendered font metrics for every text
              run in the PDF. Characters positioned above the baseline and
              rendered at a smaller point size than the surrounding body
              text are flagged as superscript candidates. This catches both
              traditional raised numerals and symbols like *, †, and ‡
              without requiring a fixed font size threshold.
            </p>
          </div>
          <div className="space-y-3">
            <div className="w-10 h-10 rounded-sm bg-brand flex items-center justify-center">
              <span className="font-serif text-lg text-white">2</span>
            </div>
            <h3 className="font-sans font-semibold text-text-base text-base">
              Footnote body extraction
            </h3>
            <p className="font-sans text-base text-text-muted leading-relaxed">
              For each superscript, the pipeline searches the lower region
              of the same page — or the following page if the footnote is
              long enough to wrap — for a text block that begins with the
              matching marker. Using coordinate-based proximity analysis,
              it confirms the spatial relationship, extracts the complete
              footnote body including any continuation text on the next
              page, and pairs it with the original marker.
            </p>
          </div>
          <div className="space-y-3">
            <div className="w-10 h-10 rounded-sm bg-brand flex items-center justify-center">
              <span className="font-serif text-lg text-white">3</span>
            </div>
            <h3 className="font-sans font-semibold text-text-base text-base">
              Linked output generation
            </h3>
            <p className="font-sans text-base text-text-muted leading-relaxed">
              Each matched pair becomes a bidirectional link in the output.
              The in-text marker is wrapped in an anchor element pointing
              to the footnote body; the footnote body includes a
              return-to-text link. In KFX format, the Kindle firmware
              recognises the aside element and renders the footnote as a
              popup. In EPUB, it renders as a linked navigation pair — the
              standard used by professionally published ebooks.
            </p>
          </div>
        </div>
        <p className="font-sans text-base text-text-muted leading-relaxed mt-8 max-w-2xl">
          The full pipeline is tested against books with complex footnote
          structures: multi-chapter sequences, footnotes that share a page
          with endnotes, and academic works where footnote density exceeds
          one per paragraph. The detection rate on clean text-based PDFs
          consistently exceeds 98%. For visual evidence, the{" "}
          <Link
            href="/quality"
            className="text-brand no-underline hover:underline"
          >
            quality comparison page
          </Link>{" "}
          shows a side-by-side screenshot from the same source document
          converted through Calibre and through leafbind.
        </p>
      </section>

      {/* Section 3 — Types of footnotes handled */}
      <section className="mb-16 pb-16 border-b border-border">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-8 md:gap-16 items-start">
          <div className="md:col-span-2">
            <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-4">
              Coverage
            </p>
            <h2 className="font-serif text-3xl text-text-base mb-6 leading-snug">
              Types of footnotes the pipeline handles
            </h2>
            <p className="font-sans text-base text-text-muted leading-relaxed">
              Not all footnotes are the same. The pipeline is built to
              cover the formats that appear most often in real-world
              academic and scholarly publishing.
            </p>
          </div>
          <div className="md:col-span-3">
            <ul className="space-y-5">
              {[
                {
                  label: "Numeric superscripts",
                  symbol: "¹ ² ³",
                  desc: "Standard raised numerals used in history, philosophy, theology, and most humanities scholarship. Both sequential numbering per-chapter and per-document numbering are handled.",
                },
                {
                  label: "Symbolic markers",
                  symbol: "* † ‡",
                  desc: "Asterisk, dagger, and double-dagger sequences common in older academic texts, legal documents, and annotated editions. The pipeline detects the symbol sequence and matches body text accordingly.",
                },
                {
                  label: "Inline parenthetical notes",
                  symbol: "(n)",
                  desc: "Some publishers use parenthesised numbers inline rather than superscript. These are detected as a distinct pattern and handled as linked footnotes in the output.",
                },
                {
                  label: "Chapter-end endnotes",
                  symbol: "p. 312–",
                  desc: "When notes are gathered at the end of a chapter rather than at the page foot, the pipeline treats the endnote block as a linked aside section. Jump-to-note and return-to-text links are preserved.",
                },
              ].map((item) => (
                <li key={item.label} className="flex gap-4 items-start">
                  <span className="font-serif text-lg text-brand w-12 shrink-0 pt-0.5">
                    {item.symbol}
                  </span>
                  <div>
                    <p className="font-sans font-medium text-text-base text-base mb-1">
                      {item.label}
                    </p>
                    <p className="font-sans text-base text-text-muted leading-relaxed">
                      {item.desc}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
            <div className="mt-8 p-4 rounded-sm border border-border bg-white">
              <p className="font-sans text-sm text-text-muted leading-relaxed">
                <span className="font-medium text-text-base">Outside scope:</span>{" "}
                Footnotes in scanned PDFs (image-only pages) require OCR to
                extract the text first. A Gemini-based OCR pass for scanned
                pages is on the leafbind roadmap but not yet active in the
                production converter. For text-based PDFs — the standard
                digital-born format — footnote detection is accurate and
                well-tested.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Section 4 — HowTo */}
      <section className="mb-16 pb-16 border-b border-border">
        <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-4">
          How to convert
        </p>
        <h2 className="font-serif text-3xl text-text-base mb-10 leading-snug max-w-xl">
          Three steps from PDF to Kindle-ready output
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {howToSteps.map((step) => (
            <div key={step.number} className="relative">
              <p className="font-serif text-5xl text-border leading-none mb-4 select-none">
                {step.number}
              </p>
              <h3 className="font-sans font-semibold text-text-base text-base mb-3">
                {step.title}
              </h3>
              <p className="font-sans text-base text-text-muted leading-relaxed">
                {step.body}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Section 5 — FAQ */}
      <section className="mb-16 pb-16 border-b border-border">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-8 md:gap-16 items-start">
          <div className="md:col-span-2">
            <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-4">
              FAQ
            </p>
            <h2 className="font-serif text-3xl text-text-base mb-4 leading-snug">
              Common questions about footnote conversion
            </h2>
            <p className="font-sans text-base text-text-muted leading-relaxed">
              If your question is not answered here, the{" "}
              <Link
                href="/convert/academic-pdf-to-kindle"
                className="text-brand no-underline hover:underline"
              >
                academic PDF guide
              </Link>{" "}
              covers related topics including inline citations, section
              numbering, and multi-column layout handling.
            </p>
          </div>
          <div className="md:col-span-3 space-y-8">
            {faqs.map((faq, i) => (
              <div key={i} className="border-t border-border pt-6 first:border-t-0 first:pt-0">
                <h3 className="font-sans font-semibold text-text-base text-base mb-3">
                  {faq.q}
                </h3>
                <p className="font-sans text-base text-text-muted leading-relaxed">
                  {faq.a}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Primary CTA */}
      <div className="border-t border-border pt-16 pb-8">
        <h2 className="font-serif text-3xl text-text-base mb-4 leading-snug">
          Read footnote-heavy books the way they were written
        </h2>
        <p className="font-sans text-base text-text-muted leading-relaxed mb-8 max-w-md">
          Free tier: 3 conversions per day, up to 20 MB. No account
          required. Upload your PDF and see the difference in seconds.
        </p>
        <Link
          href="/"
          className="font-sans inline-block bg-brand text-white font-medium text-base px-8 py-3 rounded-sm no-underline hover:opacity-90"
        >
          Upload your PDF
        </Link>
      </div>
    </>
  );
}
