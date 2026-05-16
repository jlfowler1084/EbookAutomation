// Image manifest (public/guides/pdf-to-kfx-for-kindle-scribe/):
//   s2k-columns-fail.jpg       — Calibre interleaved-columns failure, Kindle Scribe photo (Glubb, Fate of Empires, page 12%)
//   s2k-footnotes-stripped.jpg — Calibre flat endnote dump, Kindle Scribe photo (Jones, Mexico Illicit, Notes 21-37)
//   calibre-output.jpg         — Same shot as s2k-columns-fail (reuse)
//   leafbind-columns.jpg       — leafbind clean column flow, Kindle Scribe photo (Glubb, Introduction, landscape)
//   leafbind-footnotes.jpg     — Tappable footnote popup open, Kindle Scribe photo (Jones, Ch.1, footnote 109)
//   scribe-toc.jpg             — Chapter nav panel, Calibre viewer screenshot (Glubb: Introduction / The Fate of Empires / Search for Survival)

import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import JsonLd from "../../../../components/JsonLd";
import {
  type FAQPageSchema,
  type HowToSchema,
  type ArticleSchema,
} from "../../../../lib/structured-data";

// ISO 8601 with explicit ET offset — Schema.org Article date fields require timezone-qualified datetimes.
const PUBLISHED = "2026-05-15T00:00:00-04:00";
const SLUG = "pdf-to-kfx-for-kindle-scribe";
const CANONICAL = `https://leafbind.io/guides/${SLUG}`;
const HERO_IMAGE = `${CANONICAL}/leafbind-columns.jpg`;

export const metadata: Metadata = {
  title: "How to Convert PDFs to KFX for Kindle Scribe — leafbind",
  description:
    "Send-to-Kindle loses footnotes, merges columns, flattens headings. Learn why, " +
    "what Calibre can fix, and how leafbind delivers a clean KFX for Kindle Scribe.",
  alternates: {
    canonical: CANONICAL,
  },
  openGraph: {
    title: "How to Convert PDFs to KFX for Kindle Scribe — leafbind",
    description:
      "Footnotes, multi-column layouts, and heading structure — the three failure " +
      "modes that break every PDF converter, and how leafbind handles them differently.",
    type: "article",
    url: CANONICAL,
    images: [
      {
        url: "https://leafbind.io/quality/pipeline-columns.png",
        width: 800,
        height: 600,
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "How to Convert PDFs to KFX for Kindle Scribe — leafbind",
    description:
      "Why Send-to-Kindle and Calibre both fall short on academic PDFs — and what to do instead.",
    images: ["https://leafbind.io/quality/pipeline-columns.png"],
  },
};

// ── Schema ──────────────────────────────────────────────────────────────────

const articleSchema: ArticleSchema = {
  "@context": "https://schema.org",
  "@type": "Article",
  headline:
    "How to convert PDFs to KFX for Kindle Scribe (without Send-to-Kindle's quality loss)",
  description:
    "A practical guide covering the three realistic options for PDF to KFX conversion — " +
    "Send-to-Kindle, Calibre with the KFX Output plugin, and leafbind — with honest " +
    "assessments of failure modes, setup requirements, and output quality.",
  image: HERO_IMAGE,
  author: { "@type": "Person", name: "Joe Fowler", url: "https://github.com/jlfowler1084" },
  datePublished: PUBLISHED,
  dateModified: PUBLISHED,
  publisher: { "@type": "Organization", name: "leafbind", url: "https://leafbind.io" },
  url: CANONICAL,
};

const faqItems = [
  {
    q: "Does leafbind work on Mac, Windows, and Linux?",
    a: "Yes. leafbind is a web service — there is no software to install. Open any browser on any operating system, upload your PDF, and download the converted file. The conversion runs on leafbind's servers.",
  },
  {
    q: "Why are footnotes tappable in leafbind's output but not in Send-to-Kindle's?",
    a: "Footnote links have to be explicitly generated. In a native ebook, the author's editing software creates the links at export time. PDF-to-ebook conversion does not produce links automatically — the converter has to detect the superscript markers, match each marker to its footnote body, and write anchor pairs into the EPUB. Send-to-Kindle does not do this step. leafbind does: the pipeline identifies markers in body text, matches them to the corresponding footnote blocks at the bottom of each page region, and writes the linked pairs explicitly. In the KFX output, those links become Kindle's native footnote popups.",
  },
  {
    q: "Can I use Calibre to convert a multi-column PDF to KFX for Kindle Scribe?",
    a: "Calibre's manual (v9.8.0) states directly: \"Complex, multi-column, and image-based documents are not supported.\" This is a documented architectural limitation, not a temporary bug. For single-column PDFs, Calibre with the KFX Output plugin works well. For two-column academic papers and conference proceedings, the column interleaving problem applies — the same problem as Send-to-Kindle.",
  },
  {
    q: "Can I convert a PDF without an internet connection?",
    a: "Not with leafbind — it is a web service that requires a connection. For offline conversion, Calibre is the correct choice: install it on your desktop, install the KFX Output plugin and KFX Support Files, and convert locally. The tradeoff is Calibre's documented limitation on complex layouts.",
  },
  {
    q: "How large can the PDF be?",
    a: "Free tier: up to 20 MB per file, 3 conversions per day. Premium tier: up to 100 MB per file. Most academic papers and book chapters are well under 20 MB; book-length PDF scans often exceed it.",
  },
  {
    q: "Does leafbind handle scanned PDFs?",
    a: "Yes. When the pipeline encounters a scanned page — one where the PDF contains an image rather than text objects — it routes the page through an OCR pass powered by Gemini 2.0 Flash. The OCR output is text, so heading classification and footnote detection run on it as they would on a native-text page. Clean black-and-white scans of academic papers produce accurate OCR; heavily degraded historical documents produce more artifacts, flagged in the conversion report.",
  },
  {
    q: "Which Kindle devices support KFX format?",
    a: "KFX is supported on all Kindle devices released from 2018 onward: Paperwhite (10th generation and later), basic Kindle (10th generation and later), Oasis (9th generation and later), and all Kindle Scribe hardware. For older devices, choose EPUB output — the free tier produces EPUB, which works on all Kindle devices but without the KFX-specific typography improvements.",
  },
];

const faqSchema: FAQPageSchema = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: faqItems.map((item) => ({
    "@type": "Question",
    name: item.q,
    acceptedAnswer: { "@type": "Answer", text: item.a },
  })),
};

const howToSchema: HowToSchema = {
  "@context": "https://schema.org",
  "@type": "HowTo",
  name: "How to convert a PDF to KFX and side-load it onto a Kindle Scribe",
  step: [
    {
      "@type": "HowToStep",
      name: "Upload your PDF",
      text: "Navigate to leafbind.io/convert/pdf-to-kfx. Drag your PDF onto the upload area or click to open the file browser. The upload is encrypted in transit. The conversion starts automatically after upload.",
    },
    {
      "@type": "HowToStep",
      name: "Select KFX as the output format",
      text: "After upload, change the format selector from EPUB to KFX. If you have not unlocked a premium conversion, you will be prompted to do so — KFX is a premium output format.",
    },
    {
      "@type": "HowToStep",
      name: "Review the conversion report",
      text: "When conversion completes, the report shows headings detected, table of contents structure, and whether any pages required OCR fallback. Review it before downloading.",
    },
    {
      "@type": "HowToStep",
      name: "Download the KFX file",
      text: "Click the download button to save the .kfx container file. It is compatible with all Kindle devices released since 2018.",
    },
    {
      "@type": "HowToStep",
      name: "Side-load to your Kindle Scribe",
      text: "Connect the Scribe via USB-C and copy the KFX file into the Documents folder, or email the file to your Kindle personal document address (found in Kindle Settings > Your Account > Send-to-Kindle). The file appears in your library under Books.",
    },
  ],
};

// ── Page ─────────────────────────────────────────────────────────────────────

export default function PdfToKfxGuide() {
  return (
    <>
      <JsonLd schema={articleSchema} />
      <JsonLd schema={faqSchema} />
      <JsonLd schema={howToSchema} />

      {/* Page header */}
      <div className="py-12 md:py-16 border-b border-border mb-16">
        <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-5">
          Kindle Scribe guide
        </p>
        <h1 className="font-serif text-5xl md:text-6xl leading-tight text-text-base mb-6 max-w-3xl">
          How to convert PDFs to KFX for Kindle Scribe
        </h1>
        <p className="font-sans text-lg text-text-muted leading-relaxed max-w-2xl">
          Send-to-Kindle gets the file onto the device. What it does not get right:
          multi-column layouts, footnotes, and heading structure. This guide covers the
          three realistic options and what each one actually produces.
        </p>
        <p className="font-mono text-xs text-text-muted mt-6">
          By Joe Fowler — Updated {new Date(PUBLISHED).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })}
        </p>
      </div>

      <div className="py-0">

        {/* ── Section 1: Hook ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              If you bought a Kindle Scribe expecting to use it for serious document reading —
              research papers, academic monographs, conference proceedings — you have probably
              already tried Send-to-Kindle. It works in the narrow sense: the file arrives on the
              device and can be opened. It works less well in the sense of being readable.
            </p>
            <p>
              The specific problems are consistent. Multi-column papers become interleaved text
              streams — sentences from the left column and right column alternating line by line,
              because the conversion reads the page left-to-right without recognizing the column
              boundary. Footnotes vanish from their citation positions or reappear, disconnected,
              at the document end. Section headings flatten to plain paragraphs, taking the table
              of contents with them. On a device designed for focused long-form reading, these are
              not cosmetic issues — they turn a structured academic document into something closer
              to an OCR dump.
            </p>
            <p>
              This guide covers the three realistic options for getting a PDF onto a Kindle Scribe
              in a form that reads correctly: Amazon&rsquo;s own Send-to-Kindle service, Calibre with
              the KFX Output plugin, and leafbind. Each is assessed with its actual failure modes
              described specifically — not to push a recommendation, but because knowing the
              tradeoffs lets you pick the right tool for your actual document type.
            </p>
          </div>
        </section>

        {/* ── Section 2: Send-to-Kindle problem ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            The Send-to-Kindle quality problem
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              Amazon&rsquo;s Send-to-Kindle service is designed for convenience, not fidelity.
              Emails arrive at your Kindle personal document address and appear in your library
              within minutes, converted to Kindle format. For a simple PDF — one column, no
              footnotes, section headings with obvious font-size differences — the results are
              usable. For academic and technical PDFs, the failure modes are structural and
              predictable.
            </p>

            <h3 className="font-serif text-xl text-text-base pt-2 leading-snug">Multi-column text</h3>
            <p>
              Journal articles, IEEE papers, conference proceedings, and most academic papers
              printed in US letter or A4 format use a two-column layout. This is a typesetting
              convention that makes efficient use of the page area at standard point sizes. The
              problem is that Amazon&rsquo;s conversion reads the PDF in the internal text stream
              order — which interleaves both columns line by line as they appear on the page.
            </p>
            <p>
              A concrete example: an economics paper formatted in two columns. Left column,
              line 1: &ldquo;The monetary transmission mechanism operates through...&rdquo; Right column,
              line 1: &ldquo;methodology, we regress inflation on lagged output...&rdquo; After conversion,
              the Kindle document reads: &ldquo;The monetary transmission mechanism operates through
              methodology, we regress inflation on lagged output...&rdquo; Both sentences appear
              immediately after each other because they occupied the same horizontal strip on the
              original page. Every line of every two-column page is interleaved this way.
            </p>

            <figure className="my-8 max-w-2xl">
              <Image
                src="/guides/pdf-to-kfx-for-kindle-scribe/s2k-columns-fail.jpg"
                alt="Kindle Scribe showing the Introduction page of Glubb's Fate of Empires, with two-column source text interleaved line-by-line into a single broken text flow."
                width={1500}
                height={2000}
                sizes="(min-width: 768px) 672px, 100vw"
                className="w-full h-auto rounded-md border border-border shadow-sm"
              />
              <figcaption className="mt-2 text-sm text-text-muted leading-relaxed">
                Send-to-Kindle and Calibre both interleave two-column text. Each line you
                see is one line of the left column followed immediately by one line of the
                right column from the source PDF. Source: J.B. Glubb, <em>The Fate of
                Empires</em>, Introduction.
              </figcaption>
            </figure>

            <h3 className="font-serif text-xl text-text-base pt-2 leading-snug">Footnotes</h3>
            <p>
              Academic writing uses footnotes heavily. In PDF, a footnote is positioned at the
              bottom of a physical page — a positional artifact of the print layout model. When
              the page model is stripped to create a reflowable Kindle document, footnotes lose
              their anchor to the text they annotate. Amazon&rsquo;s service either appends all
              footnotes to the end of the document (accessible but unlinked) or drops them
              entirely.
            </p>
            <p>
              There are no tappable links. A superscript &ldquo;14&rdquo; in the body text is just text
              characters — it does not navigate to footnote 14. To check a footnote, you navigate
              manually to the back of the document, find the footnote by scanning the appended
              list, then navigate back to your reading position. For a paper with 40-60 footnotes,
              this is impractical.
            </p>

            <figure className="my-8 max-w-2xl">
              <Image
                src="/guides/pdf-to-kfx-for-kindle-scribe/s2k-footnotes-stripped.jpg"
                alt="Kindle Scribe showing the Notes section of Mexico's Illicit Drug Networks: a flat numbered list of citations 21-37 with no links back to the body text."
                width={1500}
                height={2000}
                sizes="(min-width: 768px) 672px, 100vw"
                className="w-full h-auto rounded-md border border-border shadow-sm"
              />
              <figcaption className="mt-2 text-sm text-text-muted leading-relaxed">
                Calibre output of the Notes section: a flat numbered list with no links
                back to the citation markers in the body text. Locating a referenced
                source means flipping to the back of the document and scanning manually.
                Source: Nathan Jones, <em>Mexico&rsquo;s Illicit Drug Networks</em>, Notes
                entries 21-37.
              </figcaption>
            </figure>

            <h3 className="font-serif text-xl text-text-base pt-2 leading-snug">Heading detection and chapter navigation</h3>
            <p>
              PDF is a visual format, not a semantic one. A section heading is text that the
              author formatted in a larger size — the format itself does not record &ldquo;this is a
              heading.&rdquo; Amazon&rsquo;s conversion attempts to classify headings by font properties,
              but the heuristics miss frequently in condensed academic layouts where body text is
              10pt and section headings are 12pt or 13pt. Missed headings mean no Kindle chapter
              list. The table of contents shows the document title and nothing else. The Kindle
              Scribe&rsquo;s chapter navigation feature — the progress bar at the bottom of the screen,
              swipe gestures to jump between chapters — works only when chapters are detected.
            </p>

            <h3 className="font-serif text-xl text-text-base pt-2 leading-snug">Scanned documents</h3>
            <p>
              Many academic papers available through library archives are scanned images rather
              than text PDFs — common for older publications from JSTOR, HathiTrust, and similar
              repositories. Send-to-Kindle converts the scanned image without running OCR. The
              result is a non-reflowable document: text you can zoom but not resize by changing
              your Kindle font preference. On the Kindle Scribe&rsquo;s 10.2-inch screen, zooming a
              scanned page typically means horizontal scrolling — a reading experience worse than
              a laptop screen.
            </p>
          </div>
        </section>

        {/* ── Section 3: Calibre ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            Calibre with the KFX Output plugin — the technical option
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              Calibre is the most capable open-source ebook manager, and with the KFX Output
              plugin installed, it can produce native KFX files from a range of input formats.
              For many use cases, it is the correct tool.
            </p>
            <p>
              The calibration for PDF specifically is important to understand. Calibre&rsquo;s own
              manual (v9.8.0) states directly:{" "}
              <em>
                &ldquo;Complex, multi-column, and image-based documents are not supported.&rdquo;
              </em>{" "}
              This is not a temporary limitation or a community-maintained FAQ entry — it is
              in the official documentation, and it reflects a genuine architectural constraint
              in how Calibre reads PDF files. The column-interleaving problem described in the
              previous section applies equally to Calibre as to Send-to-Kindle. For a two-column
              journal article, Calibre and Send-to-Kindle produce structurally similar output.
            </p>

            <figure className="my-8 max-w-2xl">
              <Image
                src="/guides/pdf-to-kfx-for-kindle-scribe/calibre-output.jpg"
                alt="Kindle Scribe showing a Calibre conversion of Glubb's Fate of Empires, page 5%. The same column-interleaving artifact as the Send-to-Kindle output appears, confirming the architectural constraint."
                width={1500}
                height={2000}
                sizes="(min-width: 768px) 672px, 100vw"
                className="w-full h-auto rounded-md border border-border shadow-sm"
              />
              <figcaption className="mt-2 text-sm text-text-muted leading-relaxed">
                Calibre output of an alternate Glubb passage. The interleaving artifact is
                identical to the Send-to-Kindle output above — both tools are constrained
                by the PDF text-stream order, not by their conversion logic. Source:
                Glubb, <em>The Fate of Empires</em>, page 5% region.
              </figcaption>
            </figure>

            <p>
              For single-column PDFs — a novel, a business book, most non-fiction prose — Calibre
              performs well. The PDF extraction produces a clean EPUB, the heading heuristics work
              for simple font hierarchies, and the KFX Output plugin handles the EPUB &rarr; KFX step
              reliably. If your document is structurally simple, Calibre is a viable free option.
            </p>

            <h3 className="font-serif text-xl text-text-base pt-2 leading-snug">The setup requirement</h3>
            <p>
              Producing KFX via Calibre requires: installing Calibre itself, installing the KFX
              Output plugin (available in Calibre&rsquo;s plugin repository), downloading and installing
              the KFX Support Files (a separate package), and registering a Kindle device with
              Calibre so the necessary support infrastructure is in place. This is a one-time
              setup, but it involves several steps that assume comfort with desktop software
              installation and file management. For a user who wants to convert one paper to read
              on a Kindle Scribe this afternoon, the setup cost may exceed the benefit.
            </p>

            <h3 className="font-serif text-xl text-text-base pt-2 leading-snug">No automated quality check</h3>
            <p>
              After conversion, there is no feedback mechanism to verify that headings were
              detected correctly, that footnotes survived the conversion, or that the table of
              contents has the expected structure. You sideload the file to your device, open it,
              and find out. If something is wrong — a heading misclassified, a footnote block
              appended unlinked — you adjust Calibre settings and repeat. The iteration loop is
              manual.
            </p>
            <p>
              For a developer or technically inclined user converting a small set of
              well-structured single-column PDFs, Calibre is reasonable. For converting research
              papers with two-column layouts, extensive footnotes, or OCR requirements, the
              architectural limitation documented in the official manual applies directly.
            </p>
          </div>
        </section>

        {/* ── Section 4: leafbind approach ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <div className="grid grid-cols-1 md:grid-cols-5 gap-8 md:gap-12 items-start">
            <div className="md:col-span-3">
              <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
                The leafbind approach
              </h2>
              <div className="text-text-base leading-relaxed space-y-4 text-base">
                <p>
                  leafbind addresses the PDF-to-KFX problem at the extraction layer — the step
                  where quality is actually determined — rather than at the EPUB-to-KFX step
                  where most converters spend their effort.
                </p>

                <h3 className="font-serif text-xl text-text-base pt-2 leading-snug">Column detection</h3>
                <p>
                  Every text object in a PDF has an x/y coordinate: the position on the page
                  where the text was rendered. The extraction pipeline uses those coordinates to
                  cluster text objects into columns before reading them. For a standard two-column
                  academic paper, the pipeline identifies the column boundary from the horizontal
                  coordinate distribution, then reads each column top-to-bottom in sequence. The
                  left column is extracted as a complete unit; the right column follows. No
                  interleaving.
                </p>
                <p>
                  For more complex layouts — a full-width header above two columns, or a sidebar
                  alongside single-column text — the coordinate clustering applies recursively
                  until each text block is identified and ordered. The result matches what you
                  would read if you were tracing the text manually on the physical page.
                </p>

                <figure className="my-8 max-w-2xl">
                  <Image
                    src="/guides/pdf-to-kfx-for-kindle-scribe/leafbind-columns.jpg"
                    alt="Kindle Scribe showing the same Glubb Fate of Empires Introduction passage after leafbind conversion, with the left column read completely before the right column begins, producing a continuous readable flow."
                    width={1500}
                    height={2000}
                    sizes="(min-width: 768px) 672px, 100vw"
                    className="w-full h-auto rounded-md border border-border shadow-sm"
                  />
                  <figcaption className="mt-2 text-sm text-text-muted leading-relaxed">
                    leafbind output of the same Glubb passage shown above. The left
                    column reads completely before the right column begins. Compare with
                    the interleaved Calibre/Send-to-Kindle output of the same source.
                  </figcaption>
                </figure>

                <h3 className="font-serif text-xl text-text-base pt-2 leading-snug">Heading classification</h3>
                <p>
                  The pipeline computes a font-size histogram across all text objects in the
                  document. The peak of that histogram represents the body-text size — typically
                  10pt or 11pt in an academic paper. Text runs that exceed the body-text mode by
                  a measurable threshold are classified as headings. The threshold is applied to
                  the rendered font size, not the font name or weight, which makes it robust to
                  the font-substitution artifacts common in older PDFs.
                </p>
                <p>
                  Headings classified as h2 appear in the Kindle&rsquo;s table of contents as chapters.
                  Headings classified as h3 appear as sections within chapters. The navigable
                  chapter list that Kindle readers expect from commercial ebooks is present in the
                  converted KFX file.
                </p>

                <figure className="my-8 max-w-2xl">
                  <Image
                    src="/guides/pdf-to-kfx-for-kindle-scribe/scribe-toc.jpg"
                    alt="Kindle Scribe chapter navigation panel for a leafbind-converted KFX of Cooper's The Oil Kings, showing PART ONE: GLADIATOR and PART TWO: SHOWDOWN with numbered chapters nested under each part."
                    width={1500}
                    height={2000}
                    sizes="(min-width: 768px) 672px, 100vw"
                    className="w-full h-auto rounded-md border border-border shadow-sm"
                  />
                  <figcaption className="mt-2 text-sm text-text-muted leading-relaxed">
                    Kindle Scribe chapter list from a leafbind-converted KFX. Detected
                    headings nest into the part / chapter hierarchy that the source
                    document defined. Source: Andrew Scott Cooper, <em>The Oil Kings</em>,
                    showing PART ONE: GLADIATOR and PART TWO: SHOWDOWN.
                  </figcaption>
                </figure>

                <h3 className="font-serif text-xl text-text-base pt-2 leading-snug">Footnote linking</h3>
                <p>
                  The pipeline identifies footnote markers in body text — superscript numerics,
                  symbolic markers (* and &dagger;), and styled references — by their rendered
                  position above the text baseline and their smaller-than-body-text font size. It
                  then locates the corresponding footnote body at the bottom of the page region,
                  matching markers by number or symbol in order of appearance. Each matched pair
                  generates a linked anchor in the EPUB output: one at the in-text citation, one
                  at the footnote body. In the KFX file, those links become Kindle&rsquo;s native
                  footnote popups. Tapping a superscript in body text opens the footnote as an
                  overlay; tapping elsewhere closes it and returns to the reading position.
                </p>

                <figure className="my-8 max-w-2xl">
                  <Image
                    src="/guides/pdf-to-kfx-for-kindle-scribe/leafbind-footnotes.jpg"
                    alt="Kindle Scribe showing a body paragraph from Mexico's Illicit Drug Networks Chapter 1 with a footnote popup open as an overlay, displaying the citation text for footnote 1."
                    width={1500}
                    height={2000}
                    sizes="(min-width: 768px) 672px, 100vw"
                    className="w-full h-auto rounded-md border border-border shadow-sm"
                  />
                  <figcaption className="mt-2 text-sm text-text-muted leading-relaxed">
                    Tappable footnote popup on a Kindle Scribe. Tapping the superscript
                    marker in the body text opens the citation as an overlay; tapping
                    outside dismisses it and returns to the reading position. Source:
                    Jones, <em>Mexico&rsquo;s Illicit Drug Networks</em>, Chapter 1.
                  </figcaption>
                </figure>

                <h3 className="font-serif text-xl text-text-base pt-2 leading-snug">OCR for scanned documents</h3>
                <p>
                  When the pipeline encounters a scanned page — one where the PDF contains an
                  image object rather than text — it routes the page through an OCR pass powered
                  by Gemini 2.0 Flash. The OCR output is text, so heading classification and
                  footnote detection run on it as they would on a native-text page. Clean
                  black-and-white scans of academic papers produce accurate OCR; heavily degraded
                  historical documents produce more artifacts, flagged in the conversion report.
                </p>

                <h3 className="font-serif text-xl text-text-base pt-2 leading-snug">Visual quality verification</h3>
                <p>
                  After the KFX file is produced, the pipeline renders it back to images via
                  Calibre and runs an automated quality check. The check confirms heading
                  hierarchy, table of contents structure, and footnote link integrity. If the
                  check detects an anomaly, it surfaces in the conversion report before you
                  download the file.
                </p>

                <p className="text-text-muted text-sm">
                  KFX output is a premium feature — the multi-stage pipeline requires computational
                  resources beyond what the free tier supports. Free tier conversions produce EPUB.{" "}
                  <Link href="/pricing" className="text-accent no-underline hover:underline font-medium">
                    Pricing details →
                  </Link>
                </p>
              </div>
            </div>

            <div className="md:col-span-2 mt-2 md:mt-12">
              <div className="bg-white border border-border rounded-md p-6 shadow-sm">
                <p className="font-mono text-xs font-medium text-text-muted uppercase tracking-widest mb-3">
                  See it in practice
                </p>
                <p className="text-base text-text-base leading-relaxed mb-4">
                  Side-by-side screenshots comparing Calibre output against leafbind output
                  for the same academic PDF — columns, footnotes, and headings.
                </p>
                <Link
                  href="/quality"
                  className="text-sm font-medium text-accent no-underline hover:underline"
                >
                  View quality comparison →
                </Link>
              </div>
            </div>
          </div>
        </section>

        {/* ── Section 5: Step-by-step walkthrough ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            Step-by-step: convert a PDF and read it on Kindle Scribe
          </h2>
          <p className="text-base text-text-base leading-relaxed mb-8 max-w-2xl">
            These steps assume a PDF ready to convert and a Kindle Scribe accessible via USB
            or on the same Wi-Fi network.
          </p>
          <ol className="space-y-8 max-w-2xl">
            {[
              {
                n: "1",
                title: "Upload your PDF",
                body: "Navigate to leafbind.io/convert/pdf-to-kfx. Drag your PDF onto the upload area or click to open the file browser. Files up to 20 MB are supported on the free tier; premium plans support up to 100 MB. The upload is encrypted in transit. The conversion starts automatically — no settings to configure before upload; the pipeline detects document structure and applies the correct extraction path.",
              },
              {
                n: "2",
                title: "Select KFX as the output format",
                body: "After upload, the format selector defaults to EPUB. Change it to KFX. If you have not unlocked a premium conversion, you will be prompted to do so — KFX is a premium output format. You can complete the unlock without creating an account; a single-conversion credit is the minimum purchase.",
              },
              {
                n: "3",
                title: "Monitor the conversion stages",
                body: "The conversion report shows progress across four pipeline stages: extraction, structure analysis, heading classification, and KFX output. For a 40-page text-native academic paper, total conversion time is typically 15–30 seconds. For a 200-page scanned document routed through OCR, expect 2–5 minutes.",
              },
              {
                n: "4",
                title: "Review the conversion report",
                body: "When conversion completes, the report shows the number of headings detected, the table of contents structure, and whether any pages required the OCR fallback. If heading detection found fewer headings than expected, the report flags it. For most academic papers and technical documents, the report shows no issues.",
              },
              {
                n: "5",
                title: "Download the KFX file",
                body: "Click the download button. The file is a .kfx container, compatible with all Kindle devices released since 2018, including all Kindle Scribe hardware.",
              },
              {
                n: "6",
                title: "Side-load to your Kindle Scribe",
                body: "Via USB: connect the Scribe with a USB-C cable, open the Documents folder on the device, copy the KFX file in, then eject. Via email: attach the KFX file to an email and send it to your Kindle personal document address (Kindle Settings → Your Account → Send-to-Kindle). The file appears in your library under Books within a minute or two.",
              },
              {
                n: "7",
                title: "Verify on-device",
                body: "Open the document on the Scribe. Confirm: does the table of contents list chapters? (Swipe from the left edge or tap the menu.) Are footnote superscripts tappable links? (Tap one — a popup should appear with the footnote text.) Does the document reflow at your current font size? If all three are correct, the conversion worked as intended.",
              },
            ].map((step) => (
              <li key={step.n} className="flex gap-5">
                <div className="flex-shrink-0 w-8 h-8 rounded-sm bg-accent flex items-center justify-center">
                  <span className="text-sm font-medium text-white">{step.n}</span>
                </div>
                <div>
                  <h3 className="font-medium text-brand text-base mb-1">{step.title}</h3>
                  <p className="text-base text-text-base leading-relaxed">{step.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        {/* ── Section 6: Edge cases ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            Edge cases worth knowing
          </h2>
          <div className="max-w-3xl space-y-6">
            {[
              {
                heading: "Scanned academic papers",
                body: "Papers scanned from physical journals are common in university library databases. The pipeline routes them through OCR, which handles clean black-and-white scans well. For color scans or documents with complex embedded images (microscopy, charts), the text extraction is accurate but embedded images are placed as inline block images rather than floating figures. The text reads correctly; image positioning is approximate.",
              },
              {
                heading: "Papers with extensive figures",
                body: "Academic papers often include numbered figures with captions referenced from the body. Figures are extracted and placed inline at approximately the position they occupied on the original page. Figure captions are preserved as regular text. The link between an in-text \"see Figure 3\" and the actual figure is not generated — this requires semantic understanding of figure references that the pipeline does not currently attempt.",
              },
              {
                heading: "Books with endnotes rather than footnotes",
                body: "Many academic books collect notes at the back rather than at the bottom of each page. The pipeline detects these as a separate block of text in a consistent format — numbered list, set apart in a distinct section — and links them to their in-text citations by number matching. The behavior is the same as for footnotes: tapping the superscript in body text opens the endnote as a Kindle popup.",
              },
              {
                heading: "Very long documents",
                body: "Heading detection and footnote linking scale linearly with document length. A 600-page academic monograph takes longer than a 40-page paper but produces the same quality. The main practical consideration is that very long scanned documents will take several minutes for the OCR pass.",
              },
              {
                heading: "Multi-column papers in landscape orientation",
                body: "Some technical reports and older journal formats use landscape-oriented pages with three or four columns. The coordinate-based extraction handles these correctly — the column detection reads any number of columns as long as they have distinct horizontal bounding boxes. The column count is determined by the document, not hardcoded.",
              },
            ].map((item) => (
              <div key={item.heading}>
                <h3 className="font-serif text-xl text-brand mb-2 leading-snug">{item.heading}</h3>
                <p className="text-base text-text-base leading-relaxed max-w-2xl">{item.body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ── Section 7: FAQ ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-8 leading-snug">
            Frequently asked questions
          </h2>
          <div className="space-y-8 max-w-3xl">
            {faqItems.map((item) => (
              <div key={item.q}>
                <h3 className="font-serif text-xl text-brand mb-2 leading-snug">{item.q}</h3>
                <p className="text-base text-text-base leading-relaxed">{item.a}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ── Cross-links ── */}
        <section className="mb-16">
          <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-4">
            Related
          </p>
          <div className="flex flex-wrap gap-4">
            <Link
              href="/convert/pdf-to-kfx"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-2 hover:bg-accent/5"
            >
              PDF to KFX converter →
            </Link>
            <Link
              href="/convert/academic-pdf-to-kindle"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-2 hover:bg-accent/5"
            >
              Academic PDF to Kindle →
            </Link>
            <Link
              href="/convert/multi-column-pdf-kindle"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-2 hover:bg-accent/5"
            >
              Multi-column PDF conversion →
            </Link>
            <Link
              href="/quality"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-2 hover:bg-accent/5"
            >
              Quality comparison →
            </Link>
            <Link
              href="/pricing"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-2 hover:bg-accent/5"
            >
              Premium plans →
            </Link>
          </div>
        </section>

        {/* ── CTA + author bio ── */}
        <section className="border-t border-border pt-16 pb-8">
          <h2 className="font-serif text-3xl text-text-base mb-4 leading-snug">
            Try leafbind free
          </h2>
          <p className="font-sans text-base text-text-muted leading-relaxed mb-2 max-w-xl">
            Upload a PDF and convert to EPUB at no cost — 3 conversions per day, up to 20 MB,
            no account required. KFX output (heading detection, footnote linking, visual QA
            pass) is available on premium plans with single-conversion credits.
          </p>
          <p className="font-sans text-sm text-text-muted leading-relaxed mb-8">
            <Link href="/pricing" className="text-brand font-medium no-underline hover:underline">
              See pricing
            </Link>{" "}
            — plans start at a single conversion credit with no subscription required.
          </p>
          <Link
            href="/convert/pdf-to-kfx"
            className="font-sans inline-block bg-brand text-white font-medium text-base px-8 py-3 rounded-sm no-underline hover:opacity-90"
          >
            Convert a PDF to KFX
          </Link>

          <div className="mt-12 pt-8 border-t border-border max-w-xl">
            <p className="font-sans text-sm text-text-muted leading-relaxed">
              <span className="font-medium text-text-base">Joe Fowler</span> is a developer and
              technical writer who built leafbind after spending an unreasonable amount of time
              coaxing academic PDFs into something readable on a Kindle. He writes about PDF
              structure, ebook formats, and the conversion pipeline at leafbind.io.
            </p>
          </div>
        </section>

      </div>
    </>
  );
}
