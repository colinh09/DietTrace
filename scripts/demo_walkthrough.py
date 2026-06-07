"""End-to-end demo walkthrough — drives the LIVE backend through the exact
sequence a judge would see in the frontend, and prints a PASS/FAIL checklist.

This is the rehearsal script: run it until the narrative lands reliably, and the
frontend demo becomes a veneer over a path you've already proven. It hits the
real HTTP endpoints (live Gemini + food DB), so the dev server must be running.

    ./run-dev.sh            # in another terminal
    uv run python scripts/demo_walkthrough.py
"""

from __future__ import annotations

import json
import urllib.request

API = "http://localhost:8080"
USER = "demo-walkthrough"
H = {"X-DietTrace-User": USER, "Content-Type": "application/json"}

# The held-out payoff meal: a preworkout carb source NOT in the seeded set, so a
# lift here is generalization, not memorization. And a non-preworkout control.
HELD_OUT_PREWORKOUT = "a stack of pancakes with maple syrup before the gym"
NON_PREWORKOUT = "scrambled eggs and bacon for breakfast"


def call(path: str, method: str = "GET", body: dict | None = None,
         timeout: int = 120) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, headers=H, data=data, method=method)
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def macro(totals: list[dict], code: str) -> float:
    return next((t["amount"] for t in totals if t["code"] == code), 0.0)


def kcal(totals):
    return macro(totals, "208")


def carbs(totals):
    return macro(totals, "205")


RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str = "") -> None:
    RESULTS.append((name, passed, detail))
    mark = "PASS" if passed else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))


def main() -> None:
    print("═" * 70)
    print("DietTrace — demo walkthrough (live)")
    print("═" * 70)

    # ── Setup ────────────────────────────────────────────────────────────────
    call("/session/reset", "POST", {})
    seed = call("/demo/seed", "POST", {"date": "2026-06-06"})
    print(f"\nSeeded: {seed['meals']} meals · {seed['confirmations']} confirmations "
          f"· {seed['corrections']} corrections\n")

    # ── C1/C2 — honest logging + self-grading ────────────────────────────────
    print("BEAT 1 — the agent logs honestly and grades itself")
    hist = call("/history?date=2026-06-06")["meals"]
    pb = next((m for m in hist if "peanut butter" in m["text"].lower()), None)
    check("C1 clean meals logged with macros", len(hist) == 4,
          f"{len(hist)} meals on the day")
    check("C2 over-portioned meal flags itself", bool(pb and pb["needs_review"]),
          f"peanut butter: {kcal(pb['totals']):.0f} kcal, conf {pb['confidence']}, "
          f"needs_review={pb['needs_review']}")

    # ── C3 — correct in plain words ──────────────────────────────────────────
    print("\nBEAT 2 — correct it in plain words")
    before_kcal = kcal(pb["totals"])
    call("/feedback/freeform", "POST", {
        "meal_id": pb["id"], "meal_text": pb["text"],
        "feedback_text": "the peanut butter is way too much, I only use about 30 grams",
        "current_items": pb["per_item"],
    })
    pb2 = next(m for m in call("/history?date=2026-06-06")["meals"]
               if "peanut butter" in m["text"].lower())
    check("C3 correction recomputes + clears the flag",
          kcal(pb2["totals"]) < before_kcal and not pb2["needs_review"],
          f"{before_kcal:.0f} → {kcal(pb2['totals']):.0f} kcal, "
          f"conf {pb['confidence']} → {pb2['confidence']}, flag cleared")

    # ── C4 — confirm + XOR ───────────────────────────────────────────────────
    print("\nBEAT 3 — confirm what's right; correcting removes it (XOR)")
    n0 = call("/preferences")["confirmations"]
    call("/confirm", "POST", {"meal_text": "a banana and a coffee",
                              "items": [], "totals": [{"code": "208", "amount": 110}]})
    n1 = call("/preferences")["confirmations"]
    call("/feedback/freeform", "POST", {
        "meal_id": None, "meal_text": "a banana and a coffee",
        "feedback_text": "actually that banana was bigger", "current_items": []})
    n2 = call("/preferences")["confirmations"]
    check("C4 confirm grows dataset, correct removes it (XOR)",
          n1 == n0 + 1 and n2 == n0,
          f"{n0} → confirm → {n1} → correct → {n2}")

    # ── C6 baseline — log the held-out meals BEFORE learning ─────────────────
    print("\nBEAT 4 — baseline: log new meals before the agent has learned you")
    pre_before = call("/log", "POST", {"text": HELD_OUT_PREWORKOUT, "date": "2026-06-06"})
    ctrl_before = call("/log", "POST", {"text": NON_PREWORKOUT, "date": "2026-06-06"})
    print(f"  preworkout '{HELD_OUT_PREWORKOUT[:40]}': "
          f"{carbs(pre_before['totals']):.0f}g carbs / {kcal(pre_before['totals']):.0f} kcal")
    print(f"  control    '{NON_PREWORKOUT[:40]}': "
          f"{carbs(ctrl_before['totals']):.0f}g carbs / {kcal(ctrl_before['totals']):.0f} kcal")

    # ── C5 — re-tune (the gate) ──────────────────────────────────────────────
    print("\nBEAT 5 — re-tune: the corrector proposes, the gate ships (live, ~1 min)")
    rt = call("/learning/retune", "POST", {}, timeout=400)
    if not rt.get("ok"):
        check("C5 retune ran", False, f"reason={rt.get('reason')}")
        summarise()
        return
    rule = rt["rules"][0]["rule"] if rt.get("rules") else "(none)"
    print(f"  proposed rule: {rule}")
    print(f"  fit  {rt['current']['fit']:.0%} → {rt['proposed']['fit']:.0%}   "
          f"usda {rt['current']['usda']:.0%} → {rt['proposed']['usda']:.0%}")
    check("C5 retune ships (fit up, USDA held)", bool(rt["shipped"]),
          rt["verdict"]["reason"])
    check("C5b learned rule is preworkout-scoped",
          "workout" in rule.lower() or "pre-workout" in rule.lower()
          or "preworkout" in rule.lower(),
          rule)

    # ── C6/C7 — the payoff: generalization on a held-out meal, scoping holds ──
    print("\nBEAT 6 — the payoff: a NEW preworkout meal it's never seen lands right")
    pre_after = call("/log", "POST", {"text": HELD_OUT_PREWORKOUT, "date": "2026-06-06"})
    ctrl_after = call("/log", "POST", {"text": NON_PREWORKOUT, "date": "2026-06-06"})
    pre_lift = carbs(pre_after["totals"]) - carbs(pre_before["totals"])
    ctrl_delta = carbs(ctrl_after["totals"]) - carbs(ctrl_before["totals"])
    print(f"  preworkout carbs: {carbs(pre_before['totals']):.0f}g → "
          f"{carbs(pre_after['totals']):.0f}g  ({pre_lift:+.0f}g)")
    print(f"  control    carbs: {carbs(ctrl_before['totals']):.0f}g → "
          f"{carbs(ctrl_after['totals']):.0f}g  ({ctrl_delta:+.0f}g)")
    check("C6 generalizes to an unseen preworkout meal (carbs up)", pre_lift > 5,
          f"{pre_lift:+.0f}g carbs on a meal not in the dataset")
    check("C7 scoping holds (control roughly unchanged)", abs(ctrl_delta) <= 10,
          f"control moved {ctrl_delta:+.0f}g")

    summarise()


def summarise() -> None:
    print("\n" + "═" * 70)
    passed = sum(1 for _, p, _ in RESULTS if p)
    print(f"RESULT: {passed}/{len(RESULTS)} criteria passed")
    for name, p, _ in RESULTS:
        if not p:
            print(f"   ✗ {name}")
    print("═" * 70)


if __name__ == "__main__":
    main()
