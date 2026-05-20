const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

export type JobStatus = "queued" | "running" | "done" | "failed" | "expired";

// EB-324 Unit 4: Resend webhook lifecycle for Send-to-Kindle delivery.
// `accepted_by_resend` is set on the parent (and any child) the moment our
// route's POST succeeds at Resend's API. Unit 10's webhook handler later
// transitions the field through delivered/bounced/failed/delayed.
export type KindleDeliveryStatus =
  | "accepted_by_resend"
  | "delivered_to_mail_server"
  | "bounced"
  | "delivery_failed"
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
  // EB-324 Unit 5: four new contract fields the action cluster gates on.
  // Present on every status value; download_url stays done-only.
  expires_at: number;
  source_present: boolean;
  output_present: boolean;
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
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
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
