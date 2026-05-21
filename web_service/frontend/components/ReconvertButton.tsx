"use client";

import { useState } from "react";
import { ApiError, reconvertFile } from "../lib/api";
import TokenField from "./TokenField";

interface Props {
  parentJobId: string;
  /** Target format. "mobi" is free; "kfx" is premium (requires a token). */
  format: "mobi" | "kfx";
  /**
   * False once the parent's source has been swept (R4). The button renders
   * disabled with session-expired copy. Uses aria-disabled (not the HTML
   * disabled attribute) so a click still fires for the expired-action
   * telemetry wired in Unit 9b-client.
   */
  disabled?: boolean;
  /** Fired at user-activation time (the actual convert dispatch), before the
   *  API call — the engagement signal for Unit 9b-client telemetry. */
  onAttempt?: () => void;
  /** Called with the new child job_id once a re-convert is dispatched. */
  onDispatched: (childJobId: string) => void;
  /** Fired when a disabled button is activated (Unit 9b-client telemetry). */
  onDisabledClick?: () => void;
}

const FORMAT_LABEL: Record<Props["format"], string> = {
  mobi: "MOBI",
  kfx: "KFX",
};

export default function ReconvertButton({
  parentJobId,
  format,
  disabled = false,
  onAttempt,
  onDispatched,
  onDisabledClick,
}: Props) {
  const [phase, setPhase] = useState<"idle" | "token" | "submitting" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const isPremium = format === "kfx";
  const label = FORMAT_LABEL[format];

  async function dispatch(token?: string) {
    // Engagement signal at the moment the user commits to converting (free:
    // Convert click; premium: valid-token submit), before the API call.
    onAttempt?.();
    setPhase("submitting");
    setErrorMsg(null);
    try {
      const result = await reconvertFile(parentJobId, format, token);
      onDispatched(result.job_id);
      // Leave the button in submitting state; the parent ActionCluster will
      // replace this row with the child's live progress on the next poll.
    } catch (err: unknown) {
      const msg =
        err instanceof ApiError
          ? err.message
          : "Could not start the conversion. Please try again.";
      setErrorMsg(msg);
      setPhase("error");
    }
  }

  if (disabled) {
    return (
      <button
        type="button"
        aria-disabled="true"
        onClick={() => onDisabledClick?.()}
        className="cursor-not-allowed rounded-md border border-border bg-surface-muted px-4 py-2 text-sm text-text-muted opacity-60"
      >
        Convert to {label} — session expired
      </button>
    );
  }

  if (phase === "submitting") {
    return (
      <button
        type="button"
        disabled
        className="rounded-md bg-brand px-4 py-2 text-sm text-white opacity-70"
      >
        Starting {label} conversion…
      </button>
    );
  }

  // Premium KFX: reveal the inline TokenField, then dispatch on a valid token.
  if (isPremium && phase === "token") {
    return (
      <div className="space-y-2">
        <p className="text-sm text-text-muted">
          KFX is a premium format. Paste a conversion token to continue.
        </p>
        <TokenField onValidToken={(token) => dispatch(token)} />
        {errorMsg && <p className="text-sm text-red-600">{errorMsg}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => (isPremium ? setPhase("token") : dispatch())}
        className="rounded-md bg-brand px-4 py-2 text-sm text-white hover:bg-brand-dark"
      >
        {isPremium ? `Convert to ${label} — paste token` : `Convert to ${label}`}
      </button>
      {errorMsg && <p className="text-sm text-red-600">{errorMsg}</p>}
    </div>
  );
}
