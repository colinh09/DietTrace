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
pinned to a specific food so results are reproducible and regressions are unambiguous.

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
| Demo surface | FastAPI + web UI on Cloud Run |
| CI | GitHub Actions (ruff + pytest) |

## Run it

```bash
uv sync
cp .env.example .env   # fill in your Gemini / Phoenix keys
uv run uvicorn dietrace.web.app:app --reload --port 8080
```

Run the evaluation suite:

```bash
uv run python -m dietrace.evals.runner
```

Run the supervisor:

```bash
uv run python -m dietrace.agents.supervisor.run
```

## License

[Apache-2.0](./LICENSE) © Colin Hwang
