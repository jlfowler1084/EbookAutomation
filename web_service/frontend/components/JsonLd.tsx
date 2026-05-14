import type { SchemaData } from "../lib/structured-data";

export default function JsonLd({ schema }: { schema: SchemaData }) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
    />
  );
}
