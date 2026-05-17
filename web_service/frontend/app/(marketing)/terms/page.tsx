import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Terms of Service — leafbind",
  description:
    "leafbind terms of service: acceptable use, credit token model, best-effort availability, limitation of liability, and governing law (State of Georgia, US).",
  alternates: { canonical: "/terms" },
  openGraph: { type: "website", url: "https://leafbind.io/terms" },
};

export default function TermsPage() {
  return (
    <>
      {/* Page header */}
      <div className="py-12 md:py-16 border-b border-border mb-12">
        <h1 className="font-serif text-3xl sm:text-4xl md:text-5xl lg:text-6xl leading-tight text-text-base mb-6">
          Terms of Service
        </h1>
        <p className="font-sans text-sm text-text-muted">
          Last updated: <time dateTime="2026-05-17">May 17, 2026</time>
        </p>
      </div>

      {/* Body */}
      <div className="max-w-2xl space-y-12 font-sans text-text-base leading-relaxed">

        <section>
          <h2 className="font-serif text-2xl text-text-base mb-4">Agreement</h2>
          <p className="text-text-muted">
            By using leafbind.io (&ldquo;leafbind,&rdquo; &ldquo;we,&rdquo; &ldquo;us&rdquo;), you agree to these Terms of
            Service. If you do not agree, do not use the service. These terms apply to all users
            of the site, including visitors, free-tier users, and credit-pack purchasers.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-2xl text-text-base mb-4">Acceptable use</h2>
          <p className="text-text-muted mb-3">You may use leafbind to convert PDF and EPUB files that you own or have permission to convert. You may not:</p>
          <ul className="list-none space-y-2 text-text-muted ml-4">
            <li>— Upload files that you do not have the right to reproduce or convert</li>
            <li>— Upload files containing DRM (Digital Rights Management) protection for the purpose of circumventing it</li>
            <li>— Use the service through automated scripts, bots, or programmatic bulk submission without prior written consent</li>
            <li>— Upload files containing malicious code, exploits, or content designed to harm our infrastructure or other users</li>
            <li>— Resell access to the service or act as an intermediary for third-party conversions at scale</li>
          </ul>
          <p className="text-text-muted mt-3">
            We reserve the right to suspend or terminate access for violations of these rules
            without notice.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-2xl text-text-base mb-4">Credit token model</h2>
          <p className="text-text-muted mb-3">
            Premium conversions require credits (tokens). Credits are sold in one-time packs —
            no subscription:
          </p>
          <ul className="list-none space-y-2 text-text-muted ml-4 mb-3">
            <li>— <strong className="text-text-base">Starter:</strong> 3 credits for $2.99</li>
            <li>— <strong className="text-text-base">Standard:</strong> 10 credits for $7.99</li>
            <li>— <strong className="text-text-base">Power:</strong> 25 credits for $14.99</li>
          </ul>
          <p className="text-text-muted mb-3">
            One credit unlocks one premium conversion. A credit is consumed when a conversion
            begins processing — not when you upload a file. Credits expire 30 days after purchase.
          </p>
          <p className="text-text-muted">
            For information about refunds when a conversion fails, see the{" "}
            <Link href="/refund-policy" className="text-brand hover:underline">
              Refund Policy
            </Link>
            .
          </p>
        </section>

        <section>
          <h2 className="font-serif text-2xl text-text-base mb-4">Service availability</h2>
          <p className="text-text-muted mb-3">
            <strong className="text-text-base">Free tier:</strong> Provided on a best-effort
            basis. No uptime guarantee. We may adjust free-tier limits (daily conversion cap,
            file size limits, output formats) at any time.
          </p>
          <p className="text-text-muted">
            <strong className="text-text-base">Premium tier:</strong> Also best-effort. Premium
            jobs are queued with priority over free-tier jobs, but we do not offer a formal
            uptime SLA. Scheduled maintenance, third-party outages (Stripe, Calibre dependency
            changes, AI service providers), or infrastructure failures may cause temporary
            unavailability. We will not charge credits for conversions that fail due to service
            outages on our end.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-2xl text-text-base mb-4">Intellectual property</h2>
          <p className="text-text-muted">
            leafbind does not claim ownership of files you upload. You retain all rights to
            your content. By uploading a file, you grant leafbind a temporary, limited licence
            to process it solely for the purpose of performing the requested conversion and
            returning the output to you. This licence terminates when the file is deleted per
            the retention schedule described in our{" "}
            <Link href="/privacy" className="text-brand hover:underline">
              Privacy Policy
            </Link>
            .
          </p>
        </section>

        <section>
          <h2 className="font-serif text-2xl text-text-base mb-4">Disclaimer of warranties</h2>
          <p className="text-text-muted">
            THE SERVICE IS PROVIDED &ldquo;AS IS&rdquo; AND &ldquo;AS AVAILABLE&rdquo; WITHOUT WARRANTY OF ANY KIND,
            EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO WARRANTIES OF MERCHANTABILITY,
            FITNESS FOR A PARTICULAR PURPOSE, AND NON-INFRINGEMENT. WE DO NOT WARRANT THAT
            CONVERSIONS WILL BE ERROR-FREE, THAT THE SERVICE WILL BE UNINTERRUPTED, OR THAT
            OUTPUT QUALITY WILL MEET ANY PARTICULAR STANDARD. YOU USE THE SERVICE AT YOUR OWN RISK.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-2xl text-text-base mb-4">Limitation of liability</h2>
          <p className="text-text-muted">
            TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, LEAFBIND&apos;S TOTAL LIABILITY TO
            YOU FOR ANY CLAIM ARISING FROM OR RELATED TO THESE TERMS OR THE SERVICE SHALL NOT
            EXCEED THE TOTAL AMOUNT YOU PAID TO LEAFBIND IN THE 30 DAYS PRECEDING THE EVENT
            GIVING RISE TO THE CLAIM. IN NO EVENT WILL LEAFBIND BE LIABLE FOR ANY INDIRECT,
            INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, EVEN IF ADVISED OF THE
            POSSIBILITY OF SUCH DAMAGES.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-2xl text-text-base mb-4">Governing law</h2>
          <p className="text-text-muted">
            These Terms are governed by and construed in accordance with the laws of the State
            of Georgia, United States, without regard to conflict-of-law principles. Any dispute
            arising out of or related to these Terms or the service shall be subject to the
            exclusive jurisdiction of the courts of competent jurisdiction located in the State
            of Georgia.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-2xl text-text-base mb-4">Changes to these terms</h2>
          <p className="text-text-muted">
            We may update these Terms at any time. The updated version will be posted at this
            URL with a revised &ldquo;Last updated&rdquo; date. Continued use of the service after the
            updated Terms are posted constitutes your acceptance of the changes.
          </p>
        </section>

        <section>
          <h2 className="font-serif text-2xl text-text-base mb-4">Contact</h2>
          <p className="text-text-muted">
            Questions about these Terms? Email{" "}
            <a href="mailto:support@leafbind.io" className="text-brand hover:underline">
              support@leafbind.io
            </a>{" "}
            or use the{" "}
            <Link href="/contact" className="text-brand hover:underline">
              contact page
            </Link>
            .
          </p>
        </section>

      </div>
    </>
  );
}
