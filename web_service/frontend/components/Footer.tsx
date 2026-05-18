import Link from "next/link";
import { Logo } from "./Logo";

export function Footer() {
  return (
    <footer className="border-t border-border bg-surface-muted">
      <div className="mx-auto max-w-7xl px-6 py-12">
        {/*
          EB-264: Expanded from md:grid-cols-3 to sm:grid-cols-2 lg:grid-cols-4.
          EB-296: Expanded to lg:grid-cols-5 to accommodate the new Guides column.
          EB-300: Expanded to lg:grid-cols-6 to accommodate the new Legal column.
          Using sm:grid-cols-2 at 768-1023px to stack 2×2 (logo spans full width on xs).
          6 columns only at lg (≥1024px). At sm it stacks 2×2.
        */}
        <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-6">
          <div className="sm:col-span-2 lg:col-span-1">
            {/* EB-269 (F4-02): block + w-fit takes the link out of an
                "in-text-block" context for axe, so the logo isn't flagged
                as an indistinguishable inline link sitting in a paragraph. */}
            <Link href="/" aria-label="leafbind home" className="block w-fit text-text-base">
              <Logo className="h-8 w-auto" />
            </Link>
            <p className="mt-3 text-sm text-text-muted">
              PDF to Kindle, the calm way.
            </p>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-text-base">Convert</h3>
            <ul className="mt-3 space-y-1 text-sm text-text-muted">
              <li><Link href="/convert/pdf-to-kfx"               className="block py-2 hover:text-text-base transition">PDF to KFX</Link></li>
              <li><Link href="/convert/academic-pdf-to-kindle"   className="block py-2 hover:text-text-base transition">Academic PDFs</Link></li>
              <li><Link href="/convert/pdf-footnotes-kindle"     className="block py-2 hover:text-text-base transition">PDFs with footnotes</Link></li>
              <li><Link href="/convert/multi-column-pdf-kindle"  className="block py-2 hover:text-text-base transition">Multi-column PDFs</Link></li>
            </ul>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-text-base">Guides</h3>
            <ul className="mt-3 space-y-1 text-sm text-text-muted">
              <li><Link href="/guides"                                         className="block py-2 hover:text-text-base transition">All guides</Link></li>
              <li><Link href="/guides/send-to-kindle-not-working"              className="block py-2 hover:text-text-base transition">Send to Kindle not working</Link></li>
              <li><Link href="/guides/how-to-send-pdf-to-kindle"               className="block py-2 hover:text-text-base transition">How to send PDFs to Kindle</Link></li>
              <li><Link href="/guides/does-kindle-support-epub"                className="block py-2 hover:text-text-base transition">Does Kindle support EPUB?</Link></li>
              <li><Link href="/guides/kindle-scribe-vs-remarkable"             className="block py-2 hover:text-text-base transition">Kindle Scribe vs. reMarkable</Link></li>
              <li><Link href="/guides/pdf-to-kfx-for-kindle-scribe"            className="block py-2 hover:text-text-base transition">PDF to KFX for Kindle Scribe</Link></li>
            </ul>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-text-base">Account</h3>
            <ul className="mt-3 space-y-1 text-sm text-text-muted">
              <li><Link href="/pricing" className="block py-2 hover:text-text-base transition">Pricing</Link></li>
              <li><Link href="/quality" className="block py-2 hover:text-text-base transition">Quality</Link></li>
            </ul>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-text-base">Support</h3>
            <ul className="mt-3 space-y-1 text-sm text-text-muted">
              <li><Link href="/contact"  className="block py-2 hover:text-text-base transition">Contact</Link></li>
              <li><Link href="/recover"  className="block py-2 hover:text-text-base transition">Recover tokens</Link></li>
            </ul>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-text-base">Legal</h3>
            <ul className="mt-3 space-y-1 text-sm text-text-muted">
              <li><Link href="/privacy"        className="block py-2 hover:text-text-base transition">Privacy Policy</Link></li>
              <li><Link href="/terms"          className="block py-2 hover:text-text-base transition">Terms of Service</Link></li>
              <li><Link href="/refund-policy"  className="block py-2 hover:text-text-base transition">Refund Policy</Link></li>
            </ul>
          </div>
        </div>
        <p className="mt-12 border-t border-border pt-6 text-xs text-text-muted">
          &copy; {new Date().getFullYear()} leafbind. Made with care, not ads.
        </p>
      </div>
    </footer>
  );
}
