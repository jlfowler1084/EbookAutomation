"use client";

import { useEffect, useState } from "react";

interface Props {
  /** Epoch seconds when the job's artifacts expire (from StatusResponse). */
  expiresAt: number;
  /**
   * When true, the countdown hides itself — used after a consumed action
   * (e.g., a successful Send-to-Kindle) where the remaining-time copy would
   * be noise (R4 / Key Decisions: "hides on any consumed action").
   */
  hidden?: boolean;
}

/**
 * EB-324 Unit 6: coarse TTL countdown for the result-page action cluster.
 *
 * Renders a deliberately-imprecise bucket rather than a ticking clock — the
 * exact second doesn't matter to the user, and a coarse label ("about an
 * hour") reads calmer than "59:47". Buckets (plan line 542):
 *   > 30 min  → "about an hour"
 *   10–30 min → "about half an hour"
 *   < 10 min  → "less than 10 minutes"
 *   elapsed   → nothing (the disabled-state copy in ActionCluster takes over)
 */
function coarseLabel(secondsRemaining: number): string | null {
  if (secondsRemaining <= 0) return null;
  const minutes = secondsRemaining / 60;
  if (minutes > 30) return "about an hour";
  if (minutes >= 10) return "about half an hour";
  return "less than 10 minutes";
}

export default function TtlCountdown({ expiresAt, hidden = false }: Props) {
  // Re-evaluate once a minute — finer granularity is wasted on coarse buckets.
  const [now, setNow] = useState(() => Math.floor(Date.now() / 1000));

  useEffect(() => {
    const id = setInterval(() => setNow(Math.floor(Date.now() / 1000)), 60_000);
    return () => clearInterval(id);
  }, []);

  if (hidden) return null;

  const label = coarseLabel(expiresAt - now);
  if (label === null) return null;

  return (
    <p className="text-xs text-text-muted">
      These files are available for <span className="font-medium">{label}</span>.
    </p>
  );
}
