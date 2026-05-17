import { type Metadata } from "next";
import Link from "next/link";
import ConversionStatus from "../../../../components/ConversionStatus";

interface Props {
  params: Promise<{ id: string }>;
}

export const metadata: Metadata = {
  title: "Conversion Status — Leafbind",
  robots: { index: false, follow: false },
};

export default async function StatusPage({ params }: Props) {
  const { id } = await params;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-serif text-3xl text-text-base">Converting your file</h1>
        <p className="mt-2 text-sm text-text-muted break-words">Job ID: {id}</p>
      </div>

      <div className="rounded-md border border-border bg-surface-muted p-6 min-w-0">
        <ConversionStatus jobId={id} />
      </div>

      <p>
        <Link
          href="/"
          className="text-brand hover:text-brand-dark text-sm"
        >
          ← Convert another file
        </Link>
      </p>

      <p className="text-xs text-text-muted">
        Having trouble?{" "}
        <Link href="/contact" className="text-brand hover:underline">
          Contact support
        </Link>{" "}
        or email{" "}
        <a href="mailto:support@leafbind.io" className="text-brand hover:underline">
          support@leafbind.io
        </a>
        .
      </p>
    </div>
  );
}
