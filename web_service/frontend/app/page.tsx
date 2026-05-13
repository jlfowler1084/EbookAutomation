import { type Metadata } from "next";
import { Suspense } from "react";
import UploadForm from "./UploadForm";

export const metadata: Metadata = {
  title: "EbookAutomation — Free Ebook Converter",
  description:
    "Convert PDF, EPUB, MOBI, AZW, AZW3, and DJVU files to EPUB or MOBI instantly. Free tier supports files up to 20 MB.",
};

export default function HomePage() {
  return (
    <main
      style={{
        maxWidth: 640,
        margin: "60px auto",
        padding: "0 20px",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 8 }}>
        Ebook Converter
      </h1>
      <p style={{ color: "#555", marginBottom: 32 }}>
        Convert PDF, EPUB, MOBI, AZW, AZW3, or DJVU to your preferred format.
        Free tier: up to 20 MB, EPUB and MOBI output.
      </p>

      <Suspense fallback={null}>
        <UploadForm />
      </Suspense>
    </main>
  );
}
