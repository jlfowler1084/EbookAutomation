import { MetadataRoute } from "next";

export default function sitemap(): MetadataRoute.Sitemap {
  const base = "https://leafbind.io";
  const now = new Date();

  return [
    { url: `${base}/`,                                lastModified: now, changeFrequency: "weekly",  priority: 1.0 },
    { url: `${base}/pricing`,                         lastModified: now, changeFrequency: "monthly", priority: 0.8 },
    { url: `${base}/quality`,                         lastModified: now, changeFrequency: "monthly", priority: 0.9 },
    { url: `${base}/convert/pdf-to-kfx`,              lastModified: now, changeFrequency: "monthly", priority: 0.9 },
    { url: `${base}/convert/academic-pdf-to-kindle`,  lastModified: now, changeFrequency: "monthly", priority: 0.8 },
    { url: `${base}/convert/pdf-footnotes-kindle`,    lastModified: now, changeFrequency: "monthly", priority: 0.7 },
    { url: `${base}/convert/multi-column-pdf-kindle`, lastModified: now, changeFrequency: "monthly", priority: 0.7 },
    { url: `${base}/guides/pdf-to-kfx-for-kindle-scribe`, lastModified: new Date("2026-05-15"), changeFrequency: "monthly", priority: 0.9 },
    // EB-264: /contact at priority 0.5, changeFrequency: "yearly".
    // Convention would suggest "never" for a near-static contact page, but "yearly"
    // is the lowest Google-accepted value that still signals the page is worth crawling.
    // Using "yearly" rather than omitting changeFrequency so crawlers don't apply defaults.
    { url: `${base}/contact`, lastModified: new Date("2026-05-16"), changeFrequency: "yearly", priority: 0.5 },
  ];
  // Excluded: /recover (utility page, low SEO value), /status/[id] (dynamic, non-indexable)
}
