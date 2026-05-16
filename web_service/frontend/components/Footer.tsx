import Link from "next/link";
import { Logo } from "./Logo";

export function Footer() {
  return (
    <footer className="border-t border-border bg-surface-muted">
      <div className="mx-auto max-w-7xl px-6 py-12">
        <div className="grid gap-8 md:grid-cols-3">
          <div>
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
            <ul className="mt-3 space-y-2 text-sm text-text-muted">
              <li><Link href="/convert/pdf-to-kfx"               className="hover:text-text-base transition">PDF to KFX</Link></li>
              <li><Link href="/convert/academic-pdf-to-kindle"   className="hover:text-text-base transition">Academic PDFs</Link></li>
              <li><Link href="/convert/pdf-footnotes-kindle"     className="hover:text-text-base transition">PDFs with footnotes</Link></li>
              <li><Link href="/convert/multi-column-pdf-kindle"  className="hover:text-text-base transition">Multi-column PDFs</Link></li>
            </ul>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-text-base">Account</h3>
            <ul className="mt-3 space-y-2 text-sm text-text-muted">
              <li><Link href="/pricing" className="hover:text-text-base transition">Pricing</Link></li>
              <li><Link href="/quality" className="hover:text-text-base transition">Quality</Link></li>
              <li><Link href="/recover" className="hover:text-text-base transition">Recover tokens</Link></li>
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
