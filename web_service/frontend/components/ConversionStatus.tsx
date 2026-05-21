"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, type StatusResponse, getStatus } from "../lib/api";
import ActionCluster from "./ActionCluster";

interface Props {
  jobId: string;
}

type ErrorKind = "not-found" | "server";

const TERMINAL_JOB = new Set(["done", "failed", "expired"]);
// Delivery states still awaiting a Resend webhook transition. While the parent
// or any child sits in one of these, keep polling so delivered/bounced/failed
// surfaces without a manual reload.
const DELIVERY_PENDING = new Set(["accepted_by_resend", "delivery_delayed"]);

/**
 * Nothing left to watch: the parent is terminal, no child is in flight, and
 * no output is awaiting a delivery-webhook transition. This is the condition
 * to stop polling. Critically, it stays FALSE after a re-convert dispatch
 * (child in flight) or a Send-to-Kindle (delivery pending), so the loop keeps
 * running to surface that new backend state.
 */
function isSettled(status: StatusResponse): boolean {
  if (!TERMINAL_JOB.has(status.status)) return false;
  const children = status.children ?? [];
  if (children.some((c) => !TERMINAL_JOB.has(c.status))) return false;
  const deliveryPending =
    DELIVERY_PENDING.has(status.kindle_delivery_status ?? "") ||
    children.some((c) => DELIVERY_PENDING.has(c.kindle_delivery_status ?? ""));
  return !deliveryPending;
}

export default function ConversionStatus({ jobId }: Props) {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [error, setError] = useState<ErrorKind | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = useCallback(() => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const poll = useCallback(async () => {
    try {
      const result = await getStatus(jobId);
      setStatus(result);
      if (isSettled(result)) stop();
    } catch (err: unknown) {
      // EB-271: distinguish 404 (unknown/expired job) from other failures.
      const kind: ErrorKind =
        err instanceof ApiError && err.status === 404 ? "not-found" : "server";
      setError(kind);
      stop();
    }
  }, [jobId, stop]);

  // Idempotent restart. ActionCluster calls this after a re-convert dispatch
  // or a Send-to-Kindle so newly-created children + webhook-driven delivery
  // transitions surface without a reload. The immediate poll() picks up the
  // new state right away rather than waiting for the next 5s tick.
  const startPolling = useCallback(() => {
    if (intervalRef.current === null) {
      void poll();
      intervalRef.current = setInterval(() => void poll(), 5000);
    }
  }, [poll]);

  useEffect(() => {
    startPolling();
    return stop;
  }, [startPolling, stop]);

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

  // EB-324 Unit 6: the done state delegates to the result-page action cluster.
  // onActivity restarts polling after a re-convert dispatch / Send-to-Kindle so
  // the new child + delivery transitions show up live.
  if (status.status === "done") {
    return <ActionCluster jobId={jobId} status={status} onActivity={startPolling} />;
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
