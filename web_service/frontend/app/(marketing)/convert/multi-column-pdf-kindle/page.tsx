import type { Metadata } from "next";
import Link from "next/link";
import JsonLd from "../../../../components/JsonLd";
import {
  buildSoftwareApplicationSchema,
  type FAQPageSchema,
  type HowToSchema,
} from "../../../../lib/structured-data";

export const metadata: Metadata = {
  title: "Convert Multi-Column PDFs to Kindle — leafbind",
  description:
    "Multi-column PDF to Kindle converter. leafbind reads each column independently " +
    "so the text flows correctly on Kindle — not interleaved across columns.",
  alternates: { canonical: "/convert/multi-column-pdf-kindle" },
  openGraph: {
    title: "Convert Multi-Column PDFs to Kindle — leafbind",
    description:
      "Reads each column independently. Text flows correctly on Kindle, not merged.",
    type: "website",
    url: "https://leafbind.io/convert/multi-column-pdf-kindle",
    images: [{ url: "https://leafbind.io/quality/pipeline-columns.png", width: 800, height: 600 }],
  },
  twitter: {
    card: "summary",
    title: "Convert Multi-Column PDFs to Kindle — leafbind",
    description: "Multi-column PDF to Kindle: each column read in order.",
  },
};

const faqItems = [
  {
    question: "Does leafbind work on 3-column layouts?",
    answer:
      "Yes. The coordinate-based column detector handles 2- and 3-column layouts by identifying the number of distinct x-position clusters on each page and sorting text runs by cluster, then by vertical position within each cluster. Four-column and wider layouts are uncommon in the document types leafbind targets, and may fall back to single-column extraction — the output will note when a fallback was applied.",
  },
  {
    question: "What about documents with mixed layouts — some single-column pages and some double-column?",
    answer:
      "Mixed layouts are fully supported. Each page is analyzed independently: if a page has a single text column, it is extracted without column splitting. If the same document has two-column academic body pages alongside single-column abstract and reference pages, each page type is handled correctly. You do not need to split the document or set any flags — the detector adapts page by page.",
  },
  {
    question: "Will tables survive multi-column detection?",
    answer:
      "Tables that are contained within a single column are extracted cleanly. Tables that span both columns — used in some journal layouts to present wide datasets — are extracted as-is, which may produce line-wrapped cell contents in the Kindle output. Complex spanning tables benefit from manual verification in the Kindle viewer after conversion. leafbind flags spanning-table detections in the conversion log so you know which pages to check.",
  },
];

const howToSteps = [
  {
    number: "01",
    title: "Upload your PDF",
    body: "Drag the PDF onto the leafbind upload form or click to browse. Files up to 20 MB are accepted on the free tier; the premium tier raises the limit to 100 MB. No account or registration is required.",
  },
  {
    number: "02",
    title: "Select your output format",
    body: "Choose EPUB for broad Kindle compatibility or KFX for the best reading experience on Kindle Paperwhite, Kindle Scribe, and recent Kindle models. KFX format requires the premium tier and unlocks native Kindle typography.",
  },
  {
    number: "03",
    title: "Download and send to your Kindle",
    body: "The converted file downloads directly to your browser. Send it to your Kindle via USB, the Kindle app, or your personal Send-to-Kindle email address. On device, the text flows in the correct column order — no garbled reading, no interleaved lines.",
  },
];

const faqSchema: FAQPageSchema = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: faqItems.map((item) => ({
    "@type": "Question",
    name: item.question,
    acceptedAnswer: { "@type": "Answer", text: item.answer },
  })),
};

const howToSchema: HowToSchema = {
  "@context": "https://schema.org",
  "@type": "HowTo",
  name: "Three steps to a correctly ordered Kindle book",
  step: howToSteps.map((step) => ({
    "@type": "HowToStep",
    name: step.title,
    text: step.body,
  })),
};

export default function MultiColumnPdfKindlePage() {
  return (
    <>
      <JsonLd schema={buildSoftwareApplicationSchema()} />
      <JsonLd schema={faqSchema} />
      <JsonLd schema={howToSchema} />

      {/* Page header */}
      <div className="py-12 md:py-16 border-b border-border mb-16">
        <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-5">
          Multi-column PDF conversion
        </p>
        <h1 className="font-serif text-3xl sm:text-4xl md:text-5xl lg:text-6xl leading-tight text-text-base mb-6 max-w-3xl">
          Convert Multi-Column PDFs to Kindle — Columns Read in the Right Order
        </h1>
        <p className="font-sans text-lg text-text-muted leading-relaxed max-w-xl mb-8">
          Most converters merge both columns into a single stream. leafbind reads
          each column independently, so your academic papers and journal articles
          flow exactly as written.
        </p>
        <Link
          href="/#convert"
          className="font-sans inline-block bg-brand text-white font-medium text-base px-8 py-3 rounded-sm no-underline hover:opacity-90"
        >
          Upload your PDF
        </Link>
      </div>

      {/* Section 1: What goes wrong with multi-column PDFs */}
      <section className="mb-16 pb-16 border-b border-border">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-8 md:gap-12 items-start">
          <div className="md:col-span-3">
            <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-5">
              The problem
            </p>
            <h2 className="font-serif text-3xl text-text-base mb-6 leading-snug">
              What goes wrong with multi-column PDFs
            </h2>
            <div className="font-sans space-y-4 text-base text-text-base leading-relaxed">
              <p>
                When Calibre — or any converter that uses a simple left-to-right text sweep —
                processes a two-column PDF, it does not understand that the page is divided
                into independent reading lanes. It reads across the full page width at each
                vertical position, alternating between columns with every line.
              </p>
              <p>
                The result is an interleaved stream: the first sentence of the left column,
                then the first sentence of the right column, then the second sentence of
                the left column, then the second sentence of the right column — and so on
                through the entire page. What was a coherent academic argument becomes an
                unreadable alternating muddle where every other sentence belongs to a
                completely different thread of reasoning.
              </p>
              <p>
                Imagine reading a paragraph that begins: <em>"The epistemological framework
                proposed here — The study of immune response markers in —
                draws on three prior accounts — 47 adult subjects aged 22 to 65 —
                none of which fully address — were randomly assigned to one of —
                the problem of under-determination."</em> That is what column-merged extraction
                produces on every page of a two-column academic paper.
              </p>
              <p>
                This is not a bug that careful Calibre configuration can fix. It is a
                fundamental limitation of text extraction that treats the page as a
                single flat stream rather than a set of spatially organized regions.
                Fixing it requires coordinate-aware extraction — which is exactly what
                leafbind uses.
              </p>
            </div>
          </div>
          <div className="md:col-span-2 bg-surface border border-border rounded-md p-6">
            <p className="font-mono text-xs font-medium text-text-muted uppercase tracking-widest mb-3">
              The column-merge pattern
            </p>
            <div className="space-y-2 font-sans text-sm text-text-base leading-relaxed">
              <p className="text-text-muted line-through">Col 1 line 1: The epistemological framework...</p>
              <p className="text-text-muted line-through">Col 2 line 1: The study of immune markers...</p>
              <p className="text-text-muted line-through">Col 1 line 2: draws on three prior accounts...</p>
              <p className="text-text-muted line-through">Col 2 line 2: 47 adult subjects aged 22...</p>
            </div>
            <div className="mt-4 pt-4 border-t border-border space-y-2 font-sans text-sm text-text-base leading-relaxed">
              <p className="font-mono font-medium text-brand text-xs uppercase tracking-widest mb-2">
                What you want
              </p>
              <p>Col 1 line 1: The epistemological framework...</p>
              <p>Col 1 line 2: draws on three prior accounts...</p>
              <p className="text-text-muted">— end of column 1 —</p>
              <p>Col 2 line 1: The study of immune markers...</p>
              <p>Col 2 line 2: 47 adult subjects aged 22...</p>
            </div>
          </div>
        </div>
      </section>

      {/* Section 2: How leafbind detects columns */}
      <section className="mb-16 pb-16 border-b border-border">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-8 md:gap-12 items-start">
          <div className="md:col-span-2">
            <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-5">
              The detection method
            </p>
            <h2 className="font-serif text-3xl text-text-base mb-6 leading-snug">
              How leafbind detects columns
            </h2>
            <p className="font-sans text-base text-text-muted leading-relaxed mb-4">
              The foundation is pdfplumber, a coordinate-aware PDF extraction library
              that exposes the precise bounding box — x0, y0, x1, y1 — of every text
              character and word on the page. Most extraction tools discard this spatial
              data. leafbind uses it as the primary signal for column detection.
            </p>
            <Link
              href="/quality"
              className="font-sans text-sm font-medium text-brand no-underline hover:underline"
            >
              See the column comparison screenshots →
            </Link>
          </div>
          <div className="md:col-span-3 font-sans space-y-4 text-base text-text-base leading-relaxed">
            <p>
              For each page, leafbind collects the x0 (left edge) positions of all
              text runs and identifies natural gaps in that distribution. A two-column
              page has a dense cluster of x0 values near the left margin and a second
              dense cluster near the horizontal midpoint. The gap between them is the
              column gutter — the white space between columns that the eye uses to
              separate the reading lanes.
            </p>
            <p>
              Once the column boundaries are located, leafbind assigns each text run
              to its column based on its x1 (right edge) position: runs whose right
              edge falls within the left half of the page belong to column one; runs
              whose left edge starts at or beyond the midpoint boundary belong to
              column two. For three-column layouts, the same clustering approach
              identifies two gutters and three regions.
            </p>
            <p>
              Within each column, text runs are sorted by their y0 (vertical) position —
              top to bottom, as a reader would scan them. The result is a sequential
              stream that reads column one from top to bottom, then column two from
              top to bottom, preserving exactly the order the author intended.
            </p>
            <p>
              The column detector runs independently on each page. A document that
              opens with a single-column abstract, transitions to a two-column body,
              and ends with single-column references is handled correctly at each
              page boundary — no manual configuration, no document splitting. The
              visual proof is on the{" "}
              <Link href="/quality" className="text-brand no-underline hover:underline">
                quality comparison page
              </Link>
              , where the same IEEE-style paper is shown as Calibre processes it (interleaved)
              and as leafbind processes it (correctly sequenced).
            </p>
          </div>
        </div>
      </section>

      {/* Section 3: Document types */}
      <section className="mb-16 pb-16 border-b border-border">
        <div className="max-w-3xl">
          <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-5">
            Document types
          </p>
          <h2 className="font-serif text-3xl text-text-base mb-6 leading-snug">
            What document types have multi-column layouts
          </h2>
          <div className="font-sans space-y-4 text-base text-text-base leading-relaxed">
            <p>
              Multi-column layouts are the default format for a large share of academic
              and archival publishing. IEEE and ACM conference papers, journal articles
              from Nature, PLOS, and most medical publishers, newspaper archives digitized
              for historical research — all use two-column layouts that will produce
              garbled output through a naive converter.
            </p>
            <p>
              Legal documents from certain court jurisdictions, legislative records, and
              historical texts typeset in pre-digital book production often use two- or
              three-column layouts. Older newspaper archives distributed as PDF are
              particularly prone to column interleaving when converted without coordinate
              awareness.
            </p>
            <p>
              If you are reading academic research, digitized periodicals, or any
              publication that looks like a journal article on screen — two narrow
              columns of text side by side — leafbind is designed for exactly that
              document type. See also:{" "}
              <Link href="/convert/academic-pdf-to-kindle" className="text-brand no-underline hover:underline">
                converting academic PDFs to Kindle
              </Link>.
            </p>
          </div>
        </div>
      </section>

      {/* Section 3b: K2pdfopt comparison */}
      <section className="mb-16 pb-16 border-b border-border">
        <div className="max-w-3xl">
          <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-5">
            Compared to K2pdfopt
          </p>
          <h2 className="font-serif text-3xl text-text-base mb-6 leading-snug">
            How leafbind compares to K2pdfopt
          </h2>
          <div className="font-sans space-y-4 text-base text-text-base leading-relaxed">
            <p>
              K2pdfopt is the long-standing answer for multi-column PDF conversion in
              the Kindle community. It is a free command-line tool (Willus Watkins,
              willus.com) that reflows two-column academic PDFs by analyzing pixel
              density to find column boundaries. For a technical user comfortable with
              CLI tools and able to install local software, K2pdfopt is a reasonable
              option with a long track record.
            </p>
            <p>
              The friction is the install and the interface. K2pdfopt distributes as a
              binary that requires command-line invocation with multiple flags
              (<code>k2pdfopt -mode 2col -dev kpw3</code> and similar), and the project
              has not seen a major release since 2021. There is no maintained web
              interface. For converting a single paper this afternoon, the install plus
              flag-tuning often exceeds the benefit. For batch workflows where the same
              flag set works repeatedly, K2pdfopt remains practical.
            </p>
            <p>
              leafbind is web-based with no install. The pipeline uses coordinate-based
              extraction (not pixel-density analysis) and produces KFX output with
              chapter detection and footnote linking — capabilities K2pdfopt does not
              attempt. The trade-off: leafbind is paid for KFX output (a one-time
              credit pack) where K2pdfopt is free for unlimited local use. The choice
              depends on whether you value the conversion time saved or the install
              freedom of running a local binary.
            </p>
          </div>
        </div>
      </section>

      {/* Section 4: HowTo */}
      <section className="mb-16 pb-16 border-b border-border">
        <div className="max-w-3xl">
          <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-5">
            How to convert
          </p>
          <h2 className="font-serif text-3xl text-text-base mb-10 leading-snug">
            Three steps to a correctly ordered Kindle book
          </h2>
          <ol className="space-y-8">
            {howToSteps.map((step) => (
              <li key={step.number} className="grid grid-cols-1 md:grid-cols-12 gap-4 md:gap-6 items-start">
                <div className="md:col-span-1">
                  <span className="font-serif text-3xl text-brand leading-none">
                    {step.number}
                  </span>
                </div>
                <div className="md:col-span-11">
                  <h3 className="font-sans text-lg font-semibold text-text-base mb-2">
                    {step.title}
                  </h3>
                  <p className="font-sans text-base text-text-muted leading-relaxed">
                    {step.body}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* Section 5: FAQ */}
      <section className="mb-16 pb-16 border-b border-border">
        <div className="max-w-3xl">
          <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-5">
            Frequently asked
          </p>
          <h2 className="font-serif text-3xl text-text-base mb-10 leading-snug">
            Common questions about multi-column conversion
          </h2>
          <dl className="space-y-10">
            {faqItems.map((item, i) => (
              <div key={i} className="border-t border-border pt-8">
                <dt className="font-sans text-base font-semibold text-text-base mb-3">
                  {item.question}
                </dt>
                <dd className="font-sans text-base text-text-muted leading-relaxed">
                  {item.answer}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {/* Primary CTA */}
      <div className="border-t border-border pt-16 pb-8">
        <h2 className="font-serif text-3xl text-text-base mb-4 leading-snug">
          Try it on your PDF
        </h2>
        <p className="font-sans text-base text-text-muted leading-relaxed mb-8 max-w-md">
          Free tier: 3 conversions per day, up to 20 MB per file.
          No account required.
        </p>
        <div className="flex flex-wrap gap-4 items-center">
          <Link
            href="/#convert"
            className="font-sans inline-block bg-brand text-white font-medium text-base px-8 py-3 rounded-sm no-underline hover:opacity-90"
          >
            Upload your PDF
          </Link>
          <Link
            href="/quality"
            className="font-sans text-sm font-medium text-text-muted no-underline hover:text-text-base"
          >
            See quality comparison screenshots →
          </Link>
        </div>
      </div>
    </>
  );
}
