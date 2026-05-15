import "./globals.css";
import { type Metadata } from "next";
import { Newsreader, DM_Sans, IBM_Plex_Mono } from "next/font/google";
import PlausibleProvider from "next-plausible";

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
      <head>
        {/* EB-252: Plausible analytics. Privacy-first (no cookies, no PII,
            GDPR-compliant by default). Script served same-origin via the
            withPlausibleProxy rewrite in next.config.js to bypass ad-blockers.
            trackOutboundLinks captures clicks to external domains in the
            dashboard (useful for measuring referral flow back from Reddit /
            MobileRead / blogs once those channels are active per EB-242). */}
        <PlausibleProvider domain="leafbind.io" trackOutboundLinks />
      </head>
      <body style={{ margin: 0, background: "#fff", color: "#111" }}>
        {children}
      </body>
    </html>
  );
}
