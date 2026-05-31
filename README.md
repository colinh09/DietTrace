# DietTrace

**Log food in plain English. Get accurate calories and macros — proven by evals, not vibes.**

DietTrace is an AI nutrition agent. You type what you ate ("two eggs, half an avocado, slice of toast") and the agent plans and acts across multiple tools — parse the meal, look up nutrition facts, estimate portions, compute macros, and check the result against your goals. Accuracy is the headline, and it's held to account by a continuous evaluation suite running on [Arize Phoenix](https://phoenix.arize.com/).

Built for the [Google Cloud Rapid Agent Hackathon](https://rapid-agent.devpost.com/) — Arize track.

## What makes it an agent, not a chatbot

The nutrition agent decomposes a free-text meal into a deliberate tool pipeline:

```
parse_meal → search_nutrition → estimate_portion → log_entry → check_against_goals
```

Separating **search** (look up the food's nutrient facts) from **calculation** (portion math and totals) means the model never invents a number it should look up — and each stage is independently measurable.

## Architecture

Two agents that never talk to each other directly — Phoenix is the medium between them.

```
User (web) → Nutrition Agent (ADK + Gemini 3)
                 parse_meal → search_nutrition → estimate_portion → log_entry → check_against_goals
             → OpenInference spans → Arize Phoenix (traces · datasets · experiments · MCP)
                 ↑                                       ↓ (MCP read)
             Eval suite (numeric evaluators)        Supervisor Agent
                                                     reads experiments → classifies trend →
                                                     proposes prompt diff → opens GitHub PR
```

- **Nutrition agent** (`src/dietrace/agents/nutrition/`) — an ADK + Gemini 3 agent that orchestrates the five tools above. `parse_meal` is the only generative step; `search_nutrition`, `estimate_portion`, `log_entry`, and `check_against_goals` are deterministic, so numbers are looked up, not guessed. Output is structured JSON for clean scoring.
- **Food DB read layer** (`src/dietrace/nutrition/`) — an alias-aware, ranked query layer over a local USDA-derived SQLite database. Reads nutrients by numeric code (208 kcal, 203 protein, …), not by name, and returns the matched `fdc_id` so every result is reproducible.
- **Observability** (`src/dietrace/observability/`) — OpenInference instrumentation emits OTel spans to Phoenix and an in-memory buffer that powers the web "reasoning" trace. Fail-soft: a no-op without `PHOENIX_API_KEY`.
- **Eval suite** (`src/dietrace/evals/`) — deterministic numeric evaluators run as Phoenix experiments over a USDA-grounded dataset.
- **Supervisor agent** (`src/dietrace/agents/supervisor/`) — reads the experiments back over the Phoenix MCP server and, on a regression, opens a fix PR (below).
- **Web surface** (`src/dietrace/web/` + `frontend/`) — a FastAPI backend and a Next.js UI.

## Self-supervision via observability

DietTrace ships a second agent — a **supervisor** — that closes the accuracy loop:

1. Reads the latest evaluation experiments from Phoenix (via the Phoenix MCP server).
2. Classifies each test case's trend: improving / stable / regressing.
3. When a case regresses, proposes a focused prompt/tool fix as a unified diff.
4. Opens a GitHub pull request for a human to review and merge.

The agent improves itself with a human in the loop — it never edits prompts silently.

## Accuracy, measured

The eval suite scores numeric closeness to ground truth across calories and the full
macro + micronutrient panel. Ground-truth nutrition comes from the public-domain
[USDA FoodData Central](https://fdc.nal.usda.gov/) dataset (CC0 1.0). Each eval case is
pinned to a specific food by its `fdc_id`, so results are reproducible and regressions are
unambiguous.

Cases are scored in two tiers — whole foods on the full micronutrient panel, branded
foods on their label subset — by deterministic, zero-LLM evaluators: per-macro percent
error, calorie accuracy, mean absolute error, a ±15% within-tolerance pass/fail, and a
separate portion-error surface. The headline lesson the evals enforce is the **search /
calculation split**: because portion math and totals are computed, not generated, the
agent's error comes only from lookup and parsing — both of which the suite measures
directly.

> Nutrition data courtesy of U.S. Department of Agriculture, Agricultural Research
> Service. FoodData Central, [fdc.nal.usda.gov](https://fdc.nal.usda.gov/).

## Stack

| Layer | Choice |
|---|---|
| Language | Python 3.12 |
| Agent runtime | Google ADK |
| LLM | Gemini 3 (Vertex AI) |
| Observability & evals | Arize Phoenix (Cloud + MCP) |
| Wire format | OpenInference (OTel-native) |
| Demo surface | FastAPI + Next.js web UI on Cloud Run |
| CI | GitHub Actions (ruff + pytest) |

## Run it

Set up a virtualenv and install the package with its dev extras:

```bash
python -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env   # fill in your Gemini / Phoenix keys
```

Start the API + web backend:

```bash
python -m uvicorn dietrace.web.app:app --reload --port 8080
```

Run the Next.js frontend (in a second shell):

```bash
cd frontend && npm install && npm run dev   # http://localhost:3000
```

Score accuracy by running the evaluation suite:

```bash
python -m dietrace.evals.runner
```

Let the supervisor inspect the latest experiments and open a fix PR if a case regressed:

```bash
python -m dietrace.agents.supervisor.run
```

Verify the build — the test suite is fully offline (all externals mocked, no network):

```bash
python -m pytest
ruff check .
```

## License

[Apache-2.0](./LICENSE) © Colin Hwang
