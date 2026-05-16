// EB-272: SOFTWARE_APP_ID is the canonical @id used by every
// SoftwareApplication block on the site so Google's entity graph merges
// the 5+ page-level instances into a single application entity rather
// than treating them as distinct apps.
export const SOFTWARE_APP_ID = "https://leafbind.io/#software";

export interface SoftwareApplicationSchema {
  "@context": "https://schema.org";
  "@type": "SoftwareApplication";
  "@id": string;
  name: string;
  applicationCategory: string;
  operatingSystem: string;
  offers: { "@type": "Offer"; price: string; priceCurrency: string };
  url: string;
  description: string;
}

export interface WebSiteSchema {
  "@context": "https://schema.org";
  "@type": "WebSite";
  "@id": string;
  url: string;
  name: string;
  description: string;
  publisher: { "@type": "Organization"; name: string; url: string };
  potentialAction: {
    "@type": "SearchAction";
    target: { "@type": "EntryPoint"; urlTemplate: string };
    "query-input": string;
  };
}

export interface OfferSchema {
  "@type": "Offer";
  name: string;
  price: string;
  priceCurrency: string;
  availability: string;
  url: string;
  itemOffered: { "@type": "Service"; name: string };
}

export interface ProductSchema {
  "@context": "https://schema.org";
  "@type": "Product";
  name: string;
  description: string;
  brand: { "@type": "Brand"; name: string };
  offers: OfferSchema[];
}

export interface GraphSchema {
  "@context": "https://schema.org";
  "@graph": Array<WebSiteSchema | Omit<SoftwareApplicationSchema, "@context">>;
}

export interface FAQPageSchema {
  "@context": "https://schema.org";
  "@type": "FAQPage";
  mainEntity: Array<{
    "@type": "Question";
    name: string;
    acceptedAnswer: { "@type": "Answer"; text: string };
  }>;
}

export interface HowToSchema {
  "@context": "https://schema.org";
  "@type": "HowTo";
  name: string;
  step: Array<{ "@type": "HowToStep"; name: string; text: string }>;
}

export interface ArticleSchema {
  "@context": "https://schema.org";
  "@type": "Article";
  headline: string;
  description: string;
  image: string | string[];
  author: { "@type": "Person"; name: string; url?: string };
  datePublished: string;
  dateModified: string;
  publisher: { "@type": "Organization"; name: string; url: string };
  url: string;
}

export type SchemaData =
  | SoftwareApplicationSchema
  | FAQPageSchema
  | HowToSchema
  | ArticleSchema
  | WebSiteSchema
  | ProductSchema
  | GraphSchema;

export function buildSoftwareApplicationSchema(): SoftwareApplicationSchema {
  return {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "@id": SOFTWARE_APP_ID,
    name: "leafbind PDF to Kindle Converter",
    applicationCategory: "UtilitiesApplication",
    operatingSystem: "Web",
    offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
    url: "https://leafbind.io",
    description:
      "Convert PDFs to Kindle KFX with smart heading detection, footnote linking, " +
      "and multi-column layout support.",
  };
}

export function buildWebSiteSchema(): WebSiteSchema {
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    "@id": "https://leafbind.io/#website",
    url: "https://leafbind.io",
    name: "leafbind",
    description: "PDF to Kindle conversion focused on Kindle Scribe and academic reading.",
    publisher: { "@type": "Organization", name: "leafbind", url: "https://leafbind.io" },
    potentialAction: {
      "@type": "SearchAction",
      target: { "@type": "EntryPoint", urlTemplate: "https://leafbind.io/?q={search_term_string}" },
      "query-input": "required name=search_term_string",
    },
  };
}

export function buildHomepageGraph(): GraphSchema {
  // @graph lets multiple top-level entities share one @context. WebSite gives
  // sitelinks-search-box eligibility; SoftwareApplication establishes the
  // app identity that other pages reference via SOFTWARE_APP_ID.
  const { "@context": _ctx, ...appNoContext } = buildSoftwareApplicationSchema();
  return {
    "@context": "https://schema.org",
    "@graph": [buildWebSiteSchema(), appNoContext],
  };
}

interface PricingPack {
  id: string;
  label: string;
  credits: number;
  price: string; // e.g. "$2.99"
}

export function buildPricingProductSchema(packs: PricingPack[]): ProductSchema {
  return {
    "@context": "https://schema.org",
    "@type": "Product",
    name: "leafbind Premium Conversion Credits",
    description:
      "One-time credit packs that unlock premium PDF-to-KFX conversions: column-aware extraction, " +
      "heading detection, bidirectional footnote linking, and KFX output for Kindle Scribe.",
    brand: { "@type": "Brand", name: "leafbind" },
    offers: packs.map((p) => ({
      "@type": "Offer",
      name: `${p.label} pack — ${p.credits} credits`,
      price: p.price.replace(/^\$/, ""),
      priceCurrency: "USD",
      availability: "https://schema.org/InStock",
      url: `https://leafbind.io/pricing#${p.id}`,
      itemOffered: { "@type": "Service", name: "Premium PDF to KFX conversion credit" },
    })),
  };
}
