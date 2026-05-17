"use client";

export interface OutputFormat {
  id: string;
  label: string;
  premium: boolean;
}

// Source of truth for client-side output-format gating.
// Server-side enforcement lives in web_service/validation.py (PREMIUM_OUTPUT_FORMATS).
export const FORMATS: ReadonlyArray<OutputFormat> = [
  { id: "epub", label: "EPUB", premium: false },
  { id: "mobi", label: "MOBI", premium: false },
  { id: "kfx", label: "KFX", premium: true },
];

export function isFormatGated(formatId: string, tier: string): boolean {
  const fmt = FORMATS.find((f) => f.id === formatId);
  return Boolean(fmt?.premium && tier !== "premium");
}

interface Props {
  value: string;
  onChange: (format: string) => void;
  tier?: string;
}

export default function FormatSelector({ value, onChange, tier = "free" }: Props) {
  const gated = isFormatGated(value, tier);
  const selected = FORMATS.find((f) => f.id === value);

  return (
    <div>
      <label htmlFor="output-format" style={{ display: "block", marginBottom: 4 }}>
        Output format
      </label>
      <select
        id="output-format"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{ padding: "6px 12px", fontSize: 14, borderRadius: 4, border: "1px solid var(--color-border)" }}
      >
        {FORMATS.map((fmt) => {
          const showPremiumSuffix = fmt.premium && tier !== "premium";
          return (
            <option key={fmt.id} value={fmt.id}>
              {fmt.label}
              {showPremiumSuffix ? " — Premium" : ""}
            </option>
          );
        })}
      </select>
      {gated && selected && (
        <div
          role="note"
          aria-live="polite"
          data-testid="format-upsell"
          style={{
            marginTop: 8,
            padding: "8px 12px",
            border: "1px solid var(--color-border)",
            borderRadius: 4,
            fontSize: 13,
            background: "var(--color-surface-muted)",
          }}
        >
          <strong>{selected.label}</strong> is a premium format.{" "}
          <a
            href="/pricing#standard"
            style={{ color: "var(--color-accent)", fontWeight: 600 }}
          >
            Buy credits to convert →
          </a>
        </div>
      )}
    </div>
  );
}
