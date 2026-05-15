import { Header } from "../../components/Header";
import { Footer } from "../../components/Footer";

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Header />
      <main className="min-h-[60vh] bg-surface">
        <div className="mx-auto max-w-7xl px-6 py-12 md:py-16">
          {children}
        </div>
      </main>
      <Footer />
    </>
  );
}
