"use client";

import { useState } from "react";

const TOKEN_REGEX = /^lb_pk_[A-Za-z0-9_-]{43}$/;

interface Props {
  onValidToken: (token: string) => void;
}

export default function TokenField({ onValidToken }: Props) {
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  function handleBlur() {
    const trimmed = value.trim();
    if (!trimmed) {
      setError(null);
      return;
    }
    if (!TOKEN_REGEX.test(trimmed)) {
      setError("Token format invalid (expected: lb_pk_<43-char-base64url>)");
      return;
    }
    setError(null);
    onValidToken(trimmed);
  }

  return (
    <div style={{ marginTop: "1em" }}>
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={handleBlur}
        placeholder="lb_pk_..."
        style={{
          padding: "0.5em",
          width: "100%",
          maxWidth: 500,
          border: "1px solid #ccc",
          borderRadius: 4,
          fontFamily: "monospace",
          fontSize: "0.95em",
          boxSizing: "border-box",
        }}
      />
      {error && (
        <p style={{ color: "red", fontSize: "0.9em", marginTop: "0.25em" }}>{error}</p>
      )}
    </div>
  );
}
