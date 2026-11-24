FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first (cache layer)
COPY backend/pyproject.toml backend/uv.lock ./

# Install production dependencies only
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY backend/ .

# Create a directory for the persistent SQLite database
RUN mkdir -p /data

# Expose the API port
EXPOSE 8000

# Upgrade a persistent Railway database before the new application imports it.
# The command is idempotent and is a no-op for a fresh database, whose tables
# are then created by the application lifespan.
CMD ["sh", "-c", "uv run --no-dev python -m app.upgrade_laboratory && exec uv run --no-dev uvicorn app.main:app --host 0.0.0.0 --port 8000"]
