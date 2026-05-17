import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Refund Policy — leafbind",
  description:
    "leafbind refund and credit policy: when refunds are issued, when they are not, credit vs cash refunds, token expiry, and how to contact support.",
  alternates: { canonical: "/refund-policy" },
  openGraph: { type: "website", url: "https://leafbind.io/refund-policy" },
};

export default function RefundPolicyPage() {
  return (
    <>
      {/* Page header */}
      <div className="py-12 md:py-16 border-b border-border mb-12">
        <h1 className="font-serif text-3xl sm:text-4xl md:text-5xl lg:text-6xl leading-tight text-text-base mb-6">
          Refund &amp; Credit Policy
        </h1>
        <p className="font-sans text-sm text-text-muted">
          Last updated: <time dateTime="2026-05-17">May 17, 2026</time>
        </p>
      </div>

      {/* Body */}
      <div className="max-w-2xl space-y-12 font-sans text-text-base leading-relaxed">

        <section>
          <h2 className="font-serif text-2xl text-text-base mb-4">The short version</h2>
          <p className="text-text-muted">
            Credits are consumed when conversion begins. If a conversion fails for technical
            reasons (not user error), we&apos;ll refund the credit on request — contact support.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-2xl text-text-base mb-4">When refunds are issued</h2>
          <p className="text-text-muted mb-3">We will refund a credit or charge when:</p>
          <ul className="list-none space-y-2 text-text-muted ml-4">
            <li>
              — <strong className="text-text-base">Technical failure:</strong> The conversion
              failed due to a bug in our pipeline or a service outage on our end (not due to an
              unsupported file format or file that is too large — those are caught before a credit
              is consumed).
            </li>
            <li>
              — <strong className="text-text-base">Duplicate charge:</strong> You were charged
              more than once for the same purchase due to a payment processing error.
            </li>
          </ul>
        </section>

        <section>
          <h2 className="font-serif text-2xl text-text-base mb-4">When refunds are not issued</h2>
          <p className="text-text-muted mb-3">We do not issue refunds for:</p>
          <ul className="list-none space-y-2 text-text-muted ml-4">
            <li>
              — <strong className="text-text-base">User error:</strong> You uploaded the wrong
              file, or the converted output does not match your expectations because of how the
              source file was structured.
            </li>
            <li>
              — <strong className="text-text-base">Pre-flight rejection:</strong> The file was
              rejected before conversion started (file too large, unsupported format). In these
              cases, no credit is consumed, so no refund is applicable.
            </li>
            <li>
              — <strong className="text-text-base">Buyer&apos;s remorse:</strong> You purchased a
              credit pack and decided not to use the credits.
            </li>
            <li>
              — <strong className="text-text-base">Expired credits:</strong> Credits that expired
              before use. Credits expire 30 days after purchase.
            </li>
          </ul>
        </section>

        <section>
          <h2 className="font-serif text-2xl text-text-base mb-4">Credit refund vs. cash refund</h2>
          <p className="text-text-muted mb-3">
            For qualifying refunds, the default resolution is a credit re-added to your token
            pool. This is the fastest option — we can do it without waiting on Stripe&apos;s
            settlement cycle.
          </p>
          <p className="text-text-muted">
            A cash refund via Stripe is available on request for technical failures, provided the
            request is made within 30 days of the original purchase date. Cash refunds are
            processed back to the original payment method and may take 5–10 business days to
            appear depending on your bank.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-2xl text-text-base mb-4">Credit expiry</h2>
          <p className="text-text-muted">
            Credits expire 30 days after purchase. Expired credits cannot be refunded or extended.
            If you are unsure whether your credits have expired, use the{" "}
            <Link href="/recover" className="text-brand hover:underline">
              token recovery page
            </Link>{" "}
            to check.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-2xl text-text-base mb-4">How to request a refund</h2>
          <ol className="list-none space-y-3 text-text-muted ml-4">
            <li>
              <span className="text-text-base font-medium">1.</span> Email{" "}
              <a href="mailto:support@leafbind.io" className="text-brand hover:underline">
                support@leafbind.io
              </a>{" "}
              or use the{" "}
              <Link href="/contact" className="text-brand hover:underline">
                contact page
              </Link>
              .
            </li>
            <li>
              <span className="text-text-base font-medium">2.</span> Include your job ID (shown
              on the status page) and a brief description of what went wrong.
            </li>
            <li>
              <span className="text-text-base font-medium">3.</span> We respond to refund requests
              within 3 business days.
            </li>
          </ol>
        </section>

        <section>
          <h2 className="font-serif text-2xl text-text-base mb-4">Related policies</h2>
          <ul className="list-none space-y-2 text-text-muted ml-4">
            <li>
              —{" "}
              <Link href="/terms" className="text-brand hover:underline">
                Terms of Service
              </Link>{" "}
              — acceptable use, token model, limitation of liability
            </li>
            <li>
              —{" "}
              <Link href="/privacy" className="text-brand hover:underline">
                Privacy Policy
              </Link>{" "}
              — what data we collect and how long we keep it
            </li>
          </ul>
        </section>

      </div>
    </>
  );
}
