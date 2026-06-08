import type { AgentEvent } from "@/components/agent-decision";

// What a feedback row shows until a retune consumes it (set in meal-review +
// demo_seed). On a shipped retune we relabel it to name the retune that used it.
export const PENDING_FEEDBACK = "To be used to refine your DietTrace agent!";

// Fold a finished retune into the persisted activity feed: prepend its event, and
// — ONLY if it shipped — relabel every still-pending feedback row to the retune
// (version) number that just consumed it. A retune the gate rejected ships nothing,
// so its feedback stays pending. Rows already linked to an earlier retune are left
// alone (their reason no longer matches PENDING_FEEDBACK).
export function foldRetuneIntoFeed(
  cur: AgentEvent[],
  event: AgentEvent,
  shipped?: boolean,
  retuneNo?: number | null,
): AgentEvent[] {
  const next = [event, ...cur];
  if (!shipped || !retuneNo) return next.slice(0, 30);
  return next
    .map((e) =>
      e.op === "bank_feedback" && e.reason === PENDING_FEEDBACK
        ? {
            ...e,
            reason: `Used to refine your DietTrace agent in retune ${retuneNo}`,
          }
        : e,
    )
    .slice(0, 30);
}
