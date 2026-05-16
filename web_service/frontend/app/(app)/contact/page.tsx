import type { Metadata } from "next";
import JsonLd from "../../../components/JsonLd";
import { buildContactPageSchema } from "../../../lib/structured-data";
import ContactForm from "./ContactForm";

export const metadata: Metadata = {
  title: "Contact — Leafbind",
  description:
    "Get help with PDF to Kindle conversion, billing questions, or send feedback to the leafbind team.",
  alternates: {
    canonical: "https://leafbind.io/contact",
  },
  openGraph: {
    title: "Contact leafbind Support",
    description:
      "Get help with PDF to Kindle conversion, billing questions, or send feedback to the leafbind team.",
    url: "https://leafbind.io/contact",
    type: "website",
  },
};

export default function ContactPage() {
  return (
    <>
      <JsonLd schema={buildContactPageSchema()} />

      <div className="space-y-6">
        <div>
          <h1 className="font-serif text-3xl text-text-base">Contact</h1>
          <p className="mt-2 text-text-muted">
            Questions about a conversion, billing, or anything else — send us a
            message and we&apos;ll get back to you within a few business days.
            You can also email{" "}
            <a
              href="mailto:support@leafbind.io"
              className="text-brand hover:underline"
            >
              support@leafbind.io
            </a>{" "}
            directly.
          </p>
        </div>

        <div className="rounded-md border border-border bg-surface-muted p-6 min-w-0">
          <ContactForm />
        </div>
      </div>
    </>
  );
}
