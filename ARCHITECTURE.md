# Architecture

Curate turns a natural-language shopping request into grouped, explained product
recommendations. This document covers how, and — more usefully — why each
decision went the way it did.

The system is two pipelines. An **offline** one turns 1.59M raw CSV rows into a
~20k-product catalogue plus an embedding matrix. A **runtime** one turns a query
into recommendations against those artifacts. They meet at three files in
`backend/data/` and nowhere else.

### Where things are documented

| Document | Covers |
|---|---|
| [README.md](README.md) | What it does, API, setup, env, troubleshooting |
| **this file** | Runtime design, trust tiers, why each decision went this way |
| [frontend/README.md](frontend/README.md) | Streaming state machine, SSE parsing, component rules |
| [docs/dataset.md](docs/dataset.md) | The source data and every defect measured in it |
| [docs/taxonomy.md](docs/taxonomy.md), [docs/category_tiers.md](docs/category_tiers.md) | Category normalisation |
| [docs/superpowers/plans/](docs/superpowers/plans/) | Implementation plans, task by task |

## A request, end to end

*"3 days trekking in Manali in December, under ₹8,000"*

| Stage | What happens |
|---|---|
| **intent** | Model returns `activity: trekking`, `destination: Manali`, `duration_days: 3`, `budget_max: 8000`. It does **not** return `gender` — nobody said. Season is inferred, so it lands in `assumptions` as *"cold-weather conditions likely"*, confidence medium, not as a fact. Sub-needs come back as `Insulation`, `Footwear`, `Daypack`. |
| **filter** | `price > 8000` excluded — price is source-grounded, so it may exclude. Gender skipped: unstated. ~20k rows narrow to whatever survives. |
| **retrieve** | Three embeddings, not one. `Insulation` finds jackets, `Daypack` finds rucksacks. A single vector for the whole sentence would have found neither well. Top 8 each, unioned and deduped by product id — up to 24 candidates, usually fewer. |
| **prerank** | Scored, and the four colour variants of one fleece are collapsed to one by the shared `variant_key`. Top 5 per sub-need survive. |
| **rerank** | Model picks 3–5 per group and writes a reason each. It may say *"suited to cold-weather trekking"*; it may not say *"rated to −12°C"* unless that string is in the title. Any id it invents is dropped on the way out. |
| **response** | Three groups in the order the sub-needs came back. If `Daypack` had no decent candidate, it returns empty with a reason rather than vanishing. |

Now the same request again with `session_id` and the text *"make it cheaper"*:
only `budget_max` changes, everything else is carried forward by
`ShoppingIntent.merge()`, and the whole pipeline re-runs against the tighter
constraint.

## The runtime pipeline

One request runs five stages. All of them live in a single async generator,
[app/services/pipeline.py](backend/app/services/pipeline.py) — the streaming
route forwards its events, the JSON route drains them through `collect()`. One
implementation, two transports; streaming can be removed without touching the
core.

```
query
  │
  ├─ 1. intent     LLM   → ShoppingIntent + sub-needs + assumptions   ─┐ event: understood
  │
  ├─ 2. filter     code  → row subset surviving hard constraints       │
  ├─ 3. retrieve   vec   → top-8 per sub-need, unioned, deduped       ─┤ event: searching
  │
  ├─ 4. prerank    code  → top-5 per sub-need, variant-penalised       │
  ├─ 5. rerank     LLM   → 3-5 picks per group + one reason each      ─┤ event: results
  │                                                                    │
  └─ timings                                                          ─┘ event: done
```

Every stage logs one structured JSON line with `request_id` and `duration_ms`,
and the final `done` event carries per-stage timings — so a slow request is
attributable without a profiler.

### Stage 1 — Intent → sub-needs

[app/services/intent.py](backend/app/services/intent.py)

The core AI decision is **decomposition**. "Trekking essentials and clothing"
becomes two sub-needs, each with its own search phrase, and each sub-need becomes
one result group. Groups therefore derive from the request rather than being
invented after the fact.

The prompt is constrained hard in three places:

- `budget_max` and `gender` are set **only if stated**. The model never guesses a
  budget — the difference between a ₹2,000 and a ₹50,000 gift is not inferable.
- No unverifiable facts. The model has no weather or geography data, so
  *"cold-weather conditions likely"* is allowed and *"sub-zero nights at 4,200 m"*
  is not.
- Every unstated judgement goes into `assumptions`, which the UI renders as
  editable chips.

A `clarifying_question` may come back, but never blocks: results are always
returned alongside it.

Parsing is deliberately tolerant — malformed assumptions are dropped rather than
failing the request. Zero usable sub-needs is the one hard failure, since there
is nothing to search for.

**Follow-ups** merge rather than replace. On a request carrying a `session_id`,
the prior intent is injected into the prompt and the model returns only what
changed; `ShoppingIntent.merge()` overwrites with non-None delta fields only. So
*"make it cheaper"* sets a budget and leaves the destination, season and gender
intact.

### Stage 2 — Hard filters

[app/services/retrieval.py](backend/app/services/retrieval.py)

The LLM decides *what* a constraint is. This module decides *which rows survive
it*, because arithmetic over thousands of rows must be exact and testable — and
because embeddings do not encode price.

Filtering obeys the trust tiers (below). Price is source-grounded, so
`budget_max` excludes directly. Gender excludes only when title-verified: an
enrichment mistake must degrade ranking, never hide a product. Unstated
constraints are skipped entirely.

**Empty results widen rather than fail.** If a budget filters everything out, it
is relaxed by 1.25× and the user is told; if that still yields nothing, budget is
dropped and the user is told that instead. Every relaxation surfaces in the
response as a visible notice — the system never quietly ignores a constraint.

### Stage 3 — Per-sub-need retrieval

Each sub-need's search phrase is embedded and cosine-searched against the
filtered subset, top 8 each. Vectors are L2-normalised at build time, so cosine
is a plain dot product; search is a NumPy matmul over the subset rows with an
`argpartition` top-k. No vector database — at ~20k × 768 fp32 the matrix is
~60 MB and the search is sub-millisecond, so a database would add operational
weight and buy nothing.

Results union across sub-needs and deduplicate by product id, keeping the highest
similarity and the sub-need that produced it. Candidate count is at most
8 × sub-needs, usually fewer after overlap.

### Stage 4 — Deterministic pre-ranking

[app/services/scoring.py](backend/app/services/scoring.py)

This stage exists to make the LLM the final semantic *judge* rather than the
entire ranker, and to cut the rerank prompt from 8 candidates per sub-need to 5.

```
score = similarity
      + 0.10 × normalised quality score
      + 0.08 × (any intent term matches a verified attribute)
      + 0.04 × (any intent term matches an inferred attribute)
      − 0.15 × (title-variant already seen in this group)
```

Weights are deliberately conservative and similarity dominates. There are no
relevance judgements to fit against, so tuned coefficients would be guesses that
silently distort ranking and are harder to debug than plain similarity order.

Two properties matter:

- **Sub-needs are ranked independently.** A strong sub-need cannot starve a weak
  one — every group the user asked for gets its own shot at the LLM.
- **Near-duplicates are demoted, not dropped.** 35.8% of qualifying source rows
  share a title prefix with another row ([docs/dataset.md](docs/dataset.md) §3.2).
  Demotion means a sub-need whose entire candidate pool is colour variants of one
  product still returns something.

Variant detection uses the first five title tokens
([app/core/text.py](backend/app/core/text.py)). Amazon India titles are
brand-first and keyword-dense — five tokens reaches the product type on most
listings while leaving the colour/size word outside the key. This function is
shared with offline ingest by design: ingest keeps one representative per variant
family, and runtime uses the same key as a second line of defence. Two divergent
implementations would mean the runtime penalising groupings the catalogue never
formed.

### Stage 5 — LLM rerank and explain

[app/services/ranking.py](backend/app/services/ranking.py)

The model picks 3–5 per group and writes one sentence each. Three guards make
this safe to ship:

1. **Every returned `product_id` is validated against the candidate pool.**
   Hallucinated ids are dropped silently — a recommendation that doesn't exist
   in the catalogue can never reach the UI.
2. **Explanations may cite only grounded facts.** The candidate lines passed to
   the model carry verified attributes explicitly labelled. Anything else must be
   phrased as suitability (*"suited to cold-weather trekking"*), never as a
   specification (*"rated to −12°C"*). Weights, temperature ratings and
   dimensions are forbidden unless they appear in the product title.
3. **Empty groups are reported, not hidden.** Output iterates the original
   sub-needs in order, whether or not the model returned picks. A group with no
   good candidate comes back empty with a reason. An honest empty group beats a
   bad recommendation.

## Data trust tiers

The single most important rule in the system, and it governs both pipelines.
Every product attribute carries a `source`:

| Tier | `source` | May hard-filter | May rank | May be stated as fact |
|---|---|---|---|---|
| A — source-grounded (price, rating, reviews, URLs) | n/a | yes | yes | yes |
| B — extracted **and** verified against the original title | `title_verified` | yes | yes | yes |
| C — inferred by enrichment | `inferred` | **no** | yes | no |
| — absent | `None` | no | no | no |

`Product.verified(name)` returns a value only at tier B; `Product.attr(name)`
returns anything. Any code path that excludes a product must use `verified()`.
The asymmetry is the point: a wrong inferred attribute costs a slightly worse
ranking, while a wrong hard filter makes a product invisible with no way for the
user to discover the mistake.

Verification runs against `title_original`, never a translation — a translation
artifact must not be able to manufacture a verified fact.

Corollary: **missing metadata beats fabricated metadata.** Gender is unknown for
roughly half the catalogue, and that is recorded as unknown.

## Providers

[app/providers/](backend/app/providers/)

**Generation** runs behind a `FallbackChain`: primary → one fallback →
`ProviderUnavailable`. Deliberately two providers, not three — each additional
one multiplies prompt-compatibility testing across differing structured-output
support and error semantics. Failover is logged with the failing provider and
error.

### Embeddings have no fallback chain

Query vectors must come from the same model and dimensionality as the catalogue
matrix. A dynamic swap would put them in a different vector space, cosine would
still return entirely plausible-looking numbers, and every result would be noise
with nothing to debug against. So a missing embedding provider is a hard failure,
and `EMBEDDING_MODEL` / `EMBEDDING_DIMS` are pinned config.

This is enforced at startup. `load_index()` compares the configured model and
dims against `embeddings.manifest.json` and raises `ManifestMismatch` if either
differs; `CatalogueIndex.__init__` additionally refuses a product count that
doesn't match the matrix row count. Both fail loudly at boot, not at first query.

Both providers have deterministic stub implementations, so the whole pipeline is
testable with no network and no API keys — CI needs no secrets.

## Frontend

[frontend/src/](frontend/src/) — details in [frontend/README.md](frontend/README.md)

```
App.tsx                     stage-driven layout
hooks/useRecommendation.ts  status + stage machine, session id, partial state
lib/api.ts                  fetch client, SSE frame parser, ApiFailure
components/                 InputPanel, AssumptionChips, ResultGroup,
                            ProductCard, RefineBar
types.ts                    mirrors backend/app/schemas/response.py
```

The default submit path is streaming. `understood` arrives long before results,
so assumption chips and the clarifying question render while retrieval and
reranking are still running — the wait is filled with the system's reasoning
rather than a spinner.

SSE parsing keeps an incomplete trailing frame in the buffer rather than
discarding it, and skips malformed payloads instead of failing the stream.

`types.ts` is hand-mirrored from the backend response schema. Field names are
kept identical so drift shows up as a type error rather than an undefined at
runtime.

## Backend layout

```
app/main.py            app factory, CORS, AppError handler, lifespan warm-up
app/config.py          pydantic-settings; pinned embedding config
app/api/deps.py        provider construction, lru_cached pipeline singleton
app/api/routes_*.py    HTTP surface, error-code → status mapping
app/schemas/           intent, product, response models
app/providers/         generation + embedding, real and stub
app/catalogue/         gzipped-JSONL loader, NumPy index, manifest check
app/services/          intent, retrieval, scoring, ranking, sessions, pipeline
app/core/              errors, structured logging, shared title normalisation
```

Dependencies run inward: `app/core/` imports nothing of ours, and the offline
scripts import runtime code rather than the reverse. That is why `variant_key`
lives in `app/core/text.py` and not in `scripts/`.

The catalogue and matrix load once in the FastAPI lifespan hook, not per request
— and a manifest mismatch therefore kills the process at boot.

## Errors

[app/core/errors.py](backend/app/core/errors.py)

All errors are `AppError` subclasses carrying `code`, `retryable` and
`http_status`, and serialise to one envelope shape:

```json
{ "error": { "code": "PROVIDER_UNAVAILABLE", "message": "...", "retryable": false } }
```

The pipeline catches `AppError` and emits it as an `error` event; the bare
`except` beneath it emits a generic `INTERNAL` envelope, so a traceback never
reaches the client. Note that empty result *groups* are not an error — they are a
normal response body.

## How this is tested

Both providers have stub implementations, so the entire pipeline runs in tests
with no network and no API keys — CI needs no secrets, and the suite is fast
enough to run on every save.

`StubGenerationProvider` returns a scripted list of dicts and records the prompts
it was given, so a test can assert on what the model was actually asked.
`StubEmbedding` hashes text to a deterministic vector: same text, same vector;
different text, different vector. That is the only property retrieval tests need.

What this buys, and what it doesn't: the orchestration, the filters, the scoring
arithmetic, the id validation and the error paths are all covered exactly.
Prompt quality is not — no stub can tell you whether the model decomposes a real
request sensibly. That gap is why the prompts carry their rules explicitly and
why the ranking stage validates rather than trusts.

## Known constraints

- **Single worker.** `SessionStore` is a process-local TTL dict (30 min default).
  With multiple workers, a session created on one is missing on another, and
  refinement breaks. The deployment runs `--workers 1`. Redis is the production
  path — this is a documented constraint, not a discovered one.
- **No database.** The catalogue is files. Below ~100k products this is faster
  than a vector database and has no operational surface.
- **Catalogue rebuild is coupled to embedding config.** Changing the model or
  dims requires re-embedding all ~20k products before the app will start.
- **No relevance evaluation.** There is no labelled judgement set, so ranking
  quality is asserted by construction (conservative weights, deterministic
  filters) rather than measured. This is also why the scoring weights are small.

## Offline pipeline

[docs/dataset.md](docs/dataset.md) and
[docs/superpowers/plans/2026-07-26-catalogue-pipeline-v2.md](docs/superpowers/plans/2026-07-26-catalogue-pipeline-v2.md)
are the source of truth. In outline:

```
1,589,160 CSV rows
  → hygiene gate        price > 0, title length, informativeness
  → category map        214 Devanagari category names → English, no hardcoded literals
  → variant collapse    one representative per title-prefix family
  → quality score       rating × review-count confidence
  → price tiers         cohort-relative, not global thresholds
  → category quota      stratified selection to ~20k
  → enrichment          conservative attribute extraction, LLM-assisted
  → verification        tier-B claims checked against title_original
  → embeddings          gemini-embedding-001 @ 768, L2-normalised
  → catalogue.jsonl.gz + embeddings.npy + embeddings.manifest.json
```

**Line order is a contract.** Row *n* of the JSONL is row *n* of the matrix.
Nothing may reorder one without the other, which is why `CatalogueIndex` asserts
the counts match.

Built so far: `scripts/profile_dataset.py` (reproducible EDA backing every figure
in `docs/dataset.md`, streaming the 670 MB CSV with only the standard library)
and `scripts/verify_attributes.py` (tier-B verifiers). The remaining ingest
stages are in progress, so the three artifacts above are not yet in
`backend/data/`.

## Where this goes next

Redis-backed sessions to lift the single-worker constraint. A labelled relevance
set, so ranking weights can be fitted instead of assumed. Richer refinement —
editing an assumption chip directly rather than typing a follow-up. Broader
catalogue coverage as the ingest quota loosens.
