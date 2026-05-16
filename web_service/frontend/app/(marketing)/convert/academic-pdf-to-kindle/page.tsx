import type { Metadata } from "next";
import Link from "next/link";
import JsonLd from "../../../../components/JsonLd";
import {
  buildSoftwareApplicationSchema,
  type FAQPageSchema,
  type HowToSchema,
} from "../../../../lib/structured-data";

export const metadata: Metadata = {
  title: "Convert Academic PDFs to Kindle — leafbind",
  description:
    "Academic PDF to Kindle converter that preserves double-column layouts, " +
    "footnotes, section numbering, and figure captions. Free and premium tiers.",
  alternates: { canonical: "/convert/academic-pdf-to-kindle" },
  openGraph: {
    title: "Convert Academic PDFs to Kindle — leafbind",
    description: "Preserves double-column layouts, footnotes, and section numbering.",
    type: "website",
    url: "https://leafbind.io/convert/academic-pdf-to-kindle",
    images: [{ url: "https://leafbind.io/quality/pipeline-columns.png", width: 800, height: 600 }],
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
    a: "Not in the current production pipeline. leafbind's roadmap includes an OCR pass via Gemini for scanned/image pages, but it is not yet active in the live converter. For text-based PDFs — the vast majority of digital-born academic papers from IEEE, ACM, arXiv, and university repositories — the pipeline handles them reliably today.",
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
  name: "Three steps to a readable academic library",
  step: howToSteps.map((step) => ({
    "@type": "HowToStep",
    name: step.title,
    text: step.body,
  })),
};

export default function AcademicPdfToKindlePage() {
  return (
    <>
      <JsonLd schema={buildSoftwareApplicationSchema()} />
      <JsonLd schema={faqSchema} />
      <JsonLd schema={howToSchema} />

      {/* Page header */}
      <div className="py-12 md:py-16 border-b border-border mb-16">
        <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-5">
          Academic PDF conversion
        </p>
        <h1 className="font-serif text-3xl sm:text-4xl md:text-5xl lg:text-6xl leading-tight text-text-base mb-6 max-w-2xl">
          Convert Academic PDFs to Kindle — Columns, Footnotes, and Headings Preserved
        </h1>
        <p className="font-sans text-lg text-text-muted leading-relaxed max-w-2xl mb-8">
          IEEE papers, arXiv preprints, ACM proceedings, and graduate theses come with
          layout complexity that generic converters cannot handle. leafbind reads each
          column in order, links footnotes, and maps numbered section headings to a
          navigable chapter list.
        </p>
        <Link
          href="/"
          className="font-sans inline-block bg-brand text-white font-medium text-base px-8 py-3 rounded-sm no-underline hover:opacity-90"
        >
          Upload your PDF — free
        </Link>
      </div>

      {/* Section 1: The academic PDF problem */}
      <section className="mb-16 pb-16 border-b border-border">
        <div className="max-w-3xl">
            <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-4">
              The problem
            </p>
            <h2 className="font-serif text-3xl text-text-base mb-6 leading-snug">
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
      </section>

      {/* Section 2: What the pipeline preserves */}
      <section className="mb-16 pb-16 border-b border-border">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-8 md:gap-12 items-start">
          <div className="md:col-span-2">
            <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-4">
              The fix
            </p>
            <h2 className="font-serif text-3xl text-text-base mb-6 leading-snug">
              What the leafbind pipeline preserves
            </h2>
            <p className="font-sans text-text-base leading-relaxed mb-6">
              leafbind is built around four pipeline capabilities that address exactly
              these failure modes. See side-by-side screenshots from the same source
              document on the{" "}
              <Link
                href="/quality"
                className="text-brand no-underline hover:underline font-medium"
              >
                quality comparison page
              </Link>
              .
            </p>
          </div>
          <div className="md:col-span-3 space-y-6">
            <div className="border border-border rounded-md p-6 bg-white shadow-sm">
              <h3 className="font-serif text-xl text-text-base mb-2">
                Column-aware text extraction
              </h3>
              <p className="font-sans text-text-base leading-relaxed text-sm">
                The pipeline uses coordinate-based analysis to identify column
                boundaries from the PDF's internal geometry. Each column is read
                sequentially from top to bottom before moving to the next. For
                double-column IEEE and ACM papers, this means the left column is
                fully extracted before the right column begins — exactly the reading
                order the author intended.
              </p>
            </div>
            <div className="border border-border rounded-md p-6 bg-white shadow-sm">
              <h3 className="font-serif text-xl text-text-base mb-2">
                Numbered section heading detection
              </h3>
              <p className="font-sans text-text-base leading-relaxed text-sm">
                Section headings in academic PDFs are visually distinct — larger font,
                bold weight, often followed by a section number. The pipeline classifies
                text runs by rendered font size and weight, identifies heading candidates
                by visual prominence, and tags them as h2 and h3. Both flat-numbered
                sections (Section 1, Section 2) and hierarchical schemes (1.1, 2.3.4)
                are supported. The result is a structured Kindle book with a working
                chapter navigation menu.
              </p>
            </div>
            <div className="border border-border rounded-md p-6 bg-white shadow-sm">
              <h3 className="font-serif text-xl text-text-base mb-2">
                Footnote detection and linking
              </h3>
              <p className="font-sans text-text-base leading-relaxed text-sm">
                The pipeline detects superscript footnote markers in body text, matches
                each to its corresponding footnote body at the page foot, and generates
                linked pairs in the EPUB or KFX output. On Kindle Paperwhite and Scribe,
                tapping a footnote number jumps to the note text. A return link brings
                you back to your reading position.
              </p>
            </div>
            <div className="border border-border rounded-md p-6 bg-white shadow-sm">
              <h3 className="font-serif text-xl text-text-base mb-2">
                Inline citations and figure captions preserved
              </h3>
              <p className="font-sans text-text-base leading-relaxed text-sm">
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
      </section>

      {/* Section 3: Supported document types */}
      <section className="mb-16 pb-16 border-b border-border">
        <div className="max-w-3xl">
          <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-4">
            Compatibility
          </p>
          <h2 className="font-serif text-3xl text-text-base mb-6 leading-snug">
            Supported document types
          </h2>
          <p className="font-sans text-text-base leading-relaxed mb-6">
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
                <span className="font-sans text-brand font-bold text-base leading-none mt-0.5">✓</span>
                <span className="font-sans text-text-base text-sm leading-relaxed">{item}</span>
              </div>
            ))}
          </div>
          <div className="bg-surface border border-border rounded-md p-5">
            <p className="font-sans text-sm font-medium text-text-base mb-2">
              Outside current scope:
            </p>
            <p className="font-sans text-sm text-text-muted leading-relaxed">
              Scanned PDFs (image-only pages without selectable text) are not yet
              supported in production — an OCR pass for scanned content is on the
              roadmap. For digital-born academic PDFs, the pipeline handles the
              body text well; inline mathematical equations may render as plain
              text substitutes rather than properly formatted notation, and chemical
              structures and hand-drawn diagrams are not reconstructed.
            </p>
          </div>
        </div>
      </section>

      {/* Section 3b: Per-source notes — IEEE / arXiv / journal article */}
      <section className="mb-16 pb-16 border-b border-border">
        <div className="max-w-3xl">
          <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-4">
            Source notes
          </p>
          <h2 className="font-serif text-3xl text-text-base mb-6 leading-snug">
            Tuned for IEEE, arXiv, and academic journal articles
          </h2>
          <div className="font-sans space-y-4 text-base text-text-base leading-relaxed">
            <p>
              <strong>IEEE conference and journal papers</strong> use a strict two-column
              layout with numbered section headings (I, II, III), and reference lists
              numbered in citation order. The pipeline detects the column boundary from
              coordinate clusters, reads each column top-to-bottom in sequence, and
              preserves the numbered hierarchy as Kindle chapter entries. Footnote-style
              references resolve to popup links on a Kindle Scribe.
            </p>
            <p>
              <strong>arXiv preprints</strong> ship as text-based PDFs generated from
              LaTeX, which gives the extraction layer high-quality coordinate data and
              clean glyph mapping. Equations rendered as inline text typically survive
              conversion as plain-text substitutes; equations rendered as vector graphics
              are preserved as inline images. Bibliography sections and cross-references
              are linked when the source PDF includes the underlying anchors.
            </p>
            <p>
              <strong>Journal articles from publishers like Nature, PLOS, ACM, and
              medical journals</strong> follow similar two-column patterns to IEEE but
              with publisher-specific heading styles. The font-size histogram approach
              picks up section headings regardless of font choice, so the pipeline
              handles a wide range of journal templates without per-publisher tuning.
              For the academic reader on a Kindle Scribe, the output reads like a
              published book — with chapter navigation, font-size control, and tappable
              footnote popups.
            </p>
          </div>
        </div>
      </section>

      {/* Section 4: HowTo */}
      <section className="mb-16 pb-16 border-b border-border">
        <div className="max-w-3xl">
          <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-4">
            How to convert
          </p>
          <h2 className="font-serif text-3xl text-text-base mb-8 leading-snug">
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
                  <h3 className="font-sans font-semibold text-text-base text-base mb-1">
                    {step.title}
                  </h3>
                  <p className="font-sans text-text-muted text-sm leading-relaxed">
                    {step.body}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Section 5: FAQ */}
      <section className="mb-16 pb-16 border-b border-border">
        <div className="max-w-3xl">
          <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-4">
            FAQ
          </p>
          <h2 className="font-serif text-3xl text-text-base mb-8 leading-snug">
            Common questions
          </h2>
          <div className="space-y-6">
            {faqItems.map((item) => (
              <div
                key={item.q}
                className="border-t border-border pt-6"
              >
                <h3 className="font-sans font-semibold text-text-base text-base mb-3">
                  {item.q}
                </h3>
                <p className="font-sans text-text-muted text-sm leading-relaxed">
                  {item.a}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Primary CTA */}
      <div className="border-t border-border pt-16 pb-8">
        <h2 className="font-serif text-3xl text-text-base mb-4 leading-snug">
          Start converting — free
        </h2>
        <p className="font-sans text-base text-text-muted leading-relaxed mb-8 max-w-md">
          Free tier: 3 conversions per day, up to 20 MB per file.
          No account required.
        </p>
        <Link
          href="/"
          className="font-sans inline-block bg-brand text-white font-medium text-base px-8 py-3 rounded-sm no-underline hover:opacity-90"
        >
          Upload your PDF — free
        </Link>
      </div>
    </>
  );
}
