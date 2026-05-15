"use client";

import { useEffect, useState } from "react";
import { type StatusResponse, getDownloadUrl, getStatus } from "../lib/api";

interface Props {
  jobId: string;
}

export default function ConversionStatus({ jobId }: Props) {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let intervalId: ReturnType<typeof setInterval> | null = null;

    const poll = async () => {
      try {
        const result = await getStatus(jobId);
        setStatus(result);
        if (result.status === "done" || result.status === "failed") {
          if (intervalId !== null) {
            clearInterval(intervalId);
            intervalId = null;
          }
        }
      } catch {
        setError("Service unavailable. Please try again later.");
        if (intervalId !== null) {
          clearInterval(intervalId);
          intervalId = null;
        }
      }
    };

    poll();
    intervalId = setInterval(poll, 5000);

    return () => {
      if (intervalId !== null) clearInterval(intervalId);
    };
  }, [jobId]);

  if (error) {
    return <p style={{ color: "red" }}>{error}</p>;
  }

  if (!status) {
    return <p>Checking status…</p>;
  }

  const labels: Record<string, string> = {
    queued: "Queued — waiting for a conversion slot…",
    running: "Converting — this may take a minute…",
    done: "Done!",
    failed: "Conversion failed.",
    expired: "File has expired.",
  };

  return (
    <div>
      <p>
        <strong>Status:</strong> {labels[status.status] ?? status.status}
      </p>

      {status.status === "done" && status.download_url && (
        <a
          href={getDownloadUrl(jobId)}
          style={{
            display: "inline-block",
            marginTop: 8,
            padding: "8px 16px",
            background: "var(--color-accent)",
            color: "#fff",
            borderRadius: 4,
            textDecoration: "none",
          }}
        >
          Download converted file
        </a>
      )}

      {status.status === "failed" && status.error && (
        <p style={{ color: "red", marginTop: 8 }}>Error: {status.error}</p>
      )}
    </div>
  );
}
