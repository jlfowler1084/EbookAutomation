"use client";

import { useEffect, useState } from "react";
import TokenList from "./TokenList";

interface Props {
  initialSessionId?: string;
}

interface StoredTokens {
  tokens: string[];
  session_id: string;
  expires_at: number;
}

export default function RecoverClient({ initialSessionId }: Props) {
  const [storedTokens, setStoredTokens] = useState<StoredTokens | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem("leafbind.tokens");
      if (raw) {
        setStoredTokens(JSON.parse(raw) as StoredTokens);
      }
    } catch {
      // localStorage unavailable (incognito, SSR guard, etc.) — silently fall through
    }
    setChecked(true);
  }, []);

  if (!checked) return <p>Checking local storage&hellip;</p>;

  if (storedTokens && storedTokens.tokens.length > 0) {
    const expired = Date.now() / 1000 > storedTokens.expires_at;
    if (expired) {
      return (
        <p style={{ color: "#666" }}>
          Your tokens have expired (7-day window).{" "}
          <a href="/pricing" style={{ color: "var(--color-accent)" }}>
            Buy more
          </a>
        </p>
      );
    }
    return (
      <div>
        <p style={{ color: "#555" }}>Tokens recovered from this browser:</p>
        <TokenList tokens={storedTokens.tokens} sessionId={storedTokens.session_id} />
      </div>
    );
  }

  // Empty state — session_id paste form
  return (
    <div>
      <p style={{ color: "#555" }}>
        No tokens found on this device. If you have your Stripe receipt email or the original
        payment URL, paste the session ID below:
      </p>
      <form action="/api/recover" method="POST" style={{ marginTop: "1em" }}>
        <input
          type="text"
          name="session_id"
          defaultValue={initialSessionId ?? ""}
          placeholder="cs_..."
          required
          style={{
            padding: "0.5em",
            width: "100%",
            maxWidth: 500,
            border: "1px solid var(--color-border)",
            borderRadius: 4,
            fontFamily: "monospace",
            fontSize: "0.95em",
            boxSizing: "border-box",
          }}
        />
        <button
          type="submit"
          style={{
            marginLeft: "0.5em",
            padding: "0.5em 1.5em",
            backgroundColor: "var(--color-accent)",
            color: "white",
            border: "none",
            borderRadius: 4,
            cursor: "pointer",
            fontSize: "0.95em",
            verticalAlign: "top",
          }}
        >
          Recover
        </button>
      </form>
      <p style={{ marginTop: "2em", color: "#666", fontSize: "0.9em" }}>
        <a href="/pricing" style={{ color: "var(--color-accent)" }}>
          &larr; Back to pricing
        </a>
      </p>
    </div>
  );
}
