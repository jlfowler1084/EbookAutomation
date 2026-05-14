import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Convert Multi-Column PDFs to Kindle — leafbind",
  description:
    "Multi-column PDF to Kindle converter. leafbind reads each column independently " +
    "so the text flows correctly on Kindle — not interleaved across columns.",
  openGraph: {
    title: "Convert Multi-Column PDFs to Kindle — leafbind",
    description:
      "Reads each column independently. Text flows correctly on Kindle, not merged.",
    type: "website",
    url: "https://leafbind.io/convert/multi-column-pdf-kindle",
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

export default function MultiColumnPdfKindlePage() {
  return (
    <div className="font-sans bg-surface min-h-screen">
      {/* Navigation */}
      <nav className="bg-brand">
        <div className="max-w-6xl mx-auto px-8 h-14 flex items-center justify-between">
          <Link
            href="/"
            className="font-serif text-xl text-white no-underline"
          >
            leafbind
          </Link>
          <Link
            href="/"
            className="text-sm font-medium text-white no-underline border border-white/30 rounded-sm px-4 py-1.5 hover:bg-white/10"
          >
            Upload PDF →
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <header className="bg-brand pt-12 pb-16">
        <div className="max-w-6xl mx-auto px-8">
          <p className="text-accent text-sm font-medium uppercase tracking-widest mb-5">
            Multi-column PDF conversion
          </p>
          <h1 className="font-serif text-5xl leading-tight text-white mb-6 max-w-3xl">
            Convert Multi-Column PDFs to Kindle — Columns Read in the Right Order
          </h1>
          <p className="text-lg text-surface leading-relaxed max-w-xl">
            Most converters merge both columns into a single stream. leafbind reads
            each column independently, so your academic papers and journal articles
            flow exactly as written.
          </p>
          <div className="mt-8">
            <Link
              href="/"
              className="inline-block bg-accent text-white font-medium text-base px-8 py-3 rounded-sm no-underline hover:opacity-90"
            >
              Upload your PDF
            </Link>
          </div>
        </div>
      </header>

      {/* Section 1: What goes wrong with multi-column PDFs */}
      <section className="py-16 bg-white border-t border-border">
        <div className="max-w-6xl mx-auto px-8">
          <div className="grid grid-cols-1 md:grid-cols-5 gap-8 md:gap-12 items-start">
            <div className="md:col-span-3">
              <p className="text-accent text-sm font-medium uppercase tracking-widest mb-5">
                The problem
              </p>
              <h2 className="font-serif text-3xl text-brand mb-6 leading-snug">
                What goes wrong with multi-column PDFs
              </h2>
              <p className="text-base text-text-base leading-relaxed mb-4">
                When Calibre — or any converter that uses a simple left-to-right text sweep —
                processes a two-column PDF, it does not understand that the page is divided
                into independent reading lanes. It reads across the full page width at each
                vertical position, alternating between columns with every line.
              </p>
              <p className="text-base text-text-base leading-relaxed mb-4">
                The result is an interleaved stream: the first sentence of the left column,
                then the first sentence of the right column, then the second sentence of
                the left column, then the second sentence of the right column — and so on
                through the entire page. What was a coherent academic argument becomes an
                unreadable alternating muddle where every other sentence belongs to a
                completely different thread of reasoning.
              </p>
              <p className="text-base text-text-base leading-relaxed mb-4">
                Imagine reading a paragraph that begins: <em>"The epistemological framework
                proposed here — The study of immune response markers in —
                draws on three prior accounts — 47 adult subjects aged 22 to 65 —
                none of which fully address — were randomly assigned to one of —
                the problem of under-determination."</em> That is what column-merged extraction
                produces on every page of a two-column academic paper.
              </p>
              <p className="text-base text-text-base leading-relaxed">
                This is not a bug that careful Calibre configuration can fix. It is a
                fundamental limitation of text extraction that treats the page as a
                single flat stream rather than a set of spatially organized regions.
                Fixing it requires coordinate-aware extraction — which is exactly what
                leafbind uses.
              </p>
            </div>
            <div className="md:col-span-2 bg-surface border border-border rounded-md p-6">
              <p className="text-xs font-medium text-muted uppercase tracking-widest mb-3">
                The column-merge pattern
              </p>
              <div className="space-y-2 text-sm text-text-base leading-relaxed font-serif">
                <p className="text-muted line-through">Col 1 line 1: The epistemological framework...</p>
                <p className="text-muted line-through">Col 2 line 1: The study of immune markers...</p>
                <p className="text-muted line-through">Col 1 line 2: draws on three prior accounts...</p>
                <p className="text-muted line-through">Col 2 line 2: 47 adult subjects aged 22...</p>
              </div>
              <div className="mt-4 pt-4 border-t border-border space-y-2 text-sm text-text-base leading-relaxed font-serif">
                <p className="text-accent font-medium text-xs uppercase tracking-widest mb-2">
                  What you want
                </p>
                <p>Col 1 line 1: The epistemological framework...</p>
                <p>Col 1 line 2: draws on three prior accounts...</p>
                <p className="text-muted">— end of column 1 —</p>
                <p>Col 2 line 1: The study of immune markers...</p>
                <p>Col 2 line 2: 47 adult subjects aged 22...</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Section 2: How leafbind detects columns */}
      <section className="py-16 bg-surface border-t border-border">
        <div className="max-w-6xl mx-auto px-8">
          <div className="grid grid-cols-1 md:grid-cols-5 gap-8 md:gap-12 items-start">
            <div className="md:col-span-2">
              <p className="text-accent text-sm font-medium uppercase tracking-widest mb-5">
                The detection method
              </p>
              <h2 className="font-serif text-3xl text-brand mb-6 leading-snug">
                How leafbind detects columns
              </h2>
              <p className="text-base text-text-base leading-relaxed mb-4">
                The foundation is pdfplumber, a coordinate-aware PDF extraction library
                that exposes the precise bounding box — x0, y0, x1, y1 — of every text
                character and word on the page. Most extraction tools discard this spatial
                data. leafbind uses it as the primary signal for column detection.
              </p>
              <Link
                href="/quality"
                className="text-sm font-medium text-accent no-underline hover:underline"
              >
                See the column comparison screenshots →
              </Link>
            </div>
            <div className="md:col-span-3">
              <p className="text-base text-text-base leading-relaxed mb-4">
                For each page, leafbind collects the x0 (left edge) positions of all
                text runs and identifies natural gaps in that distribution. A two-column
                page has a dense cluster of x0 values near the left margin and a second
                dense cluster near the horizontal midpoint. The gap between them is the
                column gutter — the white space between columns that the eye uses to
                separate the reading lanes.
              </p>
              <p className="text-base text-text-base leading-relaxed mb-4">
                Once the column boundaries are located, leafbind assigns each text run
                to its column based on its x1 (right edge) position: runs whose right
                edge falls within the left half of the page belong to column one; runs
                whose left edge starts at or beyond the midpoint boundary belong to
                column two. For three-column layouts, the same clustering approach
                identifies two gutters and three regions.
              </p>
              <p className="text-base text-text-base leading-relaxed mb-4">
                Within each column, text runs are sorted by their y0 (vertical) position —
                top to bottom, as a reader would scan them. The result is a sequential
                stream that reads column one from top to bottom, then column two from
                top to bottom, preserving exactly the order the author intended.
              </p>
              <p className="text-base text-text-base leading-relaxed">
                The column detector runs independently on each page. A document that
                opens with a single-column abstract, transitions to a two-column body,
                and ends with single-column references is handled correctly at each
                page boundary — no manual configuration, no document splitting. The
                visual proof is on the <Link href="/quality" className="text-accent no-underline hover:underline">quality comparison page</Link>,
                where the same IEEE-style paper is shown as Calibre processes it (interleaved)
                and as leafbind processes it (correctly sequenced).
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Section 3: Document types */}
      <section className="py-16 bg-white border-t border-border">
        <div className="max-w-6xl mx-auto px-8">
          <div className="max-w-3xl">
            <p className="text-accent text-sm font-medium uppercase tracking-widest mb-5">
              Document types
            </p>
            <h2 className="font-serif text-3xl text-brand mb-6 leading-snug">
              What document types have multi-column layouts
            </h2>
            <p className="text-base text-text-base leading-relaxed mb-4">
              Multi-column layouts are the default format for a large share of academic
              and archival publishing. IEEE and ACM conference papers, journal articles
              from Nature, PLOS, and most medical publishers, newspaper archives digitized
              for historical research — all use two-column layouts that will produce
              garbled output through a naive converter.
            </p>
            <p className="text-base text-text-base leading-relaxed mb-4">
              Legal documents from certain court jurisdictions, legislative records, and
              historical texts typeset in pre-digital book production often use two- or
              three-column layouts. Older newspaper archives distributed as PDF are
              particularly prone to column interleaving when converted without coordinate
              awareness.
            </p>
            <p className="text-base text-text-base leading-relaxed">
              If you are reading academic research, digitized periodicals, or any
              publication that looks like a journal article on screen — two narrow
              columns of text side by side — leafbind is designed for exactly that
              document type. See also: <Link href="/convert/academic-pdf-to-kindle" className="text-accent no-underline hover:underline">converting academic PDFs to Kindle</Link>.
            </p>
          </div>
        </div>
      </section>

      {/* Section 4: HowTo */}
      <section className="py-16 bg-surface border-t border-border">
        <div className="max-w-6xl mx-auto px-8">
          <div className="max-w-3xl">
            <p className="text-accent text-sm font-medium uppercase tracking-widest mb-5">
              How to convert
            </p>
            <h2 className="font-serif text-3xl text-brand mb-10 leading-snug">
              Three steps to a correctly ordered Kindle book
            </h2>
            <ol className="space-y-8">
              {howToSteps.map((step) => (
                <li key={step.number} className="grid grid-cols-1 md:grid-cols-12 gap-4 md:gap-6 items-start">
                  <div className="md:col-span-1">
                    <span className="font-serif text-3xl text-accent leading-none">
                      {step.number}
                    </span>
                  </div>
                  <div className="md:col-span-11">
                    <h3 className="font-sans text-lg font-semibold text-brand mb-2">
                      {step.title}
                    </h3>
                    <p className="text-base text-text-base leading-relaxed">
                      {step.body}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
            <div className="mt-10">
              <Link
                href="/"
                className="inline-block bg-accent text-white font-medium text-base px-8 py-3 rounded-sm no-underline hover:opacity-90"
              >
                Upload your PDF now
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Section 5: FAQ */}
      <section className="py-16 bg-white border-t border-border">
        <div className="max-w-6xl mx-auto px-8">
          <div className="max-w-3xl">
            <p className="text-accent text-sm font-medium uppercase tracking-widest mb-5">
              Frequently asked
            </p>
            <h2 className="font-serif text-3xl text-brand mb-10 leading-snug">
              Common questions about multi-column conversion
            </h2>
            <dl className="space-y-10">
              {faqItems.map((item, i) => (
                <div key={i} className="border-t border-border pt-8">
                  <dt className="font-sans text-lg font-semibold text-brand mb-3">
                    {item.question}
                  </dt>
                  <dd className="text-base text-text-base leading-relaxed">
                    {item.answer}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="bg-brand py-16 border-t border-border">
        <div className="max-w-6xl mx-auto px-8">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-center">
            <div>
              <h2 className="font-serif text-3xl text-white mb-4 leading-snug">
                Try it on your PDF
              </h2>
              <p className="text-base text-surface leading-relaxed">
                Free tier: 3 conversions per day, up to 20 MB per file.
                No account required. If the column order looks wrong in
                the output, the conversion log will tell you which extraction
                path was used.
              </p>
            </div>
            <div className="flex flex-col gap-4 md:items-end">
              <Link
                href="/"
                className="inline-block bg-accent text-white font-medium text-base px-8 py-3 rounded-sm no-underline hover:opacity-90 text-center"
              >
                Upload your PDF
              </Link>
              <Link
                href="/quality"
                className="inline-block text-surface font-medium text-sm no-underline hover:text-white text-center"
              >
                See quality comparison screenshots →
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Footer cross-links */}
      <footer className="bg-surface border-t border-border py-8">
        <div className="max-w-6xl mx-auto px-8">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
            <span className="text-sm font-medium text-muted">
              Related guides:
            </span>
            <Link
              href="/quality"
              className="text-sm text-muted no-underline hover:text-text-base"
            >
              Quality comparison →
            </Link>
            <Link
              href="/convert/academic-pdf-to-kindle"
              className="text-sm text-muted no-underline hover:text-text-base"
            >
              Academic PDFs →
            </Link>
            <Link
              href="/convert/pdf-to-kfx"
              className="text-sm text-muted no-underline hover:text-text-base"
            >
              PDF to KFX →
            </Link>
            <Link
              href="/pricing"
              className="text-sm text-muted no-underline hover:text-text-base"
            >
              Pricing →
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
