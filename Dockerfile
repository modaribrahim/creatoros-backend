FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# system deps needed for building/installing wheels (asyncpg, pgvector, bcrypt)
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000

# Default command runs the API. The worker is a separate compose service
# that overrides command.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
