"use client";

import { useState } from "react";
import {
  type ChildJob,
  type StatusResponse,
  emitEvent,
  getDownloadUrl,
} from "../lib/api";
import ReconvertButton from "./ReconvertButton";
import SendToKindleForm from "./SendToKindleForm";
import TtlCountdown from "./TtlCountdown";

interface Props {
  jobId: string;
  status: StatusResponse;
}

// Re-convert offers, in display order. mobi is free; kfx is premium. EPUB is
// the default upload output, so it's never offered as a re-convert target.
const RECONVERT_FORMATS: Array<{ format: "mobi" | "kfx"; tier: "free" | "premium" }> = [
  { format: "mobi", tier: "free" },
  { format: "kfx", tier: "premium" },
];

const STATUS_LABEL: Record<string, string> = {
  queued: "Queued…",
  running: "Converting…",
  done: "Ready",
  failed: "Conversion failed",
  expired: "Expired",
};

export default function ActionCluster({ jobId, status }: Props) {
  // Hide the TTL countdown once the user consumes an action (a successful
  // Send-to-Kindle) — the remaining-time copy becomes noise at that point.
  const [countdownHidden, setCountdownHidden] = useState(false);

  const parentFormat = status.download_url ? inferFormat(status) : "epub";
  const childrenByFormat = new Map(status.children.map((c) => [c.format, c]));

  function handleSent() {
    setCountdownHidden(true);
    emitEvent("send_to_kindle_attempted", { output_format: "epub" });
  }

  function handleReconvertDispatched(format: "mobi" | "kfx", tier: string) {
    emitEvent("reconvert_attempted", { format, tier });
  }

  function handleExpiredClick(action: string) {
    emitEvent("expired_action_attempted", { action });
  }

  return (
    <div className="space-y-5">
      <TtlCountdown expiresAt={status.expires_at} hidden={countdownHidden} />

      {/* Parent output row — Download + (EPUB only) Send-to-Kindle. */}
      <div className="rounded-md border border-border bg-surface p-4 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm font-medium text-text-base uppercase">
            {parentFormat}
          </span>
          {status.output_present && status.download_url ? (
            <a
              href={getDownloadUrl(jobId)}
              className="rounded-md bg-brand px-4 py-2 text-sm text-white no-underline hover:bg-brand-dark"
            >
              Download {parentFormat.toUpperCase()}
            </a>
          ) : (
            <span className="text-sm text-text-muted">Expired</span>
          )}
        </div>

        {parentFormat === "epub" && (
          <SendToKindleForm
            jobId={jobId}
            outputPresent={status.output_present}
            kindleDeliveryStatus={status.kindle_delivery_status}
            onSent={handleSent}
          />
        )}
      </div>

      {/* Re-convert rows — one per supported format that isn't the parent's. */}
      {RECONVERT_FORMATS.filter(({ format }) => format !== parentFormat).map(
        ({ format, tier }) => {
          const child = childrenByFormat.get(format);
          return (
            <div
              key={format}
              className="rounded-md border border-border bg-surface-muted p-4"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm font-medium text-text-base uppercase">
                  {format}
                  {tier === "premium" && (
                    <span className="ml-2 rounded bg-brand/10 px-1.5 py-0.5 text-xs font-normal text-brand">
                      Premium
                    </span>
                  )}
                </span>

                {child ? (
                  <ChildRowAction jobId={jobId} child={child} />
                ) : (
                  <ReconvertButton
                    parentJobId={jobId}
                    format={format}
                    disabled={!status.source_present}
                    onDispatched={() => handleReconvertDispatched(format, tier)}
                    onDisabledClick={() => handleExpiredClick(`reconvert_${format}`)}
                  />
                )}
              </div>
            </div>
          );
        }
      )}
    </div>
  );
}

/** Renders the status/download for a dispatched re-convert child. */
function ChildRowAction({ jobId: _jobId, child }: { jobId: string; child: ChildJob }) {
  if (child.status === "done" && child.output_present && child.download_url) {
    return (
      <a
        href={getDownloadUrl(child.job_id)}
        className="rounded-md bg-brand px-4 py-2 text-sm text-white no-underline hover:bg-brand-dark"
      >
        Download {child.format.toUpperCase()}
      </a>
    );
  }
  if (child.status === "failed") {
    return <span className="text-sm text-red-600">Conversion failed</span>;
  }
  return (
    <span className="text-sm text-text-muted">
      {STATUS_LABEL[child.status] ?? child.status}
    </span>
  );
}

/**
 * The status response doesn't echo the parent's own output_fmt, but the
 * download_url + the absence of the parent format in children lets us treat
 * the primary output as EPUB for Wave 1 (the default upload output and the
 * only Send-to-Kindle-eligible format). If a non-EPUB primary ever needs
 * distinct handling, the status response should add an explicit
 * `output_format` field.
 */
function inferFormat(_status: StatusResponse): "epub" | "mobi" | "kfx" {
  return "epub";
}
