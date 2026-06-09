// The DietTrace brand mark — a clean stroked apple, optionally with an "echo
// trail" (three receding ghost copies behind it: depth, not a sideways slide).
// Geometry is the locked "Classic round" apple from the design handoff. Recolor
// via the `stroke` prop (defaults to the sage accent). Use `echo` at >=24px; the
// plain apple reads down to 16px.
import type { JSX } from "react";

interface BrandMarkProps {
  size?: number;
  echo?: boolean;
  stroke?: string;
  strokeWidth?: number;
  className?: string;
  // When set, the mark is announced to screen readers; otherwise it's decorative.
  title?: string;
}

const APPLE: JSX.Element = (
  <>
    <path d="M32 19 C 27 12 18 11 12.5 16 C 6 22 6 32 8 40 C 10.5 50 20 58 32 58 C 44 58 53.5 50 56 40 C 58 32 58 22 51.5 16 C 46 11 37 12 32 19 Z" />
    <path d="M32 19 C 33 13 33.5 11 35 8" />
    <path d="M35.5 9 C 41 4 48 5 48.5 9.5 C 45.5 13.5 39 13.5 35.5 9 Z" />
  </>
);

export function BrandMark({
  size = 24,
  echo = true,
  stroke = "var(--accent)",
  strokeWidth = 5,
  className,
  title,
}: BrandMarkProps): JSX.Element {
  // The echo viewBox is near-square; the plain apple is 64x72, so keep its ratio.
  const viewBox = echo ? "-12 -4 82 80" : "0 0 64 72";
  const width = echo ? size : Math.round((size * 64) / 72);
  return (
    <svg
      width={width}
      height={size}
      viewBox={viewBox}
      fill="none"
      stroke={stroke}
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
    >
      {echo && (
        <>
          <g transform="translate(-8 30) scale(0.45) translate(8 -30)" opacity={0.13}>
            {APPLE}
          </g>
          <g transform="translate(-8 30) scale(0.60) translate(8 -30)" opacity={0.23}>
            {APPLE}
          </g>
          <g transform="translate(-8 30) scale(0.78) translate(8 -30)" opacity={0.36}>
            {APPLE}
          </g>
        </>
      )}
      <g>{APPLE}</g>
    </svg>
  );
}
