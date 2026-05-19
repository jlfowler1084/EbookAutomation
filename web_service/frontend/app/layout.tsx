import "./globals.css";
import { type Metadata } from "next";
import { Newsreader, DM_Sans, IBM_Plex_Mono } from "next/font/google";
import Script from "next/script";

/**
 * EB-240 / EB-238: Font swap
 * - Lora → Newsreader (display serif, weight 400/500/600 + italic)
 * - Inter → DM Sans (UI body sans, weight 400/500/600/700)
 * - IBM Plex Mono added for eyebrow labels
 *
 * Newsreader decision: Adopted. At 32–34px the wordmark proportions look
 * proportionally balanced — slightly wider set than Lora but the italic .io
 * in sand reads clearly without crowding. Kept for both wordmark and page
 * headings. EB-238 absorbed.
 */

// EB-238: preload disabled. Chrome measures LCP as the first paint of the
// largest element; with display:swap the hero h1 paints with the
// adjustFontFallback metrics-adjusted fallback immediately. Preloading
// every weight × style (6 Newsreader + 4 DM Sans = 10 preload tags) was
// racing critical CSS for browser request slots, delaying that first paint.
// Disabling preload lets the fallback render unblocked; the font swap
// happens later and is not counted by Lighthouse LCP.
const newsreader = Newsreader({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
  display: "swap",
  preload: false,
  variable: "--font-newsreader",
});

const dmSans = DM_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  preload: false,
  variable: "--font-dm-sans",
});

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
  preload: false,
  variable: "--font-ibm-plex-mono",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://leafbind.io"),
  title: "leafbind — PDF to Kindle Converter",
  description:
    "Convert PDFs to Kindle KFX with smart heading detection, footnote linking, " +
    "and multi-column layout support. Free tier available.",
  openGraph: {
    siteName: "leafbind",
    url: "https://leafbind.io",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${newsreader.variable} ${dmSans.variable} ${ibmPlexMono.variable}`}
    >
      <body style={{ margin: 0, background: "#fff", color: "#111" }}>
        {/* EB-269 (F4-05): skip link is the first focusable element. Visually
            hidden until focused via Tab, then surfaces in the top-left so
            keyboard users can jump past the chrome on every page. The <main>
            target id is set in the route-group layouts. */}
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded focus:bg-surface focus:px-4 focus:py-2 focus:text-sm focus:text-text-base focus:shadow-lg focus:outline focus:outline-2 focus:outline-offset-2 focus:outline-[var(--color-accent)]"
        >
          Skip to main content
        </a>
        {/* EB-265: Direct Plausible script tag pointing at the self-hosted CE
            instance (plausible.leafbind.io). Replaces the PlausibleProvider
            wrapper from next-plausible which defaulted to plausible.io and
            required customDomain to be set. strategy="afterInteractive" loads
            after hydration so it never blocks first paint. */}
        <Script
          defer
          data-domain="leafbind.io"
          src="https://plausible.leafbind.io/js/script.js"
          strategy="afterInteractive"
        />
        {children}
      </body>
    </html>
  );
}
