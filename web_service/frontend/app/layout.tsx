import "./globals.css";
import { type Metadata } from "next";
import { Newsreader, DM_Sans, IBM_Plex_Mono } from "next/font/google";

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

const newsreader = Newsreader({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
  display: "swap",
  preload: true,
  variable: "--font-newsreader",
});

const dmSans = DM_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  preload: true,
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
        {children}
      </body>
    </html>
  );
}
