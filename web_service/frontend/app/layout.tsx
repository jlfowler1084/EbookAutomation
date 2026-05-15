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
      <body style={{ margin: 0, background: "#fff", color: "#111" }}>
        {/* EB-252 v2: PlausibleProvider wraps children inside <body>. The v1
            placement self-closed in <head> emitted only the preload link, not
            the actual <script> tag. Wrapping children lets next-plausible's
            internal <Script> component render correctly under Next.js 16 App
            Router. Pageview events POST to /api/event, which is manually
            proxied via app/api/event/route.ts to bypass the Next 16 /api/*
            rewrite precedence bug (withPlausibleProxy's /api/event rewrite
            returns 404 even though its /js/script.js rewrite works). */}
        <PlausibleProvider domain="leafbind.io" trackOutboundLinks>
          {children}
        </PlausibleProvider>
      </body>
    </html>
  );
}
