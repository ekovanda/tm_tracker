FROM python:3.13-slim AS runner

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

WORKDIR /app

# Install minimal OS dependencies for health checking
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast, reliable dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy dependency specifications and install application packages
COPY pyproject.toml README.md ./
RUN uv pip install --system --no-cache -e .

# Copy application source code and static assets
COPY *.py ./
COPY static/ ./static/

# Create a non-root system user and configure file ownership
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser && \
    chown -R appuser:appuser /app

USER appuser

# Document exposed container port (Cloud Run defaults to 8080)
EXPOSE 8080

# Container health check against FastAPI health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/health || exit 1

# Execute uvicorn with shell parameter substitution for Cloud Run dynamic PORT
CMD ["sh", "-c", "exec uvicorn api:app --host 0.0.0.0 --port ${PORT:-8080}"]
