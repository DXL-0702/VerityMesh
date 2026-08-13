FROM python:3.12.13-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.11.13 /uv /uvx /bin/

WORKDIR /workspace
COPY pyproject.toml uv.lock .python-version ./
COPY services/assistant-runtime/pyproject.toml services/assistant-runtime/pyproject.toml
COPY services/batch-worker/pyproject.toml services/batch-worker/pyproject.toml
COPY services/assistant-runtime/src services/assistant-runtime/src
COPY services/batch-worker/src services/batch-worker/src
COPY services/batch-worker/migrations services/batch-worker/migrations
COPY services/batch-worker/alembic.ini services/batch-worker/alembic.ini

RUN uv sync --frozen --no-dev --package veritymesh-batch-worker
