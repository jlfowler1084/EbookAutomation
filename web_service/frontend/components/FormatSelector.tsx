"use client";

interface Props {
  value: string;
  onChange: (format: string) => void;
  tier?: string;
}

const FREE_FORMATS = ["epub", "mobi"];
const PREMIUM_FORMATS = ["epub", "mobi", "kfx"];

export default function FormatSelector({ value, onChange, tier = "free" }: Props) {
  const formats = tier === "premium" ? PREMIUM_FORMATS : FREE_FORMATS;

  return (
    <div>
      <label htmlFor="output-format" style={{ display: "block", marginBottom: 4 }}>
        Output format
      </label>
      <select
        id="output-format"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{ padding: "6px 12px", fontSize: 14, borderRadius: 4, border: "1px solid #ccc" }}
      >
        {formats.map((fmt) => (
          <option key={fmt} value={fmt}>
            {fmt.toUpperCase()}
          </option>
        ))}
      </select>
    </div>
  );
}
