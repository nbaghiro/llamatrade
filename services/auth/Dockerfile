# LlamaTrade Auth Service Dockerfile
# Build from repo root: docker build -f services/auth/Dockerfile -t auth .

FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install buf CLI for proto generation
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && curl -sSL "https://github.com/bufbuild/buf/releases/download/v1.47.2/buf-Linux-x86_64" -o /usr/local/bin/buf \
    && chmod +x /usr/local/bin/buf \
    && rm -rf /var/lib/apt/lists/*

# Copy shared libraries first (for layer caching)
COPY libs/common /app/libs/common
COPY libs/db /app/libs/db
COPY libs/grpc /app/libs/grpc
COPY libs/proto /app/libs/proto

# Generate proto files
RUN cd /app/libs/proto && buf generate --template buf.gen.python.yaml

# Install shared libraries
RUN pip install --no-cache-dir /app/libs/common /app/libs/db /app/libs/grpc

# Copy service files and install
COPY services/auth/pyproject.toml services/auth/README.md /app/
COPY services/auth/src /app/src
RUN pip install --no-cache-dir .

# Production image
FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --from=builder /app/src /app/src

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser
USER appuser

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8001

EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')" || exit 1

# Run the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]
