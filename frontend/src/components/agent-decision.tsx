"use client";

// A compact "agent observability" line: the supervisor's per-meal decision —
// what the autonomous supervisor chose to do (bank feedback / add a held-out
// dataset point / retune) and why. Surfaces the decision the backend returns on
// /log so the agent's own actions are visible, not hidden. Renders nothing when
// no decision is present (e.g. a recalled meal).
import { Fragment, useEffect, useState } from "react";
import { Database, MessageSquare, RefreshCw } from "lucide-react";
import type { SupervisorDecision } from "@/lib/api";

const LABELS: Record<SupervisorDecision["op"], string> = {
  bank_feedback: "Saved your feedback",
  add_dataset_point: "Added to your dataset",
  retune: "Updated",
};

function OpIcon({ op }: { op: SupervisorDecision["op"] }) {
  if (op === "bank_feedback") return <MessageSquare size={13} />;
  if (op === "retune") return <RefreshCw size={13} />;
  return <Database size={13} />;
}

export function AgentDecision({ decision }: { decision?: SupervisorDecision }) {
  if (!decision) return null;
  return (
    <div className="agent-decision" role="status" data-op={decision.op}>
      <span className="agent-decision-icon" aria-hidden="true">
        <OpIcon op={decision.op} />
      </span>
      <span className="agent-decision-label">{LABELS[decision.op]}</span>
      <span className="agent-decision-reason">{decision.reason}</span>
    </div>
  );
}

// One per-meal row of a finished experiment, carried on a retune event so the
// results survive a reload (the feed is persisted; ephemeral state is not).
export interface ExperimentRow {
  set: "fit" | "usda";
  text: string;
  before: number | null;
  after: number | null;
  expected?: number;
  baseKcal?: number | null;
  tunedKcal?: number | null;
}

// One decision the supervisor made. Per-meal ops carry the meal; a re-tune event
// carries a `detail` (e.g. "fit 49→79%") instead. `when` is a short timing label.
export interface AgentEvent extends SupervisorDecision {
  id: number | string;
  mealText?: string;
  detail?: string;
  // Epoch ms the action happened — drives ticking relative time + grouping.
  // Absent on older persisted events, which fall back to the `when` label.
  ts?: number;
  when?: string;
  // The finished experiment's per-meal rows + Arize URL, attached to a retune
  // event so "See your experiment results" survives a reload (persisted with the
  // feed). See memory: diettrace-ui-must-persist-on-reload.
  experiment?: { rows: ExperimentRow[]; experimentUrl?: string };
  // For a retune (Updated) event: the before→after calorie-estimate accuracy on
  // BOTH sets, so the feed shows a clear "Accuracy recap" (Your Dataset + USDA)
  // instead of one raw number. `shipped` distinguishes an applied update from a
  // rejected one. Fractions 0–1.
  recap?: {
    shipped: boolean;
    fitBefore: number;
    fitAfter: number;
    usdaBefore: number;
    usdaAfter: number;
  };
}

// A callback to push a new activity into the feed (the id + timing are stamped by
// the page) — fired when the user confirms a meal or gives feedback, so the feed
// updates live on every action.
export type AgentActivity = (e: {
  op: AgentEvent["op"];
  reason: string;
  mealText?: string;
  // The Phoenix-MCP detail so the feed can render the Arize node.
  phoenix?: string | null;
}) => void;

const GROUP_ORDER = ["Now", "Earlier", "Yesterday"] as const;
type Group = (typeof GROUP_ORDER)[number];

// A ticking, human relative time — "just now", "4m ago", "2h ago", "yesterday".
function relTime(ts: number, now: number): string {
  const s = Math.max(0, Math.round((now - ts) / 1000));
  if (s < 45) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  return "yesterday";
}

// Group an event by recency: Now (<1h) / Earlier (today) / Yesterday (older).
// Falls back to the static `when` label for older events with no timestamp.
function groupOf(e: AgentEvent, now: number): Group {
  if (e.ts == null) {
    if (e.when === "yesterday") return "Yesterday";
    if (e.when === "now") return "Now";
    return "Earlier";
  }
  if (now - e.ts < 60 * 60 * 1000) return "Now";
  const midnight = new Date(now);
  midnight.setHours(0, 0, 0, 0);
  return e.ts >= midnight.getTime() ? "Earlier" : "Yesterday";
}

// A fraction (0–1) as a whole percent; "—" when missing.
function fmtPct(v: number | null | undefined): string {
  return v == null ? "—" : `${Math.round(v * 100)}%`;
}

// The feed headline. A retune reads as a full sentence keyed off whether the
// update actually shipped, instead of the bare "Updated".
function headlineOf(e: AgentEvent): string {
  if (e.op === "retune" && e.recap) {
    return e.recap.shipped
      ? "Your dataset has been updated"
      : "No update — accuracy didn't improve";
  }
  return LABELS[e.op];
}

// The before→after "Accuracy recap" under a retune event — Your Dataset (should
// improve) and USDA / everyday (must hold its floor), with a one-line gloss on
// what the percentage actually measures.
function RetuneRecap({ recap }: { recap: NonNullable<AgentEvent["recap"]> }) {
  const fitUp = recap.fitAfter > recap.fitBefore;
  const usdaHeld = recap.usdaAfter >= recap.usdaBefore - 0.05;
  return (
    <div className="retune-recap">
      <div className="rr-title">Accuracy recap</div>
      <div className="rr-item">
        <div className="rr-row">
          <span className="rr-set">Your dataset</span>
          <span className="rr-delta tnum">
            {fmtPct(recap.fitBefore)} <span className="rr-arrow">→</span>{" "}
            <b className={fitUp ? "up" : ""}>{fmtPct(recap.fitAfter)}</b>
          </span>
        </div>
        <div className="rr-sub">
          {fitUp
            ? "More accurately estimated calories for the foods you've logged."
            : "No change to how it estimates the foods you've logged."}
        </div>
      </div>
      <div className="rr-item">
        <div className="rr-row">
          <span className="rr-set">USDA</span>
          <span className="rr-delta tnum">
            {fmtPct(recap.usdaBefore)} <span className="rr-arrow">→</span>{" "}
            <b>{fmtPct(recap.usdaAfter)}</b>
          </span>
        </div>
        <div className="rr-sub">
          {usdaHeld
            ? "Stayed accurate on standard foods — didn't drop below the floor."
            : "Dropped below the floor on standard foods."}
        </div>
      </div>
    </div>
  );
}

// The agent-observability feed: the supervisor's decisions as a vertical TRACE
// TIMELINE (the dotted-spine motif), grouped Now / Earlier / Yesterday. Phoenix
// MCP round-trips render as first-class nodes — a blue "Arize Phoenix" tag + a
// code line — so the partner integration is visibly load-bearing, not prose.
export function AgentFeed({
  events,
  running = false,
  retuneDetail,
}: {
  events: AgentEvent[];
  // True while a re-tune is streaming — shows a live "thinking" node on top.
  running?: boolean;
  // The finished experiment's per-meal results, rendered collapsibly UNDER the most
  // recent "Updated" event — so it reads as that update's detail, not a page footer.
  retuneDetail?: React.ReactNode;
}) {
  // A ticking clock so relative times ("4m ago") stay honest without a reload.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(t);
  }, []);

  if (events.length === 0 && !running) return null;
  const groups: Partial<Record<Group, AgentEvent[]>> = {};
  for (const e of events) (groups[groupOf(e, now)] ||= []).push(e);
  // Attach the experiment-results detail to the most recent "Updated" event.
  const firstRetuneId = events.find((e) => e.op === "retune")?.id;

  return (
    <div className="rail-events" aria-label="Agent activity">
      {running && (
        <div className="revent revent-thinking revent-shimmer">
          <span className="revent-dot accent" aria-hidden="true" style={{ color: "var(--accent)" }}>
            <RefreshCw size={11} className="revent-ic" />
          </span>
          <div className="revent-head">
            <span className="revent-label">Thinking…</span>
          </div>
          <div className="revent-reason">checking a new rule against your meals in Phoenix</div>
        </div>
      )}
      {GROUP_ORDER.map((g) =>
        groups[g] ? (
          <div className="rail-group" key={g}>
            <div className="rail-group-lab">{g}</div>
            {groups[g]!.map((e) => {
              const isPhoenix = Boolean(e.phoenix);
              return (
                <Fragment key={e.id}>
                  <div className="revent" data-op={e.op}>
                    <span
                      className={"revent-dot " + (isPhoenix ? "phoenix" : "accent")}
                      aria-hidden="true"
                      style={{ color: isPhoenix ? "var(--macro-carb)" : "var(--accent)" }}
                    >
                      <OpIcon op={e.op} />
                    </span>
                    <div className="revent-head">
                      <span className="revent-label">{headlineOf(e)}</span>
                      {(e.ts != null || e.when) && (
                        <span className="revent-time">
                          {e.ts != null ? relTime(e.ts, now) : e.when}
                        </span>
                      )}
                    </div>
                    {e.mealText && <div className="revent-meal">{e.mealText}</div>}
                    {e.op === "retune" && e.recap && e.reason && (
                      <div className="revent-section">Agent recap</div>
                    )}
                    {e.reason && <div className="revent-reason">{e.reason}</div>}
                    {e.op === "retune" && e.recap && <RetuneRecap recap={e.recap} />}
                    {e.detail && <div className="revent-reason mono">{e.detail}</div>}
                    {e.phoenix && e.op !== "retune" && (
                      <div className="phoenix-line">
                        <span className="phoenix-tag">
                          <span className="pdot" /> Arize Phoenix
                        </span>
                        <span className="phoenix-code">{e.phoenix}</span>
                      </div>
                    )}
                  </div>
                  {retuneDetail && e.id === firstRetuneId && (
                    <div className="revent-detail">{retuneDetail}</div>
                  )}
                </Fragment>
              );
            })}
          </div>
        ) : null,
      )}
    </div>
  );
}
