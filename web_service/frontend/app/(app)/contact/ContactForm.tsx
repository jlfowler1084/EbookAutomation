"use client";

/**
 * EB-264: Contact form for leafbind.io/contact.
 *
 * Design decisions:
 * - Submit target: https://forms.leafbind.io/contact (NOT api.leafbind.io)
 *   api.leafbind.io serves the FastAPI conversion backend on Hetzner VM.
 * - Loading state pattern: UploadZone.tsx (useState<boolean> + label-swap)
 * - Accessibility: aria-describedby wired between each input and its error —
 *   deliberate improvement over TokenField.tsx which is missing this wiring.
 * - Turnstile: uses the NEXT_PUBLIC_TURNSTILE_SITE_KEY env var (visible in source;
 *   site keys are public by design — only the secret key is private).
 * - sessionStorage draft: input saved on each change and cleared on success.
 * - Honeypot field (hidden, aria-hidden) to trip naive bots without disrupting UX.
 */

import { useRef, useState, type ChangeEvent, type FormEvent } from "react";
import Script from "next/script";

// Turnstile JS object shape we depend on. Cast through unknown because the library
// is loaded via <Script> and not present in the Window typedef.
interface TurnstileApi {
  render: (
    el: string | HTMLElement,
    opts: {
      sitekey: string;
      callback: (token: string) => void;
      "error-callback"?: () => void;
      "expired-callback"?: () => void;
      "timeout-callback"?: () => void;
      execution?: "render" | "execute";
      appearance?: "always" | "execute" | "interaction-only";
      retry?: "auto" | "never";
    }
  ) => string;
  reset: (widgetId: string) => void;
  getResponse: (widgetId: string) => string | undefined;
}
interface TurnstileWindow extends Window {
  turnstile?: TurnstileApi;
}

const WORKER_URL = "https://forms.leafbind.io/contact";

// Turnstile site key is public — safe to embed in source.
// Set NEXT_PUBLIC_TURNSTILE_SITE_KEY in Vercel environment variables.
// Cloudflare Turnstile: Dashboard → Turnstile → Add Site → leafbind.io → Site Key.
const TURNSTILE_SITE_KEY =
  process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY ?? "";

const TOPICS = [
  { value: "general", label: "General question" },
  { value: "billing", label: "Billing" },
  { value: "conversion", label: "Conversion issue" },
  { value: "bug", label: "Bug report" },
  { value: "feature", label: "Feature request" },
] as const;

const DRAFT_KEY = "lb_contact_draft";

interface FormFields {
  name: string;
  email: string;
  topic: string;
  message: string;
}

function loadDraft(): Partial<FormFields> {
  try {
    const raw = sessionStorage.getItem(DRAFT_KEY);
    return raw ? (JSON.parse(raw) as Partial<FormFields>) : {};
  } catch {
    return {};
  }
}

function saveDraft(fields: Partial<FormFields>) {
  // Merge with existing draft so rapid cross-field edits (before React re-renders)
  // don't drop earlier field changes via stale-closure reads of state.
  try {
    const existing = loadDraft();
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ ...existing, ...fields }));
  } catch {
    // sessionStorage unavailable — silent
  }
}

function clearDraft() {
  try {
    sessionStorage.removeItem(DRAFT_KEY);
  } catch {
    // silent
  }
}

export default function ContactForm() {
  const draft = loadDraft();

  const [name, setName] = useState(draft.name ?? "");
  const [email, setEmail] = useState(draft.email ?? "");
  const [topic, setTopic] = useState(draft.topic ?? "general");
  const [message, setMessage] = useState(draft.message ?? "");
  const [honeypot, setHoneypot] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Partial<FormFields>>({});

  const successRef = useRef<HTMLDivElement>(null);

  // Turnstile state: token is set once the widget solves (which Cloudflare does
  // either invisibly or after a brief user interaction). widgetIdRef holds the
  // handle so we can reset() after a submit to get a fresh token.
  const [turnstileToken, setTurnstileToken] = useState<string>("");
  const widgetIdRef = useRef<string | null>(null);

  function onTurnstileScriptLoad() {
    if (!TURNSTILE_SITE_KEY) return;
    const tWindow = window as TurnstileWindow;
    if (!tWindow.turnstile || widgetIdRef.current !== null) return;
    widgetIdRef.current = tWindow.turnstile.render("#turnstile-container", {
      sitekey: TURNSTILE_SITE_KEY,
      callback: (token) => setTurnstileToken(token),
      "error-callback": () => setTurnstileToken(""),
      "expired-callback": () => setTurnstileToken(""),
      "timeout-callback": () => setTurnstileToken(""),
      // Default execution ("render"): widget challenges as soon as it mounts and
      // calls back with the token. With appearance "interaction-only" it stays
      // invisible unless Cloudflare decides interaction is needed.
      appearance: "interaction-only",
      retry: "auto",
    });
  }

  function resetTurnstile() {
    setTurnstileToken("");
    const tWindow = window as TurnstileWindow;
    if (tWindow.turnstile && widgetIdRef.current) {
      tWindow.turnstile.reset(widgetIdRef.current);
    }
  }

  function handleChange(
    field: keyof FormFields,
    setter: (v: string) => void
  ) {
    return (e: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
      const val = e.target.value;
      setter(val);
      // Only persist the changed field — saveDraft merges with the stored draft,
      // so cross-field state from this render's closure isn't read (and can't go stale).
      saveDraft({ [field]: val });
      // Clear field error on edit
      if (fieldErrors[field]) {
        setFieldErrors((prev) => ({ ...prev, [field]: undefined }));
      }
    };
  }

  function validate(): boolean {
    const errors: Partial<FormFields> = {};
    if (!name.trim()) errors.name = "Name is required.";
    if (!email.trim()) errors.email = "Email address is required.";
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      errors.email = "Please enter a valid email address.";
    }
    if (!message.trim()) errors.message = "Message is required.";
    else if (message.trim().length < 10) {
      errors.message = "Message must be at least 10 characters.";
    }
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setServerError(null);

    if (!validate()) return;

    // Turnstile must have solved before submit. If the script hasn't loaded
    // or the widget hasn't called back yet, ask the user to wait briefly.
    // (Once the script has loaded, the widget usually solves in <1s, so this
    // path is only hit on slow networks or if the widget failed to render.)
    if (!turnstileToken) {
      setServerError(
        "Bot check is still loading. Please wait a moment and try again."
      );
      return;
    }

    setSubmitting(true);
    saveDraft({ name, email, topic, message }); // persist before fetch

    try {
      const resp = await fetch(WORKER_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          email: email.trim(),
          topic,
          message: message.trim(),
          turnstile_token: turnstileToken,
          ...(honeypot ? { honeypot } : {}),
        }),
      });

      const data = (await resp.json()) as { ok: boolean; error?: string };

      if (!resp.ok || !data.ok) {
        if (resp.status === 429) {
          setServerError(
            "You've sent too many messages recently. Please wait a while before trying again."
          );
        } else if (resp.status === 400 && data.error?.toLowerCase().includes("bot")) {
          setServerError(
            "Bot check failed. Please refresh the page and try again."
          );
        } else if (resp.status >= 500) {
          setServerError(
            "We couldn’t deliver your message right now. Please try again in a few minutes, or email us directly at support@leafbind.io."
          );
        } else {
          setServerError(
            data.error ?? "Something went wrong. Please check your details and try again."
          );
        }
        // Turnstile tokens are single-use — get a fresh one before the user retries.
        resetTurnstile();
        return;
      }

      clearDraft();
      setSuccess(true);
      // Move focus to success message for screen readers
      setTimeout(() => successRef.current?.focus(), 50);
    } catch {
      // Network error — also burn the token; next retry needs a fresh one.
      resetTurnstile();
      setServerError(
        "Network error — check your connection and try again. If the problem persists, email support@leafbind.io."
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (success) {
    return (
      <div
        ref={successRef}
        tabIndex={-1}
        role="status"
        aria-live="polite"
        className="rounded-md border border-border bg-surface-muted p-6 focus:outline-none"
      >
        <p className="font-serif text-xl text-text-base mb-2">Message sent</p>
        <p className="text-sm text-text-muted leading-relaxed">
          We received your message and will get back to you within a few
          business days. In the meantime you can email{" "}
          <a
            href="mailto:support@leafbind.io"
            className="text-brand hover:underline"
          >
            support@leafbind.io
          </a>{" "}
          directly if your issue is urgent.
        </p>
      </div>
    );
  }

  return (
    <>
      {/*
        Loads the Turnstile JS API and renders the widget into #turnstile-container
        on script load. Uses ?render=explicit so Cloudflare does NOT auto-render
        every .cf-turnstile element on the page — we control rendering explicitly
        via onTurnstileScriptLoad so we can hold a widgetId for reset().
      */}
      <Script
        src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit"
        strategy="afterInteractive"
        onLoad={onTurnstileScriptLoad}
      />

      {/* Hidden Turnstile container — invisible widget renders here */}
      <div id="turnstile-container" aria-hidden="true" />

      <form onSubmit={handleSubmit} noValidate className="space-y-5">
        {/* Honeypot — hidden from real users, visible to naive bots */}
        <div aria-hidden="true" style={{ display: "none" }}>
          <label htmlFor="lb-hp">Leave this field empty</label>
          <input
            id="lb-hp"
            name="lb-hp"
            type="text"
            tabIndex={-1}
            autoComplete="off"
            value={honeypot}
            onChange={(e) => setHoneypot(e.target.value)}
          />
        </div>

        {/* Name */}
        <div>
          <label
            htmlFor="contact-name"
            className="block text-sm font-medium text-text-base mb-1"
          >
            Name
          </label>
          <input
            id="contact-name"
            name="name"
            type="text"
            autoComplete="name"
            required
            aria-required="true"
            aria-describedby={fieldErrors.name ? "contact-name-error" : undefined}
            aria-invalid={fieldErrors.name ? "true" : "false"}
            value={name}
            onChange={handleChange("name", setName)}
            style={{
              width: "100%",
              padding: "0.5em 0.75em",
              border: `1px solid ${fieldErrors.name ? "#b91c1c" : "var(--color-border)"}`,
              borderRadius: "var(--radius-sm, 0.25rem)",
              fontSize: "1rem",
              boxSizing: "border-box",
              fontFamily: "inherit",
            }}
          />
          {fieldErrors.name && (
            <p
              id="contact-name-error"
              role="alert"
              style={{ color: "#b91c1c", fontSize: "0.875rem", marginTop: "0.25rem" }}
            >
              {fieldErrors.name}
            </p>
          )}
        </div>

        {/* Email */}
        <div>
          <label
            htmlFor="contact-email"
            className="block text-sm font-medium text-text-base mb-1"
          >
            Email
          </label>
          <input
            id="contact-email"
            name="email"
            type="email"
            autoComplete="email"
            required
            aria-required="true"
            aria-describedby={fieldErrors.email ? "contact-email-error" : undefined}
            aria-invalid={fieldErrors.email ? "true" : "false"}
            value={email}
            onChange={handleChange("email", setEmail)}
            style={{
              width: "100%",
              padding: "0.5em 0.75em",
              border: `1px solid ${fieldErrors.email ? "#b91c1c" : "var(--color-border)"}`,
              borderRadius: "var(--radius-sm, 0.25rem)",
              fontSize: "1rem",
              boxSizing: "border-box",
              fontFamily: "inherit",
            }}
          />
          {fieldErrors.email && (
            <p
              id="contact-email-error"
              role="alert"
              style={{ color: "#b91c1c", fontSize: "0.875rem", marginTop: "0.25rem" }}
            >
              {fieldErrors.email}
            </p>
          )}
        </div>

        {/* Topic */}
        <div>
          <label
            htmlFor="contact-topic"
            className="block text-sm font-medium text-text-base mb-1"
          >
            Topic
          </label>
          <select
            id="contact-topic"
            name="topic"
            value={topic}
            onChange={handleChange("topic", setTopic)}
            style={{
              width: "100%",
              padding: "0.5em 0.75em",
              border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-sm, 0.25rem)",
              fontSize: "1rem",
              boxSizing: "border-box",
              fontFamily: "inherit",
              background: "var(--color-surface)",
            }}
          >
            {TOPICS.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>

        {/* Message */}
        <div>
          <label
            htmlFor="contact-message"
            className="block text-sm font-medium text-text-base mb-1"
          >
            Message
          </label>
          <textarea
            id="contact-message"
            name="message"
            rows={6}
            required
            aria-required="true"
            aria-describedby={fieldErrors.message ? "contact-message-error" : undefined}
            aria-invalid={fieldErrors.message ? "true" : "false"}
            value={message}
            onChange={handleChange("message", setMessage)}
            style={{
              width: "100%",
              padding: "0.5em 0.75em",
              border: `1px solid ${fieldErrors.message ? "#b91c1c" : "var(--color-border)"}`,
              borderRadius: "var(--radius-sm, 0.25rem)",
              fontSize: "1rem",
              boxSizing: "border-box",
              fontFamily: "inherit",
              resize: "vertical",
              minHeight: "120px",
            }}
          />
          {fieldErrors.message && (
            <p
              id="contact-message-error"
              role="alert"
              style={{ color: "#b91c1c", fontSize: "0.875rem", marginTop: "0.25rem" }}
            >
              {fieldErrors.message}
            </p>
          )}
        </div>

        {/* Server error */}
        {serverError && (
          <div
            role="alert"
            style={{
              padding: "0.75em 1em",
              border: "1px solid #b91c1c",
              borderRadius: "0.25rem",
              color: "#b91c1c",
              fontSize: "0.875rem",
              background: "#fef2f2",
            }}
          >
            {serverError}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting}
          style={{
            padding: "0.6em 1.5em",
            background: submitting ? "var(--color-text-muted)" : "var(--color-brand)",
            color: "#fff",
            border: "none",
            borderRadius: "var(--radius-sm, 0.25rem)",
            fontSize: "1rem",
            cursor: submitting ? "not-allowed" : "pointer",
            fontFamily: "inherit",
            transition: "background 0.15s",
          }}
        >
          {submitting ? "Sending…" : "Send message"}
        </button>
      </form>
    </>
  );
}
