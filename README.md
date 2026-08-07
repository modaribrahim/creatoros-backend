# CreatorOS — Comment Analyzer

Backend service that turns YouTube comments into structured, aggregatable business insights, organized around **projects** that group multiple videos under one locked field configuration. Multi-user: every project is owned by an account (email + password), accessed via JWT bearer tokens.

## Features

- **Multi-user auth**: email signup + verification, bcrypt passwords, short-lived JWT access tokens, rotating hashed refresh tokens with reuse detection.
- **YouTube comment pipeline**: Celery worker fetches comments, runs them through an LLM, and stores structured per-comment records per project/video.
- **Hybrid semantic search**: exact JSONB filters + pgvector cosine (HNSW).
- **AI chat assistant**: answers project questions via read-only data tools and simple RAG over analyzed comments.

## Quick start

Requires Postgres + pgvector and Redis, plus API keys in `.env` (see `app/core/config.py`).

```bash
uv sync
uv run uvicorn app.main:app --port 8000        # API
uv run celery -A app.services.jobs:celery_app worker   # worker
uv run pytest -q                               # 71 fast unit tests
```

## Deploy (free tier)

See **[render.yaml](render.yaml)** — a Render Blueprint for the single-box demo
(API + Celery in one free process), backed by Neon (Postgres + pgvector) and
Upstash (Redis). Tables auto-create on startup (`AUTO_CREATE_TABLES=true`).

## API overview

Public auth endpoints (no token): `POST /api/v1/auth/signup`, `/login`, `/verify`, `/refresh`, `/logout`.

Protected (send `Authorization: Bearer <access_token>`): `GET /api/v1/auth/me`, all `/api/v1/projects*` and `/api/v1/jobs/{id}` endpoints (scoped to the authenticated user), and the chat service:

- `POST /api/v1/chat/sessions` — create a chat (optionally bound to a project)
- `POST /api/v1/chat/sessions/{id}/messages` — send a message; the AI answers by calling read-only data tools and simple RAG over analyzed comments
- `GET /api/v1/chat/sessions` and `GET /api/v1/chat/sessions/{id}/messages` — history
