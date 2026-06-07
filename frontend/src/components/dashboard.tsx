"use client";

// The observability dashboard — the right rail beside the day's logging. It makes
// DietTrace's self-supervision loop visible AT ALL TIMES (not behind a modal): the
// gated re-tune streaming live, the corrections you've taught, the held-out
// dataset it's scored against, and the latest meal's agent trace.
import { AgentFeed, type AgentEvent } from "@/components/agent-decision";
import { LearningObservability } from "@/components/learning-observability";
import { StepGlyph } from "@/components/meal-trace";
import type { TraceStep } from "@/lib/api";

export interface LatestTrace {
  text: string;
  steps: TraceStep[];
}

function LatestTraceCard({ trace }: { trace: LatestTrace }) {
  return (
    <section className="dash-card">
      <div className="dash-card-head mono">latest trace</div>
      <div className="dash-trace-meal">{trace.text}</div>
      <div className="dash-trace-flow">
        {trace.steps.map((s, i) => (
          <span className="dash-trace-step" key={`${s.step}-${i}`}>
            <span className="dash-trace-glyph">
              <StepGlyph step={s.step} />
            </span>
            <span className="dash-trace-fn mono">{s.step}</span>
          </span>
        ))}
      </div>
    </section>
  );
}

export function Dashboard({
  reloadSignal,
  latestTrace,
  agentEvents = [],
  autoRetune = 0,
}: {
  // Bumped by the page whenever a correction/confirmation happens, so the
  // learning panel refetches and stays in sync (persisting across navigation).
  reloadSignal: number;
  latestTrace: LatestTrace | null;
  // The supervisor's per-meal decisions, newest first (the agent feed).
  agentEvents?: AgentEvent[];
  // Bumped when the supervisor decides "retune", so the panel auto-runs it.
  autoRetune?: number;
}) {
  return (
    <aside className="dash" aria-label="Observability dashboard">
      <div className="dash-head">
        <span className="dash-title mono">agent observability</span>
      </div>

      <AgentFeed events={agentEvents} />

      <LearningObservability reloadSignal={reloadSignal} autoRetune={autoRetune} />

      {latestTrace && latestTrace.steps.length > 0 && (
        <LatestTraceCard trace={latestTrace} />
      )}
    </aside>
  );
}
