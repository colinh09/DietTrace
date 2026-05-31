FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

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

EXPOSE 8080
CMD ["uvicorn", "dietrace.web.app:app", "--host", "0.0.0.0", "--port", "8080"]
