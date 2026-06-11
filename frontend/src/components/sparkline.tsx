// A compact 7-day trend sparkline: an area+line of daily calorie totals with a
// dashed target reference and a dot on the latest day. Pure SVG, no deps; the
// caller supplies the data, so it stays a dumb chart for the day summary's
// "glance zone". Stretched to its box via preserveAspectRatio="none".
export function Sparkline({
  data,
  target,
  label = "7-day trend",
  width = 168,
  height = 38,
}: {
  data: number[];
  // The daily target, drawn as a dashed reference line when given.
  target?: number;
  label?: string;
  width?: number;
  height?: number;
}) {
  // Self-defense: an empty series would make Math.max(...[]) → -Infinity and a
  // NaN path. Callers already guard, but never render a broken chart.
  if (!data || data.length === 0) return null;

  const refs = target != null ? [...data, target] : data;
  const max = Math.max(...refs) * 1.08;
  const min = Math.min(...data) * 0.85;
  const span = max - min || 1;
  const x = (i: number) => (data.length <= 1 ? 0 : (i / (data.length - 1)) * width);
  const y = (v: number) => height - ((v - min) / span) * height;

  const line = data
    .map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`)
    .join(" ");
  const area = `${line} L${width},${height} L0,${height} Z`;
  const lastX = x(data.length - 1);
  const lastY = y(data[data.length - 1]);

  return (
    <svg
      className="dm-spark-svg"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={`${label} of daily calories`}
    >
      <defs>
        <linearGradient id="dm-sparkg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="var(--macro-cal)" stopOpacity="0.18" />
          <stop offset="1" stopColor="var(--macro-cal)" stopOpacity="0" />
        </linearGradient>
      </defs>
      {target != null && (
        <line
          x1="0"
          y1={y(target)}
          x2={width}
          y2={y(target)}
          stroke="var(--line-strong)"
          strokeWidth="1"
          strokeDasharray="3 3"
        />
      )}
      <path d={area} fill="url(#dm-sparkg)" />
      <path
        d={line}
        fill="none"
        stroke="var(--macro-cal)"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={lastX} cy={lastY} r="3" fill="var(--macro-cal)" stroke="var(--surface)" strokeWidth="1.5" />
    </svg>
  );
}
