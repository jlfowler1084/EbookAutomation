import { type Metadata } from "next";
import Link from "next/link";
import ConversionStatus from "../../../components/ConversionStatus";

interface Props {
  params: Promise<{ id: string }>;
}

export const metadata: Metadata = {
  title: "Conversion Status — EbookAutomation",
};

export default async function StatusPage({ params }: Props) {
  const { id } = await params;

  return (
    <main
      style={{
        maxWidth: 640,
        margin: "60px auto",
        padding: "0 20px",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 8 }}>
        Conversion Status
      </h1>
      <p style={{ color: "#555", marginBottom: 32 }}>Job ID: {id}</p>

      <ConversionStatus jobId={id} />

      <p style={{ marginTop: 32 }}>
        <Link href="/" style={{ color: "#0070f3", textDecoration: "none" }}>
          ← Convert another file
        </Link>
      </p>
    </main>
  );
}
