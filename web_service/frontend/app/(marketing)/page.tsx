import { type Metadata } from "next";
import { Suspense } from "react";
import Link from "next/link";
import UploadForm from "../UploadForm";
import { Logo } from "../../components/Logo";

export const metadata: Metadata = {
  title: "leafbind — PDF to Kindle, the calm way",
  description:
    "Smart PDF to Kindle conversion with heading detection, footnote linking, and multi-column support. Free tier available. No ads, no tracking.",
};

const STEPS = [
  {
    n: "01",
    title: "Drop a file",
    body: "PDF, EPUB, MOBI, AZW, AZW3, or DJVU. Up to 20 MB on the free tier; 100 MB on premium.",
  },
  {
    n: "02",
    title: "Pick a format",
    body: "EPUB or MOBI on free. Premium adds KFX — Kindle's native enhanced typesetting format.",
  },
  {
    n: "03",
    title: "We convert",
    body: "Smart heading detection, bidirectional footnote linking, and column-aware extraction run automatically.",
  },
  {
    n: "04",
    title: "Download",
    body: "Grab the file and side-load it, or email it to your Kindle. Your source is wiped within 24 hours.",
  },
];

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

const FAQS: [string, React.ReactNode][] = [
  [
    "Does leafbind store my files?",
    <>
      No. Your file lives only inside the conversion job slot, and it&apos;s
      wiped within 24 hours regardless of outcome. No accounts, no tracking,
      no ads — and nothing is ever shared with third parties or used to train
      models.
    </>,
  ],
  [
    "What's the difference between free and premium?",
    <>
      Free runs your PDF through Calibre for a quick EPUB or MOBI. Premium runs
      leafbind&apos;s smart pipeline — column-aware extraction, font-size-based
      heading detection, bidirectional footnote linking, and KFX output. See
      the <Link href="/quality" className="text-brand hover:underline font-medium">quality page</Link> for
      side-by-side examples on real books.
    </>,
  ],
  [
    "Why does Kindle care about KFX?",
    <>
      KFX is Kindle&apos;s native enhanced typesetting format. Pagination,
      hyphenation, and reflow all render noticeably better than EPUB or MOBI on
      the device. For long-form text — academic books especially — the
      difference is visible at a glance.
    </>,
  ],
  [
    "What if my conversion fails?",
    <>
      Failed premium conversions don&apos;t burn a credit. Your token stays
      valid for the full 7-day expiry and you can retry. If you&apos;ve already
      lost track of your token, you can{" "}
      <Link href="/recover" className="text-brand hover:underline font-medium">recover it by email</Link>.
    </>,
  ],
];

export default function HomePage() {
  return (
    <>
      {/* Hero — two-column on lg, stacked on mobile */}
      <section
        id="convert"
        className="scroll-mt-24 grid grid-cols-1 gap-12 lg:grid-cols-[1.05fr_1fr] lg:gap-16 lg:items-center"
      >
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

      {/* Formats matrix — full-bleed dark ink band */}
      <section
        className="mt-20 md:mt-28 mx-[calc(50%-50vw)] bg-[var(--lb-ink)] text-[var(--lb-cream)] py-20 md:py-24"
      >
        <div className="mx-auto max-w-[1240px] px-6 lg:px-16">
          <span className="font-mono text-xs uppercase tracking-[0.16em] text-[var(--lb-sand)]">
            02 · Formats
          </span>
          <h2 className="font-serif text-3xl md:text-4xl font-medium leading-[1.1] tracking-tight mt-3 mb-5 max-w-2xl">
            Drop in <em className="italic text-[var(--lb-sand)] font-medium">anything</em>.
            Get out a Kindle file that opens.
          </h2>
          <p className="font-sans text-base md:text-lg text-[rgba(244,239,226,0.7)] leading-relaxed max-w-xl mb-14">
            Scanned PDF, messy EPUB, ancient AZW — leafbind normalizes the input
            and produces a Kindle-ready file with the table of contents,
            footnotes, and reflow intact.
          </p>

          <div className="grid grid-cols-1 lg:grid-cols-[1fr_auto_1fr] gap-10 lg:gap-12 items-center">
            {/* Inputs */}
            <div>
              <div className="font-mono text-[11px] uppercase tracking-[0.12em] text-[rgba(244,239,226,0.4)] mb-4">
                Inputs
              </div>
              <div className="flex flex-wrap gap-2">
                {["PDF", "EPUB", "MOBI", "AZW", "AZW3", "DJVU"].map((i) => (
                  <span
                    key={i}
                    className="font-sans font-medium text-sm px-4 py-2.5 rounded-full border border-[rgba(244,239,226,0.2)]"
                  >
                    {i}
                  </span>
                ))}
              </div>
            </div>

            {/* Center: stroke-only leaf + bind label */}
            <div className="flex flex-col items-center gap-2 py-2 text-[var(--lb-sand)]">
              <svg
                viewBox="0 0 100 100"
                className="h-16 w-16"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                aria-hidden="true"
              >
                <path d="M50 6 C72 14, 88 32, 88 54 C88 76, 72 92, 50 94 C28 92, 12 76, 12 54 C12 32, 28 14, 50 6 Z" />
                <path
                  d="M50 12 Q49 50, 47 92"
                  strokeWidth="1.4"
                  opacity="0.75"
                />
              </svg>
              <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[rgba(244,239,226,0.5)]">
                bind
              </span>
            </div>

            {/* Outputs */}
            <div>
              <div className="font-mono text-[11px] uppercase tracking-[0.12em] text-[rgba(244,239,226,0.4)] mb-4">
                Outputs
              </div>
              <div className="flex flex-wrap gap-2">
                {["EPUB", "MOBI", "KFX"].map((o) => (
                  <span
                    key={o}
                    className="font-sans font-semibold text-sm px-4 py-2.5 rounded-full bg-[var(--lb-sand)] text-[var(--lb-ink)]"
                  >
                    {o}
                  </span>
                ))}
              </div>
              <p className="font-sans text-xs text-[rgba(244,239,226,0.45)] mt-4 max-w-xs">
                KFX is premium — Kindle's native enhanced typesetting format.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* How it works — 4-step paper cards */}
      <section className="mt-20 md:mt-28">
        <span className="font-mono text-xs uppercase tracking-[0.16em] text-brand">
          03 · Workflow
        </span>
        <h2 className="font-serif text-3xl md:text-4xl font-medium leading-tight tracking-tight text-text-base mt-3 mb-12 max-w-xl">
          From drop to download in{" "}
          <em className="italic text-brand">four steps</em>.
        </h2>
        <ol className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((s) => (
            <li
              key={s.n}
              className="rounded-2xl border border-border bg-[var(--lb-paper)] p-7"
            >
              <div className="font-mono text-[11px] uppercase tracking-[0.12em] text-brand mb-3">
                {s.n}
              </div>
              <h3 className="font-serif text-xl text-text-base mb-3 leading-snug">
                {s.title}
              </h3>
              <p className="font-sans text-sm text-text-muted leading-relaxed">
                {s.body}
              </p>
            </li>
          ))}
        </ol>
      </section>

      {/* Three capability cards */}
      <section className="mt-20 md:mt-28">
        <span className="font-mono text-xs uppercase tracking-[0.16em] text-brand">
          04 · Why leafbind
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

      {/* FAQ — 2-column Q/A list */}
      <section className="mt-20 md:mt-28">
        <span className="font-mono text-xs uppercase tracking-[0.16em] text-brand">
          05 · Questions
        </span>
        <h2 className="font-serif text-3xl md:text-4xl font-medium leading-tight tracking-tight text-text-base mt-3 mb-10 max-w-xl">
          Things you&apos;ll{" "}
          <em className="italic text-brand">ask anyway</em>.
        </h2>
        <div className="flex flex-col">
          {FAQS.map(([q, a], i) => (
            <div
              key={i}
              className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_1.4fr] md:gap-12 border-t border-border py-8"
            >
              <h3 className="font-serif text-xl md:text-2xl font-medium text-text-base leading-snug">
                {q}
              </h3>
              <p className="font-sans text-base text-text-muted leading-relaxed">
                {a}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Bottom CTA strip — paper-cream centered band with leaf bleed */}
      <section className="mt-20 md:mt-28 relative overflow-hidden rounded-3xl border border-border bg-[var(--lb-paper)] px-8 py-14 md:px-16 md:py-20 text-center">
        {/* Decorative leaf bleed (right edge, low opacity) */}
        <div className="pointer-events-none absolute -right-12 -bottom-12 opacity-10 text-brand">
          <Logo variant="glyph" className="h-64 w-64" />
        </div>

        <div className="relative">
          <h2 className="font-serif text-3xl md:text-4xl font-medium leading-tight tracking-tight text-text-base mb-4 mx-auto max-w-xl">
            Convert your first book —{" "}
            <em className="italic text-brand">free</em>.
          </h2>
          <p className="font-sans text-base md:text-lg text-text-muted leading-relaxed max-w-xl mx-auto mb-8">
            Drop a PDF, pick a format, get a Kindle file. No account required.
            Pay only if you want premium output (KFX, larger files, smart
            pipeline).
          </p>
          <a
            href="#convert"
            className="inline-flex items-center gap-2 rounded-full bg-[var(--lb-ink)] text-[var(--lb-cream)] px-7 py-3.5 font-sans font-medium text-sm hover:opacity-90 transition"
          >
            Start converting
            <span aria-hidden="true">→</span>
          </a>
        </div>
      </section>
    </>
  );
}
