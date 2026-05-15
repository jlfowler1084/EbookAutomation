import { ImageResponse } from 'next/og';
import { readFile } from 'fs/promises';
import path from 'path';

export const alt = 'leafbind — convert PDF';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

export default async function Image({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const title = slug
    .replace(/-/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());

  const loraData = await readFile(
    path.join(process.cwd(), 'public', 'fonts', 'Lora-Medium.ttf')
  );

  return new ImageResponse(
    (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          width: '100%',
          height: '100%',
          background: '#f4efe2',   /* EB-240: updated to --lb-cream */
          color: '#1a3a1a',
          padding: '80px',
        }}
      >
        {/* Leaf glyph inline — geometry matches components/Logo.tsx LeafGlyphPaths().
            Satori (ImageResponse) does not support <defs>/<linearGradient>/<clipPath>,
            so gradient on the folded flap is replaced with a solid back-of-paper tone. */}
        <svg
          width="120"
          height="120"
          viewBox="0 0 100 100"
          style={{ marginBottom: '40px', display: 'block' }}
        >
          {/* Leaf body — rounder Claude Design silhouette */}
          <path
            d="M50 6 C72 14, 88 32, 88 54 C88 76, 72 92, 50 94 C28 92, 12 76, 12 54 C12 32, 28 14, 50 6 Z"
            fill="#2f5d3a"
          />
          {/* Central vein */}
          <path
            d="M50 12 Q49 50, 47 92"
            stroke="#1f3f27"
            strokeWidth="1.6"
            strokeLinecap="round"
            opacity="0.55"
            fill="none"
          />
          {/* Side veins */}
          <path d="M49 28 Q40 30, 26 34" stroke="#1f3f27" strokeWidth="0.9" strokeLinecap="round" opacity="0.32" fill="none" />
          <path d="M48 44 Q38 48, 22 54" stroke="#1f3f27" strokeWidth="0.9" strokeLinecap="round" opacity="0.32" fill="none" />
          <path d="M47 60 Q38 66, 24 74" stroke="#1f3f27" strokeWidth="0.9" strokeLinecap="round" opacity="0.32" fill="none" />
          <path d="M46 76 Q38 82, 28 86" stroke="#1f3f27" strokeWidth="0.9" strokeLinecap="round" opacity="0.32" fill="none" />
          {/* Page body: top-right corner cut out along fold hinge — leaf green shows through */}
          <path d="M50 12 L70 14 L84 28 L84 90 L50 94 Z" fill="#fbf7ec" />
          {/* Text ruling on the flat page section */}
          <line x1="55" y1="38" x2="79" y2="38" stroke="#2f5d3a" strokeWidth="1.4" strokeLinecap="round" opacity="0.82" />
          <line x1="55" y1="46" x2="81" y2="46" stroke="#2f5d3a" strokeWidth="1.4" strokeLinecap="round" opacity="0.82" />
          <line x1="55" y1="54" x2="77" y2="54" stroke="#2f5d3a" strokeWidth="1.4" strokeLinecap="round" opacity="0.82" />
          <line x1="55" y1="62" x2="80" y2="62" stroke="#2f5d3a" strokeWidth="1.4" strokeLinecap="round" opacity="0.82" />
          <line x1="55" y1="70" x2="74" y2="70" stroke="#2f5d3a" strokeWidth="1.4" strokeLinecap="round" opacity="0.82" />
          <line x1="55" y1="78" x2="78" y2="78" stroke="#2f5d3a" strokeWidth="1.4" strokeLinecap="round" opacity="0.82" />
          {/* Folded flap: A(70,14) B(84,28) C'(70,28) — solid back-of-paper tone (no gradient in Satori) */}
          <path d="M70 14 L84 28 L70 28 Z" fill="#e0d8c0" />
          {/* Crease along the fold hinge */}
          <path
            d="M70 14 L84 28"
            stroke="#1f3f27"
            strokeWidth="0.7"
            strokeLinecap="round"
            opacity="0.4"
            fill="none"
          />
          {/* Soft outline on flap free edges */}
          <path
            d="M70 14 L70 28 L84 28"
            stroke="#1f3f27"
            strokeWidth="0.4"
            strokeLinejoin="round"
            opacity="0.18"
            fill="none"
          />
        </svg>

        {/* Slug-derived title */}
        <div
          style={{
            fontFamily: 'Lora',
            fontSize: '64px',
            fontWeight: 500,
            letterSpacing: '-1.2px',
            textAlign: 'center',
            lineHeight: 1.15,
            maxWidth: '1000px',
            display: 'flex',
            color: '#1a3a1a',
          }}
        >
          {title}
        </div>

        {/* Domain mark */}
        <div
          style={{
            marginTop: '40px',
            fontSize: '24px',
            color: '#6a6a6a',
            letterSpacing: '0.4px',
            display: 'flex',
          }}
        >
          leafbind.io
        </div>
      </div>
    ),
    {
      ...size,
      fonts: [
        {
          name: 'Lora',
          data: loraData,
          style: 'normal',
          weight: 500,
        },
      ],
    }
  );
}
