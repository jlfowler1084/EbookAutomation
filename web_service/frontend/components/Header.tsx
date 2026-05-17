import Link from "next/link";
import { Logo } from "./Logo";

export function Header() {
  return (
    <header className="border-b border-border bg-surface">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
        <Link href="/" aria-label="leafbind home" className="text-text-base">
          <Logo className="h-8 w-auto" />
        </Link>
        <nav className="flex items-center gap-3 sm:gap-6 text-sm text-text-muted">
          <Link href="/convert/pdf-to-kfx"          className="py-3 hover:text-text-base transition">Convert</Link>
          <Link href="/guides"                       className="py-3 hover:text-text-base transition">Guides</Link>
          <Link href="/pricing"                     className="py-3 hover:text-text-base transition">Pricing</Link>
          <Link href="/quality"                     className="py-3 hover:text-text-base transition">Quality</Link>
          <Link href="/recover"                     className="py-3 hover:text-text-base transition">Recover</Link>
        </nav>
      </div>
    </header>
  );
}
