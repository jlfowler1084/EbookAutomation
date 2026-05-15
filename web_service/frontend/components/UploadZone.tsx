"use client";

import { type DragEvent, useRef, useState } from "react";
import { startConversion } from "../lib/api";
import FormatSelector from "./FormatSelector";
import TokenField from "./TokenField";

interface Props {
  onJobStarted: (jobId: string) => void;
}

export default function UploadZone({ onJobStarted }: Props) {
  const [dragging, setDragging] = useState(false);
  const [outputFormat, setOutputFormat] = useState("epub");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [token, setToken] = useState<string>("");
  const [tokenValid, setTokenValid] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const tier: "free" | "premium" = tokenValid ? "premium" : "free";

  const handleFile = async (file: File) => {
    setError(null);
    setUploading(true);
    try {
      const { job_id } = await startConversion(file, outputFormat, tier, token || undefined);
      onJobStarted(job_id);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed. Please try again.");
    } finally {
      setUploading(false);
    }
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  const onDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(true);
  };

  const onDragLeave = () => setDragging(false);

  return (
    <div>
      <div
        role="button"
        tabIndex={0}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
        style={{
          border: `2px dashed ${dragging ? "var(--color-accent)" : "var(--color-border)"}`,
          borderRadius: 8,
          padding: "40px 20px",
          textAlign: "center",
          cursor: "pointer",
          background: dragging ? "var(--color-surface-muted)" : "var(--color-surface-muted)",
          transition: "all 0.15s",
        }}
      >
        <p style={{ margin: 0 }}>
          {uploading
            ? "Uploading…"
            : "Drop your PDF or ebook here, or click to browse"}
        </p>
        <p style={{ margin: "8px 0 0", fontSize: 12, color: "#666" }}>
          Supported: PDF, EPUB, MOBI, AZW, AZW3, DJVU · Free tier: 20 MB max
        </p>
      </div>

      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.epub,.mobi,.azw,.azw3,.djvu"
        style={{ display: "none" }}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
        }}
      />

      <div style={{ marginTop: 16 }}>
        <FormatSelector value={outputFormat} onChange={setOutputFormat} tier={tier} />
      </div>

      <details style={{ marginTop: "1em" }}>
        <summary style={{ cursor: "pointer", color: "var(--color-accent)" }}>I have a token</summary>
        <TokenField
          onValidToken={(t) => {
            setToken(t);
            setTokenValid(true);
          }}
        />
      </details>

      {error && <p style={{ color: "red", marginTop: 12 }}>{error}</p>}
    </div>
  );
}
