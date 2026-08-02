FROM python:3.14-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Build context is the repo root (see docker-compose.yml db-migrate.build.context).
# llamatrade_db.models imports llamatrade_proto.generated for enum constants, and
# llamatrade_proto's client layer imports llamatrade_common.auth, so both proto and
# common must be installed even though libs/db's pyproject declares neither.
COPY libs/telemetry /app/libs/telemetry
COPY libs/proto /app/libs/proto
COPY libs/common /app/libs/common
RUN pip install --no-cache-dir /app/libs/common /app/libs/telemetry /app/libs/proto

# Copy db package files (keep package at /app/llamatrade_db so the dev volume
# mount target /app/llamatrade_db continues to line up)
COPY libs/db/pyproject.toml /app/
COPY libs/db/llamatrade_db/ /app/llamatrade_db/

# Install package
RUN pip install --no-cache-dir .

# Set working directory for alembic
WORKDIR /app/llamatrade_db/alembic

# Run migrations
CMD ["alembic", "upgrade", "head"]
