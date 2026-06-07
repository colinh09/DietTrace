"use client";

// A compact "agent observability" line: the supervisor's per-meal decision —
// what the autonomous supervisor chose to do (bank feedback / add a held-out
// dataset point / retune) and why. Surfaces the decision the backend returns on
// /log so the agent's own actions are visible, not hidden. Renders nothing when
// no decision is present (e.g. a recalled meal).
import { Database, MessageSquare, RefreshCw } from "lucide-react";
import type { SupervisorDecision } from "@/lib/api";

const LABELS: Record<SupervisorDecision["op"], string> = {
  bank_feedback: "Banked your feedback",
  add_dataset_point: "Added to the held-out dataset",
  retune: "Re-tuned",
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

// One decision the supervisor made. Per-meal ops carry the meal; a re-tune event
// carries a `detail` (e.g. "fit 49→79%") instead. `when` is a short timing label.
export interface AgentEvent extends SupervisorDecision {
  id: number | string;
  mealText?: string;
  detail?: string;
  when?: string;
}

// The agent-observability feed: the supervisor's decisions in order (newest
// first), so the agent's autonomous choices read like a log as they happen.
export function AgentFeed({
  events,
  running = false,
}: {
  events: AgentEvent[];
  // True while a re-tune is streaming — shows a live "re-tuning…" row on top.
  running?: boolean;
}) {
  if (events.length === 0 && !running) return null;
  return (
    <ul className="agent-feed" aria-label="Agent activity">
      {running && (
        <li className="agent-feed-row agent-feed-running" data-op="retune">
          <span className="agent-feed-icon" aria-hidden="true">
            <RefreshCw size={13} />
          </span>
          <span className="agent-feed-body">
            <span className="agent-feed-head">
              <span className="agent-feed-label">Re-tuning…</span>
            </span>
            <span className="agent-feed-reason">running the gated eval</span>
          </span>
        </li>
      )}
      {events.map((e) => (
        <li key={e.id} className="agent-feed-row" data-op={e.op}>
          <span className="agent-feed-icon" aria-hidden="true">
            <OpIcon op={e.op} />
          </span>
          <span className="agent-feed-body">
            <span className="agent-feed-head">
              <span className="agent-feed-label">{LABELS[e.op]}</span>
              {e.when && <span className="agent-feed-when">{e.when}</span>}
            </span>
            {e.mealText && <span className="agent-feed-meal">{e.mealText}</span>}
            {e.detail && <span className="agent-feed-detail mono">{e.detail}</span>}
            <span className="agent-feed-reason">{e.reason}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}
