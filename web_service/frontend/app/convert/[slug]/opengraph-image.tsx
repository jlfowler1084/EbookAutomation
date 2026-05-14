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
          background: '#FAF8F3',
          color: '#1a3a1a',
          padding: '80px',
        }}
      >
        {/* Leaf glyph inline — paths from components/Logo.tsx LeafGlyphPaths() */}
        <svg
          width="120"
          height="120"
          viewBox="0 0 64 64"
          style={{ marginBottom: '40px', display: 'block' }}
        >
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
          <line
            x1="42"
            y1="8"
            x2="50"
            y2="20"
            stroke="#A89A75"
            strokeWidth="0.3"
            strokeLinecap="round"
            opacity="0.6"
          />
          <rect x="35" y="26" width="14" height="1.3" rx="0.65" fill="#3a3a3a" />
          <rect x="35" y="32" width="12" height="1.3" rx="0.65" fill="#3a3a3a" />
          <rect x="35" y="38" width="14" height="1.3" rx="0.65" fill="#3a3a3a" />
          <rect x="35" y="44" width="10" height="1.3" rx="0.65" fill="#3a3a3a" />
          <rect x="35" y="50" width="13" height="1.3" rx="0.65" fill="#3a3a3a" />
          <line
            x1="32"
            y1="6"
            x2="32"
            y2="58"
            stroke="#1a3a1a"
            strokeWidth="0.6"
            strokeLinecap="round"
          />
          <path
            d="M 30 22 Q 24 22 16 24"
            stroke="#1a3a1a"
            strokeWidth="0.5"
            fill="none"
            strokeLinecap="round"
            opacity="0.55"
          />
          <path
            d="M 30 42 Q 22 44 14 46"
            stroke="#1a3a1a"
            strokeWidth="0.5"
            fill="none"
            strokeLinecap="round"
            opacity="0.55"
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
