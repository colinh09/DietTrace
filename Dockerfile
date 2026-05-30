FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md ./
COPY src ./src
RUN uv pip install --system --no-cache .

# The read-only food DB (data/food.sqlite) is built by the obscured tools/
# pipeline and baked in (or mounted) at deploy time — it is not in the repo.

EXPOSE 8080
CMD ["uvicorn", "dietrace.web.app:app", "--host", "0.0.0.0", "--port", "8080"]
