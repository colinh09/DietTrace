"use client";

// The /accuracy route — still works for deep links, but the same content also
// appears as a popup over the main page (ObservabilityModal). Body lives in
// AccuracyView; this just adds the page chrome + the fetch. Read from GET /accuracy.
import { useEffect, useState } from "react";
import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { AccuracyView } from "@/components/accuracy-view";
import { BrandMark } from "@/components/brand-mark";
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
            <BrandMark size={18} />
            <span className="brand-name">accuracy</span>
            <Link href="/trust" className="hdr-link mono">
              trust
            </Link>
          </div>
        </header>
        <header className="ov-head">
          <span className="ov-eyebrow mono">Accuracy</span>
          <h1 className="ov-title">An AI nutritionist, graded on accuracy</h1>
          <p className="ov-sub">
            DietTrace reads plain-English meals against USDA data and learns how{" "}
            <i>you</i> eat — and every change is scored against known calories before
            it ships. Measured, not claimed.
          </p>
        </header>
        {report && <AccuracyView report={report} />}
      </main>
    </div>
  );
}
