import type { SchemaData } from "../lib/structured-data";

// Accept any JSON-serializable structured-data shape. The SchemaData union is
// the strict-typed surface used by current call sites; `Record<string, unknown>`
// is the escape hatch for ad-hoc @graph payloads. JSON.stringify treats both
// identically.
export default function JsonLd({
  schema,
}: {
  schema: SchemaData | Record<string, unknown>;
}) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
    />
  );
}
