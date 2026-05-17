import type { Metadata } from "next";
import Link from "next/link";
import JsonLd from "../../../../components/JsonLd";
import {
  buildArticleSchema,
  buildFAQPageSchema,
  buildHowToSchema,
} from "../../../../lib/structured-data";

// ISO 8601 with explicit ET offset — Schema.org Article date fields require timezone-qualified datetimes.
const PUBLISHED = "2026-05-17T00:00:00-04:00";
const SLUG = "how-to-send-pdf-to-kindle";
const CANONICAL = `https://leafbind.io/guides/${SLUG}`;

export const metadata: Metadata = {
  title: "How to Send PDFs (and EPUBs, Docs, MOBI) to Kindle: Every Method — leafbind",
  description:
    "Four methods for sending PDFs and other files to any Kindle device: Send-to-Kindle email, " +
    "the mobile app, USB cable, and converting to KFX for sideloading. Step-by-step for each.",
  alternates: {
    canonical: CANONICAL,
  },
  openGraph: {
    title: "How to Send PDFs (and EPUBs, Docs, MOBI) to Kindle: Every Method — leafbind",
    description:
      "Send-to-Kindle email, the app, USB cable, or convert and sideload — every method for " +
      "getting PDFs, EPUBs, and documents onto your Kindle, with the tradeoffs explained.",
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
    title: "How to Send PDFs (and EPUBs, Docs, MOBI) to Kindle: Every Method — leafbind",
    description:
      "Every method for sending files to Kindle: email, app, USB, and KFX sideloading. " +
      "Covers PDFs, EPUBs, MOBI, DOC/DOCX — with file size limits and format support explained.",
    images: ["https://leafbind.io/quality/pipeline-headings.png"],
  },
};

// ── FAQ items as single source of truth ────────────────────────────────────

const faqItems = [
  {
    q: "Can I send PDFs to Kindle for free?",
    a: "Yes. The Send-to-Kindle email method is free for all Amazon account holders. You email your PDF to your Kindle personal document address — found in Amazon Account → Manage Your Content and Devices → Preferences → Personal Document Settings — and it appears in your library. Amazon converts the PDF to Kindle format during delivery. Data charges may apply if your Kindle downloads over mobile network rather than Wi-Fi.",
  },
  {
    q: "What is the file size limit for Send to Kindle?",
    a: "Send to Kindle via email accepts files up to 50 MB. Via the Send to Kindle app on iOS and Android, the limit is also 50 MB. USB cable transfers have no size limit — you can copy files of any size directly to the Kindle's Documents folder. If your file exceeds 50 MB, USB transfer is the most practical option.",
  },
  {
    q: "Can I send EPUB files to Kindle?",
    a: "Yes. Amazon added native EPUB support in 2022. You can send EPUB files via the Send-to-Kindle email method, the mobile app, or USB cable. EPUB files with DRM (copy protection from commercial ebook stores) cannot be sent — only DRM-free EPUB files are accepted. For USB transfers, EPUB files open directly in the Kindle app without conversion.",
  },
  {
    q: "Why does my PDF look different after sending to Kindle?",
    a: "Amazon converts PDFs to Kindle format during delivery, which strips the original layout. Multi-column text gets interleaved line by line, footnotes are detached from citations or dropped, and headings often lose their hierarchy. This affects academic papers, research PDFs, and technical documents the most. For PDFs where layout matters, convert to KFX using leafbind instead — it uses coordinate-based extraction to handle columns and footnotes correctly.",
  },
  {
    q: "How do I send a PDF to Kindle Scribe specifically?",
    a: "The same four methods apply to Kindle Scribe: Send-to-Kindle email to your Scribe's personal document address, the Send-to-Kindle app, USB-C cable transfer (copy to the Documents folder), or convert to KFX with leafbind and sideload via USB. For academic PDFs, the KFX sideload method produces the best result on Scribe — native KFX format uses the Scribe's full layout engine with navigable chapters and tappable footnotes.",
  },
  {
    q: "How do I send a PDF to Kindle from my iPhone?",
    a: "Install the Send to Kindle app from the App Store. Open any PDF in the Files app or another app, tap Share, then choose Send to Kindle from the share sheet. You will be prompted to select a destination device and whether to convert to Kindle format. The file is delivered to your Kindle library within a few minutes, subject to the 50 MB limit and approved sender list requirements.",
  },
  {
    q: "Can I transfer a PDF to Kindle without email?",
    a: "Yes — USB cable transfer requires no email or Amazon account interaction. Connect your Kindle with its USB cable, open the device in File Explorer (Windows) or Finder (Mac), and copy the PDF into the Documents folder. On Windows, the Kindle appears as a removable drive under This PC. The file appears in your library immediately after you safely eject the device.",
  },
  {
    q: "What file formats can I send to Kindle?",
    a: "Send-to-Kindle (email and app) accepts: PDF, EPUB (DRM-free), DOC/DOCX, RTF, TXT, HTML, MOBI. USB cable accepts: PDF, EPUB, MOBI, AZW3, TXT, and KFX. Amazon's full list of supported personal document types is at amazon.com/sendtokindle in the Help section — check there for the most current version, as Amazon periodically updates format support.",
  },
  {
    q: "How long does it take for a file to appear on my Kindle after sending?",
    a: "Delivery via Send-to-Kindle email or app is usually within a few minutes. Amazon documents that it can take up to 15 minutes. If the file has not appeared after 15 minutes, check your Amazon library at amazon.com/mycd — the file may be in your library but not yet synced to the physical device. Force a sync by toggling Wi-Fi off and on or by restarting the Kindle. USB transfers appear immediately.",
  },
];

// ── Schemas ────────────────────────────────────────────────────────────────

const articleSchema = buildArticleSchema({
  headline: "How to send PDFs (and EPUBs, Docs, MOBI) to Kindle: every method",
  description:
    "A complete guide to all four methods for sending files to any Kindle device — " +
    "Send-to-Kindle email, the mobile app, USB cable, and KFX sideloading via leafbind — " +
    "with file size limits, format support, and quality tradeoffs explained for each.",
  image: "https://leafbind.io/quality/pipeline-headings.png",
  datePublished: PUBLISHED,
  dateModified: PUBLISHED,
  url: CANONICAL,
  author: { name: "Joe Fowler", url: "https://github.com/jlfowler1084" },
});

const faqSchema = buildFAQPageSchema(faqItems);

const howToSchema = buildHowToSchema({
  name: "How to send a PDF to Kindle using the Send-to-Kindle email method",
  step: [
    {
      name: "Find your Kindle email address",
      text: "Go to amazon.com → Account → Manage Your Content and Devices → Preferences → Personal Document Settings. Your Kindle personal document address is listed there — it ends in @kindle.com. Each Kindle device has its own address.",
    },
    {
      name: "Add your sending address to the approved list",
      text: "On the same Personal Document Settings page, find Approved Personal Document E-mail List and add the email address you will send from. Amazon rejects documents from unapproved addresses silently — this is the most common reason Send-to-Kindle fails.",
    },
    {
      name: "Attach your PDF or file to an email",
      text: "Create a new email, attach the file (up to 50 MB), and leave the subject line blank or type 'convert' if you want Amazon to convert the file to Kindle format. Leaving it blank also triggers conversion for PDF files.",
    },
    {
      name: "Send the email to your Kindle address",
      text: "Address the email to your Kindle personal document address (the @kindle.com address from step 1) and send. Amazon receives the email, converts the file, and queues it for delivery.",
    },
    {
      name: "Check your Amazon library",
      text: "Open amazon.com/mycd to confirm the file appears in your library. Delivery is usually within a few minutes, up to 15 minutes according to Amazon's documentation. Check the library on the website first — device sync can lag behind server-side delivery.",
    },
    {
      name: "Sync your Kindle device",
      text: "On your Kindle, go to the home screen and pull down to sync, or toggle Wi-Fi off and on. The file appears in your library under Docs or Books depending on file type. If it is not appearing, force a sync by going to Settings → Sync Your Kindle.",
    },
  ],
});

// ── Page ───────────────────────────────────────────────────────────────────

export default function HowToSendPdfToKindle() {
  return (
    <>
      <JsonLd schema={articleSchema} />
      <JsonLd schema={faqSchema} />
      <JsonLd schema={howToSchema} />

      {/* Page header */}
      <div className="py-12 md:py-16 border-b border-border mb-16">
        <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-5">
          Kindle transfer guide
        </p>
        <h1 className="font-serif text-3xl sm:text-4xl md:text-5xl lg:text-6xl leading-tight text-text-base mb-6 max-w-3xl">
          How to Send PDFs (and EPUBs, Docs, MOBI) to Kindle: Every Method
        </h1>
        <p className="font-sans text-lg text-text-muted leading-relaxed max-w-2xl">
          To send a PDF to Kindle, you have four main options: Send-to-Kindle
          email, the Send-to-Kindle mobile app, USB cable transfer, or convert
          to KFX and sideload. All four work — but they differ on file size
          limits, format support, and how well they preserve multi-column
          layouts, footnotes, and heading structure in the converted result.
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

        {/* ── Decision table ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            Which method should you use?
          </h2>
          <p className="font-sans text-base text-text-muted leading-relaxed mb-6 max-w-2xl">
            The right method depends on your file type and what you need the result to look like.
            Send-to-Kindle email and the app are the most convenient — no cable required — but
            Amazon converts your file during delivery, which breaks multi-column layouts and
            drops footnote links in academic PDFs. USB cable transfers the original file without
            conversion but requires a cable. KFX sideloading via leafbind gives the best result
            for complex PDFs at the cost of an extra conversion step.
          </p>

          {/* Standalone AI-citation-ready passage */}
          <div className="bg-surface border border-border rounded-sm p-6 mb-8 max-w-3xl">
            <p className="font-sans text-sm font-medium text-text-muted uppercase tracking-widest font-mono mb-3">
              Quick reference
            </p>
            <p className="font-sans text-base text-text-base leading-relaxed">
              For a simple PDF — one column, no footnotes — Send-to-Kindle email
              is the fastest option: email the file to your Kindle address, it
              arrives in minutes. For academic papers with two-column layouts or
              tappable footnote links, Send-to-Kindle&apos;s conversion strips that
              structure; use USB cable to transfer the original file, or convert
              to KFX with leafbind first. For EPUBs and MOBI files,
              Send-to-Kindle email and the app both work natively. For files
              over 50 MB, only USB cable transfer works without size restrictions.
            </p>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm font-sans border-collapse min-w-[560px]">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left font-medium text-text-muted py-3 pr-4 pl-0 w-28">File type</th>
                  <th className="text-center font-medium text-text-muted py-3 px-4">
                    <span className="block">Send-to-Kindle</span>
                    <span className="block font-normal">Email</span>
                  </th>
                  <th className="text-center font-medium text-text-muted py-3 px-4">
                    <span className="block">Send-to-Kindle</span>
                    <span className="block font-normal">App</span>
                  </th>
                  <th className="text-center font-medium text-text-muted py-3 px-4">
                    <span className="block">USB</span>
                    <span className="block font-normal">Cable</span>
                  </th>
                  <th className="text-center font-medium text-text-muted py-3 px-4">
                    <span className="block">leafbind</span>
                    <span className="block font-normal">→ KFX</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {[
                  {
                    type: "PDF",
                    email: "✓",
                    emailNote: "50 MB max, converted",
                    app: "✓",
                    appNote: "50 MB max, converted",
                    usb: "✓",
                    usbNote: "original file, no limit",
                    leafbind: "✓",
                    leafbindNote: "→ KFX, best quality",
                  },
                  {
                    type: "EPUB",
                    email: "✓",
                    emailNote: "DRM-free only",
                    app: "✓",
                    appNote: "DRM-free only",
                    usb: "✓",
                    usbNote: "DRM-free, native",
                    leafbind: "—",
                    leafbindNote: "",
                  },
                  {
                    type: "DOC / DOCX",
                    email: "✓",
                    emailNote: "converted",
                    app: "✓",
                    appNote: "converted",
                    usb: "⚠",
                    usbNote: "limited support",
                    leafbind: "—",
                    leafbindNote: "",
                  },
                  {
                    type: "MOBI",
                    email: "✓",
                    emailNote: "deprecated format",
                    app: "✓",
                    appNote: "deprecated format",
                    usb: "✓",
                    usbNote: "native",
                    leafbind: "—",
                    leafbindNote: "",
                  },
                  {
                    type: "AZW3",
                    email: "—",
                    emailNote: "",
                    app: "—",
                    appNote: "",
                    usb: "✓",
                    usbNote: "native",
                    leafbind: "—",
                    leafbindNote: "",
                  },
                  {
                    type: "TXT / RTF",
                    email: "✓",
                    emailNote: "converted",
                    app: "✓",
                    appNote: "converted",
                    usb: "✓",
                    usbNote: "basic reading",
                    leafbind: "—",
                    leafbindNote: "",
                  },
                ].map((row) => (
                  <tr key={row.type} className="hover:bg-surface/50">
                    <td className="py-3 pr-4 pl-0 font-medium text-text-base">{row.type}</td>
                    <td className="py-3 px-4 text-center">
                      <span className={`block font-medium ${row.email === "✓" ? "text-brand" : row.email === "⚠" ? "text-text-muted" : "text-text-muted"}`}>
                        {row.email}
                      </span>
                      {row.emailNote && (
                        <span className="block text-xs text-text-muted mt-0.5">{row.emailNote}</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span className={`block font-medium ${row.app === "✓" ? "text-brand" : row.app === "⚠" ? "text-text-muted" : "text-text-muted"}`}>
                        {row.app}
                      </span>
                      {row.appNote && (
                        <span className="block text-xs text-text-muted mt-0.5">{row.appNote}</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span className={`block font-medium ${row.usb === "✓" ? "text-brand" : row.usb === "⚠" ? "text-text-muted" : "text-text-muted"}`}>
                        {row.usb}
                      </span>
                      {row.usbNote && (
                        <span className="block text-xs text-text-muted mt-0.5">{row.usbNote}</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span className={`block font-medium ${row.leafbind === "✓" ? "text-brand" : "text-text-muted"}`}>
                        {row.leafbind}
                      </span>
                      {row.leafbindNote && (
                        <span className="block text-xs text-text-muted mt-0.5">{row.leafbindNote}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="font-sans text-xs text-text-muted mt-3">
            ✓ supported &nbsp;·&nbsp; ⚠ limited support &nbsp;·&nbsp; — not applicable.
            Amazon&apos;s{" "}
            <a
              href="https://www.amazon.com/sendtokindle"
              target="_blank"
              rel="noopener"
              className="text-accent no-underline hover:underline"
            >
              Send-to-Kindle help page
            </a>{" "}
            lists the current supported personal document types.
          </p>
        </section>

        {/* ── Method 1: Send-to-Kindle Email ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            Method 1 — Send-to-Kindle Email
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              Every Amazon account includes a Send-to-Kindle email address — a personal{" "}
              <code className="font-mono text-sm bg-gray-100 px-1 rounded">@kindle.com</code>{" "}
              address that accepts personal documents. Email a file to that address,
              and it appears in your Kindle library within minutes. No software to
              install, no cable required.
            </p>
            <p>
              Before the first use, you must add your sending email address to
              Amazon&apos;s Approved Personal Document E-mail List. Amazon silently
              drops documents from unapproved addresses — no bounce email, no
              notification. To add an address: go to{" "}
              <a
                href="https://www.amazon.com/mycd"
                target="_blank"
                rel="noopener"
                className="text-accent no-underline hover:underline font-medium"
              >
                amazon.com/mycd
              </a>{" "}
              → Preferences → Personal Document Settings → Approved Personal
              Document E-mail List.
            </p>
          </div>

          <div className="mt-8 space-y-10 max-w-3xl">
            <div>
              <h3 className="font-serif text-2xl text-text-base mb-3 leading-snug">
                For PDFs
              </h3>
              <div className="text-text-base leading-relaxed space-y-3 text-base">
                <p>
                  Attach the PDF to an email and send it to your Kindle address.
                  Leave the subject blank — Amazon converts PDFs to Kindle format
                  automatically during delivery. The 50 MB size limit applies.
                </p>
                <p>
                  Important: Amazon&apos;s conversion strips PDF layout. Multi-column
                  text gets interleaved — both columns read line by line as they
                  appeared on the printed page, not column by column. Footnotes
                  are detached from their in-text citations. Section headings often
                  lose their hierarchy, removing the navigable chapter list. For
                  simple single-column PDFs (books, reports, prose), the result
                  is usable. For academic papers with two-column layouts and
                  footnotes, the conversion degrades readability significantly.
                </p>
                <p>
                  If you need the PDF to read correctly on Kindle — particularly a
                  research paper, journal article, or technical document — the
                  Send-to-Kindle email method is not the right choice. See{" "}
                  <Link
                    href="/convert/pdf-to-kfx"
                    className="text-accent no-underline hover:underline font-medium"
                  >
                    Method 4 (KFX conversion)
                  </Link>{" "}
                  for the alternative.
                </p>
              </div>
            </div>

            <div>
              <h3 className="font-serif text-2xl text-text-base mb-3 leading-snug">
                For EPUBs
              </h3>
              <div className="text-text-base leading-relaxed space-y-3 text-base">
                <p>
                  Amazon added native EPUB support in 2022. Attach a DRM-free EPUB
                  to an email and send it to your Kindle address — it delivers as
                  an EPUB, not converted to AZW. EPUB files with DRM (copy
                  protection from commercial ebook stores) are not accepted; only
                  DRM-free files work.
                </p>
                <p>
                  The 50 MB limit applies to EPUB files. Most EPUB files are well
                  under this limit — typical ebooks are 1-5 MB.
                </p>
              </div>
            </div>

            <div>
              <h3 className="font-serif text-2xl text-text-base mb-3 leading-snug">
                For documents (DOC / DOCX / TXT / RTF)
              </h3>
              <div className="text-text-base leading-relaxed space-y-3 text-base">
                <p>
                  Microsoft Word files (DOC, DOCX), plain text (TXT), and RTF
                  are all accepted. Amazon converts them to Kindle format for
                  delivery. For Word documents, formatting is preserved reasonably
                  well — paragraph styles, bold, italic, and lists carry over.
                  Complex tables and precise layout do not.
                </p>
              </div>
            </div>

            <div>
              <h3 className="font-serif text-2xl text-text-base mb-3 leading-snug">
                For MOBI files
              </h3>
              <div className="text-text-base leading-relaxed space-y-3 text-base">
                <p>
                  MOBI is an older Kindle format that Amazon deprecated in 2022 for
                  newer devices, but Send-to-Kindle email still accepts MOBI files
                  and delivers them. If you have MOBI files from older Calibre
                  conversions or older ebook purchases, they will still work via
                  email delivery on supported devices.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* ── Method 2: Send-to-Kindle App ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            Method 2 — Send-to-Kindle App
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              Amazon&apos;s Send-to-Kindle app is available for iOS and Android and
              works as a share sheet extension. On iOS: open a PDF in any app,
              tap Share, then choose Send to Kindle. On Android: open a file in
              Files or another app, tap Share, then Send to Kindle.
            </p>
            <p>
              The app delivers the same formats as the email method (PDF, EPUB, DOC,
              TXT, MOBI) with the same 50 MB limit and the same conversion behavior
              for PDFs. The main advantage over email is convenience — no email client
              required, and the share sheet integration works from any app that can
              share files.
            </p>
            <p>
              The app requires your sending device&apos;s Amazon account email address to
              be on your Approved Personal Document E-mail List, the same as the email
              method. If the app is sending but files are not appearing, this is the
              first thing to check.
            </p>
            <p>
              The desktop Send-to-Kindle extension for Chrome and Edge works by
              right-clicking a PDF link in the browser and choosing &ldquo;Send to
              Kindle&rdquo; — it opens a dialog to select your device. This is useful for
              papers found through Google Scholar or publisher sites.
            </p>
          </div>
        </section>

        {/* ── Method 3: USB cable ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            Method 3 — USB cable transfer
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              Connecting your Kindle via USB and copying files directly is the
              simplest method for files that don&apos;t need conversion — and the only
              method without a file size limit.
            </p>

            <h3 className="font-serif text-xl text-text-base pt-2 leading-snug">
              On Windows
            </h3>
            <ol className="list-decimal pl-6 space-y-2 text-base">
              <li>Connect your Kindle with its USB cable (USB-C for Scribe, Paperwhite 5+; micro-USB for older models)</li>
              <li>Open File Explorer — the Kindle appears as a removable drive under This PC</li>
              <li>Open the{" "}
                <code className="font-mono text-sm bg-gray-100 px-1 rounded">Documents</code>{" "}
                folder on the Kindle drive</li>
              <li>Copy your PDF, EPUB, MOBI, or KFX file into the Documents folder</li>
              <li>Safely eject the Kindle using the Safely Remove Hardware option in the taskbar</li>
              <li>The file appears in your Kindle library immediately after ejection</li>
            </ol>

            <h3 className="font-serif text-xl text-text-base pt-4 leading-snug">
              On Mac
            </h3>
            <ol className="list-decimal pl-6 space-y-2 text-base">
              <li>Connect via USB — the Kindle appears on the Desktop or in Finder under Locations</li>
              <li>Open the{" "}
                <code className="font-mono text-sm bg-gray-100 px-1 rounded">Documents</code>{" "}
                folder on the Kindle volume</li>
              <li>Drag your file into the Documents folder</li>
              <li>Eject using the eject button in Finder before disconnecting</li>
            </ol>

            <p className="pt-2">
              USB cable transfers the original file without any conversion — the
              PDF arrives as a PDF, not reprocessed. For PDFs, this means the same
              layout limitations apply when Kindle renders it: multi-column text
              and footnotes will have the same problems as the email method. The
              difference is that USB transfer bypasses the 50 MB limit and
              requires no internet connection or Amazon account interaction.
            </p>
            <p>
              For the best results with a complex PDF, convert it to KFX using
              leafbind first (see Method 4), then transfer the KFX file via USB.
              KFX files transferred via USB use Kindle&apos;s native layout engine —
              the column detection, footnote linking, and heading structure from
              the conversion are fully preserved.
            </p>
          </div>
        </section>

        {/* ── Method 4: leafbind KFX conversion ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            Method 4 — Convert to KFX and sideload via leafbind
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              If you need a PDF to read correctly on Kindle — multi-column layouts,
              tappable footnote links, navigable chapter structure — converting to
              KFX before transferring produces the best result. KFX is Kindle&apos;s
              native format; a properly structured KFX file uses the device&apos;s full
              layout engine rather than falling back to a PDF viewer.
            </p>
            <p>
              <Link
                href="/convert/pdf-to-kfx"
                className="text-accent no-underline hover:underline font-medium"
              >
                leafbind converts PDFs to KFX
              </Link>{" "}
              using coordinate-based text extraction — the same approach that
              distinguishes left column from right column in a two-column academic
              paper, rather than reading the text stream in the interleaved order
              that Send-to-Kindle and Calibre both produce.
            </p>

            <h3 className="font-serif text-xl text-text-base pt-2 leading-snug">
              How to convert and sideload
            </h3>
            <ol className="list-decimal pl-6 space-y-2 text-base">
              <li>
                Upload your PDF at{" "}
                <Link
                  href="/convert/pdf-to-kfx"
                  className="text-accent no-underline hover:underline font-medium"
                >
                  leafbind.io/convert/pdf-to-kfx
                </Link>
              </li>
              <li>Select KFX as the output format (premium conversion)</li>
              <li>Download the converted KFX file</li>
              <li>Connect your Kindle via USB and copy the KFX file into the Documents folder</li>
              <li>Eject and open the file on your Kindle — it appears in the library under Books</li>
            </ol>

            <p>
              The converted KFX includes a navigable table of contents from
              detected headings, tappable footnote popups for superscript citations,
              and correct column ordering for multi-column source PDFs. The conversion
              report after step 2 shows how many headings were detected and whether
              any pages required OCR fallback.
            </p>
            <p className="text-text-muted text-sm">
              Free tier: EPUB output, up to 20 MB, 3 conversions per day, no account
              required. KFX output is available on premium plans.{" "}
              <Link
                href="/pricing"
                className="text-accent no-underline hover:underline font-medium"
              >
                See pricing →
              </Link>
            </p>
          </div>
        </section>

        {/* ── Common failures ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            Common failures and fixes
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              If Send-to-Kindle isn&apos;t working at all — files not arriving,
              app not sending, files rejected — most problems fall into four
              categories: unapproved sender address, file size over 50 MB, file
              format not supported, or Amazon service delays. These are covered in
              detail in the troubleshooting guide.
            </p>
            <p>
              <Link
                href="/guides/send-to-kindle-not-working"
                className="text-accent no-underline hover:underline font-medium"
              >
                Send to Kindle not working: 7 fixes →
              </Link>
            </p>
            <p>
              The most common failure for new users: sending from an email address
              that has not been added to the Approved Personal Document E-mail List.
              Amazon delivers no error for this — the email appears to send normally,
              but the file never arrives. Fix: add the sending address at{" "}
              <a
                href="https://www.amazon.com/mycd"
                target="_blank"
                rel="noopener"
                className="text-accent no-underline hover:underline font-medium"
              >
                amazon.com/mycd
              </a>{" "}
              → Preferences → Personal Document Settings.
            </p>
            <p>
              The most common failure for academic users: the file arrives but
              is not readable. Two-column text is interleaved, footnotes are
              missing or dumped at the end unlinked. This is not a configuration
              problem — it is a conversion limitation. The fix is to use Method 4
              (KFX sideloading) instead of Send-to-Kindle for those files.
            </p>
          </div>
        </section>

        {/* ── Kindle Scribe specific note ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            A note on Kindle Scribe and academic PDFs
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              Kindle Scribe&apos;s 10.2-inch screen makes it well-suited for academic
              reading, but the screen size alone does not solve the conversion
              quality problems. A two-column PDF sent via Send-to-Kindle to a
              Scribe produces the same interleaved text output as on a Paperwhite —
              the conversion happens server-side before the file reaches the device.
            </p>
            <p>
              For academic use on Kindle Scribe, the recommended workflow is:
              convert to KFX with leafbind, transfer via USB-C cable. The Scribe&apos;s
              native KFX support handles column-ordered text, footnote popups, and
              navigable headings correctly — and the annotation features (handwriting,
              typed notes) work on properly-structured KFX files in ways they do not
              on PDFs rendered in PDF view mode.
            </p>
            <p>
              More detail on the Scribe conversion workflow:{" "}
              <Link
                href="/guides/pdf-to-kfx-for-kindle-scribe"
                className="text-accent no-underline hover:underline font-medium"
              >
                PDF to KFX for Kindle Scribe →
              </Link>
            </p>
            <p>
              If you are deciding between the Kindle Scribe and other devices for
              PDF reading:{" "}
              <Link
                href="/guides/kindle-scribe-vs-remarkable"
                className="text-accent no-underline hover:underline font-medium"
              >
                Kindle Scribe vs reMarkable vs iPad — which is best for PDFs? →
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
              Send to Kindle not working →
            </Link>
            <Link
              href="/convert/pdf-to-kfx"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-3 hover:bg-accent/5"
            >
              PDF to KFX converter →
            </Link>
            <Link
              href="/guides/pdf-to-kfx-for-kindle-scribe"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-3 hover:bg-accent/5"
            >
              PDF to KFX for Kindle Scribe →
            </Link>
            <Link
              href="/guides/kindle-scribe-vs-remarkable"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-3 hover:bg-accent/5"
            >
              Kindle Scribe vs reMarkable →
            </Link>
          </div>
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
