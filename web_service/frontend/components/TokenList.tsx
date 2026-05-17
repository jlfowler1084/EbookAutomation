"use client";

interface Props {
  tokens: string[];
  sessionId?: string;
}

export default function TokenList({ tokens, sessionId }: Props) {
  function copyToken(token: string) {
    navigator.clipboard.writeText(token);
  }

  function downloadAll() {
    const text = tokens.join("\n") + "\n";
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "leafbind-tokens.txt";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div>
      {sessionId && (
        <p style={{ color: "#666", fontSize: "0.9em", marginBottom: "0.5em" }}>
          Session: <span style={{ fontFamily: "monospace" }}>{sessionId}</span>
        </p>
      )}
      <ol style={{ fontFamily: "monospace", fontSize: "0.95em", lineHeight: 1.8 }}>
        {tokens.map((t) => (
          <li key={t} style={{ padding: "0.25em 0" }}>
            <span>{t}</span>
            <button
              type="button"
              onClick={() => copyToken(t)}
              style={{
                marginLeft: "0.75em",
                padding: "0.2em 0.6em",
                cursor: "pointer",
                fontSize: "0.85em",
                border: "1px solid var(--color-border)",
                borderRadius: 3,
                background: "var(--color-surface-muted)",
              }}
            >
              Copy
            </button>
          </li>
        ))}
      </ol>
      <div style={{ marginTop: "1em", display: "flex", gap: "0.75em" }}>
        <button
          type="button"
          onClick={downloadAll}
          style={{
            padding: "0.5em 1em",
            cursor: "pointer",
            border: "1px solid var(--color-border)",
            borderRadius: 4,
            background: "var(--color-surface-muted)",
            fontSize: "0.95em",
          }}
        >
          Download tokens.txt
        </button>
        <button
          type="button"
          onClick={() => window.print()}
          style={{
            padding: "0.5em 1em",
            cursor: "pointer",
            border: "1px solid var(--color-border)",
            borderRadius: 4,
            background: "var(--color-surface-muted)",
            fontSize: "0.95em",
          }}
        >
          Print tokens
        </button>
      </div>
    </div>
  );
}
