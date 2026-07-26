# Deployment: Render (backend) + Vercel (frontend)

Status: **planning only**. Nothing in this document has been deployed, and no
network or build command has been run to produce it. It exists so someone can
execute a real deploy later without re-deriving these decisions. See the
closing checklist for what still blocks an actual deploy.

Files this plan produced: `backend/Dockerfile`, `backend/.dockerignore`,
`render.yaml` (repo root), `frontend/vercel.json`, this document.

This lives at the repo root rather than under `docs/` because `docs/` is
gitignored — a deployment plan nobody can read is not a deployment plan.

## 1. Prerequisites

- A Render account, with the repo connected (or `render.yaml` applied as a
  Blueprint).
- A Vercel account, with the repo connected.
- API keys for at least one generation provider and the embedding provider —
  see below. **Not currently held** (see checklist).
- Docker is only needed if you want to build the backend image locally to
  sanity-check it before pushing; Render builds it server-side from
  `backend/Dockerfile`.

### Backend environment variables

Real names, read from `backend/app/config.py:9-37` (pydantic-settings maps
each field to its uppercased name unless told otherwise):

| Variable | Config field | Default | Notes |
|---|---|---|---|
| `GEMINI_API_KEY` | `gemini_api_key` | `None` | Required for real embeddings — `_build_embedding` raises `ProviderUnavailable` if unset, because embeddings have no fallback provider (query vectors must share the catalogue's vector space). **Not required when `EMBEDDING_MODEL=hashing-bow-v1`**, the keyless lexical embedder used by the mock catalogue (§7). |
| `GROQ_API_KEY` | `groq_api_key` | `None` | Needed only if `groq` appears in the chain. A provider with no key is skipped, not fatal. |
| `CEREBRAS_API_KEY` | `cerebras_api_key` | `None` | Same. Cerebras is called over its OpenAI-compatible HTTP API. |
| `GITHUB_TOKEN` | `github_token` | `None` | GitHub Models. A **personal access token with the `models:read` scope**, not an API key — hence the different name. Free, low daily ceiling. |
| `GEMINI_API_KEYS` / `GROQ_API_KEYS` / `CEREBRAS_API_KEYS` / `GITHUB_TOKENS` | `*_api_keys`, `github_tokens` | `[]` | Comma-separated. Several credentials for one provider; a rate limit rotates to the next and retries. Merged with the singular form. |
| `GENERATION_CHAIN` | `generation_chain` | unset | Ordered, comma-separated, e.g. `gemini,cerebras,groq,github`. Overrides the two settings below. |
| `GENERATION_PRIMARY` | `generation_primary` | `"gemini"` | Legacy pair, used when `GENERATION_CHAIN` is unset. `"gemini"`, `"groq"`, `"cerebras"`, `"github"`, or `"mock"` — `mock` is the keyless rule-based provider (§7) and ends any chain it appears in. |
| `CEREBRAS_MODEL` | `cerebras_model` | `"llama-3.3-70b"` | Configurable so a model rename is an env change, not a code change. |
| `CEREBRAS_BASE_URL` | `cerebras_base_url` | `"https://api.cerebras.ai/v1"` | |
| `GITHUB_MODEL` | `github_model` | `"openai/gpt-4o-mini"` | GitHub Models ids are publisher-qualified (`openai/…`, `meta/…`, `mistral-ai/…`). |
| `GITHUB_BASE_URL` | `github_base_url` | `"https://models.github.ai/inference"` | |
| `GENERATION_FALLBACK` | `generation_fallback` | `"groq"` | Same constraint; set to empty/None to disable fallback. |
| `EMBEDDING_MODEL` | `embedding_model` | `"gemini-embedding-001"` | **Pinned to whatever built the committed embeddings.** Changing it without rebuilding `embeddings.npy` trips `ManifestMismatch` (`app/catalogue/index.py:49-53`) by design — do not "fix" that check. |
| `EMBEDDING_DIMS` | `embedding_dims` | `768` | Same constraint, checked at `app/catalogue/index.py:54-56`. |
| `DATA_DIR` | `data_dir` | `<repo>/backend/data` | In the container this resolves to `/app/data` (WORKDIR is `/app`, and the default is `Path(__file__).parent.parent / "data"` relative to `app/config.py`). Override to `/app/data/mock` for the mock-data variant (§6). |
| `CORS_ORIGINS` | `cors_origins` | `["http://localhost:5173"]` | Comma-separated string, split by `_split_origins` (`config.py:32-37`). Must include the deployed Vercel production domain (see §5b) — preview domains are covered separately. |
| `SESSION_TTL_SECONDS` | `session_ttl_seconds` | `1800` | How long a session survives in the in-memory store (`app/services/sessions.py`). |
| `LLM_TIMEOUT_SECONDS` | `llm_timeout_seconds` | `30.0` | Per-call timeout passed to both generation providers. |

`PORT` is also read, but by the Dockerfile's `CMD`, not by `Settings` — Render
sets it automatically and the container binds `${PORT:-8000}`.

### Frontend environment variables

Only one, from `frontend/.env.example:1`:

| Variable | Used at | Notes |
|---|---|---|
| `VITE_API_BASE_URL` | `frontend/src/lib/api.ts:3` (`import.meta.env.VITE_API_BASE_URL ?? ""`) | Set to the deployed backend's public URL in Vercel's project environment variables. Empty string falls back to same-origin, which is only correct when frontend and backend share a domain — they will not here. |

## 2. Backend on Render (Docker)

Render builds `backend/Dockerfile` using `backend/` as the Docker build
context (`render.yaml`: `dockerfilePath: ./backend/Dockerfile`,
`dockerContext: ./backend`).

Steps:

1. Push `render.yaml`, `backend/Dockerfile`, and `backend/.dockerignore` to
   the branch Render is watching.
2. In Render, create a Blueprint from the repo (picks up `render.yaml`), or
   create the web service manually with the same `dockerfilePath` /
   `dockerContext` / `healthCheckPath` values.
3. Set `GEMINI_API_KEY`, `GROQ_API_KEY`, `CORS_ORIGINS` in the Render
   dashboard (they're declared `sync: false` in `render.yaml`, i.e. Render
   will prompt for values rather than storing them in the file).
4. Deploy, then verify independently of the frontend:

   ```bash
   curl -s https://<backend-host>/api/health
   ```

   Expect `{"status": "ok"}` (`backend/app/api/routes_recommend.py:20-22`).
   If the service fails to start instead of serving this, check the deploy
   log for `ManifestMismatch` first (§5a).

   ```bash
   curl -s -X POST https://<backend-host>/api/recommend \
     -H 'content-type: application/json' \
     -d '{"query":"wireless headphones for office calls under 5000"}' | head -40
   ```

   This exercises the full non-streaming pipeline
   (`backend/app/api/routes_recommend.py:24-36`) including both API keys, so
   a clean response here means the deployment is functionally sound before
   the frontend is even involved.

## 3. Frontend on Vercel

1. Import the repo into Vercel, with `frontend/` as the project root.
   `frontend/vercel.json` supplies `buildCommand: npm run build`,
   `outputDirectory: dist` (Vite's default `outDir`, unmodified in
   `frontend/vite.config.ts`), `framework: vite`, and an SPA rewrite so
   client-side routes don't 404 on refresh.
2. Set `VITE_API_BASE_URL` to the Render backend's public URL, in Vercel's
   project environment settings, for the Production environment (and
   Preview, if preview deployments should also hit the real backend).
3. Deploy.
4. Add the resulting production domain (e.g. `https://<project>.vercel.app`
   or a custom domain) to the backend's `CORS_ORIGINS` and redeploy the
   backend, or the frontend will get CORS errors on every request (§5b).
5. Verify: open the deployed frontend, submit a query, confirm results
   render. This is a manual check — no scripted verification is meaningful
   here since it depends on the browser's CORS behaviour and (if streaming)
   incremental rendering, both covered next.

## 4. Why a single worker

`backend/app/services/sessions.py` is a **process-local, in-memory** TTL
dict (`self._data: dict[str, tuple[float, ShoppingIntent]]`, no shared
store). If Render (or any host) ran more than one worker process, a session
created by a request routed to worker A would not exist on worker B, so a
follow-up "refine this" request landing on worker B would get a 404-equivalent
"session not found" instead of continuity. The sessions module's own
docstring calls this out: "The deployment therefore runs `--workers 1`, and
that constraint is documented rather than discovered (spec 6)." The
Dockerfile's `CMD` hardcodes `--workers 1` for exactly this reason — it is
not a placeholder to bump up for throughput. The module also names the real
fix if concurrency is ever needed: Redis as a shared session store, not more
uvicorn workers.

## 5. Failure modes most likely to bite

### (a) `ManifestMismatch` at startup

`app/catalogue/index.py`'s `load_index()` compares the catalogue's build-time
manifest (`embeddings.manifest.json`) against the configured
`EMBEDDING_MODEL` / `EMBEDDING_DIMS` and raises `ManifestMismatch` — a
`RuntimeError` — if they disagree (`index.py:49-56`). Because
`app/main.py`'s lifespan calls `deps.get_pipeline()` eagerly at startup
(`main.py:27-30`, comment: "fails fast on a manifest mismatch rather than at
first query"), this surfaces as a failed deploy / crash-looping container,
not a runtime 500. Symptom: Render logs show `ManifestMismatch: catalogue
built with ... but configured embedding_model is ...`. Fix: rebuild the
committed embeddings against the configured model/dims, or fix the env var to
match what the committed catalogue was actually built with — **never** loosen
or remove the check; it exists specifically to stop query vectors and
catalogue vectors silently living in different vector spaces
(`ManifestMismatch` docstring, `index.py:16-21`).

### (b) CORS

`app/main.py:36-42` configures CORS with two independent allowances:

```
allow_origins=settings.cors_origins
allow_origin_regex=r"https://.*\.vercel\.app"
```

The regex covers Vercel preview deployments automatically — nothing to do
there. It does **not** cover the production domain if that domain is a
custom domain or otherwise doesn't match `https://.*\.vercel\.app` exactly
as a full-string regex match; the production/custom domain must be added to
`CORS_ORIGINS` explicitly (§2 step 3, §3 step 4). Symptom: browser console
shows a CORS error on the production frontend while previews work fine. Fix:
add the exact production origin to `CORS_ORIGINS` and redeploy the backend
(env var changes require a redeploy to take effect, since `Settings` is
constructed once via `get_settings()`'s `lru_cache`).

### (b2) Rate limits, and what the client sees

Free tiers are the limit this project reaches first. Two mechanisms cover it,
and they are not the same thing:

- **Key rotation** — several keys for one provider, advanced on a 429 and
  retried. Same model, same vector space, invisible to correctness. This is why
  embeddings may rotate keys but must never change provider.
- **The provider chain** — `GENERATION_CHAIN=gemini,cerebras,groq`, tried in
  order. Generation only.

When every key on every provider has refused, the API returns **429
`RATE_LIMITED` with `retryable: true`**, not a 503. A client can act on that
difference; a generic failure hides it. Anything that is not a rate limit — a
revoked key, a bad model name — fails immediately without rotating, because it
would fail identically on every key and burn the whole ring discovering that.

### (c) A proxy buffering the SSE stream

`/api/recommend/stream` (`app/api/routes_recommend.py:41-63`) is
implemented as fetch + `ReadableStream` on the client rather than
`EventSource`, specifically because `EventSource` is GET-only and the query
needs to go in the POST body (routes_recommend.py:47-50). The response
already sets `"X-Accel-Buffering": "no"` (`routes_recommend.py:62`) to stop
nginx-class proxies from buffering it. If a proxy between Vercel and Render
buffers anyway, the symptom is the whole SSE payload arriving as one block in
the Network tab instead of incrementally (assumption chips, then product
cards, arriving in stages). Fix, in order: confirm the header is actually
present on the live response (`curl -i`), then check for any intermediate
proxy/CDN that might be stripping or ignoring it. If streaming genuinely
cannot be made to work cross-origin within reasonable effort, the documented
fallback is to point the frontend at the non-streaming `/api/recommend`
JSON path instead (switch `InputPanel` back to `submit`) — a reliable
deployed app beats a broken stream.

## 6. Render free-tier cold start

Render's free web service tier spins the container down after roughly 15
minutes idle; the first request after that can take on the order of 50
seconds while it cold-starts (and, on this backend, re-runs the catalogue
load in the lifespan hook). This needs to be a conscious decision, made
**before** recording any demo video — either accept and narrate the cold
start, keep the service warm with a scheduled ping, or move to a host that
doesn't idle out (Fly.io is the noted alternative; it does not have this
free-tier idle behaviour).

## 7. Running and deploying with mock data — no API keys at all

A synthetic catalogue now exists at `backend/data/mock/`, built by
`backend/scripts/build_mock_catalogue.py`: 79 invented products across 14
categories, in the real catalogue schema, with a matching
`embeddings.manifest.json`. Rebuild it any time with:

```bash
cd backend && python scripts/build_mock_catalogue.py
```

Combined with two keyless providers, the whole application runs with no
credentials:

| Piece | Real | Keyless stand-in |
|---|---|---|
| Embeddings | `gemini-embedding-001`, 768 dims | `hashing-bow-v1`, 256 dims — hashed bag of words, real lexical overlap, no semantics |
| Generation | Gemini 2.5 Flash → Groq | `MockGeneration` — keyword rules; explanations assembled only from fields the candidate carries |

Locally:

```bash
cd backend && DATA_DIR=data/mock EMBEDDING_MODEL=hashing-bow-v1 \
  EMBEDDING_DIMS=256 GENERATION_PRIMARY=mock \
  uvicorn app.main:app --workers 1 --port 8000
```

Deployed, the same four variables (with `DATA_DIR=/app/data/mock`) give a
public demo that costs nothing to run and cannot exhaust a rate limit.
`backend/data/mock/` is small — a 6 KB catalogue and a 40 KB matrix — so it
ships in the image without any of the concerns in §8.

**What this is worth, stated plainly.** It proves the machinery: retrieval,
tier-gated filtering, grouping, streaming, error envelopes, deployment. It
proves nothing about recommendation quality. The products are invented, the
ASINs are fabricated so product links resolve to nothing, images are
placeholders, `hashing-bow-v1` matches words rather than meaning, and
`MockGeneration` matches keywords rather than reading a request. Anything
demoed this way must be labelled as such.

The manifest is what keeps the two modes from mixing: swapping `DATA_DIR` to
the mock catalogue without also setting `EMBEDDING_MODEL`/`EMBEDDING_DIMS`
raises `ManifestMismatch` at startup rather than serving nonsense (§5a).

## 8. What is NOT done yet (blocks a real deploy)

- No real catalogue is committed for production use — `backend/data/` today
  holds the raw ~640 MB source CSV
  (`amz_in_total_products_data_processed.csv`, confirmed via `du -sh`:
  `639M`) and a `profile.json`, not the built `catalogue.jsonl.gz` /
  `embeddings.npy` / `embeddings.manifest.json` that `app/catalogue/index.py`
  actually loads. Until those exist, the default `DATA_DIR` has no manifest to
  read and the container fails at startup — deploy the mock variant (§7) or
  wait for the real pipeline.
- The Kaggle dataset's licence has not been verified as clear for a public,
  deployed service. This must be resolved before deploying with the real
  catalogue rather than the mock one.
- No `GEMINI_API_KEY` or `GROQ_API_KEY` has been provisioned or set anywhere
  (Render dashboard, local `.env`, or otherwise).
- Neither service has actually been created in Render or Vercel; this
  document and the four config files are preparation, not a deployment.

None of these block the mock-data deployment in §7, which needs no catalogue,
no licence decision, and no keys. They block deploying the *real* one.
