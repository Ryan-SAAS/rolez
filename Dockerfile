FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --upgrade pip \
 && pip install .

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
COPY cli ./cli
COPY start.sh ./start.sh
RUN chmod +x /app/start.sh

ENV PORT=8000
EXPOSE 8000

CMD ["/app/start.sh"]
