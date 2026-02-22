# LlamaTrade Market Data Service Dockerfile

FROM python:3.12-slim AS builder

WORKDIR /app

COPY pyproject.toml .
COPY ../libs/common /app/libs/common

RUN pip install --no-cache-dir /app/libs/common
RUN pip install --no-cache-dir .

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY src/ /app/src/

RUN useradd --create-home --shell /bin/bash appuser
USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8004

EXPOSE 8004

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8004/health')" || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8004"]
