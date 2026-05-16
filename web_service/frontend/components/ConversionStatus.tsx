"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, type StatusResponse, getDownloadUrl, getStatus } from "../lib/api";

interface Props {
  jobId: string;
}

type ErrorKind = "not-found" | "server";

export default function ConversionStatus({ jobId }: Props) {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [error, setError] = useState<ErrorKind | null>(null);

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
      } catch (err: unknown) {
        // EB-271: distinguish 404 (unknown/expired job) from other failures.
        // Both used to surface as "Service unavailable", which masked the
        // 24-hour file-deletion policy as a backend bug.
        const kind: ErrorKind = err instanceof ApiError && err.status === 404 ? "not-found" : "server";
        setError(kind);
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

  if (error === "not-found") {
    return (
      <div>
        <p className="text-text-base font-medium">
          We couldn&apos;t find that conversion.
        </p>
        <p className="mt-2 text-sm text-text-muted">
          It may have expired — we delete files 24 hours after conversion — or the link may be incorrect.
        </p>
        <Link
          href="/"
          className="mt-4 inline-block rounded bg-[var(--color-accent)] px-4 py-2 text-sm text-white no-underline"
        >
          Convert another file
        </Link>
      </div>
    );
  }

  if (error === "server") {
    return (
      <p style={{ color: "red" }}>
        We can&apos;t reach the conversion service right now. Please try again in a minute.
      </p>
    );
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
