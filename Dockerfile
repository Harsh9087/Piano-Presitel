FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend/ /app/backend/
COPY frontend/dist/ /app/frontend/dist/

COPY deploy/docker-entrypoint.sh /app/docker-entrypoint.sh
RUN sed -i 's/\r$//' /app/docker-entrypoint.sh && chmod +x /app/docker-entrypoint.sh

RUN mkdir -p /app/data

WORKDIR /app/backend

ENV SQLITE_DB_PATH=/app/data/db.sqlite3 \
    PORT=8012

EXPOSE 8012

ENTRYPOINT ["/bin/sh", "/app/docker-entrypoint.sh"]
