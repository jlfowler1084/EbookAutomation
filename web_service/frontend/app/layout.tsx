import "./globals.css";
import { type Metadata } from "next";

export const metadata: Metadata = {
  title: "leafbind — PDF to Kindle Converter",
  description:
    "Convert PDFs to Kindle KFX with smart heading detection, footnote linking, " +
    "and multi-column layout support. Free tier available.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
  openGraph: {
    siteName: "leafbind",
    url: "https://leafbind.io",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, background: "#fff", color: "#111" }}>
        {children}
      </body>
    </html>
  );
}
