# Curate

Curate is a personal shopping assistant that turns plain-English shopping requests into grouped, explained product recommendations from a large Amazon India catalogue.

## What Curate does

- Understands a user’s shopping intent and sub-needs from natural language.
- Applies deterministic filters and retrieval over a curated product catalogue.
- Groups recommendations by need, explains why each result fits, and surfaces trade-offs.
- Serves the experience through a FastAPI backend and a React-based frontend.

## Product vision

The goal is to help people shop with more confidence by combining structured retrieval with LLM-generated explanations. Curate is designed to feel more like a thoughtful shopping companion than a simple search box.

## Tech stack

- Python 3.11 with FastAPI and Pydantic v2
- React 18, TypeScript, Vite, and Tailwind CSS
- Gemini and Groq for generation workflows
- Embedding-based retrieval over a pinned catalogue index

## Repository layout

- backend/ — API, services, data pipeline, and tests
- frontend/ — React app and UI components
- docs/ — planning, specs, and supporting documentation

## Getting started

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
pytest -q
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Notes

- The catalogue source file is large and must not be committed.
- Dataset attribution and licensing details should be maintained in the repository documentation.
- The implementation plan for this product lives in [docs/superpowers/plans/2026-07-26-personal-shopping-assistant.md](docs/superpowers/plans/2026-07-26-personal-shopping-assistant.md).
