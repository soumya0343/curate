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

**It refuses to fabricate specs.** Product attributes carry provenance. Only
title-verified facts may be stated as fact or used to exclude a product; inferred
ones can only nudge ranking. That guarantee holds. A separate claim — that a group
with no good match returns empty rather than padding with a bad pick — does not:
`ranking.py`'s `build_groups()` falls back to the closest-scoring retrieved
candidates when the LLM declines every candidate for a sub-need, with no
similarity floor gating that fallback. See [Future improvements](#future-improvements).

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
[Thermal Base Layers]  empty — Sorry, I couldn't find anything close to this in the catalogue right now.
```

Note the last group. It is empty and says why, rather than being dropped.

## Setup instructions

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

A synthetic catalogue (157 invented products, 25 categories) stands in for the
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
python scripts/ingest_enriched.py --embedder jina     # needs JINA_API_KEY; real semantic retrieval
python scripts/ingest_enriched.py --embedder gemini   # needs GEMINI_API_KEY; same, tighter free quota
python scripts/ingest_enriched.py --embedder hashing  # no key, quick smoke test only
```

`--embedder jina` is the practical default for a one-off catalogue build:
Gemini's free-tier embedding quota (a handful of requests before a 429, shared
across all keys on one project — key rotation does not help) is too tight for
a 6,000-row batch job; Jina's free tier (100 RPM / 100K TPM) has enough
headroom. Both give real semantic retrieval; `hashing` does not (see mode 1).

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
cd backend && python -m pytest -q     # 214 tests, no network, no keys
cd frontend && npx vitest run         # 56 tests
```

Run the backend suite **from `backend/`**. `pytest.ini` lives there, so from the
repo root `asyncio_mode` never applies and every async test fails on a missing
plugin — a working-directory mistake that reads as a code regression.

## Architecture overview

```
query
  │
  ├─ 1. intent     LLM   → ShoppingIntent + sub-needs + assumptions
  ├─ 2. filter     code  → row subset surviving hard constraints
  ├─ 3. retrieve   vec   → top-8 per sub-need, unioned, deduped
  ├─ 4. prerank    code  → top-5 per sub-need, variant-penalised
  └─ 5. rerank     LLM   → 3-5 picks per group + one reason each
```

Two LLM calls (intent, rerank) bracket three deterministic Python stages
(filter, retrieve, prerank). Filtering and ranking arithmetic need to be exact
and testable, and embeddings don't encode price — so anything that has to be
*correct*, not just *plausible*, is plain code, not a model call.

**Storage is one in-memory catalogue, not a database.** `catalogue.jsonl.gz`
plus an `.npy` embedding matrix load once at startup and stay resident in
process memory. `/api/recommend` searches it with a NumPy matmul;
`/api/catalogue` (browsing) filters/sorts/paginates the same loaded list —
one data source, two access patterns, nothing to keep in sync. Full
rationale, including why a Postgres mirror was tried and removed, in
[ARCHITECTURE.md](ARCHITECTURE.md#storage-one-in-memory-catalogue-two-access-patterns).

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full pipeline walkthrough,
trust tiers, provider chain design, and known constraints.

## API

| Method | Path | Behaviour |
|---|---|---|
| `GET` | `/api/health` | `{"status": "ok"}` |
| `POST` | `/api/recommend` | Runs the pipeline, returns one JSON response |
| `POST` | `/api/recommend/stream` | Same pipeline, streamed as SSE frames |
| `GET` | `/api/catalogue` | Browse products — filter, sort, paginate (same in-memory list) |
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
`PROVIDER_UNAVAILABLE` (503), `INTERNAL` (500).

Only `RATE_LIMITED` is `retryable: true`; the rest are not. That distinction is
the point of having codes at all.

## Stack

- **Backend** — Python 3.11+ (developed on 3.13), FastAPI, Pydantic v2, NumPy.
- **Frontend** — React 19, TypeScript, Vite, Tailwind 3.
- **One data source, not two.** The catalogue is a gzipped JSONL plus an
  `.npy` matrix, loaded once at startup and kept in process memory.
  `/api/recommend` searches it with a cosine matmul (~1 ms at this scale);
  `/api/catalogue` (browsing) filters, sorts and paginates the same loaded
  list. There used to be a second store (Postgres) mirroring the JSONL
  one-way for browsing only — dropped because a few thousand read-only rows
  don't earn back what a service, a connection pool and a sync script cost.
  See [ARCHITECTURE.md](ARCHITECTURE.md#storage-one-in-memory-catalogue-two-access-patterns).

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

Embeddings are `gemini-embedding-001` at 768 dims, `jina-embeddings-v3` also at
768 dims (an alternative with a far roomier free tier), or the keyless
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
| `GEMINI_API_KEY` | — | Required unless `EMBEDDING_MODEL` is `hashing-bow-v1` or `jina-embeddings-v3` |
| `JINA_API_KEY` | — | Required when `EMBEDDING_MODEL=jina-embeddings-v3`. Free tier: 100 RPM / 100K TPM |
| `GROQ_API_KEY`, `CEREBRAS_API_KEY` | — | Optional chain members |
| `GITHUB_TOKEN` | — | GitHub Models. A PAT with `models:read`, not an API key |
| `*_API_KEYS`, `GITHUB_TOKENS` | — | Comma-separated. Several credentials per provider; a rate limit rotates to the next and retries |
| `GENERATION_CHAIN` | — | e.g. `gemini,groq,github`. Overrides the pair below |
| `GENERATION_PRIMARY` / `GENERATION_FALLBACK` | `gemini` / `groq` | Legacy pair, still honoured |
| `GEMINI_MODEL`, `GROQ_MODEL`, `CEREBRAS_MODEL`, `GITHUB_MODEL` | see table above | Model ids drift; all four are config, not code |
| `EMBEDDING_MODEL` / `EMBEDDING_DIMS` | `gemini-embedding-001` / `768` | Pinned. Must match `embeddings.manifest.json` — **the config default does not match the committed catalogue**, which was built with `jina-embeddings-v3` (`backend/data/embeddings.manifest.json`). Leaving the default unset trips `ManifestMismatch` at boot against the real catalogue; set `EMBEDDING_MODEL=jina-embeddings-v3` explicitly |
| `DATA_DIR` | `backend/data` | Point at `data/mock` for the synthetic catalogue |
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
| `ProviderUnavailable: GEMINI_API_KEY is required for embeddings` | No key and not using `hashing-bow-v1`/`jina-embeddings-v3` | Set `GEMINI_API_KEY`, or switch `EMBEDDING_MODEL` |
| `RateLimited: all N gemini-embedding key(s) are rate limited` | Gemini's free-tier embedding quota is per-project, not per-key — extra keys on the same project don't help | Use `--embedder jina` for the catalogue build instead |
| `404 … no longer available to new users` | The model id retired | Set `GEMINI_MODEL`. `check_providers.py` finds this in seconds |
| `402 payment_required` from Cerebras | Free tier does not include inference | Drop `cerebras` from `GENERATION_CHAIN` until billing is on |
| `RATE_LIMITED` (429) | Every credential on every provider refused on quota | Add keys to `*_API_KEYS`, or wait. It is retryable |
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

## Design decisions

- **Two deterministic stages bracket two LLM calls, not the reverse.** Intent
  parsing and reranking need judgement; filtering and pre-ranking need to be
  exact and testable. See [ARCHITECTURE.md](ARCHITECTURE.md#the-runtime-pipeline).
- **Sub-needs get independent searches, not one blended query.** A single
  embedding of "trekking essentials and clothing" drifts toward whatever the
  catalogue holds most of. See [ARCHITECTURE.md](ARCHITECTURE.md#stage-1--intent--sub-needs).
- **Attribute provenance gates hard filtering, not ranking.** Only
  title-verified facts may exclude a product; inferred ones only nudge score.
  See [ARCHITECTURE.md](ARCHITECTURE.md#data-trust-tiers).
- **Generation has a fallback chain; embeddings don't.** A second key is the
  same model; a second provider is a different vector space. See
  [ARCHITECTURE.md](ARCHITECTURE.md#embeddings-have-no-fallback-chain).
- **Catalogue browsing reads the same in-memory list `/api/recommend`
  searches, not a second store.** A Postgres mirror was tried and removed —
  thousands of read-only rows don't earn back a service and a sync script.
  See [ARCHITECTURE.md](ARCHITECTURE.md#storage-one-in-memory-catalogue-two-access-patterns).
- **Single worker, by design, not yet.** Sessions are a process-local dict;
  multiple workers would split them. See [ARCHITECTURE.md](ARCHITECTURE.md#known-constraints).

## AI approach

Two LLM calls per request: **intent** (parses the query into a `ShoppingIntent`,
sub-needs and assumptions) and **rerank** (picks 3–5 candidates per group and
writes one reason each). Everything between them — hard filtering, vector
retrieval, deterministic pre-ranking — is plain Python, because arithmetic over
a few thousand rows must be exact, and because embeddings don't encode price.

Both the generation and embedding providers have keyless stand-ins
(`MockGeneration`, keyword rules; `HashingEmbedding`, hashed bag-of-words), so
the whole pipeline runs with no credentials — see mode 1 under
[Setup instructions](#setup-instructions). This proves the machinery, not
recommendation quality: `HashingEmbedding` has no IDF, so "cotton" and
"thermal" score alike.

**There is no eval harness.** `backend/eval/queries.yaml` holds a golden and
unseen query set; nothing runs it yet. This is a deliberate scope cut for this
pass, not an oversight — see [Future improvements](#future-improvements) #4.
Ranking quality is currently asserted by construction (conservative weights,
deterministic filters, a test that bounds how much the score adjustments can
move a candidate) rather than measured against labelled relevance judgements.

## Future improvements

Priority order — regressions first, then gaps:

1. **Fix the ambiguity/clarity-gate short-circuit.** A vague *first-turn* query
   (no session yet) raises `INVALID_QUERY` before the clarity gate that's
   supposed to handle it ever runs, because `app/services/intent.py`'s
   zero-sub-needs guard only tolerates empty sub-needs on a follow-up turn
   (`allow_empty_sub_needs=prior is not None`).
2. **Key retrieval's cross-sub-need dedup by `(sub_need, product_id)`, not
   `product_id` alone.** Two sub-needs whose searches surface the same product
   currently let only one of them keep it — this can starve or spuriously
   empty a semantically overlapping sub-need (the "trekking essentials" /
   "trekking clothing" shape).
3. **Add a similarity floor to retrieval and to the rerank fallback**, chosen
   empirically — right now `ranking.py`'s `build_groups()` pads an empty group
   with the closest-scoring candidates regardless of how weak that match is.
4. **Build the eval harness** (`eval/queries.yaml` exists; nothing runs it) —
   property assertions first, LLM-as-judge relevance pass second. Explicitly
   deferred, not attempted, in this pass.
5. **IDF weighting in `HashingEmbedding`** — the keyless mode's only defense
   against "cotton" outscoring "thermal" on a thermal-wear query.
6. **Redis-backed sessions**, to lift the single-worker constraint.
7. **Run sub-need reranking concurrently** instead of one combined prompt.
8. **Fix two known frontend bugs:** `ProductCard` checks `price_tier` against
   `"mid-range"`, which the backend never emits (it sends `"mid"`), so that
   badge never renders; and the streaming hook never wires an `onDone`
   handler, so `timings_ms`/`intent` arrive as `{}` on the client even though
   the backend sends both.
9. **Deploy and record the demo video** — the mock-data path needs no
   credentials; see [DEPLOYMENT.md](DEPLOYMENT.md).

**Built and tested:** the runtime pipeline, both API surfaces, streaming, the
frontend, key rotation across four providers, the synthetic catalogue, the
real catalogue, and the deployment configuration. 214 backend tests and 56
frontend tests, no network and no credentials required — 4 backend and 4
frontend currently fail; see [Pre-existing failures](ARCHITECTURE.md#how-this-is-tested)
in ARCHITECTURE.md for which and why.

**Verified against live APIs:** Gemini (generation and embeddings, 768 dims),
Groq and GitHub Models all answer. Cerebras returns 402 — the account needs
billing.

**Real catalogue:** built and committed. `backend/data/` holds 6,000 real
Amazon India products across 109 categories, embedded with `jina-embeddings-v3`
at 768 dims (`backend/data/embeddings.manifest.json`), built by
`scripts/ingest_enriched.py` from `backend/data/enriched.csv` — an
offline-enriched (translated, categorised, attribute-extracted) sample of the
source dataset, after dropping 94 rows with no resolved category. It maps onto
`Product` with no schema changes and re-verifies title-derived attributes with
the same `scripts/verify_attributes.py` gate the mock catalogue uses.

## Repository layout

```
backend/app/        API, services, providers, schemas — the runtime path
backend/scripts/    Profiling, verifiers, mock + real catalogue ingest, provider check
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
