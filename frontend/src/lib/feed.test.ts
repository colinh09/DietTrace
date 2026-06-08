import { describe, expect, it } from "vitest";
import { foldRetuneIntoFeed, PENDING_FEEDBACK } from "@/lib/feed";
import type { AgentEvent } from "@/components/agent-decision";

const fb = (id: string, reason = PENDING_FEEDBACK): AgentEvent => ({
  id,
  op: "bank_feedback",
  reason,
  mealText: "oatmeal before my run",
});
const retune = (): AgentEvent => ({
  id: "r1",
  op: "retune",
  reason: "a new rule is now in effect",
});

describe("foldRetuneIntoFeed", () => {
  it("prepends the retune and flips pending feedback to the shipped retune number", () => {
    const out = foldRetuneIntoFeed([fb("f1"), fb("f2")], retune(), true, 3);
    expect(out[0].op).toBe("retune");
    expect(out[1].reason).toBe("Used to refine your DietTrace agent in retune 3");
    expect(out[2].reason).toBe("Used to refine your DietTrace agent in retune 3");
  });

  it("leaves feedback pending when the retune did not ship (gate rejected it)", () => {
    const out = foldRetuneIntoFeed([fb("f1")], retune(), false, null);
    expect(out.find((e) => e.id === "f1")?.reason).toBe(PENDING_FEEDBACK);
  });

  it("does not re-flip feedback already linked to an earlier retune", () => {
    const already = fb("f1", "Used to refine your DietTrace agent in retune 1");
    const out = foldRetuneIntoFeed([already], retune(), true, 2);
    expect(out.find((e) => e.id === "f1")?.reason).toBe(
      "Used to refine your DietTrace agent in retune 1",
    );
  });

  it("does not touch non-feedback events", () => {
    const dataset: AgentEvent = { id: "d1", op: "add_dataset_point", reason: "" };
    const out = foldRetuneIntoFeed([dataset], retune(), true, 5);
    expect(out.find((e) => e.id === "d1")?.reason).toBe("");
  });
});
