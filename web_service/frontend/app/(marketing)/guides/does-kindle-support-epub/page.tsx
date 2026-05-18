import type { Metadata } from "next";
import Link from "next/link";
import JsonLd from "../../../../components/JsonLd";
import {
  buildArticleSchema,
  buildFAQPageSchema,
} from "../../../../lib/structured-data";

// ISO 8601 with explicit ET offset — Schema.org Article date fields require timezone-qualified datetimes.
const PUBLISHED = "2026-05-17T00:00:00-04:00";
const SLUG = "does-kindle-support-epub";
const CANONICAL = `https://leafbind.io/guides/${SLUG}`;

export const metadata: Metadata = {
  title: "Does Kindle Support EPUB? Yes — Here's How (and Where to Convert) — leafbind",
  description:
    "Yes, Kindle accepts EPUB via Send-to-Kindle (since 2022). Amazon converts it to KFX " +
    "server-side. Honest guide: when STK works, when to use Calibre, and when a hosted " +
    "converter helps.",
  alternates: {
    canonical: CANONICAL,
  },
  openGraph: {
    title: "Does Kindle Support EPUB? Yes — Here's How (and Where to Convert) — leafbind",
    description:
      "Kindle accepts EPUB via Send-to-Kindle since 2022. Honest guide to what happens, " +
      "what to do when STK rejects your file, and where leafbind fits in.",
    type: "article",
    url: CANONICAL,
    images: [
      {
        url: "https://leafbind.io/quality/pipeline-headings.png",
        width: 800,
        height: 600,
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Does Kindle Support EPUB? Yes — Here's How — leafbind",
    description:
      "Kindle accepts EPUB via Send-to-Kindle since 2022. Honest guide to STK, Calibre, " +
      "and where a hosted converter helps.",
    images: ["https://leafbind.io/quality/pipeline-headings.png"],
  },
};

// ── FAQ items as single source of truth ────────────────────────────────────
// Ordering: highest-volume keyword first (PL-4 compromise — lead with the
// can-form keyword at 1,300/mo to capture the top-of-FAQ citation slot),
// then intent-grouped from there: does-form → can-form → positional.

const faqItems = [
  {
    q: "Can Kindle read EPUB?",
    a: "Can Kindle read EPUB? Yes — since 2022. Amazon's Send-to-Kindle service accepts EPUB files via email (amazon.com/sendtokindle/email) and via the web uploader (amazon.com/sendtokindle). Once you send the file, Amazon converts it server-side to KFX (modern Kindles) or KF8/AZW3 (older firmware) and delivers the converted book to your library. The end-user experience is identical to native EPUB support: open the book on your Kindle and read. The one nuance worth knowing is that Kindle does not natively render the EPUB file itself — what lives on your device is the converted KFX or AZW3. For DRM-protected EPUBs, this won't work: Send-to-Kindle rejects them. For files under 200 MB without DRM, Send-to-Kindle is the easiest path.",
  },
  {
    q: "Does Kindle support EPUB?",
    a: "Does Kindle support EPUB? Yes, through Send-to-Kindle. Amazon added EPUB ingestion to Send-to-Kindle in May 2022 (email path) and November 2022 (the web uploader). MOBI support was sunset on December 20, 2023, leaving EPUB, PDF, DOC, DOCX, RTF, TXT, HTML, and image files as the currently supported set. Send-to-Kindle is the recommended path for most users — drop the file in, Amazon does the conversion, and the book appears on your Kindle. The web uploader at send.amazon.com handles files up to 200 MB; the email path caps at 50 MB. Files that exceed those caps, or files with DRM, won't go through Send-to-Kindle and need a different tool — Calibre with the KFX Output plugin is the standard alternative.",
  },
  {
    q: "Does Kindle read EPUB?",
    a: "Does Kindle read EPUB? Yes, but with a technical nuance: Kindle accepts EPUB as input via Send-to-Kindle, then converts it to its own internal format (KFX or AZW3) at ingestion time. The file you read on the device is the converted version, not the original EPUB. For the user, this is invisible — once Send-to-Kindle finishes processing, the book appears in your library and reads normally. The conversion preserves text, basic formatting, and embedded images. It does not preserve EPUB-specific features that don't map to KFX, such as fixed-layout templates or scripted interactivity (rare in trade EPUBs). If the original EPUB is well-formed, the converted KFX is virtually indistinguishable from a native Kindle book.",
  },
  {
    q: "Does Kindle take EPUB?",
    a: "Does Kindle take EPUB? Yes — three paths work: Send-to-Kindle email (50 MB cap, requires the sending address to be on your approved list at amazon.com/mycd); Send-to-Kindle web uploader at send.amazon.com (200 MB cap, no email approval needed); and local conversion with Calibre plus the KFX Output plugin (no size cap, no internet round trip, but requires Calibre and the plugin installed on your desktop). All three produce a Kindle-readable file. Send-to-Kindle is fastest for clean EPUBs without DRM. Calibre is the right answer when files exceed Amazon's caps, when Send-to-Kindle silently fails on a malformed EPUB, or when you want local control over the conversion. DRM-protected EPUBs are rejected by Send-to-Kindle outright; Calibre with the DeDRM plugin is the path for personal-archive DRM-removal where legally permitted.",
  },
  {
    q: "Does Kindle read EPUB format?",
    a: "Does Kindle read EPUB format? Kindle reads EPUB as an input format only — it ingests EPUB via Send-to-Kindle and converts to its native KFX or AZW3 format for on-device display. EPUB is not the format Kindle uses internally. This matters in two practical ways. First: if you sideload an EPUB directly to a Kindle via USB cable, the Kindle won't open it (USB sideload bypasses the conversion step that Send-to-Kindle handles). Second: the file you see in your Kindle library after sending is a KFX or AZW3 file, not your original EPUB — so if you re-export the book from the device, you're exporting a converted version, not your source file. For most readers this is invisible. For format-sensitive workflows, keep the original EPUB locally.",
  },
  {
    q: "Can Kindle use EPUB?",
    a: "Can Kindle use EPUB? Yes, but it uses EPUB as an upload format rather than a native on-device format. Send-to-Kindle accepts EPUB at the upload step; Amazon converts to KFX or AZW3 server-side; the converted file is what gets delivered to your Kindle. Practically, this means you can use any well-formed, DRM-free EPUB with your Kindle by sending it through Send-to-Kindle or by converting locally with Calibre and the KFX Output plugin. EPUBs from sources like Project Gutenberg, Standard Ebooks, or your own EPUB collection work without issue. EPUBs from commercial stores (Apple Books, Kobo, Google Play Books) typically have DRM and won't go through Send-to-Kindle — those stay locked to their source ecosystem unless you legally remove the DRM with Calibre's DeDRM plugin.",
  },
  {
    q: "EPUB format to Kindle: how does it work?",
    a: "EPUB format to Kindle works through Amazon's Send-to-Kindle service. You upload the EPUB at send.amazon.com (web, files up to 200 MB) or email it to your Kindle's @kindle.com address from an approved sender (email, files up to 50 MB). Amazon's servers receive the file, convert the EPUB to KFX (Kindle's modern format) or AZW3 (older Kindles), and push the converted book to every Kindle device and app on your account within a few minutes. The conversion is automatic and unconfigurable — Amazon makes the call on heading detection, image placement, and text flow. For most trade EPUBs the result is fine. For EPUBs with custom typography or complex layouts, you may want to convert locally with Calibre's KFX Output plugin instead, which gives you control over the conversion settings.",
  },
  {
    q: "EPUB format on Kindle: what to know",
    a: "EPUB format on Kindle isn't actually stored on the device — Kindle stores KFX or AZW3, which is what the EPUB gets converted to during Send-to-Kindle ingestion. Practically, this means once your EPUB is on the Kindle, you're reading the converted version, not the original file. Two limits worth knowing: Send-to-Kindle rejects DRM-protected EPUBs (no exception, no workaround within Amazon's service); Send-to-Kindle's size cap is 200 MB on the web uploader and 50 MB on the email path. Files larger than that won't ingest. For DRM-protected EPUBs from commercial stores (Apple Books, Kobo, Google Play Books), the legal path is to keep reading them in their source app, since Amazon will not accept the file with DRM intact.",
  },
];

// ── Schemas ────────────────────────────────────────────────────────────────

const articleSchema = buildArticleSchema({
  headline:
    "Does Kindle support EPUB? Yes — here's how it works (and where to convert when STK fails)",
  description:
    "Honest answer: yes, Kindle accepts EPUB via Send-to-Kindle since 2022. " +
    "Amazon converts EPUB to KFX server-side. Guide covers what STK does well, " +
    "when Calibre is the right alternative, and where a hosted web converter helps.",
  image: "https://leafbind.io/quality/pipeline-headings.png",
  datePublished: PUBLISHED,
  dateModified: PUBLISHED,
  url: CANONICAL,
  author: { name: "Joe Fowler", url: "https://github.com/jlfowler1084" },
});

const faqSchema = buildFAQPageSchema(faqItems);

// ── Page ───────────────────────────────────────────────────────────────────

export default function DoesKindleSupportEpub() {
  return (
    <>
      <JsonLd schema={articleSchema} />
      <JsonLd schema={faqSchema} />

      {/* Page header */}
      <div className="py-12 md:py-16 border-b border-border mb-16">
        <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-5">
          EPUB on Kindle
        </p>
        <h1 className="font-serif text-3xl sm:text-4xl md:text-5xl lg:text-6xl leading-tight text-text-base mb-6 max-w-3xl">
          Does Kindle Support EPUB? Yes — Here&apos;s How (and Where to Convert)
        </h1>
        <p className="font-sans text-lg text-text-muted leading-relaxed max-w-2xl">
          Short answer: yes. Amazon&apos;s Send-to-Kindle service accepts EPUB
          and converts it to KFX on the way to your device. For most readers,
          Send-to-Kindle is the right tool. This page explains what actually
          happens to your EPUB, when Send-to-Kindle is the wrong tool, and
          where a hosted converter like{" "}
          <Link href="/convert/pdf-to-kfx" className="text-accent no-underline hover:underline font-medium">
            leafbind
          </Link>{" "}
          fits in — honestly, since for clean EPUBs you probably don&apos;t
          need us.
        </p>
        <p className="font-mono text-xs text-text-muted mt-6">
          By Joe Fowler &mdash; Updated{" "}
          {new Date(PUBLISHED).toLocaleDateString("en-US", {
            year: "numeric",
            month: "long",
            day: "numeric",
          })}
        </p>
      </div>

      <div className="py-0">

        {/* ── Short answer ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            Short answer
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              Kindle accepts EPUB via{" "}
              <a
                href="https://www.amazon.com/sendtokindle"
                target="_blank"
                rel="noopener"
                className="text-accent no-underline hover:underline font-medium"
              >
                Send-to-Kindle
              </a>
              . Amazon added EPUB ingestion in May 2022 (email path) and
              November 2022 (the web uploader at send.amazon.com). MOBI was
              fully sunset on December 20, 2023 — EPUB is now Amazon&apos;s
              preferred personal-document format alongside PDF, DOC/DOCX, RTF,
              TXT, HTML, and image files.
            </p>
            <p>
              Once you send the file, Amazon converts it server-side to KFX
              (modern Kindles) or AZW3 (older firmware) and delivers the
              converted book to your library. The end-user experience looks
              like &quot;EPUB on Kindle.&quot; Technically, it&apos;s
              EPUB-to-KFX via Amazon&apos;s servers — Kindle is not a native
              EPUB reader.
            </p>
            <p>
              For most readers with a clean, DRM-free EPUB under 200 MB,
              that&apos;s the entire answer. Send-to-Kindle handles it.
            </p>
          </div>
        </section>

        {/* ── Your options ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            Your three options
          </h2>
          <p className="font-sans text-base text-text-muted leading-relaxed mb-6 max-w-2xl">
            Three tools handle EPUB-to-Kindle for personal documents. Pick the
            one that fits your situation — they&apos;re all legitimate.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 max-w-3xl">
            <div className="border border-border rounded-sm p-5 bg-white">
              <p className="font-mono text-xs font-medium text-text-muted uppercase tracking-widest mb-2">
                Best for most users
              </p>
              <p className="font-sans font-medium text-text-base text-base mb-2">
                Send-to-Kindle (Amazon)
              </p>
              <p className="font-sans text-sm text-text-muted leading-relaxed mb-3">
                Free. Up to 200 MB via the web uploader, 50 MB via email.
                Amazon handles the EPUB-to-KFX conversion. Rejects DRM.
              </p>
              <a
                href="https://www.amazon.com/sendtokindle"
                target="_blank"
                rel="noopener"
                className="text-sm font-medium text-accent no-underline hover:underline"
              >
                send.amazon.com →
              </a>
            </div>
            <div className="border border-border rounded-sm p-5 bg-white">
              <p className="font-mono text-xs font-medium text-text-muted uppercase tracking-widest mb-2">
                Best for local control
              </p>
              <p className="font-sans font-medium text-text-base text-base mb-2">
                Calibre + KFX Output plugin
              </p>
              <p className="font-sans text-sm text-text-muted leading-relaxed mb-3">
                Free, open-source. No file-size cap. Local install required.
                Plus DeDRM for personal-archive DRM removal where legal.
              </p>
              <a
                href="https://calibre-ebook.com/"
                target="_blank"
                rel="noopener"
                className="text-sm font-medium text-accent no-underline hover:underline"
              >
                calibre-ebook.com →
              </a>
            </div>
            <div className="border border-border rounded-sm p-5 bg-white">
              <p className="font-mono text-xs font-medium text-text-muted uppercase tracking-widest mb-2">
                Best for hosted, no-install
              </p>
              <p className="font-sans font-medium text-text-base text-base mb-2">
                leafbind (hosted Calibre)
              </p>
              <p className="font-sans text-sm text-text-muted leading-relaxed mb-3">
                Free tier returns EPUB (3/day, 20 MB). Premium credits return
                KFX (100 MB). No DRM stripping. Standard Calibre tolerance.
              </p>
              <Link
                href="/convert/pdf-to-kfx"
                className="text-sm font-medium text-accent no-underline hover:underline"
              >
                Try leafbind →
              </Link>
            </div>
          </div>
          <p className="font-sans text-sm text-text-muted leading-relaxed mt-6 max-w-2xl">
            <span className="font-medium text-text-base">Worth saying out loud:</span>{" "}
            leafbind isn&apos;t built around EPUB conversion — that&apos;s
            convenience, not the point. Our actual strength is{" "}
            <Link href="/convert/pdf-to-kfx" className="text-accent no-underline hover:underline font-medium">
              PDF-to-Kindle conversion
            </Link>{" "}
            where Send-to-Kindle and Calibre commonly fail: multi-column
            academic papers, footnote-heavy documents, and PDFs with custom
            heading hierarchies. If your next conversion problem is a PDF, we
            may genuinely help.
          </p>
        </section>

        {/* ── When STK isn't the right tool ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            When Send-to-Kindle isn&apos;t the right tool
          </h2>
          <p className="font-sans text-base text-text-muted leading-relaxed mb-6 max-w-2xl">
            Send-to-Kindle handles most EPUBs cleanly. Four cases are exceptions
            — each has a verifiable signal that tells you Send-to-Kindle is the
            wrong path for this file.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-2xl">
            <div className="border border-border rounded-sm p-4 bg-white">
              <p className="font-sans font-medium text-text-base text-sm mb-1">
                DRM-protected EPUB
              </p>
              <p className="font-sans text-sm text-text-muted leading-relaxed">
                Signal: Amazon rejects the upload with a message about personal
                document services not accepting DRM. Send-to-Kindle does not
                strip DRM. For commercial-store EPUBs (Apple Books, Kobo,
                Google Play Books), the legal path is to keep reading them in
                their source app.
              </p>
            </div>
            <div className="border border-border rounded-sm p-4 bg-white">
              <p className="font-sans font-medium text-text-base text-sm mb-1">
                File over 200 MB
              </p>
              <p className="font-sans text-sm text-text-muted leading-relaxed">
                Signal: send.amazon.com rejects the upload at the size-check
                step. The web uploader caps at 200 MB; the email path caps at
                50 MB. Larger files won&apos;t ingest. Use Calibre locally —
                no size cap.
              </p>
            </div>
            <div className="border border-border rounded-sm p-4 bg-white">
              <p className="font-sans font-medium text-text-base text-sm mb-1">
                Malformed EPUB
              </p>
              <p className="font-sans text-sm text-text-muted leading-relaxed">
                Signal: Send-to-Kindle accepts the upload but the book never
                appears in your library, or appears with broken structure
                (missing chapters, garbled text). The community tool{" "}
                <a
                  href="https://kindle-epub-fix.netlify.app/"
                  target="_blank"
                  rel="noopener"
                  className="text-accent no-underline hover:underline"
                >
                  Kindle EPUB Fix
                </a>{" "}
                exists specifically for this failure class.
              </p>
            </div>
            <div className="border border-border rounded-sm p-4 bg-white">
              <p className="font-sans font-medium text-text-base text-sm mb-1">
                Mixed-format archive
              </p>
              <p className="font-sans text-sm text-text-muted leading-relaxed">
                Signal: you have a ZIP or folder containing both EPUB and PDF
                files. Send-to-Kindle accepts one file at a time and rejects
                archives. Extract the EPUBs and send them individually, or
                batch-convert locally with Calibre.
              </p>
            </div>
          </div>
        </section>

        {/* ── Frequently asked questions ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            Frequently asked questions
          </h2>
          <p className="font-sans text-base text-text-muted leading-relaxed mb-8 max-w-2xl">
            Direct answers to the eight most-searched variants of the
            EPUB-on-Kindle question, each grounded in Amazon&apos;s current
            documentation.
          </p>
          <div className="space-y-8 max-w-3xl">
            {faqItems.map((item) => (
              <div key={item.q}>
                <h3 className="font-serif text-xl text-text-base mb-3 leading-snug">
                  {item.q}
                </h3>
                <p className="font-sans text-base text-text-base leading-relaxed">
                  {item.a}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* ── Related guides ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            Related guides
          </h2>
          <p className="font-sans text-base text-text-muted leading-relaxed mb-6 max-w-2xl">
            If you&apos;re here because Send-to-Kindle didn&apos;t work for your
            file, or because your next problem is a PDF instead of an EPUB,
            these guides go deeper.
          </p>
          <div className="flex flex-col sm:flex-row gap-3 flex-wrap max-w-3xl">
            <Link
              href="/guides/send-to-kindle-not-working"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-3 hover:bg-accent/5"
            >
              Send to Kindle not working: 7 fixes →
            </Link>
            <Link
              href="/guides/how-to-send-pdf-to-kindle"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-3 hover:bg-accent/5"
            >
              How to send PDFs (and EPUBs) to Kindle →
            </Link>
            <Link
              href="/convert/pdf-to-kfx"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-3 hover:bg-accent/5"
            >
              Convert PDF to KFX (leafbind) →
            </Link>
          </div>
        </section>

        {/* ── Sources ── */}
        <section className="mb-16 pb-8 border-b border-border">
          <p className="font-mono text-xs font-medium text-text-muted uppercase tracking-widest mb-3">
            Sources
          </p>
          <ul className="space-y-1">
            <li className="font-sans text-sm text-text-muted">
              <a
                href="https://www.amazon.com/sendtokindle"
                target="_blank"
                rel="noopener"
                className="text-accent no-underline hover:underline"
              >
                Amazon Send to Kindle — supported file types and web uploader (200 MB cap)
              </a>{" "}
              (last verified 2026-05-17)
            </li>
            <li className="font-sans text-sm text-text-muted">
              <a
                href="https://www.amazon.com/sendtokindle/email"
                target="_blank"
                rel="noopener"
                className="text-accent no-underline hover:underline"
              >
                Amazon Send to Kindle by Email — 50 MB cap, approved sender list
              </a>{" "}
              (last verified 2026-05-17)
            </li>
            <li className="font-sans text-sm text-text-muted">
              <a
                href="https://calibre-ebook.com/"
                target="_blank"
                rel="noopener"
                className="text-accent no-underline hover:underline"
              >
                Calibre — open-source ebook management with the KFX Output plugin
              </a>
            </li>
          </ul>
        </section>

        {/* ── CTA ── */}
        <section className="border-t border-border pt-16 pb-8">
          <h2 className="font-serif text-3xl text-text-base mb-4 leading-snug">
            Got a stubborn PDF instead?
          </h2>
          <p className="font-sans text-base text-text-muted leading-relaxed mb-2 max-w-xl">
            For clean EPUBs, Send-to-Kindle and Calibre are the right tools and
            you probably don&apos;t need us. leafbind&apos;s actual strength is
            PDFs that other tools mangle: multi-column academic papers,
            footnote-heavy documents, and PDFs with custom heading hierarchies.
            Free tier converts to EPUB at no cost — 3 conversions per day, up
            to 20 MB, no account required. KFX output with column detection,
            footnote linking, and heading classification is available on
            premium plans.
          </p>
          <p className="font-sans text-sm text-text-muted leading-relaxed mb-8">
            <Link
              href="/pricing"
              className="text-brand font-medium no-underline hover:underline"
            >
              See pricing
            </Link>{" "}
            — one-time credit packs, no subscription.
          </p>
          <Link
            href="/convert/pdf-to-kfx"
            className="font-sans inline-block bg-brand text-white font-medium text-base px-8 py-3 rounded-sm no-underline hover:opacity-90"
          >
            Try a PDF conversion →
          </Link>

          <div className="mt-12 pt-8 border-t border-border max-w-xl">
            <p className="font-sans text-sm text-text-muted leading-relaxed">
              <span className="font-medium text-text-base">Joe Fowler</span> is
              a developer and technical writer who built leafbind after spending
              an unreasonable amount of time coaxing academic PDFs into something
              readable on a Kindle. He writes about PDF structure, ebook
              formats, and the conversion pipeline at leafbind.io.
            </p>
          </div>
        </section>

      </div>
    </>
  );
}
