"use client";

// A small hover/focus text tooltip — the calm, readable replacement for native
// `title=` strings — no giant native title attributes. Wraps
// any element and shows a styled bubble on hover/keyboard focus. For richer
// disclosures (the confidence chip's four checks) use ConfidenceTooltip instead.
export function Tooltip({
  label,
  children,
}: {
  // The plain-language hint. Keep it clear and say what the thing IS / does.
  label: string;
  // The anchor element the tooltip describes.
  children: React.ReactNode;
}) {
  // The bubble is a sighted-hover hint and is aria-hidden: the anchor it wraps
  // already carries the meaning (visible chip text, or the button's aria-label),
  // so exposing the bubble too would double-announce and leak into ancestor
  // names. Richer, screen-reader-exposed disclosures use ConfidenceTooltip.
  return (
    <span className="utip-anchor">
      {children}
      <span className="utip" aria-hidden="true">
        {label}
      </span>
    </span>
  );
}
