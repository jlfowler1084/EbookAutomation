import type { Metadata } from "next";
import Link from "next/link";
import JsonLd from "../../../components/JsonLd";
import { buildItemListSchema } from "../../../lib/structured-data";

const CANONICAL = "https://leafbind.io/guides";

export const metadata: Metadata = {
  title: "Kindle & PDF Guides — leafbind",
  description:
    "Step-by-step guides for sending PDFs to Kindle, fixing Send-to-Kindle problems, " +
    "converting to KFX, and choosing the right e-reader for PDF-heavy workflows.",
  alternates: {
    canonical: CANONICAL,
  },
  openGraph: {
    title: "Kindle & PDF Guides — leafbind",
    description:
      "Practical guides for Kindle PDF conversion: fix Send-to-Kindle failures, " +
      "convert multi-column PDFs to KFX, compare Kindle Scribe vs. reMarkable, and more.",
    type: "website",
    url: CANONICAL,
  },
};

const guides = [
  {
    slug: "send-to-kindle-not-working",
    title: "Send to Kindle not working: 7 fixes and a backup that always works",
    summary:
      "Troubleshooting guide for all common Send-to-Kindle failures — approved sender list, " +
      "file size limits, unsupported formats, delivery delays, and a KFX sideload fallback.",
    lastUpdated: "2026-05-17",
  },
  {
    slug: "how-to-send-pdf-to-kindle",
    title: "How to send PDFs (and EPUBs, Docs, MOBI) to Kindle: every method",
    summary:
      "All four methods for sending files to any Kindle device — Send-to-Kindle email, " +
      "the mobile app, USB cable, and converting to KFX for sideloading.",
    lastUpdated: "2026-05-17",
  },
  {
    slug: "kindle-scribe-vs-remarkable",
    title: "Kindle Scribe vs. reMarkable vs. iPad vs. Paperwhite: which is best for reading PDFs?",
    summary:
      "Use-case-first comparison of four e-reading devices for PDF-heavy workflows — " +
      "academic papers, annotations, general reading, and multi-column documents.",
    lastUpdated: "2026-05-17",
  },
  {
    slug: "pdf-to-kfx-for-kindle-scribe",
    title: "How to convert PDFs to KFX for Kindle Scribe",
    summary:
      "Covers Send-to-Kindle's specific failure modes (column collapse, footnote loss, flat headings), " +
      "Calibre's documented limits, and where a web-based converter helps.",
    lastUpdated: "2026-05-15",
  },
];

const itemListSchema = buildItemListSchema({
  name: "Kindle & PDF Guides — leafbind",
  description:
    "Step-by-step guides for Kindle PDF conversion, Send-to-Kindle troubleshooting, " +
    "KFX conversion, and e-reader comparisons.",
  url: CANONICAL,
  items: guides.map((g) => ({
    name: g.title,
    url: `https://leafbind.io/guides/${g.slug}`,
    description: g.summary,
  })),
});

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export default function GuidesHub() {
  return (
    <>
      <JsonLd schema={itemListSchema} />

      {/* Page header */}
      <div className="py-12 md:py-16 border-b border-border mb-16">
        <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-5">
          Guides
        </p>
        <h1 className="font-serif text-3xl sm:text-4xl md:text-5xl lg:text-6xl leading-tight text-text-base mb-6 max-w-3xl">
          Kindle &amp; PDF guides
        </h1>
        <p className="font-sans text-lg text-text-muted leading-relaxed max-w-2xl">
          Practical guides for sending PDFs to Kindle, fixing Send-to-Kindle failures,
          converting to KFX format, and choosing the right e-reader for reading-heavy
          workflows.
        </p>
      </div>

      {/* Guide list */}
      <div className="pb-16">
        <ul className="space-y-0 divide-y divide-border">
          {guides.map((guide) => (
            <li key={guide.slug}>
              <Link
                href={`/guides/${guide.slug}`}
                className="group block py-8 no-underline hover:bg-surface-muted -mx-4 px-4 transition"
              >
                <p className="font-mono text-xs text-text-muted uppercase tracking-widest mb-2">
                  Updated {formatDate(guide.lastUpdated)}
                </p>
                <h2 className="font-serif text-xl sm:text-2xl text-text-base group-hover:text-brand leading-snug mb-2 transition">
                  {guide.title}
                </h2>
                <p className="font-sans text-base text-text-muted leading-relaxed max-w-2xl">
                  {guide.summary}
                </p>
                <span className="mt-3 inline-block text-sm font-medium text-accent no-underline">
                  Read guide →
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </div>

      {/* CTA */}
      <div className="border-t border-border pt-16 pb-8">
        <h2 className="font-serif text-2xl text-text-base mb-3 leading-snug">
          Ready to convert?
        </h2>
        <p className="font-sans text-base text-text-muted leading-relaxed mb-8 max-w-xl">
          Upload a PDF and convert to EPUB at no cost — 3 conversions per day, up to
          20&nbsp;MB, no account required. Premium plans unlock KFX output with heading
          detection, footnote linking, and visual QA.
        </p>
        <Link
          href="/convert/pdf-to-kfx"
          className="font-sans inline-block bg-brand text-white font-medium text-base px-8 py-3 rounded-sm no-underline hover:opacity-90"
        >
          Convert a PDF to KFX
        </Link>
      </div>
    </>
  );
}
