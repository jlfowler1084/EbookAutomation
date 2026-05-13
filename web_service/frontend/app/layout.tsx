import { type Metadata } from "next";

export const metadata: Metadata = {
  title: "EbookAutomation — Ebook Converter",
  description: "Convert ebooks between PDF, EPUB, MOBI, AZW, AZW3, and DJVU formats.",
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
