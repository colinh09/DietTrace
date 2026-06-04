"use client";

// The /accuracy route — still works for deep links, but the same content also
// appears as a popup over the main page (ObservabilityModal). Body lives in
// AccuracyView; this just adds the page chrome + the fetch. Read from GET /accuracy.
import { useEffect, useState } from "react";
import Link from "next/link";
import { ChevronLeft, Sparkle } from "lucide-react";
import { AccuracyView } from "@/components/accuracy-view";
import { getAccuracy, type AccuracyReport } from "@/lib/api";

export default function AccuracyPage() {
  const [report, setReport] = useState<AccuracyReport | null>(null);

  useEffect(() => {
    getAccuracy()
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
            <span className="brand-name">accuracy</span>
            <Link href="/trust" className="hdr-link mono">
              trust
            </Link>
          </div>
        </header>
        {report && <AccuracyView report={report} />}
      </main>
    </div>
  );
}
