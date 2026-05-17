import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Privacy Policy — leafbind",
  description:
    "How leafbind handles your data: Plausible analytics (no cookies, no PII), Stripe email for receipts, file retention after conversion, and AI service use on the premium tier.",
  alternates: { canonical: "/privacy" },
  openGraph: { type: "website", url: "https://leafbind.io/privacy" },
};

export default function PrivacyPage() {
  return (
    <>
      {/* Page header */}
      <div className="py-12 md:py-16 border-b border-border mb-12">
        <h1 className="font-serif text-3xl sm:text-4xl md:text-5xl lg:text-6xl leading-tight text-text-base mb-6">
          Privacy Policy
        </h1>
        <p className="font-sans text-sm text-text-muted">
          Last updated: <time dateTime="2026-05-17">May 17, 2026</time>
        </p>
      </div>

      {/* Body */}
      <div className="max-w-2xl space-y-12 font-sans text-text-base leading-relaxed">

        <section>
          <h2 className="font-serif text-2xl text-text-base mb-4">Overview</h2>
          <p className="text-text-muted">
            leafbind is designed to be minimal by default. We do not create accounts, we do not
            store your email address unless you complete a payment, and we do not use tracking
            cookies. This page explains exactly what we collect and why.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-2xl text-text-base mb-4">Analytics — Plausible</h2>
          <p className="text-text-muted mb-3">
            We use{" "}
            <a
              href="https://plausible.io"
              target="_blank"
              rel="noopener noreferrer"
              className="text-brand hover:underline"
            >
              Plausible Analytics
            </a>
            , a privacy-focused analytics tool. Plausible does not use cookies, does not track
            users across sites, and does not collect personally identifiable information.
          </p>
          <p className="text-text-muted mb-3">
            What Plausible collects per page view:
          </p>
          <ul className="list-none space-y-2 text-text-muted ml-4">
            <li>— Page URL visited</li>
            <li>— HTTP referrer (the site you came from, if any)</li>
            <li>— Browser type and operating system (derived from the User-Agent string; the raw string is not stored)</li>
            <li>— Country of origin (derived from IP address at request time; the IP address itself is not stored)</li>
            <li>— Screen size category</li>
          </ul>
          <p className="text-text-muted mt-3">
            What Plausible does NOT collect: no IP addresses, no cookies, no cross-site tracking,
            no fingerprinting, no PII of any kind. Data is aggregated and never sold.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-2xl text-text-base mb-4">Payments — Stripe</h2>
          <p className="text-text-muted mb-3">
            Credit pack purchases are processed by{" "}
            <a
              href="https://stripe.com"
              target="_blank"
              rel="noopener noreferrer"
              className="text-brand hover:underline"
            >
              Stripe
            </a>
            . leafbind does not receive or store your card number, CVC, or billing address —
            those stay with Stripe.
          </p>
          <p className="text-text-muted mb-3">
            If you complete a purchase, Stripe shares your email address with us for the purpose
            of delivering your credits and for support follow-up (for example, if a refund is
            requested). We do not use that email address for marketing, and we do not share it
            with third parties beyond what is required to operate the service.
          </p>
          <p className="text-text-muted">
            Stripe&apos;s own privacy practices are described in the{" "}
            <a
              href="https://stripe.com/privacy"
              target="_blank"
              rel="noopener noreferrer"
              className="text-brand hover:underline"
            >
              Stripe Privacy Policy
            </a>
            .
          </p>
        </section>

        <section>
          <h2 className="font-serif text-2xl text-text-base mb-4">Uploaded files</h2>
          <p className="text-text-muted mb-3">
            Files you upload to leafbind are used solely to perform the conversion you requested.
            They are stored temporarily in an isolated job directory on our server and deleted
            automatically once the job&apos;s retention window expires:
          </p>
          <ul className="list-none space-y-2 text-text-muted ml-4">
            <li>— <strong className="text-text-base">Free tier:</strong> source file and output are deleted 1 hour after the job is created.</li>
            <li>— <strong className="text-text-base">Premium tier:</strong> source file and output are deleted 24 hours after the job is created.</li>
          </ul>
          <p className="text-text-muted mt-3">
            We do not retain your files beyond these windows, do not use them for training, and do
            not share them with third parties except as described in the AI services section below.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-2xl text-text-base mb-4">AI services (premium tier only)</h2>
          <p className="text-text-muted mb-3">
            The premium conversion pipeline may send portions of your uploaded PDF to two external
            AI services for processing:
          </p>
          <ul className="list-none space-y-2 text-text-muted ml-4 mb-3">
            <li>
              — <strong className="text-text-base">Google Gemini</strong> — used for OCR remediation
              on pages where text-extraction libraries (pdfminer, pypdf, PyMuPDF) fail to produce
              usable output, typically scanned pages or complex graphical layouts. Only affected
              page images are sent.
            </li>
            <li>
              — <strong className="text-text-base">Anthropic Claude</strong> — used for the
              post-conversion visual quality-assurance pass, which re-renders the output and checks
              heading hierarchy, table-of-contents accuracy, and footnote rendering. Only output
              page images are sent, not the original source content.
            </li>
          </ul>
          <p className="text-text-muted">
            The free tier does not use AI services. Content is not submitted to these services for
            training. Both services are used under API agreements that restrict data use to
            providing the requested service.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-2xl text-text-base mb-4">Cookies and local storage</h2>
          <p className="text-text-muted mb-3">
            leafbind does not use cookies. We do not show a cookie consent banner because there is
            nothing to consent to.
          </p>
          <p className="text-text-muted">
            Your browser&apos;s <code className="text-sm bg-surface-muted px-1 rounded">localStorage</code> is
            used to store the anonymous job token(s) associated with your current conversion or
            token pack. This is stored on your device only — it is never transmitted to our servers
            beyond what is needed to check job status and recover tokens. You can clear it at any
            time by clearing your browser&apos;s site data.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-2xl text-text-base mb-4">No accounts</h2>
          <p className="text-text-muted">
            leafbind does not require account registration. We do not collect a username, password,
            or profile. The service is designed to work without persistent identity — your token
            pack is the only credential.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-2xl text-text-base mb-4">Your rights and contact</h2>
          <p className="text-text-muted mb-3">
            Because we hold minimal data, most privacy requests are straightforward to fulfil.
            If you have questions about what we hold, or want to request deletion of any data
            associated with a Stripe purchase, contact us at:
          </p>
          <p className="text-text-muted">
            <a href="mailto:support@leafbind.io" className="text-brand hover:underline">
              support@leafbind.io
            </a>
            {" "}or via the{" "}
            <Link href="/contact" className="text-brand hover:underline">
              contact page
            </Link>
            .
          </p>
        </section>

        <section>
          <h2 className="font-serif text-2xl text-text-base mb-4">Changes to this policy</h2>
          <p className="text-text-muted">
            If we make material changes to this policy, we will update the &ldquo;Last updated&rdquo; date
            at the top of this page. Continued use of the service after a change constitutes
            acceptance of the updated policy.
          </p>
        </section>

      </div>
    </>
  );
}
