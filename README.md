# AquaTrace Backend

AquaTrace is a FastAPI backend for water-quality monitoring, alert management,
incident tracking, user management, and approved-document RAG explanations.

## Requirements

- Python 3.11
- uv
- PostgreSQL for deployment

## Local setup

Install dependencies:

    uv sync --frozen --all-groups

Configure your local `.env` using `.env.example`.

Start the API:

    uv run uvicorn main:app --reload

API documentation: http://localhost:8000/docs

Health check: http://localhost:8000/health

## Quality checks

    uv run pytest
    uv run ruff check .

## Render deployment

This repository is for a separate Render deployment. It does not replace
or modify the existing Heroku deployment.

Configure the Render Web Service:

- Repository: clairepanashetsuro/aquatrace_backend
- Branch: feature/render-deployment
- Runtime: Python
- Build command: pip install uv && uv sync --frozen --no-dev
- Start command: uvicorn main:app --host 0.0.0.0 --port $PORT
- Health check path: /health

Create a separate Render PostgreSQL database. Set DATABASE_URL and the
application's other environment variables in Render's environment settings.
Use .env.example as a reference. Never commit production credentials.

## RAG document ingestion

Approved documents and their manifest are stored in docs/rag_sources/.

Preview ingestion:

    uv run python -m scripts.ingest_rag_documents

Set DATABASE_URL, GEMINI_API_KEY, and GEMINI_FILE_SEARCH_STORE_NAME first.

Upload only after reviewing the preview:

    uv run python -m scripts.ingest_rag_documents --apply

## Deployment separation

The Render service and database are separate from the existing Heroku
deployment. Deploying the service does not automatically back up the
production database. Database backup and restoration must be managed separately.
