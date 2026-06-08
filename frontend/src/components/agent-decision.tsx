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

// Which time-group an event belongs to (newest-first events keep their order
// within a group). The page stamps `when` as "now" / "yesterday" on each event.
const GROUP_ORDER = ["Now", "Earlier", "Yesterday"] as const;
function groupOf(when?: string): (typeof GROUP_ORDER)[number] {
  if (when === "now") return "Now";
  if (when === "yesterday") return "Yesterday";
  return "Earlier";
}

// The agent-observability feed: the supervisor's decisions as a vertical TRACE
// TIMELINE (the dotted-spine motif), grouped Now / Earlier / Yesterday. Phoenix
// MCP round-trips render as first-class nodes — a blue "Arize Phoenix" tag + a
// code line — so the partner integration is visibly load-bearing, not prose.
export function AgentFeed({
  events,
  running = false,
}: {
  events: AgentEvent[];
  // True while a re-tune is streaming — shows a live "re-tuning…" node on top.
  running?: boolean;
}) {
  if (events.length === 0 && !running) return null;
  const groups: Partial<Record<(typeof GROUP_ORDER)[number], AgentEvent[]>> = {};
  for (const e of events) (groups[groupOf(e.when)] ||= []).push(e);

  return (
    <div className="rail-events" aria-label="Agent activity">
      {running && (
        <div className="revent">
          <span className="revent-dot accent" aria-hidden="true" style={{ color: "var(--accent)" }}>
            <RefreshCw size={11} className="revent-ic" />
          </span>
          <div className="revent-head">
            <span className="revent-label">Re-tuning…</span>
          </div>
          <div className="revent-reason">running the gated eval in Phoenix</div>
        </div>
      )}
      {GROUP_ORDER.map((g) =>
        groups[g] ? (
          <div className="rail-group" key={g}>
            <div className="rail-group-lab">{g}</div>
            {groups[g]!.map((e) => {
              const isPhoenix = Boolean(e.phoenix);
              return (
                <div className="revent" key={e.id} data-op={e.op}>
                  <span
                    className={"revent-dot " + (isPhoenix ? "phoenix" : "accent")}
                    aria-hidden="true"
                    style={{ color: isPhoenix ? "var(--macro-carb)" : "var(--accent)" }}
                  >
                    <OpIcon op={e.op} />
                  </span>
                  <div className="revent-head">
                    <span className="revent-label">{LABELS[e.op]}</span>
                    {e.when && <span className="revent-time">{e.when}</span>}
                  </div>
                  {e.mealText && <div className="revent-meal">{e.mealText}</div>}
                  <div className="revent-reason">{e.reason}</div>
                  {e.detail && <div className="revent-reason mono">{e.detail}</div>}
                  {e.phoenix && (
                    <div className="phoenix-line">
                      <span className="phoenix-tag">
                        <span className="pdot" /> Arize Phoenix
                      </span>
                      <span className="phoenix-code">{e.phoenix}</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : null,
      )}
    </div>
  );
}
