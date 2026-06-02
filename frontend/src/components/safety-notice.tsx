"use client";

// A calm, supportive notice surfaced when a logged input trips the rule-based
// safety guardrail. It never blocks the log — the meal is
// still recorded — it just sits above the day's meals with a non-judgmental
// message pointing toward support. An all-clear (or absent) result renders
// nothing, so ordinary meals are visually unaffected.
import { Heart } from "lucide-react";
import type { Safety } from "@/lib/api";

export function SafetyNotice({ safety }: { safety?: Safety }) {
  if (!safety?.flagged) return null;
  return (
    <aside className="safety-notice" role="note">
      <span className="safety-notice-icon" aria-hidden="true">
        <Heart size={14} />
      </span>
      <p className="safety-notice-msg">{safety.message}</p>
    </aside>
  );
}
