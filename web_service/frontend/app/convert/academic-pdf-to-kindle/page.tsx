import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Convert Academic PDFs to Kindle — leafbind",
  description:
    "Academic PDF to Kindle converter that preserves double-column layouts, " +
    "footnotes, section numbering, and figure captions. Free and premium tiers.",
  openGraph: {
    title: "Convert Academic PDFs to Kindle — leafbind",
    description: "Preserves double-column layouts, footnotes, and section numbering.",
    type: "website",
    url: "https://leafbind.io/convert/academic-pdf-to-kindle",
  },
  twitter: {
    card: "summary",
    title: "Convert Academic PDFs to Kindle — leafbind",
    description: "Academic PDF to Kindle: columns, footnotes, and numbering preserved.",
  },
};

const howToSteps = [
  {
    number: "01",
    title: "Upload your academic PDF",
    body: "Drop your paper, thesis, or textbook on the leafbind upload page. Files up to 20 MB are accepted on the free tier; premium accounts accept up to 100 MB.",
  },
  {
    number: "02",
    title: "Let the pipeline analyse the layout",
    body: "leafbind automatically detects column boundaries, identifies section numbering patterns, matches footnote markers to footnote bodies, and classifies figure captions. No configuration needed.",
  },
  {
    number: "03",
    title: "Download and send to Kindle",
    body: "Your converted file is ready within seconds. Download the EPUB or KFX file and send it to your Kindle via USB, email, or the Send to Kindle app.",
  },
];

const faqItems = [
  {
    q: "Does it work on scanned academic PDFs?",
    a: "Partially. leafbind includes an OCR fallback for scanned pages, but complex mathematical notation, chemical structures, and hand-drawn diagrams are not fully reconstructed in the current version. For text-based PDFs — the vast majority of digital-born academic papers from IEEE, ACM, arXiv, and university repositories — the pipeline handles them reliably.",
  },
  {
    q: "Will chapter and section numbers survive? What about headings like 1.1 or 2.3.4?",
    a: "Yes. The pipeline detects numbered headings by their visual prominence and position. Whether your paper uses a flat Section 1 / Section 2 pattern or a hierarchical 1.1, 1.2.3 numbering scheme, the headings are tagged as h2 and h3 in the output. On Kindle, they appear in the chapter navigation menu so you can jump directly to any section.",
  },
  {
    q: "What about inline citations like [1] or (Author, 2022)?",
    a: "Inline citations are preserved as body text. They are not stripped, reordered, or linked (linking citations to a bibliography is outside the scope of v1). The citation markers appear exactly where they appear in the original PDF — so if your PDF reads \"…as shown in prior work [14, 15]…\" your Kindle will read the same thing.",
  },
  {
    q: "Is there a file size limit?",
    a: "The free tier accepts PDFs up to 20 MB, which covers most individual research papers and many textbooks. The premium tier raises the limit to 100 MB, which handles large textbooks and multi-chapter dissertations. If your file exceeds 100 MB, consider splitting it by chapter using a PDF editor before uploading.",
  },
];

export default function AcademicPdfToKindlePage() {
  return (
    <div className="font-sans bg-surface min-h-screen">

      {/* Navigation */}
      <nav className="bg-brand">
        <div className="max-w-5xl mx-auto px-8 h-14 flex items-center justify-between">
          <Link href="/" className="font-serif text-xl text-white no-underline">
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
        <div className="max-w-5xl mx-auto px-8">
          <p className="text-accent text-sm font-medium uppercase tracking-widest mb-5">
            Academic PDF conversion
          </p>
          <h1 className="font-serif text-4xl leading-tight text-white mb-6 max-w-2xl">
            Convert Academic PDFs to Kindle — Columns, Footnotes, and Headings Preserved
          </h1>
          <p className="text-lg text-surface leading-relaxed max-w-2xl mb-8">
            IEEE papers, arXiv preprints, ACM proceedings, and graduate theses come with
            layout complexity that generic converters cannot handle. leafbind reads each
            column in order, links footnotes, and maps numbered section headings to a
            navigable chapter list.
          </p>
          <Link
            href="/"
            className="inline-block bg-accent text-white font-medium text-base px-8 py-3 rounded-sm no-underline hover:opacity-90"
          >
            Upload your PDF — free
          </Link>
        </div>
      </header>

      {/* Section 1: The academic PDF problem */}
      <section className="py-16 border-t border-border bg-white">
        <div className="max-w-5xl mx-auto px-8">
          <div className="max-w-3xl">
            <p className="text-accent text-sm font-medium uppercase tracking-widest mb-4">
              The problem
            </p>
            <h2 className="font-serif text-3xl text-brand mb-6 leading-snug">
              Why academic PDFs break every other converter
            </h2>
            <div className="space-y-4 text-text-base leading-relaxed">
              <p>
                Academic publishing uses a set of layout conventions that made sense for
                print but are structurally hostile to ebook conversion. The double-column
                format used by IEEE, ACM, and most major journals splits a single flow of
                text across two vertical columns on each page. Most converters read text
                left-to-right across the full page width — which interleaves both columns
                line by line into unreadable output.
              </p>
              <p>
                Section numbering is another obstacle. Academic papers use hierarchical
                numbered headings — 1, 1.1, 1.2, 2, 2.1, 2.2.1 — that Calibre and most
                generic EPUB converters cannot reliably distinguish from numbered list items
                or figure labels. The result is a document with no navigable structure and
                a blank table of contents.
              </p>
              <p>
                Footnotes compound the problem. Journal-style footnotes sit at the physical
                foot of the page — a position that loses all meaning when page boundaries
                disappear in reflow. Most converters either strip footnotes entirely or dump
                them in a disconnected block at the document end, with no link back to the
                in-text citation. For papers that rely heavily on footnotes — legal scholarship,
                philosophy, history of science — this makes the converted document nearly
                unusable. Inline citations in the form <code className="font-mono text-sm bg-surface px-1 rounded-sm">[1]</code>,{" "}
                <code className="font-mono text-sm bg-surface px-1 rounded-sm">[14, 15]</code>, or{" "}
                <code className="font-mono text-sm bg-surface px-1 rounded-sm">(Author, 2022)</code> survive
                only if the converter treats them as ordinary text and does not strip
                superscript runs. Figure captions face a similar fate — images and their
                captions are often separated during extraction, leaving orphaned figures
                with no explanation.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Section 2: What the pipeline preserves */}
      <section className="py-16 border-t border-border bg-surface">
        <div className="max-w-5xl mx-auto px-8">
          <div className="grid grid-cols-1 md:grid-cols-5 gap-8 md:gap-12 items-start">
            <div className="md:col-span-2">
              <p className="text-accent text-sm font-medium uppercase tracking-widest mb-4">
                The fix
              </p>
              <h2 className="font-serif text-3xl text-brand mb-6 leading-snug">
                What the leafbind pipeline preserves
              </h2>
              <p className="text-text-base leading-relaxed mb-6">
                leafbind is built around four pipeline capabilities that address exactly
                these failure modes. See side-by-side screenshots from the same source
                document on the{" "}
                <Link
                  href="/quality"
                  className="text-accent no-underline hover:underline font-medium"
                >
                  quality comparison page
                </Link>
                .
              </p>
            </div>
            <div className="md:col-span-3 space-y-6">
              <div className="bg-white border border-border rounded-md p-6 shadow-sm">
                <h3 className="font-serif text-xl text-brand mb-2">
                  Column-aware text extraction
                </h3>
                <p className="text-text-base leading-relaxed text-sm">
                  The pipeline uses coordinate-based analysis to identify column
                  boundaries from the PDF's internal geometry. Each column is read
                  sequentially from top to bottom before moving to the next. For
                  double-column IEEE and ACM papers, this means the left column is
                  fully extracted before the right column begins — exactly the reading
                  order the author intended.
                </p>
              </div>
              <div className="bg-white border border-border rounded-md p-6 shadow-sm">
                <h3 className="font-serif text-xl text-brand mb-2">
                  Numbered section heading detection
                </h3>
                <p className="text-text-base leading-relaxed text-sm">
                  Section headings in academic PDFs are visually distinct — larger font,
                  bold weight, often followed by a section number. The pipeline classifies
                  text runs by rendered font size and weight, identifies heading candidates
                  by visual prominence, and tags them as h2 and h3. Both flat-numbered
                  sections (Section 1, Section 2) and hierarchical schemes (1.1, 2.3.4)
                  are supported. The result is a structured Kindle book with a working
                  chapter navigation menu.
                </p>
              </div>
              <div className="bg-white border border-border rounded-md p-6 shadow-sm">
                <h3 className="font-serif text-xl text-brand mb-2">
                  Footnote detection and linking
                </h3>
                <p className="text-text-base leading-relaxed text-sm">
                  The pipeline detects superscript footnote markers in body text, matches
                  each to its corresponding footnote body at the page foot, and generates
                  linked pairs in the EPUB or KFX output. On Kindle Paperwhite and Scribe,
                  tapping a footnote number jumps to the note text. A return link brings
                  you back to your reading position.
                </p>
              </div>
              <div className="bg-white border border-border rounded-md p-6 shadow-sm">
                <h3 className="font-serif text-xl text-brand mb-2">
                  Inline citations and figure captions preserved
                </h3>
                <p className="text-text-base leading-relaxed text-sm">
                  Inline citation markers — whether numeric{" "}
                  <code className="font-mono text-xs bg-surface px-1 rounded-sm">[1]</code>,
                  author-year <code className="font-mono text-xs bg-surface px-1 rounded-sm">(Smith, 2019)</code>,
                  or symbol-based — are retained as body text and not stripped. Figure
                  captions are associated with their adjacent images during extraction,
                  preserving the figure-caption relationship in the converted output.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Section 3: Supported document types */}
      <section className="py-16 border-t border-border bg-white">
        <div className="max-w-5xl mx-auto px-8">
          <div className="max-w-3xl">
            <p className="text-accent text-sm font-medium uppercase tracking-widest mb-4">
              Compatibility
            </p>
            <h2 className="font-serif text-3xl text-brand mb-6 leading-snug">
              Supported document types
            </h2>
            <p className="text-text-base leading-relaxed mb-6">
              The pipeline is calibrated for digital-born PDFs produced by academic
              publishing tools. The following document types work reliably:
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-8">
              {[
                "IEEE conference and journal papers",
                "arXiv preprints (PDF format)",
                "ACM Digital Library proceedings",
                "University theses and dissertations",
                "Technical textbooks and monographs",
                "Medical and scientific journal articles",
                "Legal scholarship with footnote-heavy text",
                "Government and policy research reports",
              ].map((item) => (
                <div
                  key={item}
                  className="flex items-start gap-3 bg-surface border border-border rounded-sm px-4 py-3"
                >
                  <span className="text-accent font-bold text-base leading-none mt-0.5">✓</span>
                  <span className="text-text-base text-sm leading-relaxed">{item}</span>
                </div>
              ))}
            </div>
            <div className="bg-surface border border-border rounded-md p-5">
              <p className="text-sm font-medium text-brand mb-2">
                Outside current scope:
              </p>
              <p className="text-sm text-text-base leading-relaxed">
                Scanned PDFs (image-only pages without selectable text) are partially
                supported via an OCR fallback, but complex mathematical equations and
                chemical structure diagrams are not fully reconstructed in v1. If your
                paper is heavily equation-dense — e.g., pure mathematics or physics —
                the body text will convert correctly, but inline equations may render
                as plain text substitutes rather than properly formatted notation.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Section 4: HowTo */}
      <section className="py-16 border-t border-border bg-surface">
        <div className="max-w-5xl mx-auto px-8">
          <div className="max-w-3xl">
            <p className="text-accent text-sm font-medium uppercase tracking-widest mb-4">
              How to convert
            </p>
            <h2 className="font-serif text-3xl text-brand mb-8 leading-snug">
              Three steps to a readable academic library
            </h2>
            <div className="space-y-6">
              {howToSteps.map((step) => (
                <div key={step.number} className="flex gap-6 items-start">
                  <div className="flex-shrink-0 w-12 h-12 bg-brand rounded-sm flex items-center justify-center">
                    <span className="font-serif text-lg text-white font-bold leading-none">
                      {step.number}
                    </span>
                  </div>
                  <div>
                    <h3 className="font-sans font-semibold text-brand text-base mb-1">
                      {step.title}
                    </h3>
                    <p className="text-text-base text-sm leading-relaxed">
                      {step.body}
                    </p>
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-10">
              <Link
                href="/"
                className="inline-block bg-accent text-white font-medium text-base px-8 py-3 rounded-sm no-underline hover:opacity-90"
              >
                Start converting — free
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Section 5: FAQ */}
      <section className="py-16 border-t border-border bg-white">
        <div className="max-w-5xl mx-auto px-8">
          <div className="max-w-3xl">
            <p className="text-accent text-sm font-medium uppercase tracking-widest mb-4">
              FAQ
            </p>
            <h2 className="font-serif text-3xl text-brand mb-8 leading-snug">
              Common questions
            </h2>
            <div className="space-y-6">
              {faqItems.map((item) => (
                <div
                  key={item.q}
                  className="border-t border-border pt-6"
                >
                  <h3 className="font-sans font-semibold text-brand text-base mb-3">
                    {item.q}
                  </h3>
                  <p className="text-text-base text-sm leading-relaxed">
                    {item.a}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Cross-links footer */}
      <section className="bg-brand py-16 border-t border-border">
        <div className="max-w-5xl mx-auto px-8">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div>
              <h3 className="font-serif text-xl text-white mb-3 leading-snug">
                See quality proof
              </h3>
              <p className="text-sm text-surface leading-relaxed mb-4">
                Side-by-side screenshots showing exactly what Calibre gets wrong and
                what leafbind preserves — same source document, both outputs.
              </p>
              <Link
                href="/quality"
                className="text-sm font-medium text-accent no-underline hover:underline"
              >
                View quality comparison →
              </Link>
            </div>
            <div>
              <h3 className="font-serif text-xl text-white mb-3 leading-snug">
                PDF to KFX conversion
              </h3>
              <p className="text-sm text-surface leading-relaxed mb-4">
                KFX is the native Kindle format — richer typography, better reflow, and
                correct rendering of the chapter navigation you just built.
              </p>
              <Link
                href="/convert/pdf-to-kfx"
                className="text-sm font-medium text-accent no-underline hover:underline"
              >
                PDF to KFX guide →
              </Link>
            </div>
            <div>
              <h3 className="font-serif text-xl text-white mb-3 leading-snug">
                Footnote preservation
              </h3>
              <p className="text-sm text-surface leading-relaxed mb-4">
                Every detail about how footnote markers are detected, matched, and linked
                in the Kindle output — with examples from heavily footnoted academic texts.
              </p>
              <Link
                href="/convert/pdf-footnotes-kindle"
                className="text-sm font-medium text-accent no-underline hover:underline"
              >
                Footnote conversion guide →
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-surface border-t border-border py-8">
        <div className="max-w-5xl mx-auto px-8 flex flex-wrap items-center justify-between gap-4">
          <Link href="/" className="font-serif text-lg text-brand no-underline">
            leafbind
          </Link>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
            <Link href="/" className="text-sm text-muted no-underline hover:text-text-base">
              Convert
            </Link>
            <Link href="/pricing" className="text-sm text-muted no-underline hover:text-text-base">
              Pricing
            </Link>
            <Link href="/quality" className="text-sm text-muted no-underline hover:text-text-base">
              Quality
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
