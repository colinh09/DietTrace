"use client";

// "What you've taught" — a small panel listing the portion corrections this user
// has made (food · before → after grams). It makes the self-supervision loop
// visible in-app: every fix here became real ground truth the next eval scores
// against. Renders nothing until there's a
// correction, so a fresh user's view stays uncluttered.
import type { RecentCorrection } from "@/lib/api";

export function TaughtPanel({
  corrections,
}: {
  corrections: RecentCorrection[];
}) {
  if (!corrections.length) return null;
  return (
    <section className="taught" aria-label="What you've taught">
      <h2 className="taught-title">What you&apos;ve taught</h2>
      <ul className="taught-list">
        {corrections.map((c) => (
          <li key={`${c.created_at}-${c.food}`} className="taught-row">
            <span className="taught-food">{c.food}</span>
            <span className="taught-grams">
              {Math.round(c.original_grams)} g <span aria-hidden="true">→</span>{" "}
              {Math.round(c.corrected_grams)} g
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
