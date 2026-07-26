# Curate — frontend

React UI for the shopping assistant. Takes a plain-English request, streams the
backend's reasoning as it happens, and renders recommendations grouped by need.

Backend and pipeline docs: [../README.md](../README.md), [../ARCHITECTURE.md](../ARCHITECTURE.md).

## Running

```bash
npm install
cp .env.example .env
npm run dev          # http://localhost:5173
```

The backend must be running on `http://localhost:8000`.

| Command | Does |
|---|---|
| `npm run dev` | Vite dev server with HMR |
| `npm run build` | `tsc -b` then production build |
| `npm run preview` | Serve the built output |
| `npm run lint` | Oxlint |
| `npx vitest run` | Tests — no `npm test` script yet |

## How it reaches the backend

Two paths, and which one you get depends on `.env`:

- **`VITE_API_BASE_URL` set** (what `.env.example` does) — requests go straight
  to `http://localhost:8000`, cross-origin. The backend's `CORS_ORIGINS` must
  include `http://localhost:5173`, which it does by default.
- **`VITE_API_BASE_URL` empty or unset** — requests are relative, and the Vite
  dev proxy in [vite.config.ts](vite.config.ts) forwards `/api` to port 8000.
  Same-origin, no CORS involved.

Either works in dev. The proxy exists so the app can be served from the same
origin as the API in a deployment that wants that.

## Streaming is the default path

`InputPanel` submits through `submitStreaming`, not the plain JSON call. Both
exist in [src/hooks/useRecommendation.ts](src/hooks/useRecommendation.ts) —
`submit` / `refine` use `POST /api/recommend` and block until the whole pipeline
finishes; `submitStreaming` reads `POST /api/recommend/stream`.

The point of streaming is that `understood` lands well before `results`. So the
assumption chips and the clarifying question render while retrieval and reranking
are still running, and the wait is filled with what the system is thinking rather
than a spinner.

Two pieces of state track this:

- `status` — `idle | loading | ready | error`, used by the non-streaming path.
- `stage` — `idle | understanding | searching | ranking | ready | error`, driven
  by the SSE events, and what the streaming UI actually renders against.

`partial` holds the assumptions and clarifying question from the `understood`
event, before groups exist.

## SSE over POST

Native `EventSource` is GET-only. The request body carries a free-text query plus
session state — in a URL that hits length limits and writes user queries into
access logs. So [src/lib/api.ts](src/lib/api.ts) uses `fetch` +
`ReadableStream` and parses frames by hand.

Two things the parser has to get right, both covered in
[src/lib/stream.test.ts](src/lib/stream.test.ts):

- **Chunk boundaries.** A network chunk can split a frame mid-way. The reader
  slices at the last `\n\n`, hands the complete part to `parseSseFrames`, and
  keeps the remainder for the next chunk.
- **Malformed payloads.** A frame with unparseable JSON is skipped, not thrown —
  one bad frame must not kill the stream.

## Refinement

Every response carries a `session_id`, held in a ref. `refine` sends the next
query with it, and the backend merges the delta onto the prior intent — so
"make it cheaper" keeps the destination and season.

Two entry points: the quick chips and free-text box in `RefineBar` below the
results, and the answer box in `AssumptionChips` when the backend asked a
clarifying question. Both call `refine`.

## Components

```
App.tsx                 stage-driven layout: input → chips → relaxations → groups → refine bar
InputPanel.tsx          textarea, submit, three one-click example queries
AssumptionChips.tsx     what the model inferred, with confidence; clarifying-question form
ResultGroup.tsx         one sub-need = one section
ProductCard.tsx         image, INR price, tier, rating, and the model's reason
RefineBar.tsx           sticky follow-up bar
```

Design rules worth keeping:

- **Empty groups render.** A sub-need with no good match shows its
  `empty_reason` in a dashed box. Hiding the section would make a real gap in
  the catalogue look like it was never asked for.
- **Assumptions are visible and labelled with confidence.** The `reason` is on
  the chip's `title` attribute.
- **Relaxation notices render.** If the backend had to widen a budget, the user
  is told in an amber banner.
- **Rating only shows when `reviews > 0`.** Two thirds of source rows have no
  reviews, so a bare "0.0" would be misinformation.
- **Prices use `Intl.NumberFormat("en-IN")`**, not string concatenation — Indian
  digit grouping is 2,2,3, so ₹1,25,000, not ₹125,000.

## Types

[src/types.ts](src/types.ts) mirrors `backend/app/schemas/response.py`. Field
names are kept identical, so backend drift surfaces as a type error rather than
an `undefined` at runtime. If you change a response model on the backend, change
this file in the same commit.

## Tests

Vitest + Testing Library, jsdom environment (configured in
[vite.config.ts](vite.config.ts), not a separate config file).

```
src/lib/api.test.ts                    recommend(): success, session id, ApiFailure code
src/lib/stream.test.ts                 parseSseFrames(): multi-frame, incomplete tail, bad JSON
src/hooks/useRecommendation.test.ts    submit/refine: status, response, session reuse, errors
src/components/AssumptionChips.test.tsx  chips, empty render, clarifying question + answer
```

`fetch` is stubbed throughout. No backend, no API keys.

Gaps worth knowing: `recommendStream` itself has no test — only the frame parser
it delegates to. The hook's tests cover `submit` and `refine`, not
`submitStreaming`, which is the path the UI actually uses.
