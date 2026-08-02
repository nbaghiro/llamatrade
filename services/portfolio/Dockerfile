# LlamaTrade Portfolio Service Dockerfile
# Build from repo root: docker build -f services/portfolio/Dockerfile -t portfolio .

FROM python:3.14-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy shared libraries first (for layer caching)
COPY libs/telemetry /app/libs/telemetry
COPY libs/common /app/libs/common
COPY libs/db /app/libs/db
COPY libs/proto /app/libs/proto
COPY libs/events /app/libs/events
COPY libs/alpaca /app/libs/alpaca

# Install shared libraries (telemetry first; events needs proto)
RUN pip install --no-cache-dir /app/libs/telemetry /app/libs/common /app/libs/db /app/libs/proto /app/libs/events /app/libs/alpaca

# Copy service files and install
COPY services/portfolio/pyproject.toml services/portfolio/README.md /app/
COPY services/portfolio/src /app/src
RUN pip install --no-cache-dir .

# Production image
FROM python:3.14-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --from=builder /app/src /app/src

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8860

EXPOSE 8860

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8860/health')" || exit 1

# Run the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8860"]
