import type { Metadata } from "next";
import Link from "next/link";
import JsonLd from "../../../../components/JsonLd";
import {
  buildArticleSchema,
  buildFAQPageSchema,
} from "../../../../lib/structured-data";

// ISO 8601 with explicit ET offset — Schema.org Article date fields require timezone-qualified datetimes.
const PUBLISHED = "2026-05-17T00:00:00-04:00";
const SLUG = "kindle-scribe-vs-remarkable";
const CANONICAL = `https://leafbind.io/guides/${SLUG}`;

export const metadata: Metadata = {
  title: "Kindle Scribe vs reMarkable vs iPad vs Paperwhite: Best for PDFs? — leafbind",
  description:
    "Comparing the Kindle Scribe, reMarkable Paper Pro, iPad, and Kindle Paperwhite for reading PDFs. " +
    "Which is best for academic papers, note-taking, and general reading — and what none of them solve alone.",
  alternates: {
    canonical: CANONICAL,
  },
  openGraph: {
    title: "Kindle Scribe vs reMarkable vs iPad vs Paperwhite: Best for PDFs? — leafbind",
    description:
      "A use-case-first comparison of four e-reading devices for PDF-heavy workflows — " +
      "academic papers, annotations, general reading, and multi-column documents.",
    type: "article",
    url: CANONICAL,
    images: [
      {
        url: "https://leafbind.io/quality/pipeline-headings.png",
        width: 800,
        height: 600,
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Kindle Scribe vs reMarkable vs iPad vs Paperwhite: Best for PDFs? — leafbind",
    description:
      "Which device is best for reading PDFs? A comparison of Kindle Scribe, reMarkable, iPad, " +
      "and Paperwhite — with honest coverage of each device's tradeoffs.",
    images: ["https://leafbind.io/quality/pipeline-headings.png"],
  },
};

// ── FAQ items as single source of truth ────────────────────────────────────

const faqItems = [
  {
    q: "Can the Kindle Scribe handle multi-column PDFs?",
    a: "Not well, when files are sent via Send-to-Kindle. Amazon's conversion reads PDFs in their internal text stream order, which interleaves two-column text line by line rather than column by column. A two-column journal article arrives on the Scribe with both columns mixed together. The same problem applies to reMarkable and iPad PDF viewers when opening the file natively. The fix is to convert the PDF to a properly structured format before loading it — not a device-specific solution.",
  },
  {
    q: "Is the iPad worth buying just for reading PDFs?",
    a: "The iPad is the most flexible PDF device in this comparison — it supports every file format, every app, and every annotation style — but that flexibility comes with tradeoffs that matter for long reading sessions: glossy LCD screen causes eye fatigue over extended periods, battery drains faster than e-ink devices, and the device is heavier to hold for an hour of reading. If PDF reading is a primary use case rather than one of many, a dedicated e-ink device usually produces less fatigue.",
  },
  {
    q: "Does the reMarkable Paper Pro work with the Kindle library?",
    a: "No. The reMarkable Paper Pro does not access the Kindle store or your Kindle library. It supports PDF and EPUB files transferred via USB or the reMarkable cloud sync app, but it does not connect to Amazon's ecosystem. Books purchased from the Kindle store are in AZW3 or KFX format with DRM and cannot be transferred to reMarkable. If you have an existing Kindle library, the reMarkable is a supplementary device, not a replacement.",
  },
  {
    q: "Will my PDFs look good on a 6-inch Kindle Paperwhite?",
    a: "For simple single-column PDFs — a novel, a report, a business document — the Paperwhite's 7-inch screen (12th gen) renders text cleanly at 300 PPI. For academic papers in standard letter or A4 format with two-column layouts, the 7-inch screen makes text uncomfortably small when the full page is displayed. You can zoom in, but that introduces horizontal scrolling. For serious PDF reading, a 10-inch or larger screen is the practical minimum.",
  },
  {
    q: "Can I annotate PDFs on the Kindle Scribe?",
    a: "Yes. The Kindle Scribe supports handwritten annotations directly on PDF documents using the included Pen. Notes appear as handwriting overlaid on the page and are stored in the document. The Scribe also supports typed notes. Annotation syncs to the Kindle app on other devices. The reMarkable Paper Pro's annotation experience is generally considered more refined — the paper-like texture of the reMarkable screen gives better stylus feedback than the Scribe's glass surface.",
  },
  {
    q: "What is the difference between the Kindle Scribe and the Kindle Scribe Colorsoft?",
    a: "The Kindle Scribe uses a monochrome e-ink display. The Kindle Scribe Colorsoft adds Amazon's Colorsoft display technology — a color e-ink panel that renders color content and covers. For PDF reading, color is most useful for documents with charts, figures, and highlighted text. For plain academic papers, the color difference is minimal. Both support the same note-taking features and pen input. The Colorsoft variant is priced at a premium tier above the standard Scribe.",
  },
  {
    q: "Which device has the best battery life for long reading sessions?",
    a: "E-ink devices (Kindle Scribe, Kindle Paperwhite, reMarkable Paper Pro) all have significantly better battery life than the iPad. The Kindle Scribe and Paperwhite are rated for several weeks of reading on a single charge; the reMarkable Paper Pro for approximately one to two weeks. The iPad's battery supports roughly 10 hours of active use. For week-long travel without charging access, any e-ink device is preferable to the iPad.",
  },
];

// ── Schemas ────────────────────────────────────────────────────────────────

const articleSchema = buildArticleSchema({
  headline:
    "Kindle Scribe vs reMarkable vs iPad vs Paperwhite: which is best for reading PDFs?",
  description:
    "A use-case-first comparison of the Kindle Scribe, reMarkable Paper Pro, iPad, and " +
    "Kindle Paperwhite for PDF-heavy workflows — academic papers, annotation, general " +
    "reading, and the multi-column problem none of them solve by default.",
  image: "https://leafbind.io/quality/pipeline-headings.png",
  datePublished: PUBLISHED,
  dateModified: PUBLISHED,
  url: CANONICAL,
  author: { name: "Joe Fowler", url: "https://github.com/jlfowler1084" },
});

const faqSchema = buildFAQPageSchema(faqItems);

// ── Page ───────────────────────────────────────────────────────────────────

export default function KindleScribeVsRemarkable() {
  return (
    <>
      <JsonLd schema={articleSchema} />
      <JsonLd schema={faqSchema} />

      {/* Page header */}
      <div className="py-12 md:py-16 border-b border-border mb-16">
        <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-5">
          Device comparison
        </p>
        <h1 className="font-serif text-3xl sm:text-4xl md:text-5xl lg:text-6xl leading-tight text-text-base mb-6 max-w-3xl">
          Kindle Scribe vs reMarkable vs iPad vs Paperwhite: Which Is Best for Reading PDFs?
        </h1>
        <p className="font-sans text-lg text-text-muted leading-relaxed max-w-2xl">
          For academic PDFs, the Kindle Scribe is the best e-ink choice within
          the Kindle ecosystem; the reMarkable Paper Pro for handwriting-first
          workflows outside it; the iPad for flexibility at the cost of screen
          and battery. But whichever device you choose, all four share the same
          problem with multi-column PDFs — and that problem has a device-agnostic
          fix.
        </p>
        <p className="font-mono text-xs text-text-muted mt-6">
          By Joe Fowler &mdash; Updated{" "}
          {new Date(PUBLISHED).toLocaleDateString("en-US", {
            year: "numeric",
            month: "long",
            day: "numeric",
          })}
        </p>
      </div>

      <div className="py-0">

        {/* ── TL;DR ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            TL;DR — which device for which use case
          </h2>
          <div className="space-y-4 max-w-2xl">
            {[
              {
                condition: "If you want Kindle library access + e-ink + note-taking",
                verdict: "Kindle Scribe or Kindle Scribe Colorsoft. Large e-ink screen, included Pen, Kindle ecosystem. Colorsoft adds color display at a premium price tier.",
              },
              {
                condition: "If you want the best handwriting experience on a paper-like screen",
                verdict: "reMarkable Paper Pro. The paper-texture screen produces better stylus feedback than any Kindle. Trade-off: no Kindle ecosystem, limited app support.",
              },
              {
                condition: "If you want one device for reading, annotation, email, and everything else",
                verdict: "iPad. No e-ink limitations, every app available, every file format supported. Trade-off: glossy screen causes more eye fatigue than e-ink for extended reading.",
              },
            ].map((item) => (
              <div key={item.condition} className="border border-border rounded-sm p-5 bg-surface">
                <p className="font-sans text-sm font-medium text-text-muted mb-1">
                  {item.condition}
                </p>
                <p className="font-sans text-base text-text-base leading-relaxed">
                  {item.verdict}
                </p>
              </div>
            ))}
          </div>
          <p className="font-sans text-sm text-text-muted mt-5 max-w-2xl">
            None of these devices solves the multi-column PDF problem by default.
            That requires converting the PDF before loading — see{" "}
            <Link
              href="/guides/how-to-send-pdf-to-kindle"
              className="text-accent no-underline hover:underline font-medium"
            >
              How to send PDFs to Kindle
            </Link>{" "}
            and the{" "}
            <Link
              href="#pdf-problem"
              className="text-accent no-underline hover:underline font-medium"
            >
              PDF problem section
            </Link>{" "}
            below.
          </p>
        </section>

        {/* ── Comparison table ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            Device comparison table
          </h2>
          <p className="font-sans text-base text-text-muted leading-relaxed mb-6 max-w-2xl">
            Device specs and price tiers as of 2026. Verify current pricing and
            availability on each manufacturer&apos;s product page — specs change and
            this table may lag new releases.
          </p>

          <div className="overflow-x-auto">
            <table className="w-full text-sm font-sans border-collapse min-w-[720px]">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left font-medium text-text-muted py-3 pr-4 pl-0 w-36">Device</th>
                  <th className="text-left font-medium text-text-muted py-3 px-3">Display</th>
                  <th className="text-left font-medium text-text-muted py-3 px-3">Note-taking</th>
                  <th className="text-left font-medium text-text-muted py-3 px-3">PDF readability</th>
                  <th className="text-left font-medium text-text-muted py-3 px-3">Price tier</th>
                  <th className="text-left font-medium text-text-muted py-3 px-3">Battery</th>
                  <th className="text-left font-medium text-text-muted py-3 px-3">Ecosystem</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {[
                  {
                    device: "Kindle Scribe",
                    link: "https://www.amazon.com/kindle-scribe",
                    display: "10.2\" mono e-ink, 300 PPI",
                    notes: "Included Pen, handwriting + typed notes",
                    pdf: "Good for simple PDFs; multi-column requires conversion",
                    price: "Mid-range",
                    battery: "Weeks",
                    ecosystem: "Kindle only",
                  },
                  {
                    device: "Kindle Scribe Colorsoft",
                    link: "https://www.amazon.com/kindle-scribe",
                    display: "10.2\" color e-ink (Colorsoft), 300 PPI",
                    notes: "Included Pen, same as Scribe",
                    pdf: "Same as Scribe + color charts/highlights",
                    price: "Premium",
                    battery: "Weeks",
                    ecosystem: "Kindle only",
                  },
                  {
                    device: "Kindle Paperwhite",
                    link: "https://www.amazon.com/kindle-paperwhite",
                    display: "7\" mono e-ink, 300 PPI",
                    notes: "None — reading only",
                    pdf: "Limited — 7\" screen makes academic PDFs small",
                    price: "Entry-level",
                    battery: "Weeks",
                    ecosystem: "Kindle only",
                  },
                  {
                    device: "reMarkable Paper Pro",
                    link: "https://remarkable.com/store/remarkable-paper-pro",
                    display: "11.8\" color e-ink (CANVAS Color), 229 PPI",
                    notes: "Excellent — paper-texture screen, Marker Plus",
                    pdf: "Good native PDF viewer; multi-column not solved",
                    price: "Premium",
                    battery: "~1–2 weeks",
                    ecosystem: "Open (no Kindle)",
                  },
                  {
                    device: "iPad (10th gen)",
                    link: "https://www.apple.com/ipad",
                    display: "10.9\" LCD Liquid Retina",
                    notes: "Apple Pencil (sold separately)",
                    pdf: "Every format, best zoom; eye fatigue on LCD",
                    price: "Mid-range",
                    battery: "~10 hours",
                    ecosystem: "Open, all apps",
                  },
                ].map((row) => (
                  <tr key={row.device} className="hover:bg-surface/50">
                    <td className="py-3 pr-4 pl-0">
                      <a
                        href={row.link}
                        target="_blank"
                        rel="noopener nofollow"
                        className="font-medium text-accent no-underline hover:underline"
                      >
                        {row.device}
                      </a>
                    </td>
                    <td className="py-3 px-3 text-text-base">{row.display}</td>
                    <td className="py-3 px-3 text-text-base">{row.notes}</td>
                    <td className="py-3 px-3 text-text-base">{row.pdf}</td>
                    <td className="py-3 px-3 text-text-muted">{row.price}</td>
                    <td className="py-3 px-3 text-text-muted">{row.battery}</td>
                    <td className="py-3 px-3 text-text-muted">{row.ecosystem}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="font-sans text-xs text-text-muted mt-3">
            Price tiers are relative (entry-level / mid-range / premium) — no dollar amounts
            because pricing changes frequently. Visit each manufacturer&apos;s product page for
            current pricing.
          </p>
        </section>

        {/* ── For reading academic PDFs ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            For reading academic PDFs
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              Academic PDFs — journal articles, conference papers, research
              monographs — place the most demanding requirements on an e-reading
              device. They are typically formatted in two-column letter or A4
              layouts at body text sizes between 9pt and 11pt, contain footnotes
              or endnotes referenced from body text, and use heading hierarchies
              that should produce navigable chapters.
            </p>
            <p>
              Screen size is the first constraint. A 7-inch Paperwhite displays
              an A4-format academic paper at roughly 60-70% of its original size —
              small enough that most readers need to zoom in, which introduces
              horizontal scrolling on every line. A 10-inch or larger screen
              (Kindle Scribe, reMarkable Paper Pro) can display academic PDFs at
              full width with legible body text without zooming.
            </p>

            {/* Standalone 134-167-word AI Overview passage */}
            <div className="bg-surface border border-border rounded-sm p-6 my-6">
              <p className="font-mono text-xs font-medium text-text-muted uppercase tracking-widest font-sans mb-3">
                Summary
              </p>
              <p className="font-sans text-base text-text-base leading-relaxed">
                For reading academic PDFs on e-ink, the Kindle Scribe and
                reMarkable Paper Pro are the two realistic options — both have
                screens large enough to display standard academic paper layouts
                without zooming. The Scribe stays in the Kindle ecosystem;
                the reMarkable operates independently with better stylus
                feedback. Neither device resolves the underlying problem with
                academic PDFs: multi-column layouts, footnote links, and heading
                structure are not preserved by default conversion methods. The
                same document that reads poorly on a Scribe after Send-to-Kindle
                reads equally poorly on a reMarkable loaded natively. A
                properly converted KFX or EPUB file — one produced with
                coordinate-based column extraction and explicit footnote linking
                — reads correctly on any device. Device choice determines the
                reading experience; file preparation determines whether the
                document is readable at all.
              </p>
            </div>

            <p>
              Between the Scribe and reMarkable for academic reading: the Scribe
              keeps your Kindle library accessible — papers sit alongside your
              Kindle books in one library, one app. The reMarkable has no Kindle
              integration but handles PDF files natively without conversion to
              a Kindle format, and its paper-texture screen is widely preferred
              for extended reading sessions where the glass feel of the Scribe
              becomes noticeable.
            </p>
            <p>
              For academic users who already own Kindle books: the Scribe is the
              practical choice. For users starting fresh with no existing Kindle
              library: the reMarkable Paper Pro is worth serious consideration,
              particularly if handwriting is a primary workflow.
            </p>
          </div>
        </section>

        {/* ── For marginalia / note-taking ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            For marginalia and note-taking
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              Annotation during reading — margin notes, highlights, passages
              marked for later — is a different use case from pure reading.
              Each device handles it differently.
            </p>

            <h3 className="font-serif text-xl text-text-base pt-2 leading-snug">
              Kindle Scribe
            </h3>
            <p>
              The Scribe supports handwritten annotations directly on PDF and
              ebook pages using the included Pen. Annotations sync to Kindle
              apps on other devices. The note-taking experience is functional:
              you write on the page, the notes appear as handwriting overlaid
              on the content. The glass display surface provides less
              paper-like resistance than the reMarkable, which some annotators
              find affects long writing sessions. Typed notes are also supported.
            </p>

            <h3 className="font-serif text-xl text-text-base pt-2 leading-snug">
              reMarkable Paper Pro
            </h3>
            <p>
              reMarkable&apos;s core strength is the writing experience. The
              paper-texture screen — a textured glass overlay on the e-ink
              panel — creates friction that closely mimics writing on paper.
              The Marker Plus stylus has an eraser on the back. For academics
              who annotate extensively, legal professionals, or anyone for
              whom handwriting quality matters more than any other factor,
              the reMarkable Paper Pro is the clearest choice in this
              comparison.
            </p>
            <p>
              The trade-off: reMarkable&apos;s PDF handling is native (no
              conversion required), but its library management is separate
              from Kindle and its export options are more limited than
              the iPad.
            </p>

            <h3 className="font-serif text-xl text-text-base pt-2 leading-snug">
              iPad
            </h3>
            <p>
              With the Apple Pencil (sold separately), the iPad supports
              annotation in every PDF app (GoodNotes, Notability, PDF Expert,
              Apple Books). The annotation ecosystem on iPad is larger than
              any e-ink device, with features like shape recognition,
              audio recording alongside notes, and cloud sync across any app.
              The trade-off for extended annotation sessions: the LCD screen
              and the device&apos;s weight cause more fatigue than e-ink over
              several hours.
            </p>

            <h3 className="font-serif text-xl text-text-base pt-2 leading-snug">
              Kindle Paperwhite
            </h3>
            <p>
              The Paperwhite does not support handwriting or stylus input.
              It supports text highlights and typed notes but is a reading
              device, not an annotation device. For note-heavy workflows,
              the Paperwhite is not the right choice.
            </p>
          </div>
        </section>

        {/* ── For general fiction / book reading ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            For general fiction and book reading
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              For reading novels, non-fiction prose, and commercial ebooks —
              content formatted natively for ebook readers rather than academic
              print — the requirements shift. Large screen size matters less;
              Kindle library access matters more; battery life and weight for
              holding the device matter for casual long sessions.
            </p>
            <p>
              The Kindle Paperwhite is the most purpose-fitted device for
              general book reading in this comparison. It is lighter than the
              Scribe (making it easier to hold one-handed), priced at an
              entry level, and has full Kindle library access. Its smaller
              7-inch screen is not a meaningful limitation for reflowable
              ebook content — the text reflows to fit any screen size.
            </p>
            <p>
              The Kindle Scribe is capable for book reading but the larger
              screen and heavier device are optimizations for documents rather
              than casual fiction reading. If ebooks are the primary use case
              with occasional PDFs, the Paperwhite is the more considered choice
              and the price difference is significant.
            </p>
            <p>
              The reMarkable Paper Pro is generally not recommended as a
              primary device for Kindle-library book reading — it has no
              Kindle integration, and most commercial ebooks are in DRM-protected
              AZW3 or KFX format that cannot be transferred to reMarkable.
            </p>
          </div>
        </section>

        {/* ── For multi-column PDFs ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            For multi-column PDFs specifically
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              Two-column academic papers — IEEE papers, journal articles,
              conference proceedings — are the most common PDF format in
              research contexts and the format that causes the most problems
              on every device in this comparison.
            </p>
            <p>
              The problem is not device-specific. When a multi-column PDF is
              loaded using default methods on any of these devices, the text
              reads incorrectly:
            </p>
            <ul className="list-disc pl-6 space-y-2 text-base">
              <li>
                <strong>Kindle Scribe (via Send-to-Kindle):</strong> Amazon converts the PDF in transit,
                reading the text stream in the interleaved order both columns appear on the page.
                The result: left-column line 1, right-column line 1, left-column line 2, right-column
                line 2 — prose from both columns mixed together throughout the document.
              </li>
              <li>
                <strong>reMarkable (native PDF):</strong> The PDF is displayed as a rendered image of
                the original page. At full-page view, text is small. Zoomed in, you read one column
                at a time but must scroll and reposition for every page. There is no text reflow.
              </li>
              <li>
                <strong>iPad (native PDF apps):</strong> Same behavior as reMarkable — PDF rendered
                as-is, zoom required, no reflow. iPad&apos;s larger screen makes this more manageable
                but does not solve it.
              </li>
              <li>
                <strong>Kindle Paperwhite (via Send-to-Kindle):</strong> Same interleaving problem as
                the Scribe, compounded by the smaller 7-inch screen.
              </li>
            </ul>
            <p>
              The solution is not choosing a different device — it is converting the PDF before
              loading it. A converter that uses coordinate-based text extraction can read each
              column as a complete unit, left column first then right column, producing
              correctly ordered reflowable text that reads on any device.
            </p>
          </div>
        </section>

        {/* ── The PDF problem affects all devices ── */}
        <section id="pdf-problem" className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            The PDF problem affects all of these devices
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              The core issue with PDFs on e-reading devices is not display
              quality — it is the gap between how PDFs encode information
              and what e-reading devices need.
            </p>
            <p>
              A PDF is a visual format: it stores text as positioned objects
              on a page, not as a semantic document structure. Headings in a
              PDF are text that an author formatted in a larger font — the
              format itself has no concept of &ldquo;this is a chapter title.&rdquo;
              Footnotes are text positioned at the bottom of a physical page
              region — not links, not semantic annotations. Multi-column
              layouts are text objects positioned side by side — there is
              no column boundary marker in the format.
            </p>
            <p>
              E-reading devices need the opposite: reflowable text, semantic
              headings, linked footnotes. Getting from a PDF to a well-structured
              ebook requires a conversion step that extracts meaning from the
              PDF&apos;s visual structure. Most conversion tools — Amazon&apos;s
              Send-to-Kindle, Calibre&apos;s default PDF conversion — attempt this
              but fall short on complex layouts.
            </p>
            <p>
              <Link
                href="/convert/pdf-to-kfx"
                className="text-accent no-underline hover:underline font-medium"
              >
                leafbind converts PDFs to KFX
              </Link>{" "}
              using coordinate-based extraction — the approach that identifies
              column boundaries from the horizontal distribution of text objects,
              reads each column as a unit, matches footnote markers to footnote
              bodies, and classifies headings from the document&apos;s own font
              hierarchy. The output is a properly structured KFX or EPUB file
              that reads correctly on any device:
            </p>
            <ul className="list-disc pl-6 space-y-2 text-base">
              <li>On a Kindle Scribe: KFX with navigable chapters, tappable footnote popups</li>
              <li>On a reMarkable: EPUB with correct column ordering, readable reflow</li>
              <li>On an iPad: EPUB in any reader app with properly structured text</li>
              <li>On a Paperwhite: KFX with text reflow at any font size</li>
            </ul>
            <p>
              This is why device choice and PDF preparation are separate decisions.
              The right device is whichever fits your ecosystem, workflow, and
              budget. The right PDF preparation is whatever correctly extracts the
              document&apos;s structure before you put it on the device.
            </p>
            <p className="text-text-muted text-sm">
              Free tier: EPUB output, up to 20 MB, 3 conversions per day, no account required.
              KFX output is available on premium plans.{" "}
              <Link
                href="/pricing"
                className="text-accent no-underline hover:underline font-medium"
              >
                See pricing →
              </Link>
            </p>
          </div>
        </section>

        {/* ── Scribe-specific note ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-5 leading-snug">
            A note on the Kindle Scribe specifically
          </h2>
          <div className="max-w-3xl text-text-base leading-relaxed space-y-4 text-base">
            <p>
              The Kindle Scribe is the device in this comparison that benefits most
              from a good PDF-to-KFX conversion. Its 10.2-inch screen is large
              enough to display a full academic paper at legible size; its Kindle
              ecosystem means it opens KFX files natively with the full heading
              navigation, footnote popups, and chapter list that KFX format supports;
              and its annotation features work correctly on well-structured KFX
              documents in ways they do not on PDFs displayed in PDF view mode.
            </p>
            <p>
              For a detailed walkthrough of the Scribe conversion workflow:{" "}
              <Link
                href="/guides/pdf-to-kfx-for-kindle-scribe"
                className="text-accent no-underline hover:underline font-medium"
              >
                PDF to KFX for Kindle Scribe →
              </Link>
            </p>
            <p>
              For troubleshooting Send-to-Kindle delivery failures to the Scribe:{" "}
              <Link
                href="/guides/send-to-kindle-not-working"
                className="text-accent no-underline hover:underline font-medium"
              >
                Send to Kindle not working: 7 fixes →
              </Link>
            </p>
          </div>
        </section>

        {/* ── FAQ ── */}
        <section className="mb-16 pb-16 border-b border-border">
          <h2 className="font-serif text-3xl text-brand mb-8 leading-snug">
            Frequently asked questions
          </h2>
          <div className="space-y-8 max-w-3xl">
            {faqItems.map((item) => (
              <div key={item.q}>
                <h3 className="font-serif text-xl text-brand mb-2 leading-snug">
                  {item.q}
                </h3>
                <p className="font-sans text-base text-text-base leading-relaxed">
                  {item.a}
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* ── Related links ── */}
        <section className="mb-16">
          <p className="font-mono text-sm font-medium text-text-muted uppercase tracking-widest mb-4">
            Related
          </p>
          <div className="flex flex-wrap gap-4">
            <Link
              href="/convert/pdf-to-kfx"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-3 hover:bg-accent/5"
            >
              PDF to KFX converter →
            </Link>
            <Link
              href="/guides/pdf-to-kfx-for-kindle-scribe"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-3 hover:bg-accent/5"
            >
              PDF to KFX for Kindle Scribe →
            </Link>
            <Link
              href="/guides/how-to-send-pdf-to-kindle"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-3 hover:bg-accent/5"
            >
              How to send PDFs to Kindle →
            </Link>
            <Link
              href="/guides/send-to-kindle-not-working"
              className="text-sm font-medium text-accent no-underline border border-accent/30 rounded-sm px-4 py-3 hover:bg-accent/5"
            >
              Send to Kindle not working →
            </Link>
          </div>
        </section>

        {/* ── CTA ── */}
        <section className="border-t border-border pt-16 pb-8">
          <h2 className="font-serif text-3xl text-text-base mb-4 leading-snug">
            Try leafbind free
          </h2>
          <p className="font-sans text-base text-text-muted leading-relaxed mb-2 max-w-xl">
            Upload a PDF and convert to EPUB at no cost — 3 conversions per day,
            up to 20 MB, no account required. KFX output with column detection,
            footnote linking, and heading classification is available on premium
            plans.
          </p>
          <p className="font-sans text-sm text-text-muted leading-relaxed mb-8">
            <Link
              href="/pricing"
              className="text-brand font-medium no-underline hover:underline"
            >
              See pricing
            </Link>{" "}
            — plans start at a single conversion credit with no subscription
            required.
          </p>
          <Link
            href="/convert/pdf-to-kfx"
            className="font-sans inline-block bg-brand text-white font-medium text-base px-8 py-3 rounded-sm no-underline hover:opacity-90"
          >
            Convert a PDF to KFX →
          </Link>

          <div className="mt-12 pt-8 border-t border-border max-w-xl">
            <p className="font-sans text-sm text-text-muted leading-relaxed">
              <span className="font-medium text-text-base">Joe Fowler</span> is
              a developer and technical writer who built leafbind after spending
              an unreasonable amount of time coaxing academic PDFs into something
              readable on a Kindle. He writes about PDF structure, ebook formats,
              and the conversion pipeline at leafbind.io.
            </p>
          </div>
        </section>

      </div>
    </>
  );
}
