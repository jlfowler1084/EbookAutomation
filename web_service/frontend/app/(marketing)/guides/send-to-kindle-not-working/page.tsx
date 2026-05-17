import type { Metadata } from "next";
import Link from "next/link";
import JsonLd from "../../../../components/JsonLd";
import {
  buildArticleSchema,
  buildFAQPageSchema,
} from "../../../../lib/structured-data";

// ISO 8601 with explicit ET offset — Schema.org Article date fields require timezone-qualified datetimes.
const PUBLISHED = "2026-05-17T00:00:00-04:00";
const SLUG = "send-to-kindle-not-working";
const CANONICAL = `https://leafbind.io/guides/${SLUG}`;

export const metadata: Metadata = {
  title: "Send to Kindle Not Working: 7 Fixes (and a Backup That Always Works) — leafbind",
  description:
    "Send to Kindle failing? The most common causes are email approval list misconfiguration, " +
    "file size limits, and format restrictions. 7 step-by-step fixes — plus a KFX sideload fallback.",
  alternates: {
    canonical: CANONICAL,
  },
  openGraph: {
    title: "Send to Kindle Not Working: 7 Fixes (and a Backup That Always Works) — leafbind",
    description:
      "Email not arriving, app crashing, or file rejected? Fix Send to Kindle in 7 steps — " +
      "approved sender list, file size limits, format restrictions, and more.",
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
    title: "Send to Kindle Not Working: 7 Fixes (and a Backup That Always Works) — leafbind",
    description:
      "7 fixes for Send to Kindle not working — approved sender list, file size, format support, " +
      "app quirks, and a KFX sideload backup when Amazon's service keeps failing.",
    images: ["https://leafbind.io/quality/pipeline-headings.png"],
  },
};

// ── FAQ items as single source of truth ────────────────────────────────────

const faqItems = [
  {
    q: "How do I find my Kindle's Send to Kindle email address?",
    a: "On your Kindle device, go to Settings → Your Account → Send-to-Kindle. Your personal document email address is listed there — it ends in @kindle.com. You can also find it at amazon.com → Account → Manage Your Content and Devices → Preferences → Personal Document Settings.",
  },
  {
    q: "What is the file size limit for Send to Kindle?",
    a: "The Send to Kindle web uploader (amazon.com/sendtokindle) accepts files up to 200 MB. The email method historically imposed a 50 MB limit; Amazon's current email page does not explicitly state this limit. USB cable transfers have no size limit. If your file exceeds 200 MB, use USB transfer or split the PDF.",
  },
  {
    q: "Why does my PDF look wrong after Send to Kindle converts it?",
    a: "Amazon converts PDFs to Kindle format, which flattens multi-column layouts, drops footnote links, and may misclassify headings — common problems with academic papers, research PDFs, and technical documents. For PDFs where layout fidelity matters, use leafbind instead: it converts PDF to KFX with column-aware extraction, footnote linking, and heading detection.",
  },
  {
    q: "How do I add an approved email to Send to Kindle?",
    a: "Go to amazon.com → Account → Manage Your Content and Devices → Preferences → Personal Document Settings → Approved Personal Document E-mail List → Add a new approved e-mail address. Only emails from addresses on this list will be delivered to your Kindle. This is the most common cause of Send to Kindle not working.",
  },
  {
    q: "Does the Send to Kindle app work on iPhone?",
    a: "Yes — the Send to Kindle iOS app is available on the App Store. It requires your Kindle personal document email to be configured and the sending email to be on your Approved Personal Document E-mail List. If the app isn't delivering files, force-close and reopen it, then verify your approved sender list in Amazon's account settings.",
  },
  {
    q: "Which file formats does Send to Kindle accept?",
    a: "Send to Kindle currently accepts PDF, DOC, DOCX, RTF, TXT, HTML, PNG, GIF, JPG, BMP, and EPUB (DRM-free only). MOBI is no longer accepted — Amazon removed MOBI support in 2022. For formats not on this list — such as CBZ, ODT, or Pages files — convert to PDF first, then send.",
  },
  {
    q: "How long does Send to Kindle take to deliver a file?",
    a: "Delivery is usually within a few minutes, but Amazon documents that it can take up to 15 minutes. Check your Kindle library on the Amazon website (amazon.com/mycd) rather than waiting for the file to appear on a physical device — library sync can lag behind server-side delivery.",
  },
];

// ── Schemas ────────────────────────────────────────────────────────────────

const articleSchema = buildArticleSchema({
  headline:
    "Send to Kindle not working: 7 fixes and a backup that always works",
  description:
    "Seven fixes for Send to Kindle not working — approved sender list misconfiguration, " +
    "50 MB file size limits, unsupported formats, delivery delays, Amazon service status, " +
    "app-specific quirks, and email domain blocking — plus a KFX sideload fallback.",
  image: "https://leafbind.io/quality/pipeline-headings.png",
  datePublished: PUBLISHED,
  dateModified: PUBLISHED,
  url: CANONICAL,
  author: { name: "Joe Fowler", url: "https://github.com/jlfowler1084" },
});

const faqSchema = buildFAQPageSchema(faqItems);

// ── Page ───────────────────────────────────────────────────────────────────

export default function SendToKindleNotWorking() {
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
          Send to Kindle Not Working: 7 Fixes (and a Backup That Always Works)
        </h1>
        <p className="font-sans text-lg text-text-muted leading-relaxed max-w-2xl">
          If Send to Kindle isn&apos;t working, the most common causes are
          email-approval-list misconfiguration, file size limits, and
          Amazon&apos;s intermittent server issues — but if Amazon&apos;s native
          flow keeps failing,{" "}
          <Link href="/convert/pdf-to-kfx" className="text-accent no-underline hover:underline font-medium">
            leafbind converts PDFs to KFX
          </Link>{" "}
          you can sideload directly, bypassing Send to Kindle entirely.
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

        {/* ── What's not working? ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            What&apos;s not working?
          </h2>
          <p className="font-sans text-base text-text-muted leading-relaxed mb-6 max-w-2xl">
            Send to Kindle failures fall into four categories. Identify yours first — the fixes are different.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-2xl">
            {[
              {
                label: "Email not arriving on Kindle",
                desc: "You sent the file but it never appeared in your library. Almost always an approved sender issue (Fix #1) or delivery delay (Fix #4).",
              },
              {
                label: "File rejected at send time",
                desc: "You got a bounce email from Amazon or the app showed an error. Check file size (Fix #2) and format (Fix #3).",
              },
              {
                label: "App crashing or not responding",
                desc: "The Send to Kindle desktop extension or mobile app is failing before sending. See Fix #6 for app-specific steps.",
              },
              {
                label: "File arrives but looks wrong",
                desc: "Text is garbled, columns are merged, or footnotes are missing. Amazon converts PDFs in ways that break academic and technical documents — see the backup option at the end of this guide.",
              },
            ].map((item) => (
              <div
                key={item.label}
                className="border border-border rounded-sm p-4 bg-white"
              >
                <p className="font-sans font-medium text-text-base text-sm mb-1">
                  {item.label}
                </p>
                <p className="font-sans text-sm text-text-muted leading-relaxed">
                  {item.desc}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* ── Fix #1: Approved sender list ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            Fix #1: Check your approved sender list
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              This is the most common cause of Send to Kindle failures.
              Amazon&apos;s service only delivers personal documents from email
              addresses you have explicitly approved. If you send from a new
              address, a work email, or any address not on the list, Amazon
              silently drops the message — no bounce email, no notification on
              the device.
            </p>
            <p>To add your sending address to the approved list:</p>
            <ol className="list-decimal pl-6 space-y-2 text-base">
              <li>Go to <a href="https://www.amazon.com/mycd" target="_blank" rel="noopener" className="text-accent no-underline hover:underline font-medium">amazon.com/mycd</a> (Manage Your Content and Devices)</li>
              <li>Click <strong>Preferences</strong></li>
              <li>Scroll to <strong>Personal Document Settings</strong></li>
              <li>Under <strong>Approved Personal Document E-mail List</strong>, click <strong>Add a new approved e-mail address</strong></li>
              <li>Enter the exact address you send from and save</li>
            </ol>
            <p>
              After adding the address, resend the file. Amazon does not
              retroactively deliver messages that were blocked before you added
              the address.
            </p>
          </div>
        </section>

        {/* ── Fix #2: File size limits ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            Fix #2: Check file size limits
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              Amazon&apos;s{" "}
              <a
                href="https://www.amazon.com/sendtokindle"
                target="_blank"
                rel="noopener"
                className="text-accent no-underline hover:underline font-medium"
              >
                Send to Kindle web uploader
              </a>{" "}
              accepts files up to <strong>200 MB</strong>. The email method
              historically capped attachments at 50 MB; Amazon&apos;s current
              email documentation no longer explicitly states this limit.
              USB cable transfers have no size restriction.
            </p>
            <p>If your file is too large, you have two options:</p>
            <ul className="list-disc pl-6 space-y-2 text-base">
              <li>
                <strong>Use the web uploader.</strong> Go to{" "}
                <a
                  href="https://www.amazon.com/sendtokindle"
                  target="_blank"
                  rel="noopener"
                  className="text-accent no-underline hover:underline font-medium"
                >
                  amazon.com/sendtokindle
                </a>{" "}
                and upload the file directly — the 200 MB limit covers most PDFs.
              </li>
              <li>
                <strong>Transfer via USB.</strong> Connect your Kindle with a
                USB cable, open the device in File Explorer, and copy the file
                into the <code className="font-mono text-sm bg-gray-100 px-1 rounded">Documents</code> folder. No size
                limit applies to USB transfers.
              </li>
            </ul>
          </div>
        </section>

        {/* ── Fix #3: File format ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            Fix #3: Verify the file format
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              Send to Kindle accepts a specific set of file formats. If you
              are sending a format not on this list, Amazon will reject it:
            </p>
            <ul className="list-disc pl-6 space-y-1 text-base">
              <li>PDF</li>
              <li>DOC, DOCX (Microsoft Word)</li>
              <li>RTF</li>
              <li>TXT</li>
              <li>HTML, HTM</li>
              <li>EPUB (DRM-free only)</li>
              <li>PNG, GIF, JPG, JPEG, BMP (images)</li>
            </ul>
            <p>
              Formats <strong>no longer accepted</strong>: MOBI — Amazon removed
              MOBI support in 2022. If you have a .mobi file, open it in Calibre
              and export to EPUB or PDF before sending.
            </p>
            <p>
              Formats commonly confused as supported but not accepted: CBZ
              (comic archives), ODT (LibreOffice), Pages (Apple), AZW3 (Kindle
              store books with DRM), and DRM-protected EPUB3 files. If your file
              is in an unsupported format, convert it to PDF first.
            </p>
          </div>
        </section>

        {/* ── Fix #4: Delivery delays ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            Fix #4: Check email delivery delays
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              Amazon documents that Send to Kindle delivery can take{" "}
              <strong>up to 15 minutes</strong>. If you sent a file recently
              and it has not appeared, wait before assuming something is broken.
            </p>
            <p>
              One common mistake: checking only the physical Kindle device
              rather than your Amazon library. Device sync can lag behind
              server-side delivery. Check your library at{" "}
              <a
                href="https://www.amazon.com/mycd"
                target="_blank"
                rel="noopener"
                className="text-accent no-underline hover:underline font-medium"
              >
                amazon.com/mycd
              </a>{" "}
              — if the file appears there but not on your device, the issue is
              device sync rather than delivery failure. Force a sync by going
              to your Kindle&apos;s home screen and pulling down to refresh, or
              toggling Wi-Fi off and back on.
            </p>
          </div>
        </section>

        {/* ── Fix #5: Amazon service status ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            Fix #5: Check Amazon&apos;s service status
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              Amazon&apos;s Send to Kindle service occasionally has outages or
              degraded performance that affect delivery. If you have verified
              your approved sender list and file format, and files are still not
              arriving after 15+ minutes, Amazon&apos;s service may be
              experiencing issues.
            </p>
            <p>
              Check Amazon&apos;s customer service help page and look for any
              notices about personal document delivery. You can also check
              third-party services like Downdetector or search recent Reddit
              posts in r/kindle — widespread issues typically surface there
              quickly. If Amazon is having a service disruption, the only option
              is to wait or use USB transfer in the meantime.
            </p>
          </div>
        </section>

        {/* ── Fix #6: App-specific issues ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            Fix #6: App-specific issues
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-6 text-base">
            <div>
              <h3 className="font-serif text-xl text-text-base mb-2 leading-snug">
                iOS and Android (mobile app)
              </h3>
              <p>
                If the Send to Kindle mobile app is crashing or not sending
                files, force-close the app completely and reopen it. On iOS:
                swipe up from the bottom edge and swipe the app card away. On
                Android: open Recent Apps and dismiss Send to Kindle, then
                relaunch. If the problem persists after a force-close, check
                for app updates in the App Store or Google Play — Amazon
                periodically releases fixes for known app issues.
              </p>
              <p className="mt-3">
                iOS-specific quirk: the Share Sheet extension (the Send to
                Kindle option in iOS&apos;s share menu) occasionally stops
                responding after an iOS update. If the Share Sheet entry is
                missing or grayed out, uninstall and reinstall the Send to
                Kindle app to re-register the extension.
              </p>
            </div>
            <div>
              <h3 className="font-serif text-xl text-text-base mb-2 leading-snug">
                Desktop (browser extension)
              </h3>
              <p>
                The Send to Kindle browser extension for Chrome and Edge
                occasionally breaks after browser updates. If the extension
                toolbar button is unresponsive or produces errors, remove the
                extension from your browser&apos;s extension settings and
                reinstall it from the Chrome Web Store or Microsoft Edge
                Add-ons page. Re-entering your Amazon account credentials
                after reinstall is normal.
              </p>
            </div>
          </div>
        </section>

        {/* ── Fix #7: Email domain blocking ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            Fix #7: Approved sender email domain
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              Some email providers and corporate email servers block outbound
              email to Amazon&apos;s kindle.com domain as a spam-prevention
              measure. If you are sending from a work, school, or custom domain
              email address, the email may be blocked before it reaches Amazon.
            </p>
            <p>
              Test by sending from a personal Gmail or Outlook account instead.
              If delivery works from Gmail but not from your work address, the
              issue is your email provider&apos;s outbound filtering — not your
              Amazon settings. In that case, the practical workaround is to
              either send from Gmail or use USB transfer.
            </p>
            <p>
              If you must send from your work address, contact your IT
              department and ask them to whitelist outbound SMTP to{" "}
              <code className="font-mono text-sm bg-gray-100 px-1 rounded">kindle.com</code>.
            </p>
          </div>
        </section>

        {/* ── Backup: leafbind ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            If nothing works: the backup that always works
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              If you have worked through all seven fixes and Send to Kindle
              is still not delivering your file — or if it is delivering but
              the converted result is not readable — sideloading is the most
              reliable alternative. It bypasses Amazon&apos;s email delivery
              system entirely.
            </p>
            <p>
              <Link
                href="/convert/pdf-to-kfx"
                className="text-accent no-underline hover:underline font-medium"
              >
                leafbind converts PDFs to KFX
              </Link>{" "}
              — Kindle&apos;s native format. Unlike Send to Kindle&apos;s
              conversion, leafbind uses coordinate-based extraction to handle
              multi-column layouts, preserves footnotes as tappable Kindle
              popups, and detects headings for a navigable table of contents.
              The resulting KFX file can be transferred directly to any Kindle
              device released since 2018 via USB — no email involved.
            </p>
            <p>
              The process: upload your PDF at{" "}
              <Link
                href="/convert/pdf-to-kfx"
                className="text-accent no-underline hover:underline font-medium"
              >
                leafbind.io/convert/pdf-to-kfx
              </Link>
              , download the KFX file, connect your Kindle via USB, and copy
              the file into the Documents folder. The file appears in your
              library immediately. No Amazon account settings required, no
              email approval list, no 50 MB limit for the sideload step itself.
            </p>
            <p className="text-text-muted text-sm">
              Free tier: EPUB output, up to 20 MB, 3 conversions per day, no
              account required. KFX output (with column detection, footnote
              linking, and heading classification) is available on premium
              plans.{" "}
              <Link
                href="/convert/pdf-to-kfx"
                className="text-accent no-underline hover:underline font-medium"
              >
                See conversion options →
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
            <Link
              href="/guides/pdf-to-kfx-for-kindle-scribe"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-3 hover:bg-accent/5"
            >
              PDF to KFX for Kindle Scribe →
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
              (last verified 2026-05-17)
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
              (last verified 2026-05-17)
            </li>
          </ul>
        </section>

        {/* ── CTA ── */}
        <section className="border-t border-border pt-16 pb-8">
          <h2 className="font-serif text-3xl text-text-base mb-4 leading-snug">
            Try leafbind free
          </h2>
          <p className="font-sans text-base text-text-muted leading-relaxed mb-2 max-w-xl">
            Upload a PDF and convert to EPUB at no cost — 3 conversions per day,
            up to 20 MB, no account required. KFX output with column detection,
            footnote linking, and heading classification is available on premium
            plans.
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
