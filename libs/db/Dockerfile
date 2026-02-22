FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy package files
COPY pyproject.toml .
COPY llamatrade_db/ ./llamatrade_db/

# Install package
RUN pip install --no-cache-dir .

# Set working directory for alembic
WORKDIR /app/llamatrade_db/alembic

# Run migrations
CMD ["alembic", "upgrade", "head"]
