import type { Metadata } from "next";
import Link from "next/link";
import JsonLd from "../../../components/JsonLd";
import { buildSoftwareApplicationSchema } from "../../../lib/structured-data";

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
    <>
      <JsonLd schema={buildSoftwareApplicationSchema()} />

      {/* Page header */}
      <div className="py-12 md:py-16 border-b border-border mb-16">
        <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-5">
          Quality comparison
        </p>
        <h1 className="font-serif text-5xl md:text-6xl leading-tight text-text-base mb-6 max-w-2xl">
          Why leafbind converts academic PDFs better than Calibre
        </h1>
        <p className="font-sans text-lg text-text-muted leading-relaxed max-w-xl">
          Three specific failure modes that break every other converter —
          each one shown with screenshots from the same source document.
        </p>
      </div>

      {/* Comparison sections */}
      <div className="space-y-16 mb-16">
        {comparisons.map((c) => (
          <section
            key={c.id}
            className="border-b border-border pb-16"
          >
            {/* 40/60 asymmetric grid: 2 cols text + 3 cols images */}
            <div className="grid grid-cols-1 md:grid-cols-5 gap-8 md:gap-12 items-start">

              {/* Left column: section label, heading, explanation */}
              <div className="md:col-span-2">
                <p className="font-mono text-text-muted text-sm font-medium mb-5 tracking-widest uppercase">
                  {c.number}
                </p>
                <h2 className="font-serif text-2xl text-text-base mb-4 leading-snug">
                  {c.heading}
                </h2>
                <p className="font-sans text-base text-text-base leading-relaxed mb-3">
                  <span className="font-medium">The problem. </span>
                  {c.problem}
                </p>
                <p className="font-sans text-base text-text-base leading-relaxed mb-8">
                  <span className="font-medium text-brand">The fix. </span>
                  {c.solution}
                </p>
                <Link
                  href={c.learnMoreHref}
                  className="font-sans text-sm font-medium text-brand no-underline hover:underline"
                >
                  {c.learnMoreLabel}
                </Link>
              </div>

              {/* Right column: 2-up side-by-side comparison images */}
              <div className="md:col-span-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <p className="font-mono text-xs font-medium text-text-muted uppercase tracking-widest mb-2">
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
                    <p className="font-mono text-xs font-medium text-brand uppercase tracking-widest mb-2">
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
          </section>
        ))}
      </div>

      {/* Primary CTA */}
      <div className="border-t border-border pt-16 pb-8">
        <h2 className="font-serif text-3xl text-text-base mb-4 leading-snug">
          See how your PDF converts
        </h2>
        <p className="font-sans text-base text-text-muted leading-relaxed mb-8 max-w-md">
          Free tier: 3 conversions per day, up to 20 MB per file.
          No account required.
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
