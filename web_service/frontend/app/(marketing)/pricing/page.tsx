import type { Metadata } from "next";
import Link from "next/link";
import BuyButtons from "../../../components/BuyButtons";
import JsonLd from "../../../components/JsonLd";
import { buildPricingProductSchema } from "../../../lib/structured-data";

export const metadata: Metadata = {
  title: "Pricing — credits for the leafbind smart conversion pipeline",
  description:
    "Free Calibre-based EPUB conversion, or premium leafbind smart pipeline — column-aware extraction, heading detection, bidirectional footnote linking, KFX output.",
  alternates: { canonical: "/pricing" },
  openGraph: { type: "website", url: "https://leafbind.io/pricing" },
};

const PACKS = [
  {
    id: "starter",
    credits: 3,
    price: "$2.99",
    perCredit: "$1.00 per credit",
    label: "Starter",
    recommended: false,
  },
  {
    id: "standard",
    credits: 10,
    price: "$7.99",
    perCredit: "$0.80 per credit",
    label: "Standard",
    recommended: true,
  },
  {
    id: "power",
    credits: 25,
    price: "$14.99",
    perCredit: "$0.60 per credit",
    label: "Power",
    recommended: false,
  },
];

const FREE_FEATURES = [
  "3 conversions per day",
  "Files up to 20 MB",
  "EPUB output via Calibre",
  "No account required",
];

const PREMIUM_FEATURES = [
  "Column-aware extraction for multi-column PDFs",
  "Smart heading detection — font-size classification produces a navigable Kindle TOC",
  "Bidirectional footnote and endnote linking",
  "KFX output — Kindle's native enhanced typesetting format",
  "Files up to 100 MB",
  "No account required",
];

export default function PricingPage() {
  return (
    <>
      <JsonLd schema={buildPricingProductSchema(PACKS)} />
      {/* Page header */}
      <div className="py-12 md:py-16 border-b border-border mb-12">
        <h1 className="font-serif text-3xl sm:text-4xl md:text-5xl lg:text-6xl leading-tight text-text-base mb-6">
          Pricing
        </h1>
        <p className="font-sans text-lg text-text-muted leading-relaxed max-w-xl">
          Free runs your PDF through Calibre for a quick EPUB. Premium runs
          leafbind&apos;s smart pipeline — the column-aware extraction, heading
          detection, and bidirectional footnote linking shown on the{" "}
          <Link href="/quality" className="text-brand hover:underline font-medium">
            quality page
          </Link>
          . Pay once per conversion — no subscription required.
        </p>
        <p className="font-sans text-sm text-text-muted mt-3">
          Tokens expire 30 days after purchase.{" "}
          <Link href="/recover" className="text-brand hover:underline font-medium">
            Lost your tokens?
          </Link>
        </p>
      </div>

      {/* What you get: free vs. premium */}
      <div className="mb-16 grid grid-cols-1 gap-8 md:grid-cols-2">
        {/* Free tier */}
        <div className="rounded-sm border border-border p-8 bg-white">
          <h2 className="font-serif text-2xl text-text-base mb-2 leading-snug">
            Free
          </h2>
          <p className="font-sans text-3xl font-bold text-text-base mb-6">
            $0
          </p>
          <ul className="space-y-3 mb-6">
            {FREE_FEATURES.map((feature) => (
              <li key={feature} className="flex items-start gap-3">
                <span className="font-sans text-sm text-text-muted mt-0.5">—</span>
                <span className="font-sans text-sm text-text-muted leading-relaxed">{feature}</span>
              </li>
            ))}
          </ul>
          <p className="font-sans text-xs text-text-muted leading-relaxed">
            Quick Calibre-based EPUB conversion. Works well for text-based PDFs
            without complex column layouts or extensive footnotes.
          </p>
        </div>

        {/* Premium tier */}
        <div className="rounded-sm border border-brand p-8 bg-white">
          <h2 className="font-serif text-2xl text-text-base mb-2 leading-snug">
            Premium
          </h2>
          <p className="font-sans text-base text-text-muted mb-6 leading-relaxed">
            leafbind&apos;s smart pipeline — the column, heading, and footnote
            work that the free Calibre pass cannot do. One-time credit purchase;
            credits unlock individual conversions — use within 30 days.
          </p>
          <ul className="space-y-3 mb-6">
            {PREMIUM_FEATURES.map((feature) => (
              <li key={feature} className="flex items-start gap-3">
                <span className="font-sans text-sm text-brand mt-0.5 font-medium">✓</span>
                <span className="font-sans text-sm text-text-base leading-relaxed">{feature}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Credit packs */}
      <div className="mb-16">
        <h2 className="font-serif text-3xl text-text-base mb-2 leading-snug">
          Choose your pack
        </h2>
        <p className="font-sans text-sm text-text-muted mb-8 leading-relaxed">
          Each credit unlocks one premium conversion. Buy once, use when you need it.
        </p>

        <div className="grid grid-cols-1 gap-6 md:grid-cols-3 mb-8">
          {PACKS.map((pack) => (
            <div
              key={pack.id}
              id={pack.id}
              className={`rounded-sm border p-6 ${
                pack.recommended
                  ? "border-brand bg-white shadow-sm"
                  : "border-border bg-white"
              }`}
            >
              <h3 className="font-serif text-xl text-text-base mb-1 leading-snug">
                {pack.label}
              </h3>
              <p className="font-sans text-3xl font-bold text-text-base mb-1">
                {pack.price}
              </p>
              <p className="font-sans text-sm text-text-muted mb-4">
                {pack.credits} credits &bull; {pack.perCredit}
              </p>
            </div>
          ))}
        </div>

        <BuyButtons packs={PACKS} />
      </div>

      {/* Footer note */}
      <div className="border-t border-border pt-8 pb-4">
        <p className="font-sans text-sm text-text-muted">
          No subscription. No account. Credits work on any premium conversion within
          30 days of purchase.{" "}
          <Link href="/recover" className="text-brand hover:underline font-medium">
            Recover existing tokens.
          </Link>
        </p>
      </div>
    </>
  );
}
