# Curate

A personal shopping assistant. You describe what you need in plain English —
*"three days trekking in Manali in December, under ₹8,000"* — and it returns
product recommendations grouped by need, each with a one-sentence reason it fits.

The catalogue is Amazon India product data (1.59M source rows, sampled down to a
~20k working catalogue). See [docs/dataset.md](docs/dataset.md) for what that data
is and what is wrong with it.

## What makes it different from a search box

**It splits the request into sub-needs.** "Trekking essentials and clothing" is
two searches, not one. A single embedding of the whole sentence is a blurry
average — it drifts toward whatever the catalogue holds most of, and a sleeping
bag never enters the candidate pool. Each sub-need gets its own vector search and
its own result group.

**It separates what the LLM decides from what code decides.** The LLM reads the
request and writes the explanations. Filtering, retrieval and pre-ranking are
plain deterministic Python — embeddings don't encode price, and a ₹2,000 jacket
and a ₹22,000 jacket have near-identical vectors.

**It shows its guesses.** Everything the model inferred but you didn't say
(season, gender, budget) comes back as an editable assumption chip. Filters that
had to be widened come back as a visible notice.

**It refuses to fabricate.** Product attributes carry provenance. Only
title-verified facts may be stated as fact or used to exclude a product; inferred
ones can only nudge ranking. A group with no good match returns empty and says
so rather than padding with a bad pick.

## API

| Method | Path | Behaviour |
|---|---|---|
| `GET` | `/api/health` | `{"status": "ok"}` |
| `POST` | `/api/recommend` | Runs the pipeline, returns one JSON response |
| `POST` | `/api/recommend/stream` | Same pipeline, streamed as SSE frames |

Request body for both recommend routes:

```json
{ "query": "3 days trekking in Manali in December", "session_id": null }
```

Pass the `session_id` from a previous response to refine — *"make it cheaper"*
merges onto the prior intent instead of starting over.

Response shape (abridged; values below are illustrative, not a real run):

```json
{
  "session_id": "8f3c…",
  "intent": { "activity": "trekking", "destination": "Manali",
              "season": "winter", "duration_days": 3, "budget_max": 8000 },
  "assumptions": [
    { "field": "season", "value": "cold-weather conditions likely",
      "reason": "December in the Himalayas", "confidence": "medium",
      "editable": true }
  ],
  "clarifying_question": null,
  "groups": [
    { "label": "Insulation",
      "recommendations": [
        { "product_id": "B0…", "title": "…", "price": 2499,
          "price_tier": "mid", "rating": 4.2, "reviews": 318,
          "image_url": "…", "product_url": "https://www.amazon.in/dp/B0…",
          "reason": "Suited to cold-weather trekking and inside your budget." }
      ],
      "empty_reason": null },
    { "label": "Daypack", "recommendations": [],
      "empty_reason": "No suitable match found in the catalogue for this need." }
  ],
  "relaxations": [],
  "timings_ms": { "intent": 812.5, "retrieval": 41.2, "prerank": 1.8,
                  "rerank": 1904.0, "total": 2760.1 }
}
```

Note the second group: empty, with a reason, rather than omitted. And
`relaxations` — non-empty when a filter had to be widened to return anything.

The stream emits `understood` → `searching` → `results` → `done`, or `error`.
It is SSE-over-POST rather than `EventSource`, which is GET-only: the query is a
free-text sentence plus session state, and putting that in a URL hits length
limits and writes user queries into access logs. The frontend reads it with
`fetch` + `ReadableStream`.

Errors return `{"error": {"code", "message", "retryable"}}` with codes
`INVALID_QUERY` (400), `RATE_LIMITED` (429), `PROVIDER_UNAVAILABLE` (503),
`INTERNAL` (500).

## Stack

- **Backend** — Python 3.11+, FastAPI, Pydantic v2, NumPy. No database: the
  catalogue is a gzipped JSONL file and an `.npy` matrix, loaded once at startup.
- **Frontend** — React 19, TypeScript, Vite, Tailwind CSS.
- **Models** — Gemini 2.5 Flash for generation with Groq `llama-3.3-70b-versatile`
  as fallback; `gemini-embedding-001` at 768 dims for embeddings (no fallback —
  see [ARCHITECTURE.md](ARCHITECTURE.md#embeddings-have-no-fallback-chain)).

## Running it

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in GEMINI_API_KEY
pytest -q                     # tests need no keys and no network
uvicorn app.main:app --reload --workers 1
```

`--workers 1` is not optional. Sessions live in a process-local dict, so a
session created on worker A is missing on worker B. Redis is the production path.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env          # VITE_API_BASE_URL, defaults to localhost:8000
npm run dev
npx vitest run                # no npm test script yet
```

Frontend specifics — streaming state machine, SSE parsing, component rules —
are in [frontend/README.md](frontend/README.md).

### Environment

| Variable | Default | Notes |
|---|---|---|
| `GEMINI_API_KEY` | — | Required. Embeddings have no fallback. |
| `GROQ_API_KEY` | — | Optional. Without it there is no generation fallback. |
| `GENERATION_PRIMARY` | `gemini` | |
| `GENERATION_FALLBACK` | `groq` | |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated. |
| `SESSION_TTL_SECONDS` | `1800` | |
| `LLM_TIMEOUT_SECONDS` | `30` | |

`EMBEDDING_MODEL` and `EMBEDDING_DIMS` are pinned. Changing either requires
rebuilding the catalogue embeddings; the manifest check will refuse to start
otherwise.

### Troubleshooting

Most failures happen at boot, on purpose — the alternative is discovering them
per-request under load.

| Symptom | Cause | Fix |
|---|---|---|
| `ManifestMismatch: catalogue built with … but configured …` | `EMBEDDING_MODEL` / `EMBEDDING_DIMS` no longer match `embeddings.manifest.json` | Revert the config, or re-embed the whole catalogue |
| `ManifestMismatch: row misalignment: N products, M vectors` | JSONL and `.npy` are out of sync — something reordered one of them | Rebuild both from ingest; line order is a contract |
| `FileNotFoundError` on `embeddings.manifest.json` | Ingest hasn't been run — see **Current state** | Nothing to do yet; tests run without it |
| `ProviderUnavailable: GEMINI_API_KEY is required for embeddings` | No key | Set it. Embeddings deliberately have no fallback |
| `PROVIDER_UNAVAILABLE` at request time | Primary failed and either there's no fallback key or it failed too | Check the `provider_failover` log line for the underlying error |
| Browser console shows a CORS error | Frontend origin not in `CORS_ORIGINS` | Add it, or drop `VITE_API_BASE_URL` and use the Vite `/api` proxy |
| Refinement forgets the previous query | Running more than one worker | `--workers 1`, or move sessions to Redis |

Logs are one JSON line per stage, keyed by `request_id`:

```json
{"request_id": "a1b2c3d4e5f6", "stage": "rerank", "duration_ms": 1904.0, "shortlist": 14, "filled": 3}
```

### Deploying

The frontend is a static build (`npm run build`) — the CORS config already
allows `https://*.vercel.app` for preview deployments. The backend needs a host
that permits a long-lived process with the catalogue in memory, run with
`--workers 1`, and `CORS_ORIGINS` pointed at the deployed frontend origin.

Serverless is a poor fit: the catalogue and embedding matrix load at startup, so
every cold start pays for it, and process-local sessions don't survive.

## Current state

The runtime pipeline, API and frontend are built and tested against stub
providers. The offline ingest that produces the catalogue artifacts is still
being built — Tasks 4–13 of
[docs/superpowers/plans/2026-07-26-catalogue-pipeline-v2.md](docs/superpowers/plans/2026-07-26-catalogue-pipeline-v2.md).

Until it runs, `backend/data/` holds the 670 MB source CSV and `profile.json`
but not the three artifacts the app loads at startup:

```
backend/data/catalogue.jsonl.gz         # products, line order is a contract
backend/data/embeddings.npy             # L2-normalised, row-aligned to the JSONL
backend/data/embeddings.manifest.json   # model + dims, checked at startup
```

Without them the app raises on startup rather than serving degraded results.
The test suite covers the pipeline end to end without them.

## Repository layout

```
backend/app/        API, services, providers, schemas — the runtime path
backend/scripts/    Offline profiling, verification, ingest
backend/tests/      93 tests, no network, no API keys
frontend/src/       React app
docs/               Dataset analysis, taxonomy, plans and specs
```

## Data

The source CSV is 670 MB and is never committed. Licence terms and what may be
redistributed are recorded in [docs/dataset.md](docs/dataset.md) §1.1 — the short
version is that derived data ships only if the licence is permissive, otherwise
only ASINs and our own generated text do.
