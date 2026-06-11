FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Node + the Phoenix MCP server. The supervisor reads experiment results back
# over MCP (npx @arizeai/phoenix-mcp), so the runtime needs Node; pre-install the
# package so the first read doesn't pay a cold npm fetch.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @arizeai/phoenix-mcp \
    && apt-get purge -y curl gnupg && apt-get autoremove -y \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md ./
COPY src ./src
RUN uv pip install --system --no-cache .

# The USDA-grounded eval cases — the /accuracy page counts them.
COPY evals/dataset ./evals/dataset

# The read-only food DB (data/food.sqlite) is built from USDA FoodData Central by
# the obscured tools/ pipeline; it is not committed but is baked in here at build
# time so the running service can resolve foods without a network call.
COPY data/food.sqlite ./data/food.sqlite

# Curated common-foods overlay (gitignored mapping, so not in the installed wheel)
# — baked in and pointed at by DIETRACE_OVERLAY at deploy time. load_overlay is
# fail-soft, so its absence just disables the overlay (ranked search still works).
COPY src/dietrace/nutrition/mappings/common_foods.json ./data/common_foods.json

EXPOSE 8080
CMD ["uvicorn", "dietrace.web.app:app", "--host", "0.0.0.0", "--port", "8080"]
