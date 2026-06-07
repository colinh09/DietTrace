"use client";

// The right rail beside the day's logging: an autonomous agent-activity feed (the
// supervisor's per-meal decisions + re-tune outcomes), with the detailed current
// state — held-out dataset, corrections, learned rules, context — behind a single
// icon (the state modal). The feed + modal both live in LearningObservability.
import { type AgentEvent } from "@/components/agent-decision";
import { LearningObservability } from "@/components/learning-observability";

export function Dashboard({
  reloadSignal,
  agentEvents = [],
  autoRetune = 0,
}: {
  // Bumped by the page whenever a correction/confirmation happens, so the
  // panel refetches and stays in sync (persisting across navigation).
  reloadSignal: number;
  // The supervisor's per-meal decisions, newest first (the activity feed).
  agentEvents?: AgentEvent[];
  // Bumped when the supervisor decides "retune", so the panel auto-runs it.
  autoRetune?: number;
}) {
  return (
    <aside className="dash" aria-label="Agent observability">
      <LearningObservability
        reloadSignal={reloadSignal}
        autoRetune={autoRetune}
        agentEvents={agentEvents}
      />
    </aside>
  );
}
