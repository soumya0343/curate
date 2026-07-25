# Dataset: Amazon India Products 2023

Analysis of the source catalogue, the defects found in it, and the plan to turn it into
the catalogue the shopping assistant serves from.

Every number below was measured directly against the file, not taken from the dataset
description. The scripts that produced them are in [Reproducing this analysis](#reproducing-this-analysis).

**Design principle for this document:** the catalogue is sampled broadly across the Amazon
India taxonomy. It is *not* constructed around the three assignment example queries. Those
are golden evaluation cases, and a catalogue hand-built to satisfy them would prove
nothing about the recommendation architecture. See [section 5](#5-ingest-pipeline).

---

## 1. Source

| | |
|---|---|
| Dataset | [Amazon India Products 2023 (1.5M)](https://www.kaggle.com/datasets/asaniczka/amazon-india-products-2023-1-5m-products) |
| File | `amz_in_total_products_data_processed.csv` |
| Size | 670 MB |
| Rows | 1,589,160 |
| Crawled | ~Sept 2023 |
| Currency | INR |
| Licence | **BLOCKER — unresolved.** See [1.1](#11-licence-and-redistribution-blocker). |

### Schema

```
asin               B08VJFZQ9S
title              प्लेन कैज़ुअल वियर बेसबॉल कैप पुरुषों और महिलाओं के लिए…
imgUrl             https://m.media-amazon.com/images/I/61DK1GchGFL._AC_UL320_.jpg
productURL         https://www.amazon.in/dp/B08VJFZQ9S
stars              0.0
reviews            0
price              299.0
listPrice          499.0
categoryName       पुरुषों के हैट्स और कैप्स
isBestSeller       False
boughtInLastMonth  0
```

**There is no description field, and no availability field.** Title is the only free text.
This drives [section 4](#4-generating-descriptions).

### 1.1 Licence and redistribution (blocker)

This must be resolved **before any derived catalogue file is committed**, not recorded as
a known limitation afterwards.

Two separate questions, and only the first is answered by the Kaggle page:

1. **The dataset compilation's licence** — governs redistribution of the scrape itself.
   The Kaggle page is JavaScript-rendered and could not be read programmatically; it needs
   a manual check.
2. **The underlying product content** — Amazon's titles and images are Amazon's, and a
   permissive licence on a scrape does not grant rights over them. This holds regardless
   of what Kaggle says.

**Decision taken: the repository is public.** That rules out the simplest mitigation
(a private repo) and makes the following measures the working policy:

| Measure | Rationale |
|---|---|
| **Verify the Kaggle licence before first commit of derived data** | Still mandatory. A manual check of the dataset page. If it forbids redistribution, the derived catalogue cannot ship in the repo at all and setup must rebuild it from a reviewer-supplied CSV. |
| **`ATTRIBUTION.md` at the repo root** | Names the source dataset, its author, its licence, the crawl date, and states the catalogue is a derived sample for demonstration. |
| **No image files stored** | Only CDN URLs are kept. Amazon's images are referenced, never redistributed. |
| **Ingest scripts committed** | Provenance is reproducible: anyone can see exactly which rows were selected and how they were transformed. |
| **Derived text is ours** | Descriptions and attributes are generated, not scraped. Titles and ASINs are the only source content retained. |

Residual risk is acknowledged rather than resolved: the Kaggle licence governs the scrape,
not Amazon's underlying rights in product titles, and no repository-side measure changes
that. For a demonstration catalogue of ~20k derived records with attribution, this is a
proportionate position for a take-home — but it is a judgement call, not a legal clearance.

If the licence check comes back restrictive, fall back to committing ASINs plus our own
generated descriptions and attributes only, and have the setup script rebuild titles from a
reviewer-supplied Kaggle CSV.

**The licence check still gates the first commit of any derived catalogue file.**

### Why this source

Considered and rejected:

| Source | Why not |
|---|---|
| [Amazon Reviews 2023 (HuggingFace)](https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023) | Real descriptions and richer metadata, but USD and US products. Indian-context queries return culturally wrong results. |
| [Flipkart 20k (PromptCloud)](https://www.kaggle.com/datasets/PromptCloudHQ/flipkart-products) | Has descriptions and is Indian, but crawled 2016 — most `product_url`s are dead. Broken links defeat an explicit requirement. |
| DummyJSON (194 items), FakeStore (20 items) | Synthetic and far too small. |

Amazon India wins on the two things a reviewer will click: **resolvable product links** and
**INR prices in an Indian catalogue**. Missing descriptions are recoverable (section 4);
dead links and wrong-country products are not.

---

## 2. Integrity: what is clean

Verified across all 1,589,160 rows.

| Check | Result |
|---|---|
| `asin` uniqueness | 1,589,160 unique — a perfect primary key |
| Nulls, any column | **zero** |
| `productURL` == `https://www.amazon.in/dp/{asin}` | 100%, no exceptions — derivable |
| `imgUrl` host | 100% `m.media-amazon.com` (1 malformed row) |
| `stars` outside 0–5 | 0 |
| `reviews` negative | 0 |
| `listPrice < price` (inverted discount) | 0 |
| One `asin` in multiple categories | 0 |

**Link resolvability, sampled 2026-07-26** — 25 random qualifying rows, HTTP HEAD:

```
images        24/24 → 200
product URLs  24/24 → 200
```

This is a 25-row sample and establishes **routing**, not availability or catalogue-wide
health. Amazon returns `200` for delisted products with an "unavailable" body. The correct
claim is "resolvable Amazon India product URLs, spot-checked during ingest" — never "live
links". Ingest performs its own bounded validation pass ([section 5](#5-ingest-pipeline)).

---

## 3. Defects found

Ordered by impact on the running application.

### 3.1 Category labels are unreliable — critical

`खेल, फिटनेस और आउटडोर` ("Sports, Fitness & Outdoor") holds 11,853 qualifying rows.
Keyword counts within it:

```
football        897        thermal          70
cricket         283        camping          37
jacket          205        hiking           25
gym             104        tent             15
                           trek              3
                           headlamp          0
                           trekking pole     0
```

It is a swimming and team-sports category wearing an outdoor label.

Harvesting the whole file by keyword shows items filed under unrelated categories:

| Item | Category it mostly lives in |
|---|---|
| sleeping bag | `स्मॉल एनीमल` — **Small Animals** (pet beds) |
| first aid | `सॉफ्टवेयर` — **Software** |
| rucksack | `सूटकेस, चेक इन और स्ट्रॉली` — Suitcases |

**Consequences:**

1. `categoryName` is retained as source metadata and used for **stratification** and
   **price-tier cohorts**, but it is not a semantic label and must not drive hard filters.
2. Stratifying across the taxonomy gives *nominal* coverage, not guaranteed *semantic*
   coverage. Broad sampling is still correct — it just cannot be claimed to guarantee that
   any given domain is well represented. The evaluation harness measures that; the
   sampling strategy does not assert it.

### 3.2 Near-duplicate variants — 35.8%

75,791 of 211,541 qualifying rows share a 45-character title prefix with another row.
Worst offenders, in Watches:

```
"combo pack watch strap silicone belt compatib…"   × 673
"watch strap silicone belt 20mm compatible wit…"   × 415
```

Exact-title deduplication does not catch these — they diverge only in a colour or size
suffix. Left alone, a gifting query returns five visually identical watch straps and the
recommendations look broken regardless of retrieval quality.

**This matters more as the catalogue grows.** At 20k products the absolute number of
near-duplicates is roughly eight times what it would be at 2,600.

Handled in two places, because neither alone suffices:

- **Ingest** — collapse on `(brand, first 6 title tokens)`, keeping the highest
  quality-scored representative. Runs *before* quota enforcement, so quotas are filled with
  distinct products rather than variants.
- **Rank time** — diversity penalty so near-identical vectors cannot occupy consecutive
  slots. Catches duplicates that survive ingest under different brand strings.

### 3.3 Gender is unknown for roughly half the catalogue

| Signal | Coverage |
|---|---|
| Row sits in a gender-named category | 18.5% |
| Title contains men/women/boys/girls/unisex | 30.9% |

A hard `gender ∈ {stated, unisex}` filter would silently delete half the catalogue.

Gender is **four-state** — `men | women | unisex | unknown` — and `unknown` is never
filtered out, only mildly demoted. Missing data must not be treated as disqualifying data.

Gender also splits across the trust tiers of [section 4.1](#41-data-trust-hierarchy):
gender stated in the title is tier B and may filter; gender inferred from category or
product type is tier C and may only rank.

### 3.4 Price defects

| | |
|---|---|
| `price <= 0` | 92,015 rows (5.79%) |
| Distribution | p50 ₹788 · p90 ₹4,794 · p99 ₹24,714 · **max ₹620,000** |
| `price > ₹1L` | 268 rows |
| `listPrice == 0` | 1,057,517 rows (66.55%) |

Drop `price <= 0`; clip above per-cohort p99.5. Otherwise a "premium gifting" query
surfaces a ₹6L outlier and price-tier boundaries are skewed by a handful of rows.

**Discount percentage is not a usable feature** — MRP is absent on two thirds of the
catalogue, so no "on sale" filtering.

### 3.5 Title defects

| | |
|---|---|
| Length | min 1 · p25 59 · median 91 · p75 137 · p95 195 · max 562 |
| Titles under 15 chars | 20,472 |
| Exact duplicate titles | 217,596 rows (13.7%) |

Duplicates concentrate in generic Hindi listings — `पुरुषों शर्ट` appears 2,095 times.
The Latin-script filter removes most of them incidentally.

Median 91 characters is good news: Amazon titles are long and keyword-dense, which makes
them viable embedding input even without descriptions.

### 3.6 Sparse sub-needs

Even harvesting all 1.5M rows, some items barely exist (Latin-script, price-valid):

```
sleeping bag      47        trekking pole     19
sleeping mat      15        first aid         17
hiking boot       47
```

Real gaps, not filter artifacts. The assistant reports *"No trekking poles in the
catalogue"* rather than padding with irrelevant items.

Note the interaction with broad sampling: these items enter the catalogue in proportion to
their presence in the source, not because they were hand-placed to serve a demo query.
That is the intended behaviour, and it means some example-query groups will legitimately
come back empty.

### 3.7 Reviews are absent on two thirds of rows

67.7% of Latin-script rows have `reviews == 0`; `boughtInLastMonth` is zero on 94.8% of all
rows; `isBestSeller` is true on 0.16% (2,533 rows).

Low severity, but it rules out "sort by reviews" as a sampling strategy and forces the
tiered fill in [section 5](#5-ingest-pipeline).

### 3.8 Process note: never hardcode Devanagari literals

An early profiling run reported men's shoes at 0 qualifying rows. The category actually has
2,236. The cause was a hand-typed category string differing from the file's by an invisible
joiner character.

The ingest script therefore **selects categories by English name** through the committed
`category_map.json`, keyed on strings read verbatim from the CSV. A silent zero-match on an
invisible character difference ships a broken catalogue that looks exactly like a retrieval
bug.

---

## 4. Generating descriptions

The dataset has no description field, and the assistant needs descriptive text for two
jobs — embedding input for retrieval, and display text on product cards.

### Rejected approaches

| Approach | Why not |
|---|---|
| Scrape amazon.in product pages | Against Amazon's ToS, rate-limited, slow and fragile at scale. |
| Amazon Product Advertising API | Requires an approved Associates account with qualifying sales. Not obtainable in the project window. |
| Switch to a dataset that has descriptions | Only the US/HuggingFace one does, and it fails the INR/India requirement. |

### 4.1 Data-trust hierarchy

**The governing rule: source-grounded facts may exclude products; LLM inference may only
rank them.** An enrichment mistake must never make a valid product unreachable.

**Tier A — source-grounded, authoritative.** Straight from the CSV, no model involved.

```
asin · price · stars · reviews · productURL · imgUrl · categoryName
```

Safe for hard filters without qualification.

**Tier B — title-grounded, programmatically verified.** Extracted by the LLM, then
*checked against the source title in code*. Verification is what makes them safe — not the
fact that they were labelled "explicit".

```python
VERIFIERS = {
    "capacity_l":      lambda v, t: re.search(rf"\b{v}\s?(l|litre|liter)\b", t, re.I),
    "water_resistant": lambda v, t: re.search(r"water[\s-]?(resistant|proof)", t, re.I),
    "gender":          lambda v, t: re.search(rf"\b{v}('s)?\b", t, re.I),
    "material":        lambda v, t: re.search(rf"\b{v}\b", t, re.I),
}
```

Passes → tier B, may participate in hard filters. Fails → dropped and logged, or demoted
to tier C. **Every tier-B attribute needs a verifier written alongside it**, which usefully
bounds how many tier-B attributes are worth having. Without the gate, tier B is just tier C
with more confidence.

**Tier C — LLM-inferred semantics.** Genuine inference, unverifiable against the title.

```
use_case · occasion · season · climate_suitability · gift_suitable · inferred gender · product_type
```

**Ranking signals only.** These never remove a product from the candidate pool.

Each attribute carries its provenance so the runtime can enforce the tiers rather than
trusting a naming convention:

```jsonc
"capacity_l":   {"value": 45,          "source": "title_verified"},
"use_case":     {"value": ["trekking"], "source": "inferred"},
"gender":       {"value": "unisex",    "source": "inferred"}
```

### 4.2 Conservative enrichment

One offline pass generates descriptions and attributes together. The model may only
restate, expand, and categorise what the title, category, and price already assert.

For the title `"Wildcraft 45L Rucksack Water Resistant Trekking Backpack"`:

| Allowed | Not allowed unless the title says so |
|---|---|
| `capacity_l = 45` | `material` — the title does not state it |
| `water_resistant = true` | `weight` |
| `product_type = "backpack"` | waterproof rating |
| `use_case = ["trekking"]` (tier C) | temperature rating |
| `brand = "Wildcraft"` | durability claims |

**Missing metadata is preferable to fabricated metadata.** Unknown fields emit `null`, not
a guess.

This matters for correctness, not tidiness: a fabricated `temp_rating_c` on a tier-B path
would flow into a hard filter and produce recommendations that are confidently wrong.

Enforced four ways:
- The prompt states the rule and instructs `null` over guessing.
- Tier-B verifiers reject anything not present in the source title (4.1).
- Tier C cannot hard-filter by construction, so inference errors degrade ranking rather
  than hiding products.
- A 30-item sample is manually reviewed against source titles before the full run.

### 4.3 Cost and mechanics

At 50 products per call, roughly `N/50` calls. Run on **Groq** (~30 RPM free tier, fast
inference) rather than Gemini (~10 RPM):

| Catalogue | Calls | Wall clock |
|---|---|---|
| 5k | 100 | ~4 min |
| 20k | 400 | ~15 min |
| 50k | 1,000 | ~35 min |

Gemini stays reserved for query-time reasoning, where quality matters more than throughput.

**Checkpointing.** Each batch writes `data/enriched/batch_NNN.json` before continuing. A
rate limit, crash, or `Ctrl-C` resumes from the last completed batch. Non-negotiable for a
job with hundreds of sequential network calls.

### 4.4 What this does not fix

Enrichment restores *descriptive* text, not *factual* detail that was never in the source.
The catalogue will not know a jacket's fill power or a tent's hydrostatic head. The
assistant reasons at "insulated jacket suitable for cold-weather trekking", never "rated to
−12 °C". An honest ceiling, recorded in the README.

---

## 5. Ingest pipeline

### 5.1 Sampling philosophy

**Broad, query-agnostic, stratified across the full taxonomy.** The three assignment
prompts are evaluation cases, not selection criteria. A catalogue assembled to make them
work would demonstrate nothing about generalisation, and a reviewer should — and probably
would — penalise it.

Concretely: sample across all 214 categories with per-category quotas, so smaller
categories stay represented instead of being swamped by Electronics and Fashion. Preserve
Amazon's original category metadata even though it is noisy (3.1) — it is still the best
available stratification key and the right cohort for price tiers.

### 5.2 Sizing

**No target cap.** The earlier ~2,600 figure was derived from per-sub-need candidate
density, which only ever established a *floor*. The real ceiling is git mechanics:

| Catalogue | `catalogue.jsonl.gz` | `embeddings.npy` (768-dim fp16) | Enrichment |
|---|---|---|---|
| 5k | ~1.5 MB | 7.5 MB | ~4 min |
| **20k** | **~6 MB** | **30 MB** | **~15 min** |
| 50k | ~15 MB | 77 MB | ~35 min |
| 100k+ | ~30 MB | 154 MB | Git LFS required |

**~20k is the working target** — no LFS, no GitHub size warnings, enrichment under 15
minutes, ~93 products per category averaged across 214. Two mechanical choices buy that
headroom:

- **float16 embeddings** — halves the file, immaterial for cosine similarity.
- **768 dimensions** — `gemini-embedding-001` supports Matryoshka truncation, so this is a
  supported operation rather than a hack.

Search performance is not a constraint at any of these sizes: numpy cosine over 20k × 768
is roughly 10 ms.

The Latin-script qualifying pool is 179,049 rows, so 20k is drawn from a ~9× larger pool —
sampling stays selective.

### 5.3 Pipeline

```
1,589,160 rows
   │
   ├─ 1. Hygiene gate          price > 0 · title ≥ 25 chars · exact-title dedup
   │                           → 179,049 rows across 151 categories with ≥80
   │
   ├─ 2. Near-dup collapse     (brand, first 6 tokens) → keep best quality_score
   │                           runs BEFORE quotas, so quotas fill with distinct products
   │                           (fixes 3.2)
   │
   ├─ 3. Price clip            drop ≤ 0, clip above per-cohort p99.5  (fixes 3.4)
   │
   ├─ 4. Stratified quota      per-category quota across all 214 categories
   │                           selected via category_map.json, never hardcoded
   │                           Devanagari (3.8)
   │
   ├─ 5. Tiered quality fill   A: reviews > 0  → rank by quality_score
   │                           B: reviews == 0 → rank by (boughtInLastMonth,
   │                                             isBestSeller, listPrice present)
   │                           fill from A, top up from B  (works around 3.7)
   │
   ├─ 6. Price tiers           deterministic percentiles within cohort (5.5)
   │
   ├─ 7. URL validation        bounded sample, not exhaustive (5.6)
   │
   └─ ~20,000 products
          │
          ├─ 8. LLM enrichment  descriptions + tiered attributes + translation (§4, §6)
          ├─ 9. Verification    tier-B verifiers; failures demoted to tier C (4.1)
          └─ 10. Embed          title_en + description + attributes → embeddings.npy
```

### 5.4 Quality score

Sorting by `reviews DESC, stars DESC` over-selects popular-but-mediocre products and
near-identical bestsellers. Use a score that balances rating against review confidence:

```python
quality_score = stars * math.log1p(reviews)
```

A 4.8-star product with 12 reviews does not outrank a 4.4-star product with 3,000, and a
3.1-star product with 50,000 reviews does not dominate on volume alone. A Bayesian-adjusted
rating would be marginally better and is not worth the complexity here.

Items with `reviews == 0` score 0, which is why the tiered fill exists — tier B is ordered
by the weak popularity signals instead.

### 5.5 Price tiers — deterministic, cohort-relative

**The LLM does not decide price tier.** ₹8,000 is premium for a backpack and cheap for a
laptop; that is arithmetic over a distribution, not a judgement call.

Computed offline from the price distribution within the cohort:

```
   0 – 33rd percentile  → budget
  33 – 67th percentile  → mid
  67 – 90th percentile  → premium
  90th percentile +     → luxury
```

**Cohort selection:** prefer the extracted `product_type` where enrichment supplies one
with enough members (≥50), falling back to `categoryName`. Product type is a better cohort
than a noisy category (3.1), but it is tier-C data, so the fallback keeps tiers computable
for everything.

Boundaries are tunable constants, not model output.

### 5.6 URL validation

Exhaustive validation of ~20k URLs is slow and abusive toward Amazon. Instead:

- A **stratified random sample** (~200 across categories), with bounded concurrency and
  polite delays.
- **Every product appearing in evaluation results**, so anything a reviewer clicks in the
  demo has been checked.
- Results recorded in `data/url_validation.json` with a timestamp, and summarised in the
  README.

Reported honestly: a sampled resolvability rate, never "all links are live".

---

## 6. Translation

### The problem

| | |
|---|---|
| Titles mostly Latin (>0.85 ASCII) | 258,896 (16.3%) |
| Titles mostly Devanagari (<0.30 ASCII) | 42.2% |
| Category names mostly Latin | 14.5% (31 of 214) |

Devanagari titles embedded against English queries means cross-lingual retrieval, which is
measurably weaker even with multilingual embedding models — and Hindi product cards read
oddly in an English-language demo.

### Strategy: filter first, translate only where forced

With 179,049 Latin-script qualifying rows against a ~20k target, there is ~9× headroom. The
cheapest translation is the one that never runs.

**Tier 1 — Latin-only (default).** 151 of 214 categories clear ≥80 qualifying rows on
Latin-script titles alone. No translation.

**Tier 2 — translate.** Categories starved of Latin rows but worth representing for
taxonomy coverage. Measured examples:

| Category | Latin qualifying | Total rows |
|---|---|---|
| `महिलाओं की लहंगा चोली` (lehenga choli) | 57 | 4,981 |
| `पुरुषों की धोती` (dhoti) | 48 | 800 |
| `गृह सज्जा` (home decor) | 43 | 10,374 |
| `पुरुषों के थर्मल अंडरवियर` (thermals) | 66 | 2,096 |

The rule, applied per category at ingest — note it is driven by quota shortfall, not by
which categories serve the example queries:

```
latin_qualifying ≥ quota   → tier 1, Latin only
20 ≤ latin < quota         → tier 2, include Hindi rows and translate
latin < 20                 → accept the shortfall; the category contributes what it has
```

### How translation happens

**Product titles — folded into the enrichment pass.** The LLM already reads every title to
generate a description (section 4). Adding `title_en` costs two output fields and no extra
calls. It also beats a general translator on brand-name survival: a generic translator
mangles `वाइल्डक्राफ्ट` into an unrecognisable transliteration; an LLM knows it is
Wildcraft.

Instruction: translate to natural English, **keep brand names and model numbers verbatim**,
do not transliterate. The Devanagari original is retained as `title_original`.

Note the interaction with tier-B verification (4.1): verifiers must run against the
**original** title, not the translation, or a translation artifact could manufacture a
"verified" fact.

**Category names — one call, committed.** All 214 translate once into
`data/category_map.json`, hand-checked, never re-run. They are the backbone of category
selection and, per 3.8, the only safe way to reference categories in code.

### Fallbacks, if LLM translation quality disappoints

| Option | Notes |
|---|---|
| `deep-translator` (`pip install deep-translator`) | Free, no key, wraps Google's web endpoint. Unofficial — never on a request path. |
| MyMemory API | Real REST API, no key, ~5k words/day anonymous. Would not cover a 20k catalogue. |
| Self-hosted LibreTranslate | Unlimited and offline. Overkill for one batch job. |
| IndicTrans2 / `Helsinki-NLP/opus-mt-hi-en` | Best Hindi→English quality, offline — but ~2 GB of `torch`, and still leaves attribute extraction to do separately. |

All are worse here than the pass already being paid for. Listed because if translation
quality is the weak link, isolating it from attribute extraction is the first thing to try.

---

## 7. Open questions

1. **Licence and redistribution** — see [1.1](#11-licence-and-redistribution-blocker).
   **Blocks committing any derived catalogue file.**
2. **Delisted products.** `200` confirms routing, not availability. The ingest validation
   pass (5.6) should sample response bodies for "currently unavailable" markers.
3. **Flipkart as a secondary source.** Explicitly out of scope for the initial build.

---

## Reproducing this analysis

All figures were produced with the Python standard library — no pandas in the environment,
and streaming `csv.DictReader` handles 670 MB without loading it into memory.

```python
import csv, collections, re
csv.field_size_limit(10**7)

def latin_fraction(s: str) -> float:
    s = str(s)
    return sum(ord(c) < 128 for c in s) / max(len(s), 1)

# hygiene gate — reproduces the 179,049 figure
qualified = collections.Counter()
seen = set()
with open('amz_in_total_products_data_processed.csv', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        title = (row['title'] or '').strip()
        if latin_fraction(title) <= 0.85 or len(title) < 25:
            continue
        try:
            if float(row['price']) <= 0:
                continue
        except ValueError:
            continue
        key = re.sub(r'\s+', ' ', title.lower())[:120]
        if key in seen:
            continue
        seen.add(key)
        qualified[row['categoryName']] += 1
```

Link resolvability:

```bash
curl -s -o /dev/null -w '%{http_code}' -I "https://m.media-amazon.com/images/I/<id>._AC_UL320_.jpg"
curl -s -o /dev/null -w '%{http_code}' -A 'Mozilla/5.0' "https://www.amazon.in/dp/<asin>"
```

These land in `scripts/profile_dataset.py` so the numbers stay checkable as ingest rules
change.

---

*Analysis performed 2026-07-26 against `amz_in_total_products_data_processed.csv`
(1,589,160 rows, 670 MB).*
