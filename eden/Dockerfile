FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./

RUN useradd --create-home --uid 10001 eden
USER eden

EXPOSE 8000
CMD ["uvicorn", "eden.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "src"]
