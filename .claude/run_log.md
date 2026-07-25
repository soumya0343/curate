# Run Log — Personal Shopping Assistant

Append-only record of everything that happens on this project: decisions, blockers,
failures, dead ends, fixes, and verification results. Written for a future reader with no
memory of this session.

**Conventions**
- Newest entries at the bottom. Never rewrite history — correct with a follow-up entry.
- Every entry carries a status: `DECISION` · `BLOCKER` · `RESOLVED` · `FAILURE` · `SUCCESS` · `NOTE`
- Failures are recorded even when trivially fixed. The dead end is the useful part.
- Quote exact error text. Paraphrased errors are not searchable.

---

## Phase: Design (2026-07-25 → 2026-07-26)

### 2026-07-25 · NOTE · Requirements extracted from PDF
`Full Stack Engineer Take Home Assignment.pdf` had no extractable text layer via standard
tooling. `pdftoppm`, `pdftotext`, `mutool`, `qpdf`, `pypdf`, and `PyMuPDF` were all absent;
raw zlib stream extraction returned font tables, not text.

**Solution that worked:** macOS PDFKit via JXA —
```bash
osascript -l JavaScript -e 'ObjC.import("Quartz"); ...doc.string'
```
Worth remembering: `/usr/bin/python3` has no `Quartz` module, but `osascript` reaches
PDFKit without any install.

### 2026-07-25 · DECISION · Stack
FastAPI + React (Vite) over Next.js full-stack. Chosen for visible backend layering against
a 30% "architecture & APIs" weighting. Cost: two run commands, two deploys.

### 2026-07-25 · DECISION · Retrieval architecture
Sub-need decomposition (spec option C) over single-vector search. A single vector for
"trekking essentials and clothing" is a blurry average that skews toward whatever the
catalogue holds most of — sleeping bags would never enter the candidate pool.

### 2026-07-26 · FAILURE · Two empty CSV exports
`amz_in_total_products_data_processed-selected-columns.csv` and its `(1)` copy were both
4,445,755 bytes, 444,567 rows, and **entirely blank** — header plus commas, zero non-empty
data lines. Byte-identical to each other.

Root cause was upstream: a column-selection step producing an all-NaN frame (a `reindex`
with mismatched names, or a merge with no key overlap — both fill NaN silently rather than
raising). Resolved by using the raw download `amz_in_total_products_data_processed.csv`
(670 MB, 1,589,160 rows) and dropping the preprocessing step entirely — column selection is
one line inside `ingest.py` anyway.

**Lesson:** a separate preprocessing pass before ingest is a step that can only introduce
bugs. Verify row *content*, not row count.

### 2026-07-26 · RESOLVED · No pandas, no SSL certs in this Python
`ModuleNotFoundError: No module named 'pandas'` — all profiling was done with stdlib
`csv.DictReader` streaming, which handles 670 MB without loading it into memory.

`urllib` link checks failed with `<urlopen error [SSL: CERTIFICATE_VERIFY_FAILED]>`
(macOS system Python has no cert bundle). Switched to `curl` for liveness checks.

### 2026-07-26 · FAILURE · Self-inflicted: hand-typed Devanagari category names
An early profiling run reported men's shoes at **0 qualifying rows**. The category actually
has 2,236. Cause: category strings copy-pasted from terminal output differed from the
file's by an invisible joiner character, so the literal matched nothing — silently, with no
error.

**This shaped the design.** `ingest.py` selects categories by English name through the
committed `category_map.json`, keyed on strings read verbatim from the CSV. Recorded in
dataset.md §3.8 and enforced in the plan.

**Lesson:** a silent zero-match on invisible character differences ships a broken catalogue
that looks exactly like a retrieval bug.

### 2026-07-26 · SUCCESS · Dataset profiling (all figures measured, not assumed)
```
rows                     1,589,160     nulls, any column           0
asin uniqueness          100%          productURL == /dp/{asin}    100%
Latin-script titles      258,896       categories                  214
hygiene-gated pool       179,049       categories with >=80        151
price <= 0               5.79%         listPrice == 0              66.55%
reviews == 0 (Latin)     67.7%         near-dup variants           35.8%
link sample              24/24 images 200, 24/24 product URLs 200
```

### 2026-07-26 · NOTE · Five dataset defects that changed the design
1. **Category labels lie.** "Sports, Fitness & Outdoor" is swimming and team sports —
   897 football, 283 cricket, 3 "trek", 0 headlamps. Sleeping bags are filed under
   "Small Animals"; first aid under "Software". → `categoryName` used for stratification
   and price cohorts only, never as a semantic filter.
2. **35.8% near-duplicate variants.** Watch straps: 673 rows sharing a title prefix. →
   collapse at ingest *and* a diversity penalty at rank time.
3. **Gender unknown for ~50%.** → four-state gender; `unknown` never filtered out.
4. **Price outliers to ₹620,000**, 268 rows over ₹1L. → clip above cohort p99.5.
5. **Genuinely sparse sub-needs.** Sleeping bags 47, trekking poles 19, sleeping mats 15
   across all 1.5M rows. → honest empty groups, not padding.

### 2026-07-26 · DECISION · Design review — 18 points, 16 accepted as stated
User review of the first spec. Four caught real defects:
- **Provider split.** The single `LLMProvider` fallback chain would have failed Gemini
  embeddings over to Groq, putting query vectors in a different space from
  `embeddings.npy`. Cosine would still return plausible numbers; results would be noise;
  **nothing would error.** → separate protocols, manifest pin, no embedding fallback.
- **EventSource is GET-only** — the query is natural language plus session state. →
  fetch + ReadableStream over POST.
- **Licence sequencing contradiction** — build step 1 committed `catalogue.json` while
  limitations said licence unverified. → promoted to a blocker.
- **The spec violated its own grounding rule** — the example JSON gave
  `"material": "polyester"` for a title that never mentions polyester.

Two needed refinement before being safe:
- **Tier B is not safe by label**, only by *programmatic verification* against the source
  title. Without a verifier, tier B is tier C with more confidence.
- **Deterministic pre-ranking introduces magic weights.** No relevance data to fit them
  on → keep similarity-dominant with bounded adjustments, and do not tune until the eval
  harness exists.

### 2026-07-26 · DECISION · Scope and distribution
- Catalogue size cap **removed**. Target ~20k, bounded by git mechanics (float16, 768 dims
  → ~30 MB) rather than an arbitrary number.
- Sampling is **query-agnostic**. The three assignment prompts are evaluation cases, not
  catalogue selection criteria.
- **Eval harness deferred to v2**; `eval/queries.yaml` still ships. Accepted consequence:
  pre-ranking weights stay untuned and no aggregate latency/quality numbers are claimed.
- **Repository is public** → attribution, no stored images, committed ingest scripts.
  Residual rights question acknowledged, not resolved.
- **Two deployments confirmed** (Vercel + Render/Fly), justified operationally.

### 2026-07-26 · SUCCESS · Plan written and self-reviewed
`docs/superpowers/plans/2026-07-26-personal-shopping-assistant.md` — 25 tasks, 169 steps.

Self-review caught five defects in the plan itself:
1. `assign_price_tiers` could never produce `luxury` — percentile cut-offs with `<=` put
   the top-priced item in `premium`, and small cohorts never reached p90. → rank-based
   assignment. Both tests had asserted behaviour the code could not deliver.
2. Tailwind v4 install paired with v3 `@tailwind` directives. → pinned v3.
3. `vercel.json` listed in Task 25's files but never written.
4. Stale closure in the streaming hook — `onResults` read `partial` from a closure
   `onUnderstood` had already superseded, dropping assumptions from the response.
5. Spec coverage gap: tier-2 Devanagari translation had no task. → deferred deliberately,
   recorded in Task 6 and the appendix.

---

## Phase: Implementation

<!-- Append below. One entry per task: what was attempted, what broke, what fixed it,
     what was verified and how. Record failures even when the fix was obvious. -->
