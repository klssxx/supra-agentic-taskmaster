# Multi-stage production container for SUPRA Agentic Taskmaster
FROM ghcr.io/astral-sh/uv:0.11.28 AS uv
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

RUN uv sync --frozen --no-dev

# Final runtime image
FROM python:3.12-slim AS runner

WORKDIR /app

# Non-root user for security
RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -s /bin/bash appuser

COPY --from=builder /app/.venv /app/.venv
COPY src/ ./src/
COPY pyproject.toml README.md ./

ENV PATH="/app/.venv/bin:$PATH" \
    PORT=8080 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

RUN mkdir -p /app/data/projects && chown -R appuser:appgroup /app

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["uvicorn", "supra_agentic.service:app", "--host", "0.0.0.0", "--port", "8080"]
