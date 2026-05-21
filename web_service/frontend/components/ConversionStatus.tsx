"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, type StatusResponse, getStatus } from "../lib/api";
import ActionCluster from "./ActionCluster";

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
        // EB-324 Unit 5/6: keep polling while ANY in-flight job exists —
        // the parent OR any re-convert child. A parent can reach "done"
        // while a child re-convert is still queued/running, and the action
        // cluster needs the child's progress to keep updating. Stop only
        // when the parent is terminal AND no child is in flight.
        const TERMINAL = new Set(["done", "failed", "expired"]);
        const parentTerminal = TERMINAL.has(result.status);
        const anyChildInFlight = (result.children ?? []).some(
          (child) => !TERMINAL.has(child.status)
        );
        if (parentTerminal && !anyChildInFlight) {
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

  // EB-324 Unit 6: the done state delegates to the result-page action
  // cluster (Download + Send-to-Kindle + Re-convert per format row). The
  // in-progress / failed / expired states keep their simple status copy.
  if (status.status === "done") {
    return <ActionCluster jobId={jobId} status={status} />;
  }

  const labels: Record<string, string> = {
    queued: "Queued — waiting for a conversion slot…",
    running: "Converting — this may take a minute…",
    failed: "Conversion failed.",
    expired: "File has expired.",
  };

  return (
    <div>
      <p>
        <strong>Status:</strong> {labels[status.status] ?? status.status}
      </p>

      {status.status === "failed" && status.error && (
        <p style={{ color: "red", marginTop: 8 }}>Error: {status.error}</p>
      )}
    </div>
  );
}
