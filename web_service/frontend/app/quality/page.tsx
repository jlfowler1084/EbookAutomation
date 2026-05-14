import type { Metadata } from "next";
import Link from "next/link";
import JsonLd from "../../components/JsonLd";
import { buildSoftwareApplicationSchema } from "../../lib/structured-data";

export const metadata: Metadata = {
  title: "PDF to Kindle Quality Comparison — leafbind",
  description:
    "See how leafbind converts multi-column layouts, footnotes, and academic heading " +
    "structures that Calibre gets wrong. Side-by-side before/after screenshots.",
  openGraph: {
    title: "PDF to Kindle Quality Comparison — leafbind",
    description:
      "Side-by-side comparison: Calibre vs. leafbind on multi-column academic PDFs.",
    images: [
      {
        url: "https://leafbind.io/quality/pipeline-columns.png",
        width: 800,
        height: 600,
      },
    ],
    type: "website",
    url: "https://leafbind.io/quality",
  },
  twitter: {
    card: "summary_large_image",
    title: "PDF to Kindle Quality Comparison — leafbind",
    description:
      "Side-by-side comparison: Calibre vs. leafbind on multi-column academic PDFs.",
    images: ["https://leafbind.io/quality/pipeline-columns.png"],
  },
};

const comparisons = [
  {
    id: "columns",
    number: "01",
    heading: "Multi-column layouts",
    problem:
      "Most converters read text left-to-right across the full page width, interleaving both columns line by line. A sentence from the left column is immediately followed by a sentence from the right column — the result is unreadable.",
    solution:
      "leafbind uses coordinate-based extraction to identify column boundaries, then reads each column sequentially. The text flows exactly as the author intended.",
    calibre: {
      src: "/quality/calibre-columns.png",
      alt: "Calibre output showing garbled two-column text — both columns merged into a single run-on stream, interleaved line by line, making the academic paper unreadable",
    },
    pipeline: {
      src: "/quality/pipeline-columns.png",
      alt: "leafbind output of the same two-column academic paper — columns correctly separated and flowing in proper reading order on Kindle",
    },
    learnMoreHref: "/convert/multi-column-pdf-kindle",
    learnMoreLabel: "Multi-column PDF conversion →",
  },
  {
    id: "footnotes",
    number: "02",
    heading: "Footnotes and backreferences",
    problem:
      "Footnotes are positional in PDF — they sit at the bottom of a physical page. When the page model disappears in a reflow format, most converters strip footnote content or dump it at the document end with no link back to the citation.",
    solution:
      "leafbind detects footnote markers, matches each to its footnote body, and generates linked pairs in the output. On Kindle, tapping a superscript jumps to the note; tapping the reference returns you to the reading position.",
    calibre: {
      src: "/quality/calibre-footnotes.png",
      alt: "Calibre EPUB output where footnote markers appear in body text but footnote content is disconnected — no navigation between citation and note",
    },
    pipeline: {
      src: "/quality/pipeline-footnotes.png",
      alt: "leafbind output with linked footnotes — each superscript number is a tappable link to the footnote text, with a return link back to the citation",
    },
    learnMoreHref: "/convert/pdf-footnotes-kindle",
    learnMoreLabel: "PDF footnote conversion →",
  },
  {
    id: "headings",
    number: "03",
    heading: "Section headings and structure",
    problem:
      "PDF has no semantic structure — only coordinates and font sizes. Calibre cannot reliably distinguish a heading from large-font body text, so sections become plain paragraphs with no table of contents and no Kindle chapter navigation.",
    solution:
      "leafbind classifies text by rendered font size and weight, identifies heading candidates by visual prominence, and tags them as h2 and h3 in the output. The result is a structured book with a navigable chapter list.",
    calibre: {
      src: "/quality/calibre-headings.png",
      alt: "Calibre output where section headings render as plain body text — no formatting hierarchy, no table of contents, and no Kindle chapter navigation",
    },
    pipeline: {
      src: "/quality/pipeline-headings.png",
      alt: "leafbind output with headings correctly tagged as h2 and h3 — the Kindle table of contents shows every chapter and section with working navigation",
    },
    learnMoreHref: "/convert/academic-pdf-to-kindle",
    learnMoreLabel: "Academic PDF conversion →",
  },
];

export default function QualityPage() {
  return (
    <div className="font-sans bg-surface min-h-screen">
      <JsonLd schema={buildSoftwareApplicationSchema()} />
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
            Quality comparison
          </p>
          <h1 className="font-serif text-5xl leading-tight text-white mb-6 max-w-2xl">
            Why leafbind converts academic PDFs better than Calibre
          </h1>
          <p className="text-lg text-surface leading-relaxed max-w-xl">
            Three specific failure modes that break every other converter —
            each one shown with screenshots from the same source document.
          </p>
        </div>
      </header>

      {/* Comparison sections */}
      {comparisons.map((c, i) => (
        <section
          key={c.id}
          className={`py-16 border-t border-border ${
            i % 2 === 0 ? "bg-surface" : "bg-white"
          }`}
        >
          <div className="max-w-6xl mx-auto px-8">
            {/* 40/60 asymmetric grid: 2 cols text + 3 cols images */}
            <div className="grid grid-cols-1 md:grid-cols-5 gap-8 md:gap-12 items-start">

              {/* Left column: section label, heading, explanation */}
              <div className="md:col-span-2">
                <p className="text-accent text-sm font-medium mb-5 tracking-widest">
                  {c.number}
                </p>
                <h2 className="font-serif text-2xl text-brand mb-4 leading-snug">
                  {c.heading}
                </h2>
                <p className="text-base text-text-base leading-relaxed mb-3">
                  <span className="font-medium text-brand">The problem. </span>
                  {c.problem}
                </p>
                <p className="text-base text-text-base leading-relaxed mb-8">
                  <span className="font-medium text-accent">The fix. </span>
                  {c.solution}
                </p>
                <Link
                  href={c.learnMoreHref}
                  className="text-sm font-medium text-accent no-underline hover:underline"
                >
                  {c.learnMoreLabel}
                </Link>
              </div>

              {/* Right column: 2-up side-by-side comparison images */}
              <div className="md:col-span-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <p className="text-xs font-medium text-muted uppercase tracking-widest mb-2">
                      Calibre raw
                    </p>
                    <img
                      src={c.calibre.src}
                      alt={c.calibre.alt}
                      width={800}
                      height={600}
                      className="rounded-sm shadow-md border border-border"
                      style={{ width: "100%", height: "auto", display: "block" }}
                    />
                  </div>
                  <div>
                    <p className="text-xs font-medium text-accent uppercase tracking-widest mb-2">
                      leafbind
                    </p>
                    <img
                      src={c.pipeline.src}
                      alt={c.pipeline.alt}
                      width={800}
                      height={600}
                      className="rounded-sm shadow-md border border-border"
                      style={{ width: "100%", height: "auto", display: "block" }}
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      ))}

      {/* CTA */}
      <section className="bg-brand py-16 border-t border-border">
        <div className="max-w-6xl mx-auto px-8">
          <div className="max-w-lg">
            <h2 className="font-serif text-3xl text-white mb-4 leading-snug">
              See how your PDF converts
            </h2>
            <p className="text-base text-surface leading-relaxed mb-8">
              Free tier: 3 conversions per day, up to 20 MB per file.
              No account required.
            </p>
            <Link
              href="/"
              className="inline-block bg-accent text-white font-medium text-base px-8 py-3 rounded-sm no-underline hover:opacity-90"
            >
              Upload your PDF
            </Link>
          </div>
        </div>
      </section>

      {/* Footer cross-links */}
      <footer className="bg-surface border-t border-border py-8">
        <div className="max-w-6xl mx-auto px-8">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
            <span className="text-sm font-medium text-muted">
              Conversion guides:
            </span>
            <Link
              href="/convert/academic-pdf-to-kindle"
              className="text-sm text-muted no-underline hover:text-text-base"
            >
              Academic PDFs →
            </Link>
            <Link
              href="/convert/pdf-footnotes-kindle"
              className="text-sm text-muted no-underline hover:text-text-base"
            >
              Footnoted PDFs →
            </Link>
            <Link
              href="/convert/multi-column-pdf-kindle"
              className="text-sm text-muted no-underline hover:text-text-base"
            >
              Multi-column PDFs →
            </Link>
            <Link
              href="/convert/pdf-to-kfx"
              className="text-sm text-muted no-underline hover:text-text-base"
            >
              PDF to KFX →
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
