# syntax=docker/dockerfile:1
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WORKSPACE_ROOT=/workspaces

WORKDIR /app

# `git` is required by the per-stage commit step (app/gitrepo.py) and
# `python -m venv` is used by the sandbox executor (app/sandbox/executor.py).
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

RUN mkdir -p /workspaces

EXPOSE 8000
# Single worker: SQLite + in-process workflow tasks are not multi-worker safe.
# PORT is injected by Railway (5000) / Render (10000); fall back to 8000.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --log-level info"]