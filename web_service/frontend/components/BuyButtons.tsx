"use client";

import Link from "next/link";
import { useState } from "react";
import { createCheckoutSession } from "../lib/api";

interface Pack {
  id: string;
  label: string;
}

interface Props {
  packs: Pack[];
}

export default function BuyButtons({ packs }: Props) {
  const [creating, setCreating] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleBuy(packId: string) {
    if (creating) return;
    setCreating(packId);
    setError(null);
    try {
      const resp = await createCheckoutSession(packId);
      window.location.href = resp.checkout_url;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start checkout");
      setCreating(null);
    }
  }

  return (
    <div>
      <div
        style={{
          display: "flex",
          gap: "1em",
          marginTop: "1em",
          justifyContent: "center",
          flexWrap: "wrap",
        }}
      >
        {packs.map((p) => (
          <button
            key={p.id}
            onClick={() => handleBuy(p.id)}
            disabled={creating !== null}
            style={{
              padding: "0.875em 2em",
              minHeight: "44px",
              backgroundColor: creating === p.id ? "var(--color-border)" : "var(--color-accent)",
              color: "white",
              border: "none",
              borderRadius: 4,
              cursor: creating !== null ? "not-allowed" : "pointer",
              fontSize: "1em",
              fontWeight: 600,
              transition: "background-color 0.15s",
            }}
          >
            {creating === p.id ? "Redirecting to checkout…" : `Buy ${p.label}`}
          </button>
        ))}
      </div>
      {error && (
        <p style={{ color: "red", marginTop: "1em", textAlign: "center" }}>{error}</p>
      )}
      <p style={{ marginTop: "1em", textAlign: "center", fontSize: "0.75em", color: "var(--color-text-muted)" }}>
        By purchasing you agree to our{" "}
        <Link href="/terms" style={{ color: "var(--color-accent)", textDecoration: "underline" }}>
          Terms of Service
        </Link>{" "}
        and{" "}
        <Link href="/privacy" style={{ color: "var(--color-accent)", textDecoration: "underline" }}>
          Privacy Policy
        </Link>
        .
      </p>
    </div>
  );
}
