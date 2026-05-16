type LogoProps = {
  className?: string;
  variant?: "full" | "glyph";
};

export function Logo({ className, variant = "full" }: LogoProps) {
  // EB-269 (F4-03): SVG is presentational. All current call sites (Header,
  // Footer, hero glyph) wrap Logo in a labeled link or sit in a labeled
  // context; the prior `role="img"` + `aria-label` + `<title>` triple caused
  // screen readers to announce "leafbind.io" twice on every wrapping link.
  if (variant === "glyph") {
    return (
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 100 100"
        aria-hidden="true"
        fill="none"
        className={className}
      >
        <LeafGlyphPaths gradId="lbCurlShade_glyph" clipId="lbLeafClip_glyph" />
      </svg>
    );
  }

  return (
    // EB-240: viewBox widened 370→380 to fit italic .io suffix; font updated
    // to Newsreader (EB-238 absorbed). The .io tspan uses sand accent + italic
    // per Claude Design logos.jsx LogoLockup pattern.
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 380 100"
      aria-hidden="true"
      fill="none"
      className={className}
    >
      <LeafGlyphPaths gradId="lbCurlShade_full" clipId="lbLeafClip_full" />
      <text
        x="116"
        y="68"
        fontFamily="var(--font-newsreader), Georgia, serif"
        fontSize="53"
        fontWeight="500"
        fill="currentColor"
        letterSpacing="-0.8"
      >
        leafbind<tspan fill="#c9a96e" fontStyle="italic">.io</tspan>
      </text>
    </svg>
  );
}

function LeafGlyphPaths({ gradId, clipId }: { gradId: string; clipId: string }) {
  return (
    <>
      <defs>
        {/* Gradient for folded-flap: paper face fading to back-of-paper tone */}
        <linearGradient id={gradId} x1="0.15" y1="0" x2="0.85" y2="1">
          <stop offset="0"    stopColor="#fbf7ec" />
          <stop offset="0.55" stopColor="#fbf7ec" />
          <stop offset="1"    stopColor="#e0d8c0" />
        </linearGradient>
        {/* Clip to leaf silhouette so page/veins never bleed outside */}
        <clipPath id={clipId}>
          <path d="M50 6 C72 14, 88 32, 88 54 C88 76, 72 92, 50 94 C28 92, 12 76, 12 54 C12 32, 28 14, 50 6 Z" />
        </clipPath>
      </defs>

      {/* Leaf body — rounder Claude Design silhouette */}
      <path
        d="M50 6 C72 14, 88 32, 88 54 C88 76, 72 92, 50 94 C28 92, 12 76, 12 54 C12 32, 28 14, 50 6 Z"
        fill="#2f5d3a"
      />

      <g clipPath={`url(#${clipId})`}>
        {/* Central vein (drawn before page so hidden under paper) */}
        <path
          d="M50 12 Q49 50, 47 92"
          stroke="#1f3f27"
          strokeWidth="1.6"
          strokeLinecap="round"
          opacity="0.55"
        />
        {/* Side veins on the green half */}
        <g stroke="#1f3f27" strokeWidth="0.9" strokeLinecap="round" opacity="0.32">
          <path d="M49 28 Q40 30, 26 34" />
          <path d="M48 44 Q38 48, 22 54" />
          <path d="M47 60 Q38 66, 24 74" />
          <path d="M46 76 Q38 82, 28 86" />
        </g>

        {/* Page body: right half with top-right corner cut out along the fold hinge.
            The missing triangle (above hinge AB) reveals leaf green — physically correct. */}
        <path d="M50 12 L70 14 L84 28 L84 90 L50 94 Z" fill="#fbf7ec" />

        {/* Text ruling on the still-flat page section */}
        <g stroke="#2f5d3a" strokeWidth="1.4" strokeLinecap="round" opacity="0.82">
          <line x1="55" y1="38" x2="79" y2="38" />
          <line x1="55" y1="46" x2="81" y2="46" />
          <line x1="55" y1="54" x2="77" y2="54" />
          <line x1="55" y1="62" x2="80" y2="62" />
          <line x1="55" y1="70" x2="74" y2="70" />
          <line x1="55" y1="78" x2="78" y2="78" />
        </g>

        {/* Folded flap: triangle A(70,14) B(84,28) C'(70,28).
            C'=(70,28) is original corner C=(84,14) reflected across hinge AB. */}
        <path d={`M70 14 L84 28 L70 28 Z`} fill={`url(#${gradId})`} />
        {/* Crease along the fold hinge */}
        <path
          d="M70 14 L84 28"
          stroke="#1f3f27"
          strokeWidth="0.7"
          strokeLinecap="round"
          opacity="0.4"
        />
        {/* Soft outline on the flap's free edges so it reads as raised */}
        <path
          d="M70 14 L70 28 L84 28"
          stroke="#1f3f27"
          strokeWidth="0.4"
          strokeLinejoin="round"
          opacity="0.18"
        />
      </g>
    </>
  );
}
