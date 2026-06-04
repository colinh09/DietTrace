"use client";

// The /trust route — still works for deep links, but the same content also
// appears as a popup over the main page (ObservabilityModal). Body lives in
// TrustView; this just adds the page chrome + the fetch. Read from GET /trust.
import { useEffect, useState } from "react";
import Link from "next/link";
import { ChevronLeft, Sparkle } from "lucide-react";
import { TrustView } from "@/components/trust-view";
import { getTrust, type TrustReport } from "@/lib/api";

export default function TrustPage() {
  const [report, setReport] = useState<TrustReport | null>(null);

  useEffect(() => {
    getTrust()
      .then(setReport)
      .catch(() => {});
  }, []);

  return (
    <div className="page">
      <main className="wrap">
        <header className="hdr">
          <Link href="/" className="back-link mono">
            <ChevronLeft size={16} /> today
          </Link>
          <div className="brand">
            <Sparkle size={15} fill="var(--accent)" color="var(--accent)" />
            <span className="brand-name">trust</span>
            <Link href="/accuracy" className="hdr-link mono">
              accuracy
            </Link>
          </div>
        </header>
        {report && <TrustView report={report} />}
      </main>
    </div>
  );
}
