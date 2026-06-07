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
