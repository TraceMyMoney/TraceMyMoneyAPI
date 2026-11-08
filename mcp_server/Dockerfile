# syntax=docker/dockerfile:1

# Build context is TraceMyMoneyAPI/ (see docker-compose.yml's `smm_mcp`
# service), because it needs pyproject.toml + uv.lock from here.
#
# `uv sync --frozen --extra mcp --no-install-project`: installs exactly what
# uv.lock pins (fastmcp 3.4.0) plus the base deps, and does not build this
# project itself - the image only runs `python -m mcp_server.server` off the
# filesystem. If you change the fastmcp pin, run `uv lock` and commit uv.lock
# or --frozen keeps installing the old version.
FROM python:3.11-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --extra mcp --no-install-project --no-dev

COPY mcp_server ./mcp_server

FROM python:3.11-slim-bookworm AS runtime

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/mcp_server ./mcp_server

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# SMM_* settings come from docker-compose (no secrets are needed: every user
# authenticates with their own OAuth token).
USER appuser

EXPOSE 8090

# A bare TCP connect: the Streamable HTTP endpoint wants real MCP framing, so
# a plain GET would only bounce with a 4xx. This confirms the process is up.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import socket; socket.create_connection(('localhost', 8090), timeout=3)" || exit 1

CMD ["python", "-m", "mcp_server.server"]
