import { type Metadata } from "next";
import { Suspense } from "react";
import UploadForm from "../UploadForm";

export const metadata: Metadata = {
  title: "leafbind — PDF to Kindle, the calm way",
  description:
    "Smart PDF to Kindle conversion with heading detection, footnote linking, and multi-column support. Free tier available. No ads, no tracking.",
};

export default function HomePage() {
  return (
    <>
      {/* Hero band */}
      <div className="py-16 md:py-24">
        <div className="max-w-2xl">
          <h1 className="font-serif text-5xl md:text-6xl leading-tight text-text-base mb-6">
            Convert PDFs to Kindle, beautifully.
          </h1>
          <p className="font-sans text-lg text-text-muted leading-relaxed mb-4">
            Smart heading detection, footnote linking, multi-column support.
            No ads. No malware.
          </p>
          <p className="font-sans text-sm text-text-muted">
            Your file is never stored after conversion. No tracking, no ads.
          </p>
        </div>
      </div>

      {/* Upload zone card */}
      <div className="mb-16">
        <div className="rounded-sm border border-border bg-white p-8 shadow-sm">
          <Suspense fallback={null}>
            <UploadForm />
          </Suspense>
        </div>
        <p className="mt-4 text-center text-sm text-text-muted">
          Free tier available. Pay once for unlocks — no subscription.
        </p>
      </div>

      {/* Three capability callouts */}
      <div className="grid grid-cols-1 gap-8 md:grid-cols-3 pb-16 border-t border-border pt-16">
        <div>
          <h2 className="font-serif text-xl text-text-base mb-3 leading-snug">
            Headings that navigate
          </h2>
          <p className="font-sans text-sm text-text-muted leading-relaxed">
            leafbind classifies text by rendered font size, not font name — so
            your section headings become a working Kindle chapter list, not a wall
            of undifferentiated paragraphs.
          </p>
        </div>
        <div>
          <h2 className="font-serif text-xl text-text-base mb-3 leading-snug">
            Footnotes that jump
          </h2>
          <p className="font-sans text-sm text-text-muted leading-relaxed">
            Superscript markers are matched to their footnote bodies and linked
            bidirectionally. Tap a citation number on your Kindle to jump to the
            note; tap the return link to come back.
          </p>
        </div>
        <div>
          <h2 className="font-serif text-xl text-text-base mb-3 leading-snug">
            Columns in order
          </h2>
          <p className="font-sans text-sm text-text-muted leading-relaxed">
            Multi-column academic papers are read column by column, not line by
            line across the full page width. IEEE papers, arXiv preprints, and
            ACM proceedings come out readable.
          </p>
        </div>
      </div>
    </>
  );
}
