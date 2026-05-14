import type { Metadata } from "next";
import { Suspense } from "react";
import RecoverClient from "../../components/RecoverClient";

export const metadata: Metadata = {
  title: "Recover Tokens — Leafbind",
  description: "Recover your Leafbind premium tokens using your Stripe session ID.",
};

interface Props {
  searchParams: Promise<{ session_id?: string }>;
}

export default async function RecoverPage({ searchParams }: Props) {
  const { session_id } = await searchParams;

  return (
    <main
      style={{
        maxWidth: 720,
        margin: "2em auto",
        padding: "1em",
        fontFamily: "-apple-system, BlinkMacSystemFont, system-ui, sans-serif",
      }}
    >
      <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 8 }}>Recover Tokens</h1>

      <Suspense fallback={<p>Loading&hellip;</p>}>
        <RecoverClient initialSessionId={session_id} />
      </Suspense>
    </main>
  );
}
