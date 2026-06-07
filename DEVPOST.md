# DietTrace

**Log food in plain English. Get accurate calories and macros — proven by evals, not vibes.**

Built for the [Google Cloud Rapid Agent Hackathon](https://rapid-agent.devpost.com/) — Arize track.

## Problem

Calorie-tracking apps ask you to be a database clerk: search a noisy catalog, pick the
"right" entry from a dozen near-duplicates, and guess a portion. The newer "just describe
your meal to an LLM" apps fix the friction but trade it for a worse problem — they
**hallucinate the numbers**. A language model will happily tell you a chicken breast is
"about 165 calories" with total confidence and no idea whether that's a raw 4 oz cut, a
breaded cutlet, or a deli roll. There's no ground truth, no measurement, and no way to know
when the model quietly gets worse after a prompt tweak. For something people use to make
health decisions, "sounds about right" is not good enough.

## What it does

DietTrace is an AI nutrition **agent**, not a chatbot. You type what you ate —
*"two eggs, half an avocado, slice of toast"* — and the agent plans and acts across a
deliberate tool pipeline:

```
parse_meal → search_nutrition → estimate_portion → log_entry → check_against_goals
```

- **parse_meal** turns free text into a structured list of `{food, quantity, unit}` — the
  one inherently generative step.
- **search_nutrition** does a *deterministic* lookup against a local USDA-derived food DB,
  keyed by nutrient number code (208 kcal, 203 protein, …) and returning the matched
  `fdc_id` so every result is reproducible.
- **estimate_portion** converts quantity + unit to grams using the food's own serving
  sizes, preferring an edible/NLEA serving over an oversized one, and reports its confidence.
- **log_entry** does the macro/micro math (scale per-100g by grams, apply Atwater factors).
- **check_against_goals** compares the day against your targets in a supportive voice.

The hard rule under all of it: **the LLM parses and orchestrates; it never invents a number
a deterministic tool can look up.** Separating *search* from *calculation* is the
single highest-leverage accuracy decision in the project — and it's what makes each stage
independently measurable. The web UI surfaces the agent's actual trace behind every meal, so
you can see which USDA food was matched and how many grams were assumed.

## How it's built

| Layer | Choice |
|---|---|
| LLM | **Gemini 3** (Vertex AI) |
| Agent runtime | **Google ADK** (`Agent` + `Runner` + `InMemorySessionService`) |
| Observability & evals | **Arize Phoenix** (Cloud + **MCP**) |
| Wire format | OpenInference (OTel-native spans) |
| Ground truth | USDA FoodData Central (Foundation + SR Legacy + a branded subset) |
| Demo surface | FastAPI + a Next.js/shadcn web UI on Cloud Run |
| CI | GitHub Actions (ruff + pytest, fully offline) |

The nutrition agent is an ADK `Agent` whose tools are plain `FunctionTool`s — ADK inspects
each signature and docstring to expose them to **Gemini 3**. Every run emits OpenInference
spans through the ADK + GenAI + MCP instrumentors into **Arize Phoenix**, which is the
project's spine: it holds the traces, the eval datasets, and the experiments. An in-memory
span buffer powers the web "reasoning" panel without a Phoenix round-trip, so the trust
feature works even offline.

Evals are deterministic, zero-LLM code evaluators — `calorie_accuracy`, `macro_pct_error`,
`macro_mae`, `within_tolerance` (±15%), `portion_error`, plus fiber/sodium/sugar — scored
against USDA ground truth on two tiers (whole foods on the full micronutrient panel, branded
foods on the label subset). Scores are normalized to [0,1] for Phoenix charts; the raw error
magnitudes ride along in metadata so the supervisor can read true error.

## Self-supervision loop

DietTrace ships **two more** agents — a **corrector** and an autonomous **supervisor** — that
learn how *you* eat while a deterministic gate makes sure personalization never quietly
degrades general accuracy. **Arize Phoenix is the medium**, used over its **MCP server**:

1. **Every logged meal**, the supervisor observes the meal + your feedback and decides exactly
   one action: **bank feedback**, **add a held-out dataset point** (a real, user-confirmed
   meal written to a per-user Phoenix dataset via the MCP `add-dataset-examples` tool), or —
   once there's enough fresh signal — **retune**.
2. On a retune, the **corrector** generalizes your banked corrections into one short
   **preference block** — generalized rules, not few-shot echoes of single meals.
3. The supervisor runs an eval experiment (there is no run-experiment MCP tool, so it runs the
   experiment and **reads the results back over the Phoenix MCP server**) and a deterministic
   **gate** scores the candidate block on two sets: the **USDA** base set and your **own
   confirmed meals**.
4. The gate **ships** the change only if it stays within a small floor of USDA accuracy **and**
   meaningfully improves on your meals. Bad or contradictory feedback yields no held-out
   gain, so it never ships.

The split is the whole point: the agent decides *what to do*; the gate decides *whether a
change is good enough* with real numbers on a held-out set — never an LLM vouching for itself.
A conservative/powerful mode toggle controls how much the supervisor reasons (and spends) per
meal, and the web UI's right rail is a live feed of every decision it makes.

## Accuracy, measured before/after

Because search is deterministic, a *correctly matched* food is essentially exact against
USDA — the accuracy battle is fought in parsing, food matching, and portion estimation, and
that's exactly what the eval suite pins down. Each case is bound to a specific `fdc_id`, so a
regression is unambiguous rather than a vibe.

Personalization is demonstrated as a **before/after** on a held-out set of *your own* meals:

- **Before** — without a preference block, the agent estimates a logged meal from the generic
  pipeline; for a user who consistently eats bigger preworkout portions, those meals land low.
- **After** — you correct a couple of meals and confirm a few as ground truth; the supervisor
  retunes, the corrector proposes a block, and the gate scores it on the **USDA** base set and
  your **confirmed** meals. When the block improves your held-out fit (e.g. **79% → 100%**
  calorie accuracy on the preworkout set) while USDA stays within its floor, it **ships** — and
  the next identical meal is now estimated correctly.

The point isn't a single leaderboard number — it's that every prompt change is **proven on a
held-out set** against a named ground truth (USDA) *and* the user's own confirmed meals before
it ever ships. A change that would help your meals but quietly cost general accuracy is
rejected by the gate, automatically.

## Challenges

- **Trustworthy numbers from an untrustworthy source.** The breakthrough was refusing to let
  the LLM produce nutrient values at all — making `search_nutrition` a deterministic,
  reproducible DB lookup keyed by USDA nutrient codes, with the model restricted to parsing
  and orchestration.
- **Food matching is deceptively hard.** "Chicken breast" should resolve to a plain raw/cooked
  cut, not a deli roll; "half an avocado" needs an edible serving, not a pit-in gram weight.
  Tuning the canonical ranking and portion fallback to prefer the obvious answer took real
  iteration — and is now locked down by fixture tests.
- **Letting the agent adapt without letting it cheat.** The risk of "accept any feedback" is an
  agent that games its own grader. The fix is a generator/verifier split: the corrector
  proposes, but a deterministic **gate** decides — scoring every candidate on a **held-out** set
  of the user's confirmed meals it never trained on, plus a USDA floor. Bad feedback simply
  produces no held-out gain, so it can't ship.
- **Cost discipline.** GCP credits were scarce, so the entire test suite is offline: a
  no-network guard blocks real sockets and every external (Vertex, Phoenix, USDA, GitHub) is
  mocked. CI is $0; live calls are opt-in only.

## What's next

- Photo logging and restaurant / mixed-dish estimation (currently out of eval scope).
- A micronutrient-forward UI surfacing the full panel the DB already carries.
- Apple Health sync and a React Native client.
- Letting the supervisor read recent **traces over MCP** to diagnose *why* a case regressed,
  not just that it did — and widen what it can retune beyond the preference block.
- A cloud/RDS port behind the thin adapters already in place.

---

Nutrition data courtesy of U.S. Department of Agriculture, Agricultural Research Service.
FoodData Central, [fdc.nal.usda.gov](https://fdc.nal.usda.gov/) (CC0 1.0).

[Apache-2.0](./LICENSE) © Colin Hwang
