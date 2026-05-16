import { type Metadata } from "next";
import { Suspense } from "react";
import UploadForm from "../UploadForm";
import { Logo } from "../../components/Logo";

export const metadata: Metadata = {
  title: "leafbind — PDF to Kindle, the calm way",
  description:
    "Smart PDF to Kindle conversion with heading detection, footnote linking, and multi-column support. Free tier available. No ads, no tracking.",
};

const CAPABILITIES = [
  {
    n: "01",
    eyebrow: "Navigation",
    title: "Headings that navigate",
    body:
      "leafbind classifies text by rendered font size, not font name — so your section headings become a working Kindle chapter list, not a wall of undifferentiated paragraphs.",
  },
  {
    n: "02",
    eyebrow: "Footnotes",
    title: "Footnotes that jump",
    body:
      "Superscript markers are matched to their footnote bodies and linked bidirectionally. Tap a citation number on your Kindle to jump to the note; tap the return link to come back.",
  },
  {
    n: "03",
    eyebrow: "Columns",
    title: "Columns in order",
    body:
      "Multi-column academic papers are read column by column, not line by line across the full page width. IEEE papers, arXiv preprints, and ACM proceedings come out readable.",
  },
];

export default function HomePage() {
  return (
    <>
      {/* Hero — two-column on lg, stacked on mobile */}
      <section className="grid grid-cols-1 gap-12 lg:grid-cols-[1.05fr_1fr] lg:gap-16 lg:items-center">
        {/* Left column — copy + CTA + trust strip */}
        <div>
          <span className="font-mono text-xs uppercase tracking-[0.16em] text-brand">
            01 · Convert
          </span>
          <h1 className="font-serif text-5xl md:text-6xl font-normal leading-[1.02] tracking-tight text-text-base mt-5 mb-6">
            Convert PDFs to Kindle,{" "}
            <em className="italic text-brand font-medium">beautifully</em>.
          </h1>
          <p className="font-sans text-lg text-text-muted leading-relaxed max-w-md mb-4">
            Smart heading detection, footnote linking, multi-column support.
            No ads. No malware.
          </p>
          <p className="font-sans text-sm text-text-muted max-w-md mb-8">
            Your file is never stored after conversion. No tracking, no ads.
          </p>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 font-mono text-xs text-text-muted">
            <span>✓ no account required</span>
            <span>✓ 20 MB free tier</span>
            <span>✓ pay once, no subscription</span>
          </div>
        </div>

        {/* Right column — converter card with window chrome */}
        <div
          className="rounded-2xl border border-border bg-[var(--lb-paper)] p-6 md:p-7"
          style={{
            boxShadow:
              "0 30px 60px -30px rgba(47,93,58,0.25), 0 8px 24px -12px rgba(26,31,28,0.1)",
          }}
        >
          {/* Window chrome */}
          <div className="flex items-center gap-1.5 mb-5">
            <span className="block h-2.5 w-2.5 rounded-full bg-[#e9c8aa]" />
            <span className="block h-2.5 w-2.5 rounded-full bg-[#dcd2b8]" />
            <span className="block h-2.5 w-2.5 rounded-full bg-brand opacity-50" />
            <span className="ml-auto font-mono text-[11px] text-text-muted">
              leafbind.io / convert
            </span>
          </div>

          {/* Upload form (existing functional component) */}
          <Suspense fallback={null}>
            <UploadForm />
          </Suspense>

          <p className="mt-5 text-center font-mono text-[11px] uppercase tracking-[0.12em] text-text-muted">
            free tier · pay once to unlock premium
          </p>
        </div>
      </section>

      {/* Three capability cards */}
      <section className="mt-20 md:mt-28">
        <span className="font-mono text-xs uppercase tracking-[0.16em] text-brand">
          02 · Why leafbind
        </span>
        <h2 className="font-serif text-3xl md:text-4xl font-medium leading-tight tracking-tight text-text-base mt-3 mb-12 max-w-xl">
          The parts other converters{" "}
          <em className="italic text-brand">skip</em>.
        </h2>
        <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
          {CAPABILITIES.map((c) => (
            <article
              key={c.n}
              className="rounded-2xl border border-border bg-[var(--lb-paper)] p-7"
            >
              <div className="flex h-9 w-9 items-center justify-center rounded-md bg-[rgba(47,93,58,0.1)] mb-5">
                <Logo variant="glyph" className="h-[22px] w-[22px]" />
              </div>
              <div className="font-mono text-[11px] uppercase tracking-[0.12em] text-brand mb-2">
                {c.n} · {c.eyebrow}
              </div>
              <h3 className="font-serif text-xl text-text-base mb-3 leading-snug">
                {c.title}
              </h3>
              <p className="font-sans text-sm text-text-muted leading-relaxed">
                {c.body}
              </p>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}
