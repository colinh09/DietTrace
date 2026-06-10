// An animated "trace" motif — a dashed accent line that draws itself, with node
// dots that fade in along it (staggered). Used by the welcome head as a small
// flourish that echoes the agent-step timeline motif used elsewhere in the app.
// Honours prefers-reduced-motion (CSS freezes it to the finished state).
import type { JSX } from "react";

interface TraceMotifProps {
  // SVG width in px (height is fixed at 30).
  w?: number;
  // Node positions along the line, 0..1. The last one renders filled.
  nodes?: number[];
  // Total draw duration in seconds (drives the node stagger).
  dur?: number;
}

export function TraceMotif({
  w = 132,
  nodes = [0, 0.5, 1],
  dur = 1.8,
}: TraceMotifProps): JSX.Element {
  const h = 30;
  const y = h / 2;
  const padX = 7;
  const x = (t: number) => padX + t * (w - padX * 2);
  return (
    <svg
      className="ob-trace"
      viewBox={`0 0 ${w} ${h}`}
      width={w}
      height={h}
      aria-hidden="true"
    >
      <line className="ln" x1={x(0)} y1={y} x2={x(1)} y2={y} />
      {nodes.map((t, i) => (
        <circle
          key={i}
          className={"nd" + (i === nodes.length - 1 ? " f" : "")}
          cx={x(t)}
          cy={y}
          r={i === nodes.length - 1 ? 5 : 4}
          style={{ animationDelay: `${0.5 + t * (dur * 0.7)}s` }}
        />
      ))}
    </svg>
  );
}
