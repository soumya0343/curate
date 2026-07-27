# Curate

A personal shopping assistant. You describe what you need in plain English —
*"three days trekking in Manali in December, under ₹8,000"* — and it returns
product recommendations grouped by need, each with a one-sentence reason it fits.

The catalogue is derived from Amazon India product data (1.59M source rows).
Licence and attribution: [ATTRIBUTION.md](ATTRIBUTION.md).

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
(season, gender, budget) comes back as an assumption chip. Filters that had to be
widened come back as a visible notice.

**It refuses to fabricate.** Product attributes carry provenance. Only
title-verified facts may be stated as fact or used to exclude a product; inferred
ones can only nudge ranking. A group with no good match returns empty and says so
rather than padding with a bad pick.

A real run, against the synthetic catalogue with Gemini doing the reasoning:

```
"I am going for a trek to Hampta Pass in the last week of October for one week.
 Please find me trekking essentials and clothing."

intent      activity=trekking  destination=Hampta Pass  season=late October  duration_days=7
assumptions weather: cold-weather conditions likely (medium)
            gender: unisex / general search (low)
question    Are you looking for men's or women's clothing and footwear?

[Trekking Footwear]  ₹2199  Quechua NH100 Hiking Shoes Unisex Waterproof
                            "A waterproof unisex hiking shoe suited for keeping feet dry…"
[Outer Insulation]   ₹3999  Decathlon Forclaz MT100 Padded Winter Jacket for Men
[Trekking Backpack]  ₹4299  Tripole Walker 55L Internal Frame Rucksack with Rain Cover
                            "A 55L internal frame rucksack with an included rain cover…"
[Thermal Base Layers]  empty — No suitable match found in the catalogue for this need.
```

Note the last group. It is empty and says why, rather than being dropped.

## Running it

Three modes, in increasing order of what they need.

### 1. No credentials at all

Everything runs: API, streaming, frontend, sessions, refinement.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/build_mock_catalogue.py

DATA_DIR=data/mock EMBEDDING_MODEL=hashing-bow-v1 EMBEDDING_DIMS=256 \
  GENERATION_PRIMARY=mock uvicorn app.main:app --workers 1 --port 8000
```

A synthetic catalogue (147 invented products, 25 categories) stands in for the
real one, a hashed bag-of-words embedder stands in for Gemini, and a rule-based
provider stands in for the LLM. **It proves the machinery works; it says nothing
about recommendation quality.** The embedder has no IDF, so a query for "thermal
base layer" can rank a saree above a thermal vest.

### 2. Real models, synthetic catalogue

```bash
cp .env.example .env      # fill in at least GEMINI_API_KEY
python scripts/check_providers.py --embeddings   # verify the keys before trusting them
DATA_DIR=data/mock EMBEDDING_MODEL=hashing-bow-v1 EMBEDDING_DIMS=256 \
  uvicorn app.main:app --workers 1 --port 8000
```

Real intent extraction and real explanations, still over invented products. This
is the mode the example above was produced in.

### 3. Real catalogue

```bash
cd backend
python scripts/ingest_enriched.py --embedder gemini   # needs GEMINI_API_KEY; real semantic retrieval
python scripts/ingest_enriched.py --embedder hashing  # no key, quick smoke test only
```

Reads `backend/data/enriched.csv` (not committed, same as the raw source CSV —
see **Data**) and writes `catalogue.jsonl.gz`, `embeddings.npy` and
`embeddings.manifest.json` into `backend/data/`. That's where `DATA_DIR`
already defaults, so drop the `DATA_DIR` / `EMBEDDING_*` overrides from mode 2
once it's built. `data/mock/` is untouched either way — it stays reachable via
`DATA_DIR=data/mock` as the permanent no-credentials fallback.

`--workers 1` is not optional in any mode. Sessions live in a process-local dict,
so a session created on worker A is missing on worker B. Redis is the production
path.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env      # VITE_API_BASE_URL, defaults to localhost:8000
npm run dev               # http://localhost:5173
npx vitest run            # no npm test script yet
```

Details — streaming state machine, SSE parsing, component rules — in
[frontend/README.md](frontend/README.md).

### Tests

```bash
cd backend && python -m pytest -q     # 161 tests, no network, no keys
cd frontend && npx vitest run         # 16 tests
```

Run the backend suite **from `backend/`**. `pytest.ini` lives there, so from the
repo root `asyncio_mode` never applies and every async test fails on a missing
plugin — a working-directory mistake that reads as a code regression.

## API

| Method | Path | Behaviour |
|---|---|---|
| `GET` | `/api/health` | `{"status": "ok"}` |
| `POST` | `/api/recommend` | Runs the pipeline, returns one JSON response |
| `POST` | `/api/recommend/stream` | Same pipeline, streamed as SSE frames |
| `GET` | `/api/catalogue` | Browse products — filter, sort, paginate (Postgres) |
| `GET` | `/api/catalogue/categories` | Category names with counts |
| `GET` | `/api/catalogue/{product_id}` | One product |

Request body for both recommend routes:

```json
{ "query": "3 days trekking in Manali in December", "session_id": null }
```

Pass the `session_id` from a previous response to refine — *"make it cheaper"*
merges onto the prior intent instead of starting over.

Response shape (abridged):

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
          "image_url": "…", "product_url": "…",
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

The stream emits `understood` → `searching` → `results` → `done`, or `error`.
It is SSE-over-POST rather than `EventSource`, which is GET-only: the query is a
free-text sentence plus session state, and putting that in a URL hits length
limits and writes user queries into access logs. The frontend reads it with
`fetch` + `ReadableStream`.

Errors return `{"error": {"code", "message", "retryable"}}` with codes
`INVALID_QUERY` (400), `NOT_FOUND` (404), `RATE_LIMITED` (429),
`PROVIDER_UNAVAILABLE` (503), `CATALOGUE_UNAVAILABLE` (503), `INTERNAL` (500).

`RATE_LIMITED` and `CATALOGUE_UNAVAILABLE` are `retryable: true`; the rest are
not. That distinction is the point of having codes at all.

## Stack

- **Backend** — Python 3.11+ (developed on 3.13), FastAPI, Pydantic v2, NumPy.
- **Frontend** — React 19, TypeScript, Vite, Tailwind 3.
- **Recommendation reads files, not a database.** The catalogue is a gzipped
  JSONL plus an `.npy` matrix, loaded once at startup. At this scale a cosine
  search over the matrix is ~1 ms; a database round trip is 1–3 ms before doing
  any work.
- **Postgres backs catalogue *browsing* only** (`/api/catalogue`). It is a
  mirror, seeded one-way from the JSONL by `scripts/seed_db.py`, and it is
  optional: if it is unreachable the app still boots and recommendation is
  unaffected — browsing returns `CATALOGUE_UNAVAILABLE`.

### Models and providers

Generation runs through an ordered chain; each provider is tried in turn and one
with no credential is skipped rather than failing the chain.

| Provider | Default model | Notes |
|---|---|---|
| `gemini` | `gemini-flash-latest` | Also the embedding provider |
| `groq` | `llama-3.3-70b-versatile` | |
| `cerebras` | `gpt-oss-120b` | Needs a paid account — free tier returns 402 |
| `github` | `openai/gpt-4o-mini` | GitHub Models, a PAT with `models:read`. Low daily ceiling, so put it last |
| `mock` | — | Keyless rule-based provider. Ends any chain it appears in |

Embeddings are `gemini-embedding-001` at 768 dims, or the keyless
`hashing-bow-v1` at 256. **Embeddings never fall back to another provider** —
query vectors must share the catalogue's vector space, and a swap would return
plausible-looking numbers that are noise. Key rotation is safe and provider
fallback is not, for exactly that reason.

`scripts/check_providers.py` tests every configured credential individually
against the real API and prints which ones work, masked to the last four
characters. Run it before assuming a key is good.

### Environment

| Variable | Default | Notes |
|---|---|---|
| `GEMINI_API_KEY` | — | Required unless `EMBEDDING_MODEL=hashing-bow-v1` |
| `GROQ_API_KEY`, `CEREBRAS_API_KEY` | — | Optional chain members |
| `GITHUB_TOKEN` | — | GitHub Models. A PAT with `models:read`, not an API key |
| `*_API_KEYS`, `GITHUB_TOKENS` | — | Comma-separated. Several credentials per provider; a rate limit rotates to the next and retries |
| `GENERATION_CHAIN` | — | e.g. `gemini,groq,github`. Overrides the pair below |
| `GENERATION_PRIMARY` / `GENERATION_FALLBACK` | `gemini` / `groq` | Legacy pair, still honoured |
| `GEMINI_MODEL`, `GROQ_MODEL`, `CEREBRAS_MODEL`, `GITHUB_MODEL` | see table above | Model ids drift; all four are config, not code |
| `EMBEDDING_MODEL` / `EMBEDDING_DIMS` | `gemini-embedding-001` / `768` | Pinned. Must match `embeddings.manifest.json` |
| `DATA_DIR` | `backend/data` | Point at `data/mock` for the synthetic catalogue |
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/catalogue` | Browsing only |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated |
| `SESSION_TTL_SECONDS` | `1800` | |
| `LLM_TIMEOUT_SECONDS` | `30` | |

A single credential containing commas is read as several credentials, so putting
the list in `GEMINI_API_KEY` rather than `GEMINI_API_KEYS` works too.

### Troubleshooting

Most failures happen at boot, on purpose — the alternative is discovering them
per-request under load.

| Symptom | Cause | Fix |
|---|---|---|
| `ManifestMismatch: catalogue built with … but configured …` | `EMBEDDING_MODEL` / `EMBEDDING_DIMS` don't match the manifest | Fix the config, or re-embed the catalogue. Never loosen the check |
| `ManifestMismatch: row misalignment: N products, M vectors` | JSONL and `.npy` are out of sync | Rebuild both; line order is a contract |
| `FileNotFoundError` on `embeddings.manifest.json` | No catalogue at `DATA_DIR` | Build the mock one, or point `DATA_DIR` at `data/mock` |
| `ProviderUnavailable: GEMINI_API_KEY is required for embeddings` | No key and not using the hashing embedder | Set the key, or set `EMBEDDING_MODEL=hashing-bow-v1` |
| `404 … no longer available to new users` | The model id retired | Set `GEMINI_MODEL`. `check_providers.py` finds this in seconds |
| `402 payment_required` from Cerebras | Free tier does not include inference | Drop `cerebras` from `GENERATION_CHAIN` until billing is on |
| `RATE_LIMITED` (429) | Every credential on every provider refused on quota | Add keys to `*_API_KEYS`, or wait. It is retryable |
| `CATALOGUE_UNAVAILABLE` on `/api/catalogue` | Postgres unreachable | Start it and run `scripts/seed_db.py`. Recommendation is unaffected |
| Browser CORS error | Frontend origin not in `CORS_ORIGINS` | Add it, or drop `VITE_API_BASE_URL` and use the Vite `/api` proxy |
| Refinement forgets the previous query | More than one worker | `--workers 1` |

Logs are one JSON line per stage, keyed by `request_id`:

```json
{"request_id": "a1b2c3d4e5f6", "stage": "rerank", "duration_ms": 1904.0, "shortlist": 14, "filled": 3}
```

### Deploying

Configuration and a step-by-step plan are in [DEPLOYMENT.md](DEPLOYMENT.md):
Render for the backend (Docker), Vercel for the frontend. Nothing is deployed
yet. The mock-data variant deploys with no credentials at all.

Serverless is a poor fit: the catalogue and embedding matrix load at startup, so
every cold start pays for it, and process-local sessions don't survive.

## Current state

**Built and tested:** the runtime pipeline, both API surfaces, streaming, the
frontend, key rotation across four providers, the synthetic catalogue, and the
deployment configuration. 161 backend tests and 16 frontend tests, no network and
no credentials required.

**Verified against live APIs:** Gemini (generation and embeddings, 768 dims),
Groq and GitHub Models all answer. Cerebras returns 402 — the account needs
billing.

**Real catalogue ingest:** `scripts/ingest_enriched.py` builds the real catalogue
from `backend/data/enriched.csv` — an offline-enriched (translated, categorised,
attribute-extracted) sample of the source dataset, 6,000 products after dropping
94 rows with no resolved category. It maps onto `Product` with no schema
changes and re-verifies title-derived attributes with the same
`scripts/verify_attributes.py` gate the mock catalogue uses. Until it's run,
`backend/data/` holds the source CSV, `enriched.csv`, `profile.json` and the
synthetic catalogue in `data/mock/`, but not the three artifacts the app loads
by default.

**Known bugs, both frontend:**
- `ProductCard` checks `price_tier` against `"mid-range"`, which the backend
  never emits (it sends `"mid"`), so that badge never renders.
- The streaming path never registers an `onDone` handler, so `timings_ms` and
  `intent` arrive as `{}` on the client even though the backend sends both.

## Repository layout

```
backend/app/        API, services, providers, schemas, db — the runtime path
backend/scripts/    Profiling, verifiers, mock + real catalogue ingest, provider check, seeding
backend/data/       Source CSV (never committed), mock/ catalogue artifacts
backend/eval/       queries.yaml — golden and unseen evaluation queries
frontend/src/       React app
ATTRIBUTION.md      Dataset licence (ODC-By v1.0) and what it does not cover
DEPLOYMENT.md       Render + Vercel plan, env, failure modes
ARCHITECTURE.md     Runtime design and why each decision went this way
```

## Data

Source data is the [Amazon India Products 2023](https://www.kaggle.com/datasets/asaniczka/amazon-india-products-2023-1-5m-products)
dataset, licensed **ODC-By v1.0** — permissive, attribution required, commercial
use and derivative databases explicitly allowed.

The licence covers the *database*, not copyright in the individual contents:
product titles and images belong to their respective rights holders. No image
files are stored. The 670 MB source CSV is never committed. Full detail, and the
notices the licence requires, in [ATTRIBUTION.md](ATTRIBUTION.md).

Products under `backend/data/mock/` are invented and contain no source data at
all.
