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
  // potentialAction (SearchAction) removed — EB-298: site has no search;
  // emitting SearchAction without a real search endpoint violated Google's
  // structured-data guidelines and could suppress the sitelinks search box.
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
  image: string | string[];
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
  mainEntityOfPage: { "@type": "WebPage"; "@id": string };
}

export interface ContactPageSchema {
  "@context": "https://schema.org";
  "@type": "ContactPage";
  name: string;
  description: string;
  url: string;
}

export interface ItemListSchema {
  "@context": "https://schema.org";
  "@type": "ItemList";
  name: string;
  description: string;
  url: string;
  itemListElement: Array<{
    "@type": "ListItem";
    position: number;
    name: string;
    url: string;
    description?: string;
  }>;
}

export type SchemaData =
  | SoftwareApplicationSchema
  | FAQPageSchema
  | HowToSchema
  | ArticleSchema
  | WebSiteSchema
  | ProductSchema
  | GraphSchema
  | ContactPageSchema
  | ItemListSchema;

export function buildContactPageSchema(): ContactPageSchema {
  return {
    "@context": "https://schema.org",
    "@type": "ContactPage",
    name: "Contact leafbind Support",
    description:
      "Get help with PDF to Kindle conversion, billing, or send general feedback to the leafbind team.",
    url: "https://leafbind.io/contact",
  };
}

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
    // potentialAction (SearchAction) intentionally omitted — EB-298
  };
}

export function buildHomepageGraph(): GraphSchema {
  // @graph lets multiple top-level entities share one @context. WebSite declares
  // the canonical site identity; SoftwareApplication establishes the app entity
  // that other pages reference via SOFTWARE_APP_ID.
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
    image: [
      "https://leafbind.io/quality/pipeline-headings.png",
      "https://leafbind.io/quality/pipeline-columns.png",
      "https://leafbind.io/quality/pipeline-footnotes.png",
    ],
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

export function buildFAQPageSchema(items: Array<{ q: string; a: string }>): FAQPageSchema {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: items.map((item) => ({
      "@type": "Question",
      name: item.q,
      acceptedAnswer: { "@type": "Answer", text: item.a },
    })),
  };
}

interface ArticleArgs {
  headline: string;
  description: string;
  image: string | string[];
  author?: { name: string; url?: string };
  datePublished: string;
  dateModified: string;
  url: string;
}

export function buildArticleSchema(args: ArticleArgs): ArticleSchema {
  return {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: args.headline,
    description: args.description,
    image: args.image,
    author: {
      "@type": "Person",
      name: args.author?.name ?? "leafbind team",
      ...(args.author?.url ? { url: args.author.url } : {}),
    },
    datePublished: args.datePublished,
    dateModified: args.dateModified,
    publisher: { "@type": "Organization", name: "leafbind", url: "https://leafbind.io" },
    url: args.url,
    mainEntityOfPage: { "@type": "WebPage", "@id": args.url },
  };
}

interface HowToArgs {
  name: string;
  step: Array<{ name: string; text: string }>;
}

export function buildHowToSchema(args: HowToArgs): HowToSchema {
  return {
    "@context": "https://schema.org",
    "@type": "HowTo",
    name: args.name,
    step: args.step.map((s) => ({ "@type": "HowToStep", name: s.name, text: s.text })),
  };
}

interface ItemListArgs {
  name: string;
  description: string;
  url: string;
  items: Array<{ name: string; url: string; description?: string }>;
}

export function buildItemListSchema(args: ItemListArgs): ItemListSchema {
  return {
    "@context": "https://schema.org",
    "@type": "ItemList",
    name: args.name,
    description: args.description,
    url: args.url,
    itemListElement: args.items.map((item, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: item.name,
      url: item.url,
      ...(item.description ? { description: item.description } : {}),
    })),
  };
}
