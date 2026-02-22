FROM python:3.12-slim AS builder
WORKDIR /app
COPY pyproject.toml .
COPY ../libs/common /app/libs/common
RUN pip install --no-cache-dir /app/libs/common && pip install --no-cache-dir .

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY src/ /app/src/
RUN useradd --create-home appuser
USER appuser
ENV PYTHONUNBUFFERED=1 PORT=8007
EXPOSE 8007
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8007"]
