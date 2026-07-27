---
title: Confluxe Shopping Assistant API
emoji: 🛍️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8000
pinned: false
---

# Confluxe backend

FastAPI backend for the personal shopping assistant. Built from
`Dockerfile` in this directory; single worker (`--workers 1`) because
sessions are an in-memory, process-local TTL store — see
`app/services/sessions.py`.

This file exists to satisfy Hugging Face Spaces' Docker SDK metadata
requirement (`sdk: docker`, `app_port: 8000` in the frontmatter above). It is
pushed here via `git subtree push --prefix=backend <space-remote> main` from
the main repo, which has the full documentation:

- Setup, API, architecture: repo root `README.md` / `ARCHITECTURE.md`
- Deployment (env vars, failure modes, this Space's setup): repo root
  `DEPLOYMENT.md`

## Required Space secrets

Set under Space Settings → Repository secrets:

- `GEMINI_API_KEY`
- `GROQ_API_KEY`
- `JINA_API_KEY`

## Required Space variables

Set under Space Settings → Variables:

- `EMBEDDING_MODEL=jina-embeddings-v3`
- `EMBEDDING_DIMS=768`
- `CORS_ORIGINS=<comma-separated frontend origins, e.g. the Vercel domain>`
