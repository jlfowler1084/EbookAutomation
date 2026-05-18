// lastModified is bumped only when page content materially changes.
// Do not use new Date() for entries — see EB-295.
// Source of truth for each date: most recent commit that edited the page's content
// (not deploy-pipeline or canonical/metadata-only commits).
import { MetadataRoute } from "next";

export default function sitemap(): MetadataRoute.Sitemap {
  const base = "https://leafbind.io";

  return [
    { url: `${base}/`,                                lastModified: new Date("2026-05-16"), changeFrequency: "weekly",  priority: 1.0 },
    { url: `${base}/pricing`,                         lastModified: new Date("2026-05-16"), changeFrequency: "monthly", priority: 0.8 },
    { url: `${base}/quality`,                         lastModified: new Date("2026-05-16"), changeFrequency: "monthly", priority: 0.9 },
    { url: `${base}/convert/pdf-to-kfx`,              lastModified: new Date("2026-05-17"), changeFrequency: "monthly", priority: 0.9 },
    { url: `${base}/convert/academic-pdf-to-kindle`,  lastModified: new Date("2026-05-16"), changeFrequency: "monthly", priority: 0.8 },
    { url: `${base}/convert/pdf-footnotes-kindle`,    lastModified: new Date("2026-05-16"), changeFrequency: "monthly", priority: 0.7 },
    { url: `${base}/convert/multi-column-pdf-kindle`, lastModified: new Date("2026-05-16"), changeFrequency: "monthly", priority: 0.7 },
    { url: `${base}/guides`,                                   lastModified: new Date("2026-05-17"), changeFrequency: "weekly",  priority: 0.9 },
    { url: `${base}/guides/pdf-to-kfx-for-kindle-scribe`,     lastModified: new Date("2026-05-17"), changeFrequency: "monthly", priority: 0.9 },
    { url: `${base}/guides/send-to-kindle-not-working`,        lastModified: new Date("2026-05-17"), changeFrequency: "monthly", priority: 0.9 },
    { url: `${base}/guides/how-to-send-pdf-to-kindle`,         lastModified: new Date("2026-05-17"), changeFrequency: "monthly", priority: 0.9 },
    { url: `${base}/guides/does-kindle-support-epub`,          lastModified: new Date("2026-05-17"), changeFrequency: "monthly", priority: 0.9 },
    { url: `${base}/guides/kindle-scribe-vs-remarkable`,       lastModified: new Date("2026-05-17"), changeFrequency: "monthly", priority: 0.9 },
    // EB-264: /contact at priority 0.5, changeFrequency: "yearly".
    // Convention would suggest "never" for a near-static contact page, but "yearly"
    // is the lowest Google-accepted value that still signals the page is worth crawling.
    // Using "yearly" rather than omitting changeFrequency so crawlers don't apply defaults.
    { url: `${base}/contact`, lastModified: new Date("2026-05-16"), changeFrequency: "yearly", priority: 0.5 },
    // EB-300: Legal pages — indexable for trust and ad-network reviewability.
    { url: `${base}/privacy`,       lastModified: new Date("2026-05-17"), changeFrequency: "monthly", priority: 0.3 },
    { url: `${base}/terms`,         lastModified: new Date("2026-05-17"), changeFrequency: "monthly", priority: 0.3 },
    { url: `${base}/refund-policy`, lastModified: new Date("2026-05-17"), changeFrequency: "monthly", priority: 0.3 },
  ];
  // Excluded: /recover (utility page, low SEO value), /status/[id] (dynamic, non-indexable)
}
