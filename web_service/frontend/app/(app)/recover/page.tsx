import type { Metadata } from "next";
import { Suspense } from "react";
import RecoverClient from "../../../components/RecoverClient";

export const metadata: Metadata = {
  title: "Recover tokens — leafbind",
  description: "Recover your leafbind premium tokens using your Stripe session ID.",
  robots: { index: false, follow: false },
  alternates: {
    canonical: "/recover",
  },
  openGraph: {
    url: "https://leafbind.io/recover",
  },
};

interface Props {
  searchParams: Promise<{ session_id?: string }>;
}

export default async function RecoverPage({ searchParams }: Props) {
  const { session_id } = await searchParams;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-serif text-3xl text-text-base">Recover Tokens</h1>
        <p className="mt-2 text-text-muted">
          Enter your Stripe session ID to retrieve your premium tokens.
        </p>
      </div>

      <div className="rounded-md border border-border bg-surface-muted p-6 min-w-0">
        <Suspense fallback={<p className="text-text-muted">Loading&hellip;</p>}>
          <RecoverClient initialSessionId={session_id} />
        </Suspense>
      </div>
    </div>
  );
}
