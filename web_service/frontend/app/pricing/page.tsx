import type { Metadata } from "next";
import BuyButtons from "../../components/BuyButtons";

export const metadata: Metadata = {
  title: "Pricing — Leafbind",
  description:
    "Credit packs for premium PDF-to-Kindle conversion with smart heading detection, footnote linking, and KFX output.",
};

const PACKS = [
  {
    id: "starter",
    credits: 3,
    price: "$2.99",
    perCredit: "$1.00/credit",
    label: "Starter",
    recommended: false,
  },
  {
    id: "standard",
    credits: 10,
    price: "$7.99",
    perCredit: "$0.80/credit",
    label: "Standard",
    recommended: true,
  },
  {
    id: "power",
    credits: 25,
    price: "$14.99",
    perCredit: "$0.60/credit",
    label: "Power",
    recommended: false,
  },
];

export default function PricingPage() {
  return (
    <main
      style={{
        maxWidth: 720,
        margin: "2em auto",
        padding: "1em",
        fontFamily: "-apple-system, BlinkMacSystemFont, system-ui, sans-serif",
      }}
    >
      <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 8 }}>Pricing</h1>
      <p style={{ color: "#555", marginBottom: 0 }}>
        Premium unlocks smart heading detection, footnote linking, KFX output, and the 100 MB
        file limit. Tokens expire 7 days after purchase.{" "}
        <a href="/recover" style={{ color: "#0070f3" }}>
          Lost your tokens?
        </a>
      </p>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: "1em",
          marginTop: "2em",
        }}
      >
        {PACKS.map((pack) => (
          <div
            key={pack.id}
            style={{
              border: pack.recommended ? "2px solid #0070f3" : "1px solid #ccc",
              borderRadius: 8,
              padding: "1.5em",
              backgroundColor: pack.recommended ? "#f0f7ff" : "#fafafa",
            }}
          >
            {pack.recommended && (
              <span
                style={{
                  fontSize: "0.8em",
                  color: "#0070f3",
                  fontWeight: "bold",
                  display: "block",
                  marginBottom: "0.25em",
                }}
              >
                RECOMMENDED
              </span>
            )}
            <h2 style={{ margin: "0.5em 0", fontSize: "1.25em" }}>{pack.label}</h2>
            <p style={{ fontSize: "2em", margin: "0.5em 0", fontWeight: "bold" }}>
              {pack.price}
            </p>
            <p style={{ color: "#666", margin: "0.25em 0" }}>
              {pack.credits} credits &bull; {pack.perCredit}
            </p>
          </div>
        ))}
      </div>

      <BuyButtons packs={PACKS} />

      <div style={{ marginTop: "2em", color: "#555", fontSize: "0.95em" }}>
        <h3 style={{ marginBottom: "0.5em" }}>What premium unlocks</h3>
        <ul style={{ paddingLeft: "1.5em", lineHeight: 1.7 }}>
          <li>Smart heading detection across all book types</li>
          <li>Footnote and endnote linking</li>
          <li>KFX output (Kindle-optimised format)</li>
          <li>100 MB file limit (vs 20 MB free tier)</li>
        </ul>
      </div>

      <footer style={{ marginTop: "3em", color: "#666", fontSize: "0.9em" }}>
        <a href="/recover" style={{ color: "#0070f3" }}>
          Recover tokens
        </a>
      </footer>
    </main>
  );
}
