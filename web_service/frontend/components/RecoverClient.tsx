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

// EB-292: fire-and-forget event log. The endpoint always returns 204 and
// failures are absorbed server-side, so we don't need to wait or handle
// errors here — keepalive lets the request survive a fast navigation away
// from the page.
function logRecoverView(state: string): void {
  try {
    void fetch("/api/recovery-events/recover-view", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ localStorage_state: state }),
      keepalive: true,
    }).catch(() => {
      // Swallow — instrumentation must never break the recovery UX.
    });
  } catch {
    // Synchronous throw (e.g. fetch unavailable) — swallow.
  }
}

export default function RecoverClient({ initialSessionId }: Props) {
  const [storedTokens, setStoredTokens] = useState<StoredTokens | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    let state: string = "empty";
    let parsed: StoredTokens | null = null;
    try {
      const raw = localStorage.getItem("leafbind.tokens");
      if (raw) {
        try {
          parsed = JSON.parse(raw) as StoredTokens;
          if (parsed && Array.isArray(parsed.tokens) && parsed.tokens.length > 0) {
            const expired = Date.now() / 1000 > parsed.expires_at;
            state = expired ? "has_expired_tokens" : "has_tokens";
          } else {
            state = "invalid";
          }
        } catch {
          state = "invalid";
        }
      }
      if (parsed) {
        setStoredTokens(parsed);
      }
    } catch {
      // localStorage unavailable (incognito, SSR guard, ITP, etc.)
      state = "unavailable";
    }
    setChecked(true);
    logRecoverView(state);
  }, []);

  if (!checked) return <p>Checking local storage&hellip;</p>;

  if (storedTokens && storedTokens.tokens.length > 0) {
    const expired = Date.now() / 1000 > storedTokens.expires_at;
    if (expired) {
      return (
        <p style={{ color: "#666" }}>
          Your tokens have expired (30-day window).{" "}
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
