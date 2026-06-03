import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

// The 9.8 responsive contract lives in globals.css: a centered ~900px column on
// desktop, tightening to ~full-width on mobile. jsdom can't
// resolve media queries, so we assert the stylesheet encodes the contract.
const css = readFileSync(
  path.resolve(path.dirname(fileURLToPath(import.meta.url)), "globals.css"),
  "utf8",
);

describe("globals.css responsive layout", () => {
  it("centers the desktop column at ~900px", () => {
    const wrap = css.match(/\.wrap\s*\{([^}]*)\}/);
    expect(wrap).not.toBeNull();
    const body = wrap![1];

    const maxWidth = body.match(/max-width:\s*(\d+)px/);
    expect(maxWidth).not.toBeNull();
    const px = Number(maxWidth![1]);
    expect(px).toBeGreaterThanOrEqual(820);
    expect(px).toBeLessThanOrEqual(960);

    // centered, and the column itself spans its container so the padding (not a
    // narrow column) is what governs width on small screens.
    expect(body).toMatch(/margin:\s*0 auto/);
    expect(body).toMatch(/width:\s*100%/);
  });

  it("runs ~full-width on mobile by tightening the page padding", () => {
    expect(css).toMatch(/@media\s*\(max-width:\s*640px\)/);

    // The base `.page` horizontal padding floors at a generous 24px (the min of
    // a clamp that grows on wide screens), and at least one mobile override drops
    // it to <=16px so content runs essentially edge-to-edge.
    const baseClamp = css.match(/\.page\s*\{[^}]*padding:[^;]*clamp\(\s*(\d+)px/);
    expect(baseClamp).not.toBeNull();
    expect(Number(baseClamp![1])).toBe(24);

    const mobilePads = [
      ...css.matchAll(/\.page\s*\{[^}]*padding:\s*\d+px\s+(\d+)px/g),
    ].map((m) => Number(m[1]));
    expect(Math.min(...mobilePads)).toBeLessThanOrEqual(16);
  });
});
