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
  retune: "Retuning the prompt",
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

// One decision the supervisor made, tied to the meal that prompted it.
export interface AgentEvent extends SupervisorDecision {
  id: number;
  mealText: string;
}

// The agent-observability feed: the supervisor's per-meal decisions in order
// (newest first), so the agent's autonomous choices are visible as they happen.
export function AgentFeed({ events }: { events: AgentEvent[] }) {
  if (events.length === 0) return null;
  return (
    <section className="dash-card" aria-label="Agent decisions">
      <div className="dash-card-head mono">agent decisions</div>
      <ul className="agent-feed">
        {events.map((e) => (
          <li key={e.id} className="agent-feed-row" data-op={e.op}>
            <span className="agent-feed-icon" aria-hidden="true">
              <OpIcon op={e.op} />
            </span>
            <span className="agent-feed-body">
              <span className="agent-feed-head">
                <span className="agent-feed-label">{LABELS[e.op]}</span>
                <span className="agent-feed-meal">{e.mealText}</span>
              </span>
              <span className="agent-feed-reason">{e.reason}</span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
