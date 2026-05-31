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

DietTrace ships a **second** agent — a supervisor — that closes the accuracy loop, ported in
spirit from an earlier project of mine (axon). The two agents never talk directly; **Phoenix
is the medium**:

1. The supervisor reads the latest eval experiments from Phoenix **over the Phoenix MCP
   server** (`@arizeai/phoenix-mcp`).
2. It **classifies** each test case's trend — improving / stable / regressing — using a
   heuristic delta (e.g. MAPE worsening past a threshold) with an LLM tiebreak.
3. When a case **regresses**, it proposes a focused fix as a unified diff against the
   agent's `instruction.md`, validating the patch hunks before touching anything.
4. It opens a GitHub **pull request** for a **human** to review and merge.

It never edits prompts silently — the human stays in the loop. A `demo_regression` script
reproduces the whole narrative end-to-end: commit a deliberate instruction regression → run
evals → watch the supervisor detect it and open a PR → verify the diff → clean up.

## Accuracy, measured before/after

Because search is deterministic, a *correctly matched* food is essentially exact against
USDA — the accuracy battle is fought in parsing, food matching, and portion estimation, and
that's exactly what the eval suite pins down. Each case is bound to a specific `fdc_id`, so a
regression is unambiguous rather than a vibe.

The self-supervision loop is demonstrated as a **before/after** on the eval set:

- **Before** — a deliberately regressed instruction (it lets the model guess portions
  instead of calling `estimate_portion`) pushes several cases outside the ±15% tolerance
  band; the `within_tolerance` pass rate drops and per-macro `macro_pct_error` climbs well
  past the regression threshold on the affected cases.
- **After** — the supervisor reads the regressed experiment from Phoenix, classifies the
  failing cases, opens a PR restoring the "always call the tool" instruction, and re-running
  the experiment returns the affected cases to **0% portion error** and back inside
  tolerance.

The point isn't a single leaderboard number — it's that accuracy is a **continuously
measured quantity** with a named ground truth (USDA) and an agent watching the trend, so a
prompt change that quietly costs you accuracy gets caught and proposed-against instead of
shipping unnoticed.

## Challenges

- **Trustworthy numbers from an untrustworthy source.** The breakthrough was refusing to let
  the LLM produce nutrient values at all — making `search_nutrition` a deterministic,
  reproducible DB lookup keyed by USDA nutrient codes, with the model restricted to parsing
  and orchestration.
- **Food matching is deceptively hard.** "Chicken breast" should resolve to a plain raw/cooked
  cut, not a deli roll; "half an avocado" needs an edible serving, not a pit-in gram weight.
  Tuning the canonical ranking and portion fallback to prefer the obvious answer took real
  iteration — and is now locked down by fixture tests.
- **Two agents that must not collude.** Keeping the supervisor decoupled from the nutrition
  agent — communicating only through Phoenix experiments over MCP — kept the loop honest and
  the diff proposals grounded in measured regressions rather than guesses.
- **Cost discipline.** GCP credits were scarce, so the entire test suite is offline: a
  no-network guard blocks real sockets and every external (Vertex, Phoenix, USDA, GitHub) is
  mocked. CI is $0; live calls are opt-in only.

## What's next

- Photo logging and restaurant / mixed-dish estimation (currently out of eval scope).
- A micronutrient-forward UI surfacing the full panel the DB already carries.
- Apple Health sync and a React Native client.
- Letting the supervisor act on a wider regression surface (portion and search ranking, not
  just instruction text) — still always behind a human-reviewed PR.
- A cloud/RDS port behind the thin adapters already in place.

---

Nutrition data courtesy of U.S. Department of Agriculture, Agricultural Research Service.
FoodData Central, [fdc.nal.usda.gov](https://fdc.nal.usda.gov/) (CC0 1.0).

[Apache-2.0](./LICENSE) © Colin Hwang
