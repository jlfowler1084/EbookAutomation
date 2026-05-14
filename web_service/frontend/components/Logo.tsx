type LogoProps = {
  className?: string;
  variant?: "full" | "glyph";
};

export function Logo({ className, variant = "full" }: LogoProps) {
  if (variant === "glyph") {
    return (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 64 64"
        role="img"
        aria-label="leafbind"
        className={className}
      >
        <title>leafbind</title>
        <LeafGlyphPaths />
      </svg>
    );
  }

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 220 64"
      role="img"
      aria-label="leafbind"
      className={className}
    >
      <title>leafbind</title>
      <LeafGlyphPaths />
      <text
        x="76"
        y="44"
        fontFamily="var(--font-lora), Georgia, serif"
        fontSize="34"
        fontWeight="500"
        fill="currentColor"
        letterSpacing="-0.5"
      >
        leafbind
      </text>
    </svg>
  );
}

function LeafGlyphPaths() {
  return (
    <>
      <path
        d="M 32 4 C 34 16 50 22 52 32 C 54 50 40 58 32 60 C 24 58 10 50 12 32 C 14 22 30 16 32 4 Z"
        fill="#2D4A2B"
      />
      <path
        d="M 32 4 C 34 16 50 22 52 32 C 54 50 40 58 32 60 L 32 4 Z"
        fill="#F5F1E8"
      />
      <path d="M 42 8 L 50 20 L 38 14 Z" fill="#3a5a38" />
      <path d="M 42 8 L 50 20 L 46 11 Z" fill="#E8DEC1" />
      <line x1="42" y1="8" x2="50" y2="20" stroke="#A89A75" strokeWidth="0.3" strokeLinecap="round" opacity="0.6" />
      <rect x="35" y="26" width="14" height="1.3" rx="0.65" fill="#3a3a3a" />
      <rect x="35" y="32" width="12" height="1.3" rx="0.65" fill="#3a3a3a" />
      <rect x="35" y="38" width="14" height="1.3" rx="0.65" fill="#3a3a3a" />
      <rect x="35" y="44" width="10" height="1.3" rx="0.65" fill="#3a3a3a" />
      <rect x="35" y="50" width="13" height="1.3" rx="0.65" fill="#3a3a3a" />
      <line x1="32" y1="6" x2="32" y2="58" stroke="#1a3a1a" strokeWidth="0.6" strokeLinecap="round" />
      <path d="M 30 22 Q 24 22 16 24" stroke="#1a3a1a" strokeWidth="0.5" fill="none" strokeLinecap="round" opacity="0.55" />
      <path d="M 30 42 Q 22 44 14 46" stroke="#1a3a1a" strokeWidth="0.5" fill="none" strokeLinecap="round" opacity="0.55" />
    </>
  );
}
