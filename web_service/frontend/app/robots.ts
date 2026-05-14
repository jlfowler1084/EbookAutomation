import { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/status/", "/api/"],
      },
    ],
    sitemap: "https://leafbind.io/sitemap.xml",
  };
}
