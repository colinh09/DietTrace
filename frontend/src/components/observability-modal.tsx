"use client";

// Accuracy + Trust as a single tabbed popup over the main page (no route change).
// Both reports are cached at module scope: the FIRST open fetches (with a skeleton
// so it never looks frozen — the live Phoenix read is slow); every later open
// shows the cached data instantly and refreshes in the background.
import { useEffect, useState } from "react";
import { AccuracyView } from "@/components/accuracy-view";
import { TrustView } from "@/components/trust-view";
import { Modal } from "@/components/modal";
import { getAccuracy, getTrust, type AccuracyReport, type TrustReport } from "@/lib/api";

export type ObsTab = "accuracy" | "trust";

let accCache: AccuracyReport | null = null;
let trustCache: TrustReport | null = null;

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

export function ObservabilityModal({
  initialTab,
  onClose,
}: {
  initialTab: ObsTab;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<ObsTab>(initialTab);
  const [acc, setAcc] = useState<AccuracyReport | null>(accCache);
  const [trust, setTrust] = useState<TrustReport | null>(trustCache);

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
  }, []);

  return (
    <Modal onClose={onClose} labelledBy="obs-modal-title">
      <div className="obs-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "accuracy"}
          className={"obs-tab mono" + (tab === "accuracy" ? " on" : "")}
          onClick={() => setTab("accuracy")}
        >
          accuracy
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "trust"}
          className={"obs-tab mono" + (tab === "trust" ? " on" : "")}
          onClick={() => setTab("trust")}
        >
          trust
        </button>
      </div>
      <div className="obs-body">
        {tab === "accuracy" ? (
          acc ? <AccuracyView report={acc} /> : <Skeleton />
        ) : trust ? (
          <TrustView report={trust} />
        ) : (
          <Skeleton />
        )}
      </div>
    </Modal>
  );
}
