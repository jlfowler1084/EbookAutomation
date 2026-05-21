"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { ApiError, type KindleDeliveryStatus, sendToKindle } from "../lib/api";

// v1: the verified Resend sender. Hardcoded per the plan (planning-time call);
// promote to a server-served config value if it ever needs to vary per deploy.
const FROM_ADDRESS = "kindle@send.leafbind.io";
const LOCAL_STORAGE_KEY = "leafbind_kindle_email";
const APPROVED_SENDER_URL = "https://www.amazon.com/sendtokindle";

interface Props {
  jobId: string;
  /** False once the output has been swept — Send-to-Kindle is unavailable. */
  outputPresent: boolean;
  /**
   * Async delivery state from the status poll (Unit 10 webhook updates it).
   * Drives the graded delivery copy + the failure-known approved-sender path.
   */
  kindleDeliveryStatus: KindleDeliveryStatus;
  /** Fired on a successful send (Unit 9b-client telemetry hook). */
  onSent?: (recipient: string) => void;
}

type FormPhase = "idle" | "sending" | "sent" | "failure_generic";

export default function SendToKindleForm({
  jobId,
  outputPresent,
  kindleDeliveryStatus,
  onSent,
}: Props) {
  const [email, setEmail] = useState("");
  const [phase, setPhase] = useState<FormPhase>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const inputId = useId();
  const errorId = `${inputId}-error`;

  // Prefill from the locally-remembered address (never sent to our server
  // except as the recipient of an explicit send).
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(LOCAL_STORAGE_KEY);
      if (saved) setEmail(saved);
    } catch {
      // localStorage can throw in private-mode / disabled-storage browsers.
    }
  }, []);

  function forgetAddress() {
    try {
      window.localStorage.removeItem(LOCAL_STORAGE_KEY);
    } catch {
      /* ignore */
    }
    setEmail("");
  }

  async function handleSend() {
    const recipient = email.trim();
    if (!recipient) {
      setErrorMsg("Enter your Kindle email address.");
      setPhase("failure_generic");
      return;
    }

    setPhase("sending");
    setErrorMsg(null);
    try {
      await sendToKindle(jobId, recipient);
      try {
        window.localStorage.setItem(LOCAL_STORAGE_KEY, recipient);
      } catch {
        /* ignore */
      }
      setPhase("sent");
      onSent?.(recipient);
    } catch (err: unknown) {
      // Validation rejects (422) and send errors (502) are failure-generic:
      // inline error + retry, NO troubleshooting link (the address is likely
      // just mistyped). The approved-sender failure-known path is driven by
      // the async delivery status below, not this synchronous response.
      const msg =
        err instanceof ApiError
          ? err.message
          : "We couldn't send right now. Please try again.";
      setErrorMsg(msg);
      setPhase("failure_generic");
    }
  }

  if (!outputPresent) {
    return (
      <p className="text-sm text-text-muted">
        This file has expired, so it can no longer be sent to Kindle. Upload it
        again to convert and send.
      </p>
    );
  }

  // ── Graded async delivery state (Unit 10 webhook → status poll) ──────────
  // Shown alongside / after the synchronous send confirmation.
  const deliveryNotice = renderDeliveryNotice(kindleDeliveryStatus);

  if (phase === "sent") {
    return (
      <div className="space-y-2">
        <p className="text-sm text-text-base">
          Sent to <span className="font-medium">{email}</span>. It arrives within
          a few minutes <em>if</em> <span className="font-mono">{FROM_ADDRESS}</span>{" "}
          is on your Amazon Approved Personal Document Email List.
        </p>
        <p className="text-xs text-text-muted">
          First time?{" "}
          <a
            href={APPROVED_SENDER_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="text-brand hover:underline"
          >
            Add {FROM_ADDRESS} to your approved senders →
          </a>
        </p>
        {deliveryNotice}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-xs text-text-muted">
        We send from <span className="font-mono">{FROM_ADDRESS}</span>. First
        time?{" "}
        <a
          href={APPROVED_SENDER_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="text-brand hover:underline"
        >
          Add it to your Amazon Approved Personal Document Email List →
        </a>
      </p>

      <label htmlFor={inputId} className="block text-sm text-text-base">
        Your Kindle email address
      </label>
      <input
        id={inputId}
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="you@kindle.com"
        aria-invalid={phase === "failure_generic" ? true : undefined}
        aria-describedby={phase === "failure_generic" ? errorId : undefined}
        className="w-full max-w-md rounded-md border border-border px-3 py-2 text-sm"
      />

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={handleSend}
          disabled={phase === "sending"}
          className="rounded-md bg-brand px-4 py-2 text-sm text-white hover:bg-brand-dark disabled:opacity-70"
        >
          {phase === "sending" ? "Sending…" : "Send to Kindle"}
        </button>
        {email && (
          <button
            type="button"
            onClick={forgetAddress}
            className="text-xs text-text-muted hover:underline"
          >
            Forget this address
          </button>
        )}
      </div>

      {phase === "failure_generic" && errorMsg && (
        <p id={errorId} className="text-sm text-red-600">
          {errorMsg}
        </p>
      )}

      {deliveryNotice}
    </div>
  );
}

/**
 * Render the async (webhook-driven) delivery state. bounced/failed surface
 * the approved-sender check FIRST (R3.5 failure-known), then the EB-322
 * troubleshooting link.
 */
function renderDeliveryNotice(status: KindleDeliveryStatus) {
  switch (status) {
    case "delivered_to_mail_server":
      return (
        <p className="text-xs text-brand">
          Delivered to Amazon&apos;s mail server.
        </p>
      );
    case "delivery_delayed":
      return (
        <p className="text-xs text-text-muted">
          Amazon reported a delivery delay — it may still arrive shortly.
        </p>
      );
    case "bounced":
    case "failed":
      return (
        <div className="text-xs text-text-muted">
          <p className="text-red-600">
            Amazon didn&apos;t accept this delivery. The most common cause is
            that <span className="font-mono">{FROM_ADDRESS}</span> isn&apos;t on
            your Approved Personal Document Email List yet —{" "}
            <a
              href={APPROVED_SENDER_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="text-brand hover:underline"
            >
              add it here
            </a>
            .
          </p>
          <p className="mt-1">
            Still stuck?{" "}
            <Link href="/guides/send-to-kindle-not-working" className="text-brand hover:underline">
              Send-to-Kindle troubleshooting →
            </Link>
          </p>
        </div>
      );
    default:
      // null or accepted_by_resend → no extra notice beyond the send confirmation.
      return null;
  }
}
