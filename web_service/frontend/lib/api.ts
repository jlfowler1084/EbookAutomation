const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

export type JobStatus = "queued" | "running" | "done" | "failed" | "expired";

// EB-324 Unit 4: Resend webhook lifecycle for Send-to-Kindle delivery.
// `accepted_by_resend` is set on the parent (and any child) the moment our
// route's POST succeeds at Resend's API. Unit 10's webhook handler later
// transitions the field through delivered_to_mail_server / bounced /
// failed / delivery_delayed. NOTE: the column-canonical failure value is
// "failed", not "delivery_failed" — the latter is the telemetry event name
// (`send_to_kindle_delivery_failed`), which is a different namespace.
export type KindleDeliveryStatus =
  | "accepted_by_resend"
  | "delivered_to_mail_server"
  | "bounced"
  | "failed"
  | "delivery_delayed"
  | null;

// EB-324 Unit 5: per-child entry in StatusResponse.children[].
// Each re-convert child carries its own presence + delivery state so the
// action cluster can render Download / Send-to-Kindle / Re-convert
// independently on each row.
export interface ChildJob {
  job_id: string;
  format: string;
  status: JobStatus;
  expires_at: number;
  source_present: boolean;
  output_present: boolean;
  kindle_delivery_status: KindleDeliveryStatus;
  resend_message_id: string | null;
  download_url: string | null;
}

export interface StatusResponse {
  job_id: string;
  status: JobStatus;
  // EB-324 Unit 5: contract fields the action cluster gates on.
  // Present on every status value; download_url stays done-only.
  expires_at: number;
  source_present: boolean;
  output_present: boolean;
  // Parent Send-to-Kindle delivery state mirrors the per-child fields so
  // the parent EPUB row renders graded delivery state. Both null until
  // Send-to-Kindle has been invoked.
  kindle_delivery_status: KindleDeliveryStatus;
  resend_message_id: string | null;
  children: ChildJob[];
  download_url?: string;
  output_size?: number;
  error?: string;
}

export interface ConvertResponse {
  job_id: string;
}

export interface CheckoutResponse {
  checkout_url: string;
  session_id: string;
}

export async function startConversion(
  file: File,
  outputFormat: string,
  tier: string = "free",
  token?: string
): Promise<ConvertResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("output_format", outputFormat);
  form.append("tier", tier);
  if (token) form.append("token", token);

  const resp = await fetch(`${API_URL}/convert`, {
    method: "POST",
    body: form,
  });

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ error: "Unknown error" }));
    throw new Error(err.detail?.error ?? err.error ?? `HTTP ${resp.status}`);
  }

  return resp.json();
}

export async function createCheckoutSession(pack: string): Promise<CheckoutResponse> {
  const formData = new FormData();
  formData.append("pack", pack);

  const resp = await fetch(`${API_URL}/stripe/create-session`, {
    method: "POST",
    body: formData,
  });

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail?.error ?? err.error ?? `HTTP ${resp.status}`);
  }

  return resp.json();
}

// EB-271: typed error so callers can distinguish 404 (expired/unknown job)
// from 5xx (backend outage) — both produced the same generic UI before.
// EB-324 Unit 6: `code` carries the backend error code (e.g.,
// INVALID_RECIPIENT_DOMAIN) so the Send-to-Kindle form can pick between
// failure-known and failure-generic copy (R3.2).
export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(status: number, message: string, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export async function getStatus(jobId: string): Promise<StatusResponse> {
  const resp = await fetch(`${API_URL}/status/${jobId}`);
  if (!resp.ok) {
    throw new ApiError(resp.status, `Status check failed: HTTP ${resp.status}`);
  }
  return resp.json();
}

export function getDownloadUrl(jobId: string): string {
  return `${API_URL}/download/${jobId}`;
}

// EB-324 Unit 9b-client: fire a Plausible custom event via the self-hosted
// script's global `window.plausible`. Safe no-op when the script hasn't
// loaded (SSR, ad-blockers, tests). Privacy: callers MUST NOT pass raw
// job_id or recipient — only coarse props (format, tier, action) — since
// Plausible is an analytics sink.
type PlausibleFn = (name: string, opts?: { props?: Record<string, string | number | boolean> }) => void;

export function emitEvent(
  name: string,
  props?: Record<string, string | number | boolean>
): void {
  if (typeof window === "undefined") return;
  const plausible = (window as unknown as { plausible?: PlausibleFn }).plausible;
  if (typeof plausible === "function") {
    plausible(name, props ? { props } : undefined);
  }
}

// EB-324 Unit 6: result-page action-cluster client methods.

export interface SendToKindleResponse {
  status: "sent" | "already_sent";
}

/**
 * POST /send-to-kindle/{jobId}. Surfaces the backend error code on ApiError
 * so the form can render failure-known vs failure-generic copy (R3.2).
 */
export async function sendToKindle(
  jobId: string,
  recipient: string
): Promise<SendToKindleResponse> {
  const form = new FormData();
  form.append("recipient", recipient);

  const resp = await fetch(`${API_URL}/send-to-kindle/${jobId}`, {
    method: "POST",
    body: form,
  });

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new ApiError(
      resp.status,
      err.detail?.error ?? err.error ?? `HTTP ${resp.status}`,
      err.detail?.code
    );
  }

  return resp.json();
}

/**
 * POST /reconvert/{parentJobId}. `token` is required for premium formats
 * (KFX); omit for free formats (MOBI). Returns the child job_id.
 */
export async function reconvertFile(
  parentJobId: string,
  outputFormat: string,
  token?: string
): Promise<ConvertResponse> {
  const form = new FormData();
  form.append("output_format", outputFormat);
  if (token) form.append("token", token);

  const resp = await fetch(`${API_URL}/reconvert/${parentJobId}`, {
    method: "POST",
    body: form,
  });

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new ApiError(
      resp.status,
      err.detail?.error ?? err.error ?? `HTTP ${resp.status}`,
      err.detail?.code
    );
  }

  return resp.json();
}
