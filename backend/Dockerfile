FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser \
    && chown -R appuser:appgroup /app \
    # Pre-create the classifier model dir with app ownership: named volumes
    # mounted at /data/models inherit it on first creation, so the non-root
    # appuser can write models (a root-owned volume caused Errno 13 here).
    && mkdir -p /data/models && chown -R appuser:appgroup /data

USER appuser

ENV PYTHONPATH=/app

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
