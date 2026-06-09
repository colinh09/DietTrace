"use client";

// The "Accuracy" modal — two tabs over one popup:
//   • Accuracy      — DietTrace's measured accuracy report: the headline eval
//     numbers, the before→after bars, the accuracy-over-time trend, and the
//     self-supervision loop. Cached at module scope: the first open fetches (with
//     a skeleton), later opens show cached data instantly and refresh in the
//     background.
//   • How it works  — a plain-language written guide to each part of the app, with
//     a button to launch the proactive step-through tour.
import { useEffect, useState } from "react";
import { AccuracyView } from "@/components/accuracy-view";
import { Modal } from "@/components/modal";
import { getAccuracy, type AccuracyReport } from "@/lib/api";

let accCache: AccuracyReport | null = null;

function Skeleton() {
  return (
    <div className="obs-skel" aria-busy="true" aria-label="loading">
      <div className="obs-skel-title" />
      <div className="obs-skel-row" />
      <div className="obs-skel-stats">
        <div className="obs-skel-stat" />
        <div className="obs-skel-stat" />
        <div className="obs-skel-stat" />
      </div>
      <div className="obs-skel-block" />
    </div>
  );
}

export function OverviewModal({ onClose }: { onClose: () => void }) {
  const [acc, setAcc] = useState<AccuracyReport | null>(accCache);

  useEffect(() => {
    getAccuracy()
      .then((r) => {
        accCache = r;
        setAcc(r);
      })
      .catch(() => {});
  }, []);

  return (
    <Modal onClose={onClose} labelledBy="overview-title">
      <div className="ov">
        <header className="ov-head">
          <span className="ov-eyebrow mono">Accuracy</span>
          <h1 id="overview-title" className="ov-title">
            An AI nutritionist graded on accuracy
          </h1>
          <p className="ov-sub">
            DietTrace grades its own work on every meal against USDA data and learns
            how <i>you</i> eat — tested so personalizing never makes it less accurate.
          </p>
          <p className="ov-source">
            Every percentage below is scored against known USDA calories as a Phoenix
            experiment — measured, not claimed.
          </p>
        </header>
        <section className="ov-section">
          {acc ? <AccuracyView report={acc} /> : <Skeleton />}
        </section>
      </div>
    </Modal>
  );
}
