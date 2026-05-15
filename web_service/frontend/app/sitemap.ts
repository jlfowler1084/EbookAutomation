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
  ];
  // Excluded: /recover (utility page, low SEO value), /status/[id] (dynamic, non-indexable)
}
