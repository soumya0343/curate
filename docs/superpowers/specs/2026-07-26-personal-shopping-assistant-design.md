# Personal Shopping Assistant — Design

**Status:** revised after design review, ready for implementation planning
**Date:** 2026-07-26
**Context:** Confluxe Full Stack Engineer take-home. Deadline: 2026-07-27.

Companion document: [dataset.md](../../dataset.md) — source data analysis, defects, trust
hierarchy, and ingest rules. This spec references its conclusions rather than repeating them.

---

## 0. Governing principles

Every decision below traces to one of these. They are listed first because they resolve
most design questions without further argument.

1. **Example queries are evaluation cases, not catalogue boundaries.**
2. **Hard filters rely on trustworthy facts.** Source-grounded data may exclude a product.
3. **LLM inference improves ranking; it does not eliminate products.**
4. **Missing metadata beats fabricated metadata.**
5. **Catalogue and query embeddings must share one vector space.**
6. **Deterministic where the problem is deterministic.**
7. **The LLM goes where semantic reasoning genuinely adds value.**
8. **Measure before making quantitative claims.**
9. **Smallest end-to-end system that works well, before any infrastructure.**
10. **Licensing resolved before redistributing derived data.**

---

## 1. Problem

Users describe a shopping need in plain English. The assistant interprets intent — not
keywords — and recommends relevant products, grouped into categories, each with a reason
and a link.

The three assignment prompts (Hampta Pass trek, wedding traditional wear, anniversary
gifting hamper) are **golden evaluation queries**. They do not define scope, and the
catalogue is not built around them (principle 1). Generalisation is measured against
unseen queries — see [section 11](#11-evaluation).

Incomplete and ambiguous requests must be handled gracefully, with reasonable assumptions.

**Evaluation weighting**, which drives priorities: problem solving and engineering
judgement 35%, backend/frontend architecture and APIs 30%, AI and recommendation quality
25%, code quality and documentation 10%.

---

## 2. Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.11, FastAPI, Pydantic v2 |
| Frontend | React 18, TypeScript, Vite, Tailwind, shadcn/ui |
| Retrieval | numpy cosine over a precomputed embedding matrix |
| Generation (query time) | Gemini 2.5 Flash, one fallback provider |
| Generation (offline bulk) | Groq — ~30 RPM free tier vs Gemini's ~10, faster inference |
| Embeddings | `gemini-embedding-001`, 768-dim, float16, precomputed offline |
| Deploy | Vercel (frontend) + Render or Fly (backend), **single worker** |

**No vector database.** 20k products is a numpy matrix; cosine over 20k × 768 is ~10 ms and
stays viable past 100k rows. A vector DB here would be scale theatre.

---

## 3. Architecture

```
Browser — React SPA (Vercel)
    │  POST + fetch streaming
    ▼
FastAPI (Render / Fly, 1 worker)
    │
  api/          routers — HTTP concerns only, zero business logic
    ▼
  services/     pipeline · intent · retrieval · scoring · ranking · sessions
    ▼
  providers/    GenerationProvider  → gemini | groq  (+ fallback)
                EmbeddingProvider   → gemini-embedding-001  (NO fallback)
  catalogue/    CatalogueSource protocol → JSONCatalogue, numpy index
```

Two rules keep the boundaries real:

- Routers never call providers directly.
- Services never touch `Request` or `Response`.

### 3.1 Generation and embedding providers are separate protocols

This is a correctness boundary, not organisation.

**`GenerationProvider`** may fall back dynamically. Generated text does not need to live in
a shared vector space, so a Gemini rate-limit can fail over to Groq mid-request with no
consequence beyond slightly different phrasing.

**`EmbeddingProvider` must not fall back.** Query embeddings must come from the same model
and dimensionality as `embeddings.npy`. A dynamic swap would produce vectors in a different
space; cosine similarity would still return plausible numbers, results would be noise, and
**nothing would error** (principle 5).

Enforced structurally:

```python
# embeddings.npy ships with a sidecar manifest
{"model": "gemini-embedding-001", "dims": 768, "dtype": "float16", "built": "2026-07-26"}
```

The index refuses to load if the configured embedding model does not match the manifest.
Changing the embedding model means rebuilding the catalogue embeddings — a deliberate
offline operation, never a runtime fallback.

### 3.2 Generation fallback is two providers, not three

`Primary → one fallback → PROVIDER_UNAVAILABLE`.

Providers differ in structured-output support, JSON schema handling, context limits, error
semantics, and rate limits. Each additional provider multiplies prompt-compatibility
testing. The protocol stays extensible so Cerebras or others can be added later; building a
three-provider chain is not a good use of the deadline.

### Layout

```
backend/
├─ app/
│  ├─ main.py                 app factory, CORS, lifespan (load catalogue + vectors once)
│  ├─ config.py               pydantic-settings, env-driven
│  ├─ api/
│  │  ├─ routes_recommend.py  POST /api/recommend · POST /api/recommend/stream
│  │  └─ deps.py              DI: catalogue index, providers, session store
│  ├─ schemas/                ShoppingIntent, SubNeed, Candidate, Recommendation, StreamEvent
│  ├─ services/
│  │  ├─ pipeline.py          async generator — the orchestrator
│  │  ├─ intent.py            extraction, delta-merge, assumption tagging
│  │  ├─ retrieval.py         tier-A/B hard filters + per-sub-need vector search
│  │  ├─ scoring.py           deterministic pre-ranking + diversity  ← no LLM
│  │  ├─ ranking.py           LLM final rerank + grounded explanations
│  │  └─ sessions.py          in-memory TTL store (single worker)
│  ├─ providers/
│  │  ├─ generation.py        protocol + gemini · groq · stub
│  │  └─ embedding.py         protocol + gemini  (manifest-pinned)
│  ├─ catalogue/              loader.py (protocol + JSON impl), index.py (numpy cosine)
│  └─ core/                   logging.py, errors.py
├─ data/                      catalogue.jsonl.gz · embeddings.npy · embeddings.manifest.json
│                             category_map.json · url_validation.json
├─ scripts/                   profile_dataset.py · ingest.py · enrich.py · build_embeddings.py
├─ eval/                      queries.yaml · run_eval.py · reports/
└─ tests/

frontend/
├─ src/
│  ├─ hooks/useRecommendation.ts    streaming lifecycle, stage state
│  ├─ components/                   InputPanel · AssumptionChips · ResultGroup · ProductCard · RefineBar
│  ├─ lib/api.ts                    typed client
│  └─ types.ts                      mirrors backend schemas
```

---

## 4. Catalogue

Fully specified in [dataset.md](../../dataset.md). What the application consumes:

**~20,000 products**, sampled broadly and stratified across all 214 Amazon India
categories — *not* selected around the example queries (principle 1). Derived from
[Amazon India Products 2023](https://www.kaggle.com/datasets/asaniczka/amazon-india-products-2023-1-5m-products)
(1,589,160 rows), with INR prices and resolvable `amazon.in/dp/{asin}` links.

```jsonc
{
  "id": "B08XYZ1234",
  "title": "Wildcraft 45L Rucksack Water Resistant Trekking Backpack",
  "title_original": "…",                     // Devanagari source, when translated
  "description": "A 45-litre water-resistant rucksack for multi-day treks…",
  "category": "Rucksacks & Trekking Backpacks",   // source metadata, noisy — see below
  "price": 3499, "currency": "INR",
  "price_tier": "mid",                       // deterministic, cohort-relative percentile
  "rating": 4.3, "reviews": 212,
  "quality_score": 23.1,                     // stars × log1p(reviews)
  "attributes": {
    "capacity_l":  {"value": 45,            "source": "title_verified"},
    "water_resistant": {"value": true,      "source": "title_verified"},
    "product_type": {"value": "backpack",   "source": "inferred"},
    "use_case":    {"value": ["trekking"],  "source": "inferred"},
    "season":      {"value": ["winter"],    "source": "inferred"},
    "gender":      {"value": "unisex",      "source": "inferred"},
    "material":    {"value": null,          "source": null}
  },
  "image_url": "https://m.media-amazon.com/…",
  "product_url": "https://www.amazon.in/dp/B08XYZ1234"
}
```

Note `material` is `null`. The source title does not state it, so nothing is invented
(principle 4).

### 4.1 Trust tiers govern what may filter

| Tier | Fields | May hard-filter? |
|---|---|---|
| **A** — source-grounded | `price`, `id`, `rating`, `reviews`, `product_url` | **Yes** |
| **B** — title-verified | `capacity_l`, `water_resistant`, explicit `gender`, explicit `material` | **Yes**, only after passing a code verifier |
| **C** — LLM-inferred | `use_case`, `occasion`, `season`, `climate_suitability`, `gift_suitable`, inferred `gender`, `product_type` | **No — ranking only** |

Tier B is safe *because of the verifier*, not because it was labelled explicit. Extracted
values are regex-checked against the original title; failures are demoted to tier C and
logged. Verifiers run against `title_original`, never the translation, so a translation
artifact cannot manufacture a verified fact.

`categoryName` is preserved as source metadata and used for stratification and price-tier
cohorts, but never as a semantic filter — sleeping bags are filed under "Small Animals"
(dataset.md §3.1).

`price_tier` is computed offline from within-cohort percentiles, never by the LLM
(principle 6, dataset.md §5.5).

Distribution of `catalogue.jsonl.gz` is **gated on the licence question**
(dataset.md §1.1).

---

## 5. Pipeline

A single async generator in `pipeline.py`. The streaming route forwards its events; the
JSON route drains it and returns the final payload. **One implementation, two transports** —
and if streaming is cut under time pressure, the core is untouched.

Two LLM calls per query, regardless of request complexity.

### Stage 1 — Understand

One structured-output call. Input: the raw query, plus prior intent when `session_id` is
present.

```jsonc
{
  "intent": {
    "activity": "trekking", "destination": "Hampta Pass",
    "season": "late October", "duration_days": 7,
    "budget_max": null, "gender": null, "occasion": null
  },
  "sub_needs": [
    {"label": "Insulation layer",       "query": "warm insulated jacket for cold weather trekking"},
    {"label": "Rain & wind protection", "query": "waterproof windproof shell jacket"},
    {"label": "Trekking footwear",      "query": "ankle-support waterproof trekking boots"},
    {"label": "Backpack",               "query": "50-60L trekking rucksack multi-day"},
    {"label": "Sleeping system",        "query": "sleeping bag, insulated sleeping mat"},
    {"label": "Navigation & light",     "query": "headlamp, power bank"},
    {"label": "Trek accessories",       "query": "thermal socks, gloves, trekking poles"}
  ],
  "assumptions": [
    {"field": "climate",
     "value": "cold-weather conditions likely",
     "reason": "high-altitude trek in late October",
     "confidence": "medium", "editable": true}
  ],
  "clarifying_question": null,
  "confidence": 0.82
}
```

**Sub-need decomposition is the core AI decision.** A single vector for the whole request
is a blurry average — "trekking essentials and clothing" would skew toward whatever the
catalogue holds most of, and sleeping bags would never enter the candidate pool. Searching
per sub-need retrieves each need on its own terms, and result groups derive from the
request rather than being invented after the fact.

Simple queries ("black running shoes under ₹3,000") decompose to one sub-need, collapsing
gracefully to ordinary search.

**Assumptions must not assert unverifiable facts.** The model has no weather or geography
grounding, so it states an inference with confidence — *"assuming cold-weather trekking
conditions for late October"* — not *"Hampta Pass sits at ~4,200 m with sub-zero nights"*.
Assumptions influence ranking and are surfaced as editable chips; they never silently hard-filter
(principle 3).

Follow-up turns return an **intent delta** merged onto stored intent, not a fresh
extraction — "make it cheaper" sets `budget_max` and leaves everything else intact.

Emits `understood`. The UI renders intent and chips as soon as this stage completes,
showing useful intermediate state before retrieval and reranking finish. No latency figure
is claimed until measured (principle 8); the eval harness reports P50/P95 per stage.

### Stage 2 — Filter (deterministic, no AI)

The LLM decides *what* the constraint is; Python decides *which rows survive it*. Only
tier A and verified tier B may participate.

```python
def survives(p: Product, intent: ShoppingIntent) -> bool:
    # Tier A — source-grounded
    if intent.budget_max is not None and p.price > intent.budget_max:
        return False
    # Tier B — only when title-verified
    if intent.gender is not None:
        g = p.attributes["gender"]
        if g["source"] == "title_verified" and g["value"] not in (intent.gender, "unisex"):
            return False
    return True
```

Unstated constraints are skipped entirely. Inferred gender never excludes — it becomes a
ranking signal in Stage 4. There is no stock filter; the source dataset has no availability
field.

Two rules that prevent silent wrongness:

- **Only user-stated constraints cut.** LLM-*assumed* values become ranking boosts.
- **Empty pool widens.** Relax one step and report it: *"No trekking poles under ₹3,000 —
  showing the closest at ₹3,400."*

### Stage 3 — Retrieve per sub-need

Embed all sub-need queries in one batched call through the pinned `EmbeddingProvider`.
Cosine each against the filtered matrix, take top-8.

**Candidate count is at most `8 × number_of_subneeds`** — 56 for seven sub-needs — and is
typically lower after overlap and variant deduplication. No fixed figure is claimed
(principle 8).

Emits `searching`.

### Stage 4 — Deterministic pre-ranking (no AI)

Between retrieval and the LLM sits a plain-Python scoring pass. It exists so the LLM
becomes the final semantic judge rather than doing all the ranking, and so the rerank
prompt carries 4–5 candidates per sub-need instead of 8.

```
score = similarity                      # primary signal
      + w_quality  * normalised quality_score
      + w_attr     * verified attribute matches      (tier B)
      + w_inferred * inferred attribute matches      (tier C, smaller weight)
      - w_dup      * near-duplicate penalty
```

**Deliberately dumb in v1.** Similarity dominates; the rest are small bounded adjustments.
There is no relevance-judgement data to fit coefficients on, so free-floating tuned weights
would be guesses that silently distort ranking and are harder to debug than plain
similarity ordering. The eval harness ([section 11](#11-evaluation)) is what makes the
weights checkable — which is why it gets built *before* this stage is tuned.

The diversity penalty matters more than it looks: 35.8% of source rows are near-duplicate
variants (dataset.md §3.2), and ingest-time collapse does not catch variants listed under
different brand strings.

Every input here is deterministic and unit-testable.

### Stage 5 — Rerank and explain

One LLM call. Top 4–5 candidates per sub-need plus intent in; best 3–5 per group out, each
with a one-sentence reason grounded in the intent and the product's own attributes.

Three guards:

- **Every returned `product_id` is validated against the catalogue.** Hallucinated IDs are
  dropped and logged — the model never invents a product.
- **Explanations may only cite grounded facts.** Tier A and verified tier B may be stated
  as fact ("45 L, water-resistant"); tier C is phrased as suitability ("suited to
  cold-weather trekking"), never as specification.
- **Empty groups are reported, not hidden** — *"No rain shells in the catalogue under your
  budget."*

Emits `results`, then `done` with per-stage timings.

---

## 6. Conversation model

One rule makes single-turn, clarifying questions, and multi-turn refinement compose:
**never block on a question.**

1. Missing slots are filled with defaults and surfaced as editable **assumption chips**.
2. When a slot is both critical and un-guessable — gifting budget could mean ₹2,000 or
   ₹50,000 — one clarifying question appears *alongside* results, never instead of them.
3. Chip edits, follow-ups, and answers to the question are all the same call with a
   `session_id`, merged as an intent delta.

**Sessions are process-local.** An in-memory TTL store only works with one process: with
multiple workers, a session created on worker A is missing on worker B. The demo deployment
therefore runs a **single backend worker** (`uvicorn --workers 1`), and this is documented
rather than discovered. Redis-backed sessions are the production scaling path.

---

## 7. API

```
POST /api/recommend           full JSON response — the must-ship path
POST /api/recommend/stream    streamed stage events — enhancement
GET  /api/health              provider and catalogue readiness
```

### 7.1 Streaming transport

**Native `EventSource` supports GET only**, and the request body carries a
natural-language query, a `session_id`, and refinement state. Forcing that into query
parameters hits URL length limits and writes user queries into access logs.

**Chosen: `fetch()` + `ReadableStream` against a POST endpoint.** The endpoint stays
POST-native with a normal JSON body, and there is no `request_id` handoff to create,
correlate, or expire.

Costs, accepted: ~20 lines of manual SSE frame parsing on the client, and no automatic
reconnect. The second is a feature — a silently retried recommendation costs two LLM calls.

The alternative (POST returning a `request_id`, then `GET /api/recommend/{id}/stream`) is
recorded as a fallback if fetch streaming misbehaves on a target browser.

**Streaming must not complicate the core pipeline.** `POST /api/recommend` is the must-ship
implementation; streaming drains the same generator.

### 7.2 Errors

```jsonc
{"error": {"code": "RATE_LIMITED", "message": "…", "retryable": true}}
```

Codes: `INVALID_QUERY`, `PROVIDER_UNAVAILABLE`, `RATE_LIMITED`, `NO_RESULTS`, `INTERNAL`.

`NO_RESULTS` fires only when *every* sub-need comes back empty after relaxation — a query
about a domain the catalogue does not cover. Individually empty groups are a normal
response body, not an error.

OpenAPI docs come free at `/docs`.

---

## 8. Frontend

Single page, one column, four regions:

- **Input** — textarea plus example prompts as one-click chips.
- **Understanding strip** — assumption chips (editable, removable, showing confidence), the
  clarifying question inline with quick-answer buttons, and filter-relaxation notices.
- **Results** — one section per sub-need group; cards show image, title, price, price tier,
  rating, reason, and link. Empty groups render explicitly rather than disappearing.
- **Refine bar** — persistent: "make it cheaper", "more premium", free text.

State lives in one `useRecommendation` hook wrapping the streaming fetch. Components stay
presentational.

**Why streaming.** The pipeline takes several seconds. A blank spinner reads as broken;
staged reveal reads as thinking. Intent and chips land when Stage 1 completes, skeletons
follow, then cards fill per group.

---

## 9. Resilience and observability

**Generation fallback** — primary → one fallback → `PROVIDER_UNAVAILABLE`. Gemini's free
tier is ~10 RPM; a live demo will hit it.

**No embedding fallback, by design** (§3.1). A missing embedding provider is a hard failure,
which is correct: silently wrong retrieval is worse than a clear error.

**Structured JSON logs** — one line per stage carrying `request_id`, duration, candidate
counts, provider used, retries, and token usage.

**Timeouts** on every LLM call, surfacing `PROVIDER_UNAVAILABLE` rather than hanging an open
stream.

**Strict output parsing** — provider JSON validated into Pydantic models, one repair retry
on parse failure, then fail loudly.

---

## 10. Testing

- **filters** — budget and gender exclusion; unstated constraints skipped; inferred-gender
  products never excluded; relaxation on empty pool
- **verifiers** — tier-B attributes rejected when absent from the source title
- **index** — cosine ranking against a fixed fixture; **manifest mismatch refuses to load**
- **scoring** — deterministic pre-ranking order, diversity penalty
- **intent** — delta merge, assumption tagging
- **ranking** — hallucinated-ID rejection
- **pipeline** — end to end against a **stub provider**: no network, deterministic
- **API** — one smoke test via `TestClient`

The stub provider makes the whole pipeline testable with zero API keys, so CI needs no
secrets.

---

## 11. Evaluation

**Scheduled for v2.** The query set below is defined now because it shapes what "working
well" means, but the automated harness is not on the v1 critical path.

**v1 substitute:** the same query set is run manually during development and the demo, and
`eval/queries.yaml` is committed so the intent is legible and the harness is a small
addition rather than a design exercise. Per-stage timings are already emitted in the
structured logs (§9), so latency figures can be read off a manual run when needed.

**v2:** `eval/run_eval.py` executes the set and emits a markdown report per run into
`eval/reports/`.

Consequence of deferring, accepted: pre-ranking weights stay at their conservative untuned
defaults through v1 (§5, Stage 4), and the README reports no aggregate quality or latency
numbers rather than unmeasured ones (principle 8).

The query set:

**Golden queries** — the assignment's three:
- trekking essentials and clothing for a week at Hampta Pass in late October
- traditional wear for a friend's wedding in March
- premium gifting hamper for parents' 25th anniversary

**Unseen queries** — unrelated domains, to demonstrate the architecture generalises rather
than being engineered to pass three examples (principle 1):
- wireless headphones for office calls under ₹5,000
- beginner home workout equipment
- useful gift for someone moving into a new apartment
- comfortable shoes for daily walking
- desk accessories for working from home
- badminton equipment for a beginner
- travel essentials for a five-day trip

Each v2 report records: extracted intent, sub-needs, assumptions, candidate counts per
stage, groups returned, empty groups, and per-stage timings.

The unseen queries are the point of the set. They demonstrate that the architecture
generalises rather than being engineered to pass three known examples — which is why they
are defined alongside the golden queries rather than after them, even with the harness
deferred.

---

## 12. Build order

Sequenced so every prefix is shippable.

**Blocker, first:** verify the dataset licence (dataset.md §1.1). The repository is
**public**, so the mitigations there — `ATTRIBUTION.md`, no stored images, committed ingest
scripts — are part of the build. No derived catalogue file is committed until the licence
is checked.

**Must ship — the core recommendation flow**
1. Ingest: hygiene → near-dup collapse → price clip → stratified quota → tiered fill →
   deterministic price tiers
2. Conservative enrichment with tier-B verification, then embeddings + manifest
3. Intent extraction with sub-need decomposition
4. Deterministic hard filters (tier A + verified tier B)
5. Per-sub-need vector retrieval
6. Deterministic pre-ranking and diversity
7. LLM rerank with grounded explanations
8. `POST /api/recommend` (JSON)
9. React: input → grouped results
10. `ATTRIBUTION.md`, README, demo video

Step 6 ships with conservative untuned weights — similarity-dominant, small bounded
adjustments — and **stays untuned in v1**, because the eval harness that would justify any
change is deferred to v2 (§11). Guessed weights without measurement are worse than plain
similarity ordering.

**Then, in priority order**
11. Streaming / staged reveal
12. Assumption chips, editable
13. Refinement and sessions
14. Generation-provider fallback
15. Two deployments (§12.1)

**v2**
16. Eval harness (`eval/run_eval.py`) and reports
17. Pre-ranking weight tuning, measured against it

**Explicitly out of scope for the initial build:** Flipkart integration, a three-provider
fallback chain, catalogue-browsing UI, multi-source catalogue abstractions beyond the
single protocol already needed, and complex deployment architecture.

Keep interfaces extensible where that is cheap. Do not implement hypothetical scale before
the recommendation flow works well (principle 9).

### 12.1 On deployment

**Decision taken: two deployments** — Vercel (frontend) + Render or Fly (backend). The
justification is operational — independent logs, independent deploys, a real public API —
not architectural signalling. React and FastAPI already have a genuine HTTP boundary
regardless of hosting.

What this commits to, all of which belongs in the plan rather than being discovered late:

- **CORS** configured on the backend for the Vercel origin, including preview deployments.
- **`VITE_API_BASE_URL`** wired per environment, with local dev proxying to `localhost`.
- **Streaming across origins** — the fetch-streaming endpoint (§7.1) must be verified
  cross-origin, not only locally. This is the most likely thing to break.
- **`--workers 1`** on the backend (§6), which is a deployment setting, not a code detail.
- **Cold starts.** Render's free tier idles out after ~15 minutes, so first load can take
  ~50 s. Either state this in the README or use Fly, which behaves better. Worth deciding
  before the demo video is recorded.

**A reliable deployed application is worth more than deployment sophistication.** If the
cross-origin streaming path proves fiddly, ship the JSON endpoint deployed and correct
rather than a broken stream.

---

## 13. Known limitations

- **No real descriptions in the source data.** Descriptions are LLM-generated from titles,
  so the catalogue reasons at "insulated jacket for cold-weather trekking", never "rated to
  −12 °C".
- **Sparse sub-needs.** Sleeping bags (47), trekking poles (19), sleeping mats (15) are
  genuinely thin across all 1.5M source rows. Some golden-query groups will legitimately
  return empty — the honest consequence of query-agnostic sampling.
- **Category metadata is noisy.** Stratification gives nominal taxonomy coverage, not
  guaranteed semantic coverage of any domain.
- **Sessions are process-local**, so the deployment runs one worker.
- **Catalogue is a 2023 snapshot.** Prices and availability drift; URLs are spot-checked at
  ingest, not exhaustively validated, and resolvability is reported as a sampled rate.
- **Free-tier rate limits.** The fallback chain mitigates but does not eliminate them.
- **Pre-ranking weights are unfitted and unmeasured in v1.** Chosen conservatively,
  similarity-dominant. The eval harness that would justify tuning them is v2.
- **No aggregate quality or latency numbers in v1.** Per-stage timings exist in the logs,
  but nothing is claimed in aggregate without the harness to measure it.
- **Public repo, derived Amazon data.** Mitigated by attribution, no stored images, and
  committed provenance — but the underlying rights question is acknowledged, not resolved
  (dataset.md §1.1).

---

## 14. Future improvements

- Redis-backed sessions and horizontal scaling
- A real vector store once the catalogue passes ~100k products
- Learning-to-rank from click-through, replacing LLM reranking in the hot path
- Graded relevance judgements over the eval set, turning recommendation quality into a
  tracked metric and giving the pre-ranking weights something to be fitted on
- Multi-source catalogue federation behind the existing `CatalogueSource` protocol
