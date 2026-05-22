import type { Metadata } from "next";
import Link from "next/link";
import JsonLd from "../../../../components/JsonLd";
import {
  buildArticleSchema,
  buildFAQPageSchema,
} from "../../../../lib/structured-data";

const PUBLISHED = "2026-05-22T00:00:00-04:00";
const SLUG = "send-to-kindle-error-e999";
const CANONICAL = `https://leafbind.io/guides/${SLUG}`;

export const metadata: Metadata = {
  title: "Send to Kindle E999 Internal Error: Fix It — leafbind",
  description:
    "E999 is Amazon's generic internal-error code for Send to Kindle failures: oversized files, " +
    "malformed EPUBs, DRM rejection, or transient server errors. Diagnostic fixes for each cause.",
  alternates: {
    canonical: CANONICAL,
  },
  openGraph: {
    title: "Send to Kindle E999 Internal Error: Fix It — leafbind",
    description:
      "E999 internal error, authentication failure, or silent non-delivery? " +
      "Fix each Send to Kindle failure by error class — diagnostic steps and a backup when Amazon can't convert.",
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
    title: "Send to Kindle E999 Internal Error: Fix It — leafbind",
    description:
      "E999 internal error, authentication failures, and silent delivery failures — " +
      "what each code means and how to fix it.",
    images: ["https://leafbind.io/quality/pipeline-headings.png"],
  },
};

// ── FAQ items as single source of truth ──────────────────────────────────────

const faqItems = [
  {
    q: "What does E999 mean in Send to Kindle?",
    a: "E999 is Amazon's generic internal-error code for Send to Kindle failures. It covers four distinct causes: your file exceeds the size limit (50 MB by email, 200 MB via the web uploader), the EPUB is malformed or fails Amazon's strict XHTML validation, the file is DRM-protected and Amazon silently rejects it, or Amazon's conversion servers experienced a transient failure. Identify which cause applies before attempting fixes.",
  },
  {
    q: "How do I fix a Send to Kindle E999 internal error?",
    a: "Fix the E999 error by matching the cause to its solution: if the file is too large, switch to the web uploader at amazon.com/sendtokindle (200 MB limit) or use USB transfer. If the EPUB is malformed, run it through Calibre to normalize it and use an EPUB validator to confirm it passes. If DRM is the cause, the file source must provide a DRM-free version. If it is a transient server error, wait 30 minutes and retry. If none of these apply or conversion repeatedly fails, convert your PDF to KFX with leafbind and sideload via USB.",
  },
  {
    q: "Why does Send to Kindle say 'authentication failure'?",
    a: "A Send to Kindle authentication failure means the app cannot verify your Amazon account credentials. The most common cause is an expired session token — sign out of the app completely, then sign back in. If the error persists, check that your Amazon account region matches your device's registered region. Also verify the app is up to date, since older versions can lose authentication silently after Amazon updates its auth endpoints.",
  },
  {
    q: "What is the file size limit that causes E999?",
    a: "The Send to Kindle email attachment limit is 50 MB. The web uploader at amazon.com/sendtokindle accepts files up to 200 MB. USB transfer has no size limit. If you receive E999 and your file is over 50 MB but under 200 MB, switching to the web uploader resolves the error in most cases.",
  },
  {
    q: "How do I check if my file is DRM-protected?",
    a: "Open the file in Calibre. If it displays a padlock icon or reports an error when you attempt to view its full metadata, the file has DRM. DRM-protected files are silently rejected by Send to Kindle with an E999 error. Amazon cannot convert DRM-protected content, and only the original content source can provide a DRM-free version.",
  },
  {
    q: "Send to Kindle accepted my file but nothing appeared on my Kindle — what happened?",
    a: "Check your Amazon library at amazon.com/mycd before assuming delivery failed. Amazon documents that delivery can take up to 15 minutes, and device sync can lag behind server-side delivery. If the file appears in your library but not on the device, toggle Wi-Fi off and back on, or pull down on the Kindle home screen to force a sync. If the file is absent from the library after 30 minutes, the most likely cause is the approved sender list — Amazon silently drops messages from addresses not on your Approved Personal Document E-mail List.",
  },
  {
    q: "Does leafbind work for files that Send to Kindle rejects with E999?",
    a: "leafbind helps specifically with the size-cap and conversion-quality cases. If your file exceeds Send to Kindle's limits or Amazon's conversion produces unreadable output, leafbind converts PDFs to KFX — Kindle's native format — using coordinate-based extraction that handles multi-column layouts, footnotes, and heading detection. The KFX file transfers to any Kindle via USB, bypassing Send to Kindle entirely. leafbind does not help with DRM-protected files — those require a DRM-free version from the original source.",
  },
];

// ── Schemas ──────────────────────────────────────────────────────────────────

const articleSchema = buildArticleSchema({
  headline:
    "Send to Kindle E999 internal error: what it means and how to fix it",
  description:
    "E999 is Amazon's internal-error code covering four distinct Send to Kindle failure causes: " +
    "oversized files, malformed EPUBs, DRM rejection, and transient server failures. " +
    "Diagnostic fixes for each cause plus a fallback for when Amazon cannot convert the file.",
  image: "https://leafbind.io/quality/pipeline-headings.png",
  datePublished: PUBLISHED,
  dateModified: PUBLISHED,
  url: CANONICAL,
  author: { name: "Joe Fowler", url: "https://github.com/jlfowler1084" },
});

const faqSchema = buildFAQPageSchema(faqItems);

// ── Page ─────────────────────────────────────────────────────────────────────

export default function SendToKindleErrorE999() {
  return (
    <>
      <JsonLd schema={articleSchema} />
      <JsonLd schema={faqSchema} />

      {/* Page header */}
      <div className="py-12 md:py-16 border-b border-border mb-16">
        <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-5">
          Troubleshooting guide
        </p>
        <h1 className="font-serif text-3xl sm:text-4xl md:text-5xl lg:text-6xl leading-tight text-text-base mb-6 max-w-3xl">
          Send to Kindle E999 Internal Error: What It Means and How to Fix It
        </h1>
        <p className="font-sans text-lg text-text-muted leading-relaxed max-w-2xl">
          E999 is Amazon&apos;s generic internal-error code — not a single
          problem, but four distinct failure modes each requiring a different
          fix. This guide identifies which cause applies to your file and walks
          through the resolution. For general Send to Kindle problems not tied
          to an error code, see{" "}
          <Link
            href="/guides/send-to-kindle-not-working"
            className="text-accent no-underline hover:underline font-medium"
          >
            Send to Kindle not working: 7 fixes
          </Link>
          .
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

        {/* ── What E999 means ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            What the E999 error actually means
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              When Amazon&apos;s Send to Kindle service returns E999, it is
              reporting a generic internal error — the same code covers four
              different root causes, which is why a single fix rarely works for
              everyone. Understanding which cause applies to your specific file
              is the only reliable path to resolving it.
            </p>
            <p>The four root causes behind an E999 error are:</p>
            <ul className="list-disc pl-6 space-y-2 text-base">
              <li>
                <strong>File too large.</strong> The Send to Kindle email method
                imposes a 50&nbsp;MB limit; the web uploader at
                amazon.com/sendtokindle allows up to 200&nbsp;MB. Files over
                these thresholds trigger E999 without a descriptive message.
              </li>
              <li>
                <strong>Malformed EPUB.</strong> Amazon&apos;s conversion
                pipeline requires strict XHTML-compliant EPUBs. A file that
                opens correctly in Calibre or Apple Books may still be rejected
                if it fails Amazon&apos;s manifest or spine validation.
              </li>
              <li>
                <strong>DRM-protected file.</strong> Files with digital rights
                management are silently rejected. Amazon&apos;s service cannot
                convert DRM-protected content regardless of file type, and it
                returns E999 without explaining why.
              </li>
              <li>
                <strong>Transient server-side failure.</strong> Amazon&apos;s
                conversion infrastructure occasionally produces errors that
                clear on retry. If none of the above causes apply to your file,
                a retry after 30&nbsp;minutes often succeeds.
              </li>
            </ul>
            <p>
              In addition to E999, Send to Kindle produces two other failure
              patterns worth understanding: <em>authentication failures</em>{" "}
              (the app cannot verify your Amazon credentials — unrelated to the
              file) and <em>silent non-delivery</em> (the file is accepted
              without error but never appears on your device). Both are covered
              in the sections below.
            </p>
            <p>
              The diagnostic sections that follow address all three failure
              classes in order. Identify which pattern you are seeing — an
              explicit E999 code, an authentication message, or accepted-but-missing
              — and go directly to that section.
            </p>
          </div>
        </section>

        {/* ── H2: E999 internal error — diagnostic fixes ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            E999 internal error — diagnostic fixes by cause
          </h2>

          <div className="max-w-3xl space-y-12">

            {/* H3: File too large */}
            <div>
              <h3 className="font-serif text-xl text-text-base mb-3 leading-snug">
                File too large for Send to Kindle
              </h3>
              <div className="text-text-base leading-relaxed space-y-3 text-base">
                <p>
                  The Send to Kindle email attachment limit is{" "}
                  <strong>50&nbsp;MB</strong>. The web uploader at{" "}
                  <a
                    href="https://www.amazon.com/sendtokindle"
                    target="_blank"
                    rel="noopener"
                    className="text-accent no-underline hover:underline font-medium"
                  >
                    amazon.com/sendtokindle
                  </a>{" "}
                  accepts files up to <strong>200&nbsp;MB</strong>. If your
                  file is over 50&nbsp;MB but under 200&nbsp;MB, switching to
                  the web uploader resolves the majority of E999 errors on
                  large PDFs without any other changes.
                </p>
                <p>
                  If your file exceeds 200&nbsp;MB, your options are USB
                  transfer (no size limit — connect your Kindle, copy the file
                  into the{" "}
                  <code className="font-mono text-sm bg-gray-100 px-1 rounded">
                    Documents
                  </code>{" "}
                  folder) or convert and sideload via{" "}
                  <Link
                    href="/convert/pdf-to-kfx"
                    className="text-accent no-underline hover:underline font-medium"
                  >
                    leafbind&apos;s PDF to KFX converter
                  </Link>{" "}
                  (handles files up to 100&nbsp;MB on Premium; split files
                  over 100&nbsp;MB before converting).
                </p>
              </div>
            </div>

            {/* H3: Malformed EPUB */}
            <div>
              <h3 className="font-serif text-xl text-text-base mb-3 leading-snug">
                Malformed or invalid EPUB
              </h3>
              <div className="text-text-base leading-relaxed space-y-3 text-base">
                <p>
                  Amazon&apos;s EPUB processing requires strict compliance with
                  XHTML&nbsp;1.1 and EPUB&nbsp;2/3 manifest rules. An EPUB
                  that opens correctly in Calibre, Apple Books, or other readers
                  may still be rejected if it contains malformed HTML tags,
                  missing spine items, or content files that are not valid
                  XHTML.
                </p>
                <p>To diagnose and fix a malformed EPUB:</p>
                <ol className="list-decimal pl-6 space-y-2 text-base">
                  <li>
                    Open the EPUB in{" "}
                    <a
                      href="https://calibre-ebook.com"
                      target="_blank"
                      rel="noopener"
                      className="text-accent no-underline hover:underline font-medium"
                    >
                      Calibre
                    </a>{" "}
                    and convert it to EPUB (output format: EPUB&nbsp;2) —
                    Calibre&apos;s conversion pipeline normalizes most
                    structural issues.
                  </li>
                  <li>
                    Run the resulting file through the{" "}
                    <a
                      href="https://validator.idpf.org"
                      target="_blank"
                      rel="noopener"
                      className="text-accent no-underline hover:underline font-medium"
                    >
                      EPUB validator at validator.idpf.org
                    </a>{" "}
                    to confirm it passes validation.
                  </li>
                  <li>Send the Calibre-converted EPUB to your Kindle.</li>
                </ol>
                <p>
                  If the Calibre-converted EPUB still triggers E999, try
                  exporting the source document to PDF and sending the PDF
                  version instead.
                </p>
              </div>
            </div>

            {/* H3: DRM-protected file */}
            <div>
              <h3 className="font-serif text-xl text-text-base mb-3 leading-snug">
                DRM-protected file (silently rejected)
              </h3>
              <div className="text-text-base leading-relaxed space-y-3 text-base">
                <p>
                  Amazon&apos;s Send to Kindle service cannot process
                  DRM-protected files. This includes EPUBs purchased from
                  stores that apply Adobe DRM or proprietary encryption, and
                  PDFs with copy or print restrictions enforced by the
                  publisher. The rejection comes back as E999 without
                  identifying DRM as the cause.
                </p>
                <p>
                  To check whether DRM is the cause: open the file in Calibre.
                  If it shows a padlock icon or reports an error when you
                  attempt to view its full metadata, the file is DRM-protected.
                </p>
                <p>
                  DRM-protected files must be obtained without DRM from the
                  original source — the publisher, library, or store — to be
                  usable with Send to Kindle.
                </p>
              </div>
            </div>

            {/* H3: Transient server error */}
            <div>
              <h3 className="font-serif text-xl text-text-base mb-3 leading-snug">
                Transient server-side conversion failure
              </h3>
              <div className="text-text-base leading-relaxed space-y-3 text-base">
                <p>
                  If your file is within the size limits, passes EPUB
                  validation, and carries no DRM, the E999 error may be a
                  transient failure on Amazon&apos;s conversion servers. These
                  are not related to the file — they are temporary
                  infrastructure failures.
                </p>
                <p>
                  Wait 30&nbsp;minutes and retry. If the error persists after
                  two or three retries across different times of day, the
                  problem is likely the file itself — revisit the size, format,
                  and DRM checks above before trying again.
                </p>
              </div>
            </div>

          </div>
        </section>

        {/* ── H2: Authentication failure ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            Authentication failure (Send to Kindle app)
          </h2>
          <p className="font-sans text-base text-text-muted leading-relaxed mb-8 max-w-2xl">
            An authentication failure means the Send to Kindle app cannot
            verify your Amazon account credentials. This is a separate failure
            class from E999 — it does not indicate a problem with the file
            itself.
          </p>
          <div className="max-w-3xl space-y-10">

            {/* H3: Token expired */}
            <div>
              <h3 className="font-serif text-xl text-text-base mb-3 leading-snug">
                Expired authentication token — sign out and back in
              </h3>
              <div className="text-text-base leading-relaxed space-y-3 text-base">
                <p>
                  The most common cause of authentication failures is an expired
                  session token. Amazon&apos;s app sessions expire without
                  warning, and the error message is the same regardless of
                  cause. To resolve: sign out of the Send to Kindle app
                  completely, then sign back in with your Amazon credentials.
                  Force-close the app before signing out to ensure a clean
                  session state.
                </p>
              </div>
            </div>

            {/* H3: Region mismatch */}
            <div>
              <h3 className="font-serif text-xl text-text-base mb-3 leading-snug">
                Account region mismatch
              </h3>
              <div className="text-text-base leading-relaxed space-y-3 text-base">
                <p>
                  Amazon accounts are region-specific. A US Amazon account
                  cannot deliver content to a Kindle registered in the UK store,
                  and vice versa. If you recently changed your Amazon store
                  region or your device is registered in a different store from
                  your account, Send to Kindle will fail at the authentication
                  step.
                </p>
                <p>
                  Check your device&apos;s registered region at{" "}
                  <a
                    href="https://www.amazon.com/mycd"
                    target="_blank"
                    rel="noopener"
                    className="text-accent no-underline hover:underline font-medium"
                  >
                    amazon.com/mycd
                  </a>{" "}
                  → Devices, and verify it matches your account&apos;s store.
                </p>
              </div>
            </div>

            {/* H3: App version out of date */}
            <div>
              <h3 className="font-serif text-xl text-text-base mb-3 leading-snug">
                App version out of date
              </h3>
              <div className="text-text-base leading-relaxed space-y-3 text-base">
                <p>
                  Older versions of the Send to Kindle app on iOS, Android, and
                  desktop can lose authentication silently after Amazon updates
                  its auth endpoints. Check for available updates in the App
                  Store, Google Play, or your browser&apos;s extension manager.
                  Install any available update and sign in again after updating.
                </p>
              </div>
            </div>

          </div>
        </section>

        {/* ── H2: Silent failures ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            &ldquo;Send to Kindle doesn&apos;t work&rdquo; — silent delivery failures
          </h2>
          <p className="font-sans text-base text-text-muted leading-relaxed mb-8 max-w-2xl">
            Silent failures are cases where Send to Kindle accepts the file —
            no error code shown — but the file never appears on your device.
            These are delivery and account-configuration problems, not
            conversion errors.
          </p>
          <div className="max-w-3xl space-y-10">

            {/* H3: Accepted but never appears */}
            <div>
              <h3 className="font-serif text-xl text-text-base mb-3 leading-snug">
                File accepted but not appearing on Kindle (check library first)
              </h3>
              <div className="text-text-base leading-relaxed space-y-3 text-base">
                <p>
                  Before assuming delivery failed, check your Amazon library at{" "}
                  <a
                    href="https://www.amazon.com/mycd"
                    target="_blank"
                    rel="noopener"
                    className="text-accent no-underline hover:underline font-medium"
                  >
                    amazon.com/mycd
                  </a>
                  . Amazon documents that delivery can take up to 15&nbsp;minutes,
                  and device sync often lags behind server-side delivery. If the
                  file appears in the library but not on the device, toggle
                  Wi-Fi off and back on, or pull down on the Kindle home screen
                  to force a sync.
                </p>
                <p>
                  If the file does not appear in the library after 30&nbsp;minutes,
                  the most likely cause is the approved sender list — Amazon
                  silently drops messages from email addresses not on your
                  Approved Personal Document E-mail List. See{" "}
                  <Link
                    href="/guides/send-to-kindle-not-working"
                    className="text-accent no-underline hover:underline font-medium"
                  >
                    Send to Kindle not working: 7 fixes
                  </Link>{" "}
                  for the full approved-sender walkthrough.
                </p>
              </div>
            </div>

            {/* H3: Wrong destination device */}
            <div>
              <h3 className="font-serif text-xl text-text-base mb-3 leading-snug">
                Wrong destination device selected
              </h3>
              <div className="text-text-base leading-relaxed space-y-3 text-base">
                <p>
                  If your Amazon account has multiple registered Kindles,
                  tablets, or Kindle apps, Send to Kindle may have delivered to
                  a different device than expected. Check your library at{" "}
                  <a
                    href="https://www.amazon.com/mycd"
                    target="_blank"
                    rel="noopener"
                    className="text-accent no-underline hover:underline font-medium"
                  >
                    amazon.com/mycd
                  </a>{" "}
                  — personal documents delivered to one device are visible there
                  and can be re-sent to the correct device from the library.
                </p>
              </div>
            </div>

            {/* H3: kindle.com vs free.kindle.com */}
            <div>
              <h3 className="font-serif text-xl text-text-base mb-3 leading-snug">
                kindle.com vs. free.kindle.com address confusion
              </h3>
              <div className="text-text-base leading-relaxed space-y-3 text-base">
                <p>
                  Each Kindle has two personal document email addresses: one
                  ending in{" "}
                  <code className="font-mono text-sm bg-gray-100 px-1 rounded">
                    @kindle.com
                  </code>{" "}
                  (delivers over Wi-Fi, 3G, or cellular — older accounts may
                  incur a per-file fee) and one ending in{" "}
                  <code className="font-mono text-sm bg-gray-100 px-1 rounded">
                    @free.kindle.com
                  </code>{" "}
                  (delivers over Wi-Fi only, no charge). Sending to the wrong
                  address when the device is not on Wi-Fi can result in
                  non-delivery. Find both addresses at amazon.com/mycd →
                  Preferences → Personal Document Settings.
                </p>
              </div>
            </div>

          </div>
        </section>

        {/* ── When to skip Send to Kindle ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            When to skip Send to Kindle entirely
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              Most E999 errors are fixable through the diagnostic steps above —
              oversized files go through the web uploader, malformed EPUBs are
              normalized by Calibre, and transient errors clear on retry. If you
              have worked through the diagnostic and the error persists, or if
              Amazon&apos;s conversion delivers the file but the result is
              unreadable (garbled columns, missing footnotes, broken headings),
              converting and sideloading is the most reliable exit.
            </p>
            <p>
              <Link
                href="/convert/pdf-to-kfx"
                className="text-accent no-underline hover:underline font-medium"
              >
                leafbind converts PDFs to KFX
              </Link>{" "}
              — Kindle&apos;s native format — using coordinate-based extraction
              to handle multi-column layouts, footnotes as tappable Kindle
              popups, and heading detection for a navigable table of contents.
              Transfer the resulting KFX file via USB to any Kindle released
              since 2018. No Amazon account settings required, no email approval
              list, no 50&nbsp;MB email cap.
            </p>
            <p>
              leafbind is specifically useful for three E999 root causes where
              Amazon cannot help:
            </p>
            <ul className="list-disc pl-6 space-y-2 text-base">
              <li>
                <strong>File too large even for the web uploader:</strong> if
                your PDF still exceeds the 200&nbsp;MB limit after any
                compression, convert and sideload.
              </li>
              <li>
                <strong>Conversion quality failure:</strong> Send to Kindle
                delivers the file but the result is unreadable due to column
                collapse, missing footnotes, or flat headings.
              </li>
              <li>
                <strong>Repeated transient failures:</strong> the error persists
                across multiple retries over several days with no file-level
                cause identified.
              </li>
            </ul>
            <p>
              leafbind <strong>does not help</strong> with DRM-protected files —
              those require a DRM-free version from the original source.
            </p>
            <p className="text-text-muted text-sm">
              Free tier: EPUB output, up to 20&nbsp;MB, 3&nbsp;conversions per
              day, no account required. KFX output (with column detection,
              footnote linking, and heading classification) is available on
              premium plans.{" "}
              <Link
                href="/pricing"
                className="text-accent no-underline hover:underline font-medium"
              >
                See pricing →
              </Link>
            </p>
          </div>
        </section>

        {/* ── FAQ ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-8 leading-snug">
            Frequently asked questions
          </h2>
          <div className="space-y-8 max-w-3xl">
            {faqItems.map((item) => (
              <div key={item.q}>
                <h3 className="font-serif text-xl text-brand mb-2 leading-snug">
                  {item.q}
                </h3>
                <p className="font-sans text-base text-text-base leading-relaxed">
                  {item.a}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* ── Related links ── */}
        <section className="mb-16">
          <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-4">
            Related
          </p>
          <div className="flex flex-wrap gap-4">
            <Link
              href="/guides/send-to-kindle-not-working"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-3 hover:bg-accent/5"
            >
              Send to Kindle not working: 7 fixes →
            </Link>
            <Link
              href="/convert/pdf-to-kfx"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-3 hover:bg-accent/5"
            >
              PDF to KFX converter →
            </Link>
            <Link
              href="/guides/how-to-send-pdf-to-kindle"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-3 hover:bg-accent/5"
            >
              How to send PDFs to Kindle →
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
                Amazon Send to Kindle — supported file types and web uploader
              </a>{" "}
              (last verified 2026-05-22)
            </li>
            <li className="font-sans text-sm text-text-muted">
              <a
                href="https://www.amazon.com/sendtokindle/email"
                target="_blank"
                rel="noopener"
                className="text-accent no-underline hover:underline"
              >
                Amazon Send to Kindle for Email — step-by-step instructions
              </a>{" "}
              (last verified 2026-05-22)
            </li>
            <li className="font-sans text-sm text-text-muted">
              <a
                href="https://www.amazon.com/gp/help/customer/display.html?nodeId=G7QVXG2L5XCUTKLL"
                target="_blank"
                rel="noopener"
                className="text-accent no-underline hover:underline"
              >
                Amazon Help — Personal Document Service
              </a>{" "}
              (last verified 2026-05-22)
            </li>
          </ul>
        </section>

        {/* ── CTA ── */}
        <section className="border-t border-border pt-16 pb-8">
          <h2 className="font-serif text-3xl text-text-base mb-4 leading-snug">
            Try leafbind free
          </h2>
          <p className="font-sans text-base text-text-muted leading-relaxed mb-2 max-w-xl">
            Upload a PDF and convert to EPUB at no cost — 3&nbsp;conversions
            per day, up to 20&nbsp;MB, no account required. KFX output with
            column detection, footnote linking, and heading classification is
            available on premium plans.
          </p>
          <p className="font-sans text-sm text-text-muted leading-relaxed mb-8">
            <Link
              href="/pricing"
              className="text-brand font-medium no-underline hover:underline"
            >
              See pricing
            </Link>{" "}
            — plans start at a single conversion credit with no subscription
            required.
          </p>
          <Link
            href="/convert/pdf-to-kfx"
            className="font-sans inline-block bg-brand text-white font-medium text-base px-8 py-3 rounded-sm no-underline hover:opacity-90"
          >
            Convert a PDF to KFX →
          </Link>

          <div className="mt-12 pt-8 border-t border-border max-w-xl">
            <p className="font-sans text-sm text-text-muted leading-relaxed">
              <span className="font-medium text-text-base">Joe Fowler</span> is
              a developer and technical writer who built leafbind after spending
              an unreasonable amount of time coaxing academic PDFs into something
              readable on a Kindle. He writes about PDF structure, ebook formats,
              and the conversion pipeline at leafbind.io.
            </p>
          </div>
        </section>

      </div>
    </>
  );
}
