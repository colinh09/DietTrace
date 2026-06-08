"use client";

// The "Overview" page — one place that explains the project and stacks the two
// observability reports (Accuracy, then Trust) instead of splitting them across
// two nav tabs. Reports are cached at module scope: the first open fetches (with
// a skeleton), later opens show cached data instantly and refresh in background.
import { useEffect, useState } from "react";
import { AccuracyView } from "@/components/accuracy-view";
import { TrustView } from "@/components/trust-view";
import { Modal } from "@/components/modal";
import {
  getAccuracy,
  getTrust,
  listLearningFeedback,
  type AccuracyReport,
  type FeedbackItem,
  type TrustReport,
} from "@/lib/api";

let accCache: AccuracyReport | null = null;
let trustCache: TrustReport | null = null;
let corrCache: FeedbackItem[] | null = null;

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
  const [trust, setTrust] = useState<TrustReport | null>(trustCache);
  const [corrections, setCorrections] = useState<FeedbackItem[]>(corrCache ?? []);

  useEffect(() => {
    getAccuracy()
      .then((r) => {
        accCache = r;
        setAcc(r);
      })
      .catch(() => {});
    getTrust()
      .then((r) => {
        trustCache = r;
        setTrust(r);
      })
      .catch(() => {});
    listLearningFeedback()
      .then((r) => {
        corrCache = r.feedback;
        setCorrections(r.feedback);
      })
      .catch(() => {});
  }, []);

  return (
    <Modal onClose={onClose} labelledBy="overview-title">
      <div className="ov">
        <header className="ov-head">
          <span className="ov-eyebrow mono">Overview</span>
          <h1 id="overview-title" className="ov-title">
            An AI nutritionist graded on accuracy
          </h1>
          <p className="ov-sub">
            DietTrace logs meals from plain English against USDA data, grades its
            own work on every meal, and learns how <i>you</i> eat — and we test
            every change so personalizing for you never makes it less accurate
            overall. Below: how accurate it is, and how much to trust your numbers.
          </p>
        </header>

        <section className="ov-section">
          {acc ? <AccuracyView report={acc} /> : <Skeleton />}
        </section>

        <div className="ov-divider" aria-hidden="true" />

        <section className="ov-section">
          {trust ? (
            <TrustView report={trust} corrections={corrections} />
          ) : (
            <Skeleton />
          )}
        </section>
      </div>
    </Modal>
  );
}
