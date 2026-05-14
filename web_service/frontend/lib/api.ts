const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

export type JobStatus = "queued" | "running" | "done" | "failed" | "expired";

export interface StatusResponse {
  job_id: string;
  status: JobStatus;
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

export async function getStatus(jobId: string): Promise<StatusResponse> {
  const resp = await fetch(`${API_URL}/status/${jobId}`);
  if (!resp.ok) {
    throw new Error(`Status check failed: HTTP ${resp.status}`);
  }
  return resp.json();
}

export function getDownloadUrl(jobId: string): string {
  return `${API_URL}/download/${jobId}`;
}
