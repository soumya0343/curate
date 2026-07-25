# Personal Shopping Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a web app where a user describes a shopping need in plain English and receives grouped, explained product recommendations from a ~20k-product Amazon India catalogue.

**Architecture:** An offline pipeline turns a 1.59M-row CSV into a committed catalogue with embeddings and trust-tiered attributes. At query time, one LLM call extracts structured intent plus sub-needs; deterministic Python applies hard filters and per-sub-need vector retrieval; a deterministic pre-ranker narrows candidates; a second LLM call reranks and explains. FastAPI serves it; React renders grouped results.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, numpy, pytest · React 18, TypeScript, Vite, Tailwind · Gemini 2.5 Flash (query-time generation), Groq (offline bulk), `gemini-embedding-001` (embeddings)

**Source documents:** [design spec](../specs/2026-07-26-personal-shopping-assistant-design.md) · [dataset analysis](../../dataset.md)

## Global Constraints

Every task's requirements implicitly include this section.

- **Python 3.11**, Pydantic **v2** syntax (`model_validate`, `Field`, not v1 `parse_obj`).
- **`data/amz_in_total_products_data_processed.csv` is 670 MB and must never be committed.** It is gitignored in Task 1. Verify before every commit.
- **The repository is public.** No derived catalogue file is committed until the Kaggle licence is verified (Task 2). `ATTRIBUTION.md` ships with it.
- **Trust tiers govern filtering.** Tier A (source) and verified tier B may exclude products. Tier C (LLM-inferred) may only rank. Never invert this.
- **Missing metadata beats fabricated metadata.** Enrichment emits `null`, never a guess.
- **Embeddings are pinned.** Query and catalogue vectors must come from the same model and dimensionality. `EmbeddingProvider` never falls back.
- **Generation falls back at most once:** primary → one fallback → `PROVIDER_UNAVAILABLE`.
- **Backend runs a single worker** (`--workers 1`). Sessions are process-local.
- **No quantitative claims without measurement.** No latency figures in README or code comments unless measured.
- **Example queries are evaluation cases, not catalogue selection criteria.** Sampling stays query-agnostic.
- Commit after every task. Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`).

## File Structure

```
confluxe/
├─ .gitignore                       excludes *.csv, .env, node_modules, __pycache__
├─ ATTRIBUTION.md                   dataset source, author, licence, crawl date
├─ README.md                        setup, architecture, design decisions, AI approach, limitations
├─ docs/                            dataset.md, specs/, plans/
├─ backend/
│  ├─ requirements.txt
│  ├─ .env.example
│  ├─ app/
│  │  ├─ main.py                    app factory, CORS, lifespan
│  │  ├─ config.py                  pydantic-settings
│  │  ├─ core/
│  │  │  ├─ errors.py               AppError hierarchy + envelope
│  │  │  └─ logging.py              structured JSON logs, request_id
│  │  ├─ schemas/
│  │  │  ├─ product.py              Product, Attribute, TrustTier
│  │  │  ├─ intent.py               ShoppingIntent, SubNeed, Assumption
│  │  │  └─ response.py             Candidate, Recommendation, ResultGroup, StreamEvent
│  │  ├─ providers/
│  │  │  ├─ generation.py           GenerationProvider protocol, Gemini, Groq, Stub, chain
│  │  │  └─ embedding.py            EmbeddingProvider protocol, Gemini, Stub, manifest pin
│  │  ├─ catalogue/
│  │  │  ├─ loader.py               CatalogueSource protocol, JsonlCatalogue
│  │  │  └─ index.py                numpy cosine index + manifest verification
│  │  ├─ services/
│  │  │  ├─ intent.py               extraction, delta merge, assumptions
│  │  │  ├─ retrieval.py            tier-gated hard filters, per-sub-need search
│  │  │  ├─ scoring.py              deterministic pre-rank + diversity
│  │  │  ├─ ranking.py              LLM rerank, grounded explanations, ID validation
│  │  │  ├─ sessions.py             in-memory TTL store
│  │  │  └─ pipeline.py             async generator orchestrator
│  │  └─ api/
│  │     ├─ deps.py                 DI wiring
│  │     └─ routes_recommend.py     POST /api/recommend, /stream, /health
│  ├─ scripts/
│  │  ├─ profile_dataset.py         reproducible EDA
│  │  ├─ build_category_map.py      214 Devanagari names → English, once
│  │  ├─ ingest.py                  hygiene → dedup → clip → quota → tiers
│  │  ├─ enrich.py                  conservative enrichment, checkpointed
│  │  ├─ verify_attributes.py       tier-B verifiers (importable by app + script)
│  │  ├─ build_embeddings.py        vectors + manifest
│  │  └─ validate_urls.py           bounded sample
│  ├─ data/                         catalogue.jsonl.gz, embeddings.npy, manifest, category_map
│  ├─ eval/queries.yaml             golden + unseen queries (harness is v2)
│  └─ tests/
└─ frontend/
   ├─ .env.example                  VITE_API_BASE_URL
   └─ src/
      ├─ types.ts                   mirrors backend schemas
      ├─ lib/api.ts                 typed client, JSON + streaming
      ├─ hooks/useRecommendation.ts stage state machine
      ├─ components/                InputPanel, AssumptionChips, ResultGroup, ProductCard, RefineBar
      └─ App.tsx
```

**Why these boundaries.** `services/` splits by pipeline stage rather than technical layer, because stages are what change together and what get tested independently. `verify_attributes.py` lives in `scripts/` but is imported by the app — the verifiers must be identical offline and at runtime, or a tier-B attribute could pass ingest and fail at query time.

---

## Phase 0 — Foundations

### Task 1: Repo scaffold, gitignore, dependencies

**Files:**
- Create: `.gitignore`, `backend/requirements.txt`, `backend/.env.example`, `backend/app/__init__.py`, `backend/app/config.py`
- Test: `backend/tests/test_config.py`

**Interfaces:**
- Produces: `app.config.Settings` with fields `gemini_api_key: str | None`, `groq_api_key: str | None`, `generation_primary: str = "gemini"`, `generation_fallback: str | None = "groq"`, `embedding_model: str = "gemini-embedding-001"`, `embedding_dims: int = 768`, `data_dir: Path`, `cors_origins: list[str]`; and `get_settings() -> Settings` (cached).

- [ ] **Step 1: Initialise the repository and write `.gitignore`**

The 670 MB CSV is currently at the repo root. This step must happen before any `git add`.

```bash
cd /Users/soumyagupta/Documents/resume-projects/confluxe
git init
mkdir -p backend/data
mv amz_in_total_products_data_processed.csv backend/data/ 2>/dev/null || true
```

`.gitignore`:

```gitignore
# Source data — 670 MB, never commit
*.csv
backend/data/enriched/
backend/data/*.raw.jsonl
backend/data/profile.json

# Secrets
.env
.env.local

# Python
__pycache__/
*.py[cod]
.venv/
venv/
.pytest_cache/

# Node
node_modules/
dist/
.vite/

# OS
.DS_Store
```

- [ ] **Step 2: Verify the CSV is ignored**

```bash
git status --porcelain | grep -c 'amz_in_total' || echo "CORRECTLY IGNORED"
du -sh backend/data/*.csv
```

Expected: `CORRECTLY IGNORED`, and the file is ~670 MB in `backend/data/`.

- [ ] **Step 3: Write `backend/requirements.txt`**

```txt
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic==2.10.4
pydantic-settings==2.7.1
numpy==2.2.1
httpx==0.28.1
google-genai==0.8.0
groq==0.15.0
python-dotenv==1.0.1
pyyaml==6.0.2
pytest==8.3.4
pytest-asyncio==0.25.2
```

- [ ] **Step 4: Write the failing config test**

`backend/tests/test_config.py`:

```python
from app.config import Settings


def test_defaults_pin_embedding_model():
    s = Settings(_env_file=None)
    assert s.embedding_model == "gemini-embedding-001"
    assert s.embedding_dims == 768


def test_cors_origins_parses_comma_separated(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173,https://x.vercel.app")
    s = Settings()
    assert s.cors_origins == ["http://localhost:5173", "https://x.vercel.app"]
```

- [ ] **Step 5: Run it to verify it fails**

```bash
cd backend && python -m pytest tests/test_config.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.config'`.

- [ ] **Step 6: Write `backend/app/config.py`**

```python
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str | None = None
    groq_api_key: str | None = None

    generation_primary: str = "gemini"
    generation_fallback: str | None = "groq"

    # Pinned. Changing either requires rebuilding catalogue embeddings.
    embedding_model: str = "gemini-embedding-001"
    embedding_dims: int = 768

    data_dir: Path = Path(__file__).parent.parent / "data"
    cors_origins: list[str] = ["http://localhost:5173"]

    session_ttl_seconds: int = 1800
    llm_timeout_seconds: float = 30.0

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 7: Write `backend/.env.example`**

```bash
GEMINI_API_KEY=
GROQ_API_KEY=
GENERATION_PRIMARY=gemini
GENERATION_FALLBACK=groq
CORS_ORIGINS=http://localhost:5173
```

- [ ] **Step 8: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_config.py -v
```

Expected: 2 passed.

- [ ] **Step 9: Commit**

```bash
git add .gitignore backend/requirements.txt backend/.env.example backend/app backend/tests
git commit -m "chore: scaffold backend with pinned embedding config"
```

---

### Task 2: Licence verification and attribution (BLOCKER)

**Files:**
- Create: `ATTRIBUTION.md`, `docs/licence-check.md`

**Interfaces:**
- Produces: a recorded decision that gates every later commit of `backend/data/catalogue.jsonl.gz`.

This task is a human decision point, not code. **No derived catalogue file may be committed until it is complete.**

- [ ] **Step 1: Read the licence from the dataset page**

Open <https://www.kaggle.com/datasets/asaniczka/amazon-india-products-2023-1-5m-products> and record the licence shown in the right-hand metadata panel.

- [ ] **Step 2: Record the finding in `docs/licence-check.md`**

```markdown
# Licence check

**Dataset:** Amazon India Products 2023 (1.5M) — asaniczka
**URL:** https://www.kaggle.com/datasets/asaniczka/amazon-india-products-2023-1-5m-products
**Licence as stated on the page:** <FILL IN — e.g. CC0: Public Domain>
**Checked:** 2026-07-26 by <name>

## Decision

- [ ] Permissive (CC0 / CC BY / ODbL) → commit derived catalogue with ATTRIBUTION.md
- [ ] Restrictive or unclear → commit ASINs + our generated descriptions only;
      setup rebuilds titles from a reviewer-supplied Kaggle CSV

## Note

The dataset licence governs the scrape, not Amazon's underlying rights in product
titles and images. Mitigations applied regardless: attribution, no stored image
files (CDN URLs only), committed ingest scripts for provenance.
```

- [ ] **Step 3: Write `ATTRIBUTION.md`**

```markdown
# Attribution

Product data in this project is derived from the
[Amazon India Products 2023 (1.5M Products)](https://www.kaggle.com/datasets/asaniczka/amazon-india-products-2023-1-5m-products)
dataset by **asaniczka**, crawled approximately September 2023.
Licence: <FILL IN from docs/licence-check.md>.

## What is derived

`backend/data/catalogue.jsonl.gz` is a ~20,000-row sample of that dataset,
selected and transformed by `backend/scripts/ingest.py`. It retains the source
`asin`, `title`, `price`, `stars`, `reviews`, `categoryName`, and image/product
URLs. Descriptions and semantic attributes are generated by this project and are
not part of the source dataset.

## What is not redistributed

No image files are stored. Product images are referenced by their original
Amazon CDN URLs.

Product titles and identifiers remain the property of their respective rights
holders. This catalogue is a derived sample published for demonstration purposes.
```

- [ ] **Step 4: Commit**

```bash
git add ATTRIBUTION.md docs/licence-check.md
git commit -m "docs: record dataset licence check and attribution"
```

---

## Phase 1 — Offline data pipeline

### Task 3: Reproducible dataset profiling

**Files:**
- Create: `backend/scripts/profile_dataset.py`
- Test: `backend/tests/test_profile.py`

**Interfaces:**
- Produces: `scripts.profile_dataset.latin_fraction(s: str) -> float` and `passes_hygiene(row: dict) -> bool`, both imported by `ingest.py` in Task 5.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_profile.py`:

```python
from scripts.profile_dataset import latin_fraction, passes_hygiene


def test_latin_fraction_detects_devanagari():
    assert latin_fraction("Wildcraft 45L Rucksack Trekking Backpack") > 0.85
    assert latin_fraction("पुरुषों के हैट्स और कैप्स") < 0.30


def test_hygiene_rejects_zero_price():
    row = {"title": "A perfectly reasonable product title here", "price": "0.0"}
    assert passes_hygiene(row) is False


def test_hygiene_rejects_short_title():
    assert passes_hygiene({"title": "Cap", "price": "299.0"}) is False


def test_hygiene_rejects_devanagari_title():
    row = {"title": "प्लेन कैज़ुअल वियर बेसबॉल कैप पुरुषों और महिलाओं", "price": "299.0"}
    assert passes_hygiene(row) is False


def test_hygiene_accepts_valid_row():
    row = {"title": "Wildcraft 45L Rucksack Water Resistant Trekking Backpack",
           "price": "3499.0"}
    assert passes_hygiene(row) is True
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python -m pytest tests/test_profile.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.profile_dataset'`.

- [ ] **Step 3: Write `backend/scripts/profile_dataset.py`**

```python
"""Reproducible EDA over the source CSV.

Figures produced here back the claims in docs/dataset.md. Uses only the standard
library: streaming csv.DictReader handles 670 MB without loading it into memory.
"""
import collections
import csv
import json
import re
import sys
from pathlib import Path

csv.field_size_limit(10**7)

MIN_TITLE_LEN = 25
LATIN_THRESHOLD = 0.85


def latin_fraction(s: str) -> float:
    s = str(s)
    return sum(ord(c) < 128 for c in s) / max(len(s), 1)


def passes_hygiene(row: dict) -> bool:
    """Hygiene gate from docs/dataset.md section 5.3, step 1.

    Excludes exact-title deduplication, which is stateful and lives in ingest.py.
    """
    title = (row.get("title") or "").strip()
    if len(title) < MIN_TITLE_LEN:
        return False
    if latin_fraction(title) <= LATIN_THRESHOLD:
        return False
    try:
        if float(row.get("price") or 0) <= 0:
            return False
    except (TypeError, ValueError):
        return False
    return True


def normalise_title(title: str) -> str:
    return re.sub(r"\s+", " ", title.lower()).strip()


def profile(csv_path: Path) -> dict:
    stats = {"rows": 0, "qualified": 0, "price_le_zero": 0, "short_title": 0,
             "non_latin": 0, "reviews_zero": 0}
    per_category = collections.Counter()
    seen: set[str] = set()

    with csv_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            stats["rows"] += 1
            title = (row.get("title") or "").strip()

            if len(title) < MIN_TITLE_LEN:
                stats["short_title"] += 1
            if latin_fraction(title) <= LATIN_THRESHOLD:
                stats["non_latin"] += 1
            try:
                if float(row.get("price") or 0) <= 0:
                    stats["price_le_zero"] += 1
            except (TypeError, ValueError):
                stats["price_le_zero"] += 1

            if not passes_hygiene(row):
                continue
            key = normalise_title(title)[:120]
            if key in seen:
                continue
            seen.add(key)

            stats["qualified"] += 1
            if float(row.get("reviews") or 0) == 0:
                stats["reviews_zero"] += 1
            per_category[row["categoryName"]] += 1

    stats["categories"] = len(per_category)
    stats["categories_ge_80"] = sum(1 for v in per_category.values() if v >= 80)
    return {"stats": stats, "per_category": dict(per_category)}


if __name__ == "__main__":
    path = Path(sys.argv[1] if len(sys.argv) > 1
                else "data/amz_in_total_products_data_processed.csv")
    result = profile(path)
    print(json.dumps(result["stats"], indent=2))
    Path("data/profile.json").write_text(json.dumps(result, ensure_ascii=False))
```

- [ ] **Step 4: Make `scripts` importable**

```bash
cd backend && touch scripts/__init__.py tests/__init__.py
printf '[tool.pytest.ini_options]\npythonpath = ["."]\nasyncio_mode = "auto"\n' > pytest.ini
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_profile.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Run the profiler against the real CSV**

```bash
cd backend && python scripts/profile_dataset.py data/amz_in_total_products_data_processed.csv
```

Expected: `rows: 1589160`, `qualified: 179049`, `categories: 214`, `categories_ge_80: 151`.
These figures must match docs/dataset.md. If they do not, the CSV differs from the one
analysed and the ingest quotas in Task 5 need rechecking.

- [ ] **Step 7: Commit**

```bash
git add backend/scripts backend/tests backend/pytest.ini
git commit -m "feat: add reproducible dataset profiling with hygiene gate"
```

---

### Task 4: Category map — 214 Devanagari names to English

**Files:**
- Create: `backend/scripts/build_category_map.py`, `backend/data/category_map.json`
- Test: `backend/tests/test_category_map.py`

**Interfaces:**
- Produces: `data/category_map.json`, a `{devanagari_name: english_name}` dict read by `ingest.py`. Keys are byte-exact strings read from the CSV — never hand-typed (dataset.md §3.8).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_category_map.py`:

```python
import json
from pathlib import Path

MAP_PATH = Path(__file__).parent.parent / "data" / "category_map.json"


def test_map_exists_and_covers_all_categories():
    data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    assert len(data) == 214


def test_all_values_are_ascii_english():
    data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    for src, eng in data.items():
        assert eng.isascii(), f"{src!r} mapped to non-ASCII {eng!r}"
        assert eng.strip(), f"{src!r} mapped to empty string"


def test_known_mappings():
    data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    assert "Trekking" in data["रकसैक और ट्रेकिंग बैकपैक"]
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python -m pytest tests/test_category_map.py -v
```

Expected: FAIL — `FileNotFoundError: data/category_map.json`.

- [ ] **Step 3: Write `backend/scripts/build_category_map.py`**

```python
"""Translate all 214 source category names to English, once.

Run once; the output is committed. Category names are the only safe way to
reference categories in code (docs/dataset.md 3.8) — hand-typing Devanagari
introduces invisible joiner mismatches that silently match zero rows.
"""
import csv
import json
import os
import sys
from pathlib import Path

from groq import Groq

csv.field_size_limit(10**7)

PROMPT = """Translate each Amazon India category name to concise English.

Rules:
- Return ONLY a JSON object mapping each input string to its English translation.
- Keep translations short and shop-like: "Men's Shoes", not "Footwear for men".
- Preserve every input key EXACTLY as given, byte for byte.
- Names already in English map to themselves.

Categories:
{names}"""


def collect_categories(csv_path: Path) -> list[str]:
    seen: set[str] = set()
    with csv_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            seen.add(row["categoryName"])
    return sorted(seen)


def translate(names: list[str]) -> dict[str, str]:
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    out: dict[str, str] = {}
    for i in range(0, len(names), 40):
        batch = names[i:i + 40]
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user",
                       "content": PROMPT.format(names=json.dumps(batch, ensure_ascii=False))}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        out.update(json.loads(resp.choices[0].message.content))
        print(f"  translated {len(out)}/{len(names)}", file=sys.stderr)
    return out


if __name__ == "__main__":
    csv_path = Path(sys.argv[1] if len(sys.argv) > 1
                    else "data/amz_in_total_products_data_processed.csv")
    names = collect_categories(csv_path)
    print(f"found {len(names)} categories", file=sys.stderr)

    mapping = translate(names)
    missing = [n for n in names if n not in mapping]
    if missing:
        raise SystemExit(f"model dropped {len(missing)} keys, first: {missing[:3]!r}")

    Path("data/category_map.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(mapping)} mappings")
```

- [ ] **Step 4: Run it**

```bash
cd backend && GROQ_API_KEY=... python scripts/build_category_map.py
```

Expected: `wrote 214 mappings`. If the model drops keys the script exits non-zero — rerun.

- [ ] **Step 5: Hand-check the output**

```bash
cd backend && python -c "
import json; d=json.load(open('data/category_map.json'))
for k,v in list(d.items())[:20]: print(f'{v:45s} <- {k}')
"
```

Scan for nonsense. This file is committed and never regenerated, so errors are permanent.

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_category_map.py -v
```

Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/scripts/build_category_map.py backend/data/category_map.json backend/tests/test_category_map.py
git commit -m "feat: translate 214 source category names to English"
```

---

### Task 5: Tier-B attribute verifiers

**Files:**
- Create: `backend/scripts/verify_attributes.py`
- Test: `backend/tests/test_verifiers.py`

**Interfaces:**
- Produces: `scripts.verify_attributes.verify(field: str, value, source_title: str) -> bool` and `TIER_B_FIELDS: frozenset[str]`. Imported by both `enrich.py` (Task 7) and `services/retrieval.py` (Task 12) — the verifiers must be identical offline and at runtime.

This task comes before enrichment because enrichment depends on it. A tier-B attribute is
safe to hard-filter on *because a verifier confirmed it against the source title*, not
because the model labelled it explicit (spec §4.1).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_verifiers.py`:

```python
from scripts.verify_attributes import TIER_B_FIELDS, verify

TITLE = "Wildcraft 45L Rucksack Water Resistant Trekking Backpack"


def test_capacity_verified_when_present():
    assert verify("capacity_l", 45, TITLE) is True


def test_capacity_rejected_when_absent():
    assert verify("capacity_l", 60, TITLE) is False


def test_water_resistant_verified():
    assert verify("water_resistant", True, TITLE) is True


def test_water_resistant_rejected_on_silent_title():
    assert verify("water_resistant", True, "Wildcraft 45L Rucksack Backpack") is False


def test_gender_verified_from_title():
    assert verify("gender", "women", "Puma Running Shoes for Women Size 7") is True


def test_gender_rejected_when_only_inferred():
    assert verify("gender", "women", "Puma Running Shoes Size 7") is False


def test_material_verified():
    assert verify("material", "leather", "Hidesign Leather Wallet for Men") is True


def test_unknown_field_is_never_verified():
    assert verify("temp_rating_c", -12, TITLE) is False


def test_false_value_needs_no_verification():
    # Absence claims are safe: a False water_resistant excludes nothing.
    assert verify("water_resistant", False, TITLE) is True


def test_tier_b_fields_are_exactly_the_verifiable_ones():
    assert TIER_B_FIELDS == frozenset({"capacity_l", "water_resistant", "gender", "material"})
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python -m pytest tests/test_verifiers.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.verify_attributes'`.

- [ ] **Step 3: Write `backend/scripts/verify_attributes.py`**

```python
"""Tier-B verifiers: confirm an extracted attribute against the source title.

Governing rule (docs/dataset.md 4.1): tier B may participate in hard filters
ONLY after passing verification here. A value that fails is demoted to tier C,
where it can rank but never exclude.

Verifiers run against the ORIGINAL title, never a translation — a translation
artifact must not be able to manufacture a verified fact.
"""
import re

TIER_B_FIELDS = frozenset({"capacity_l", "water_resistant", "gender", "material"})

_GENDER_PATTERNS = {
    "men": r"\b(men|men's|mens|male|boys)\b",
    "women": r"\b(women|women's|womens|female|girls|ladies)\b",
    "unisex": r"\bunisex\b",
}


def _verify_capacity(value, title: str) -> bool:
    if not isinstance(value, (int, float)):
        return False
    n = int(value)
    return bool(re.search(rf"\b{n}\s*(l|ltr|litre|liter|liters|litres)\b", title, re.I))


def _verify_water_resistant(value, title: str) -> bool:
    if value is False:
        return True  # negative claims exclude nothing
    return bool(re.search(r"water[\s\-]?(resistant|proof)|waterproof", title, re.I))


def _verify_gender(value, title: str) -> bool:
    pattern = _GENDER_PATTERNS.get(str(value).lower())
    return bool(pattern and re.search(pattern, title, re.I))


def _verify_material(value, title: str) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    return bool(re.search(rf"\b{re.escape(value)}\b", title, re.I))


_VERIFIERS = {
    "capacity_l": _verify_capacity,
    "water_resistant": _verify_water_resistant,
    "gender": _verify_gender,
    "material": _verify_material,
}


def verify(field: str, value, source_title: str) -> bool:
    """True if `value` for `field` is supported by `source_title`.

    Unknown fields always return False: a field with no verifier cannot be tier B.
    """
    fn = _VERIFIERS.get(field)
    if fn is None or value is None:
        return False
    return fn(value, source_title or "")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_verifiers.py -v
```

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/verify_attributes.py backend/tests/test_verifiers.py
git commit -m "feat: add tier-B attribute verifiers with title grounding"
```

---

### Task 6: Ingest — hygiene, dedup, clip, stratified quota, price tiers

**Files:**
- Create: `backend/scripts/ingest.py`
- Test: `backend/tests/test_ingest.py`

**Interfaces:**
- Consumes: `scripts.profile_dataset.passes_hygiene`, `normalise_title`; `data/category_map.json`.
- Produces: `data/catalogue.raw.jsonl` (pre-enrichment) and these importable functions:
  - `quality_score(stars: float, reviews: int) -> float`
  - `variant_key(title: str) -> str`
  - `assign_price_tiers(products: list[dict]) -> None` (mutates, adds `price_tier`)
  - `select(rows: Iterable[dict], quota: int) -> list[dict]`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_ingest.py`:

```python
import math

from scripts.ingest import assign_price_tiers, quality_score, select, variant_key


def test_quality_score_balances_rating_and_confidence():
    # 4.4 stars with 3000 reviews beats 4.8 stars with 12
    assert quality_score(4.4, 3000) > quality_score(4.8, 12)


def test_quality_score_is_zero_without_reviews():
    assert quality_score(4.9, 0) == 0.0


def test_quality_score_matches_formula():
    assert quality_score(4.3, 212) == 4.3 * math.log1p(212)


def test_variant_key_collapses_colour_variants():
    a = "Boat Rockerz 450 Bluetooth Headphones Luscious Black"
    b = "Boat Rockerz 450 Bluetooth Headphones Aqua Blue"
    assert variant_key(a) == variant_key(b)


def test_variant_key_separates_different_products():
    a = "Boat Rockerz 450 Bluetooth Headphones Black"
    b = "Sony WH1000XM4 Wireless Headphones Black"
    assert variant_key(a) != variant_key(b)


def test_price_tiers_span_all_four_bands():
    products = [{"price": p, "cohort": "bags"} for p in range(100, 1100, 100)]
    assign_price_tiers(products)
    tiers = [p["price_tier"] for p in products]
    assert tiers[0] == "budget"
    assert tiers[-1] == "luxury"
    assert set(tiers) == {"budget", "mid", "premium", "luxury"}


def test_price_tiers_independent_per_cohort():
    """The same price sits in different bands depending on its cohort."""
    products = [{"price": p, "cohort": "backpacks"} for p in (500, 800, 1200, 8000)]
    products += [{"price": p, "cohort": "laptops"} for p in (8000, 40000, 60000, 90000)]
    assign_price_tiers(products)
    by = {(p["cohort"], p["price"]): p["price_tier"] for p in products}
    assert by[("backpacks", 8000)] == "luxury"
    assert by[("laptops", 8000)] == "budget"


def test_select_prefers_reviewed_then_tops_up_unreviewed():
    rows = [{"asin": f"A{i}", "title": f"Reviewed product number {i} with a long name",
             "stars": 4.0, "reviews": 100 - i, "boughtInLastMonth": 0,
             "isBestSeller": "False", "listPrice": "0.0"} for i in range(3)]
    rows += [{"asin": f"B{i}", "title": f"Unreviewed product number {i} long name here",
              "stars": 0.0, "reviews": 0, "boughtInLastMonth": 50 - i,
              "isBestSeller": "False", "listPrice": "499.0"} for i in range(3)]
    picked = select(rows, quota=4)
    assert [p["asin"] for p in picked[:3]] == ["A0", "A1", "A2"]
    assert picked[3]["asin"] == "B0"


def test_select_respects_quota_as_ceiling_not_floor():
    rows = [{"asin": "A0", "title": "Only one product available in this category here",
             "stars": 4.0, "reviews": 10, "boughtInLastMonth": 0,
             "isBestSeller": "False", "listPrice": "0.0"}]
    assert len(select(rows, quota=80)) == 1
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python -m pytest tests/test_ingest.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.ingest'`.

- [ ] **Step 3: Write `backend/scripts/ingest.py`**

```python
"""Turn the 1.59M-row source CSV into a broadly-sampled catalogue.

Sampling is query-agnostic and stratified across the full taxonomy. The three
assignment prompts are evaluation cases, not selection criteria — a catalogue
built to satisfy them would demonstrate nothing about generalisation
(docs/dataset.md 5.1).

Pipeline: hygiene -> near-dup collapse -> price clip -> stratified quota ->
tiered quality fill -> deterministic price tiers.
"""
import bisect
import collections
import csv
import json
import math
import re
import sys
from pathlib import Path
from typing import Iterable

from scripts.profile_dataset import normalise_title, passes_hygiene

csv.field_size_limit(10**7)

QUOTA_PER_CATEGORY = 100  # ceiling, not floor; ~214 categories -> ~20k target
VARIANT_TOKENS = 6
PRICE_CLIP_PERCENTILE = 99.5
# Upper bound of each band, as a fraction of the cohort's price rank.
TIER_BOUNDS = [(0.33, "budget"), (0.67, "mid"), (0.90, "premium")]
TOP_TIER = "luxury"


def quality_score(stars: float, reviews: int) -> float:
    """Balance rating against review confidence (docs/dataset.md 5.4).

    Plain `reviews DESC` over-selects popular-but-mediocre products; plain
    `stars DESC` promotes 5-star items with two reviews.
    """
    return float(stars) * math.log1p(int(reviews))


def variant_key(title: str) -> str:
    """Collapse colour/size variants of the same product.

    35.8% of source rows share a title prefix with another row
    (docs/dataset.md 3.2). Exact-title dedup misses these.
    """
    tokens = re.findall(r"[a-z0-9]+", normalise_title(title))
    return " ".join(tokens[:VARIANT_TOKENS])


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(int(len(sorted_values) * pct / 100), len(sorted_values) - 1)
    return sorted_values[idx]


def assign_price_tiers(products: list[dict]) -> None:
    """Deterministic, cohort-relative price tiers (docs/dataset.md 5.5).

    The LLM does not decide this: Rs 8,000 is premium for a backpack and cheap
    for a laptop, which is arithmetic over a distribution.

    Tiers come from each product's price RANK within its cohort, not from
    absolute percentile cut-offs. Rank normalises to the full 0-1 range whatever
    the cohort size, so a small cohort still spans all four bands. Ties share a
    tier because rank counts strictly-lower prices.
    """
    by_cohort: dict[str, list[dict]] = collections.defaultdict(list)
    for p in products:
        by_cohort[p["cohort"]].append(p)

    for cohort_products in by_cohort.values():
        prices = sorted(float(p["price"]) for p in cohort_products)
        n = len(prices)
        for p in cohort_products:
            price = float(p["price"])
            lower = bisect.bisect_left(prices, price)
            rank = lower / (n - 1) if n > 1 else 0.0
            for bound, tier in TIER_BOUNDS:
                if rank < bound:
                    p["price_tier"] = tier
                    break
            else:
                p["price_tier"] = TOP_TIER


def _tier_b_sort_key(row: dict) -> tuple:
    """Ordering for rows with no reviews: weak popularity signals only."""
    return (
        int(float(row.get("boughtInLastMonth") or 0)),
        1 if str(row.get("isBestSeller")) == "True" else 0,
        1 if float(row.get("listPrice") or 0) > 0 else 0,
    )


def select(rows: Iterable[dict], quota: int) -> list[dict]:
    """Tiered quality fill (docs/dataset.md 5.3, step 5).

    67.7% of qualifying rows have zero reviews, so quality_score alone would
    starve most categories. Fill from reviewed products first, top up from
    unreviewed ranked by weak popularity signals.
    """
    reviewed, unreviewed = [], []
    for row in rows:
        (reviewed if float(row.get("reviews") or 0) > 0 else unreviewed).append(row)

    reviewed.sort(key=lambda r: quality_score(float(r["stars"]), int(float(r["reviews"]))),
                  reverse=True)
    unreviewed.sort(key=_tier_b_sort_key, reverse=True)

    picked = reviewed[:quota]
    if len(picked) < quota:
        picked += unreviewed[: quota - len(picked)]
    return picked


def run(csv_path: Path, out_path: Path, quota: int = QUOTA_PER_CATEGORY) -> None:
    category_map = json.loads(
        (Path("data") / "category_map.json").read_text(encoding="utf-8"))

    # Pass 1: hygiene + exact-title dedup + near-dup collapse, grouped by category.
    by_category: dict[str, dict[str, dict]] = collections.defaultdict(dict)
    seen_titles: set[str] = set()
    for row in csv.DictReader(csv_path.open(encoding="utf-8")):
        if not passes_hygiene(row):
            continue
        exact = normalise_title(row["title"])[:120]
        if exact in seen_titles:
            continue
        seen_titles.add(exact)

        cat = row["categoryName"]
        vkey = variant_key(row["title"])
        bucket = by_category[cat]
        incumbent = bucket.get(vkey)
        score = quality_score(float(row["stars"]), int(float(row["reviews"])))
        if incumbent is None or score > incumbent["_score"]:
            row["_score"] = score
            bucket[vkey] = row

    # Pass 2: price clip per category, then stratified quota.
    products: list[dict] = []
    for cat, bucket in by_category.items():
        rows = list(bucket.values())
        prices = sorted(float(r["price"]) for r in rows)
        clip = _percentile(prices, PRICE_CLIP_PERCENTILE)
        rows = [r for r in rows if float(r["price"]) <= clip]

        for row in select(rows, quota):
            products.append({
                "id": row["asin"],
                "title_original": row["title"],
                "category": category_map.get(cat, cat),
                "category_source": cat,
                "cohort": category_map.get(cat, cat),
                "price": float(row["price"]),
                "currency": "INR",
                "rating": float(row["stars"]),
                "reviews": int(float(row["reviews"])),
                "quality_score": round(quality_score(
                    float(row["stars"]), int(float(row["reviews"]))), 3),
                "image_url": row["imgUrl"],
                "product_url": f"https://www.amazon.in/dp/{row['asin']}",
            })

    assign_price_tiers(products)

    with out_path.open("w", encoding="utf-8") as f:
        for p in products:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    print(f"wrote {len(products)} products across {len(by_category)} categories")


if __name__ == "__main__":
    run(Path(sys.argv[1] if len(sys.argv) > 1
             else "data/amz_in_total_products_data_processed.csv"),
        Path("data/catalogue.raw.jsonl"))
```

**Scope note — tier-2 translation is deferred.** `passes_hygiene` keeps Latin-script titles
only, so the four Devanagari-heavy categories identified in dataset.md §6 (lehenga choli,
dhoti, home decor, thermals) contribute fewer rows than their quota. That is an accepted
reduction: the Latin pool holds 179,049 qualifying rows across 151 categories against a
~20k target, so taxonomy coverage stays broad. The enrichment prompt in Task 7 already
emits `title_en`, so enabling tier 2 later means relaxing this one filter per category —
not new machinery.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_ingest.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Run ingest against the real CSV**

```bash
cd backend && python scripts/ingest.py
wc -l data/catalogue.raw.jsonl
```

Expected: roughly 15,000–20,000 products. `QUOTA_PER_CATEGORY` is a ceiling, so the total
lands below `214 × 100` because many categories cannot fill it.

- [ ] **Step 6: Sanity-check the output by eye**

```bash
cd backend && python -c "
import json, collections
rows=[json.loads(l) for l in open('data/catalogue.raw.jsonl')]
print('products:', len(rows))
print('categories:', len({r['category'] for r in rows}))
print('price tiers:', collections.Counter(r['price_tier'] for r in rows))
print('sample:'); [print(' ', r['price_tier'], int(r['price']), r['title_original'][:70]) for r in rows[:5]]
"
```

Tier counts should be uneven but present for all four. If everything is `budget`, the
cohort key is wrong.

- [ ] **Step 7: Commit**

```bash
git add backend/scripts/ingest.py backend/tests/test_ingest.py
git commit -m "feat: stratified query-agnostic catalogue ingest with deterministic price tiers"
```

---

### Task 7: Conservative enrichment with tier-B verification

**Files:**
- Create: `backend/scripts/enrich.py`
- Test: `backend/tests/test_enrich.py`

**Interfaces:**
- Consumes: `scripts.verify_attributes.verify`, `TIER_B_FIELDS`; `data/catalogue.raw.jsonl`.
- Produces: `data/catalogue.jsonl` with `description`, `title` (English), and `attributes` carrying provenance; plus `scripts.enrich.apply_trust_tiers(raw_attrs: dict, source_title: str) -> dict`.

The governing rule (spec §4.2): the model may only restate, expand, and categorise what the
title, category, and price already assert. Unknown fields emit `null`. Anything the model
claims as explicit is re-checked in code before it earns tier B.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_enrich.py`:

```python
from scripts.enrich import apply_trust_tiers

TITLE = "Wildcraft 45L Rucksack Water Resistant Trekking Backpack"


def test_verified_attribute_gets_title_verified_source():
    out = apply_trust_tiers({"capacity_l": 45}, TITLE)
    assert out["capacity_l"] == {"value": 45, "source": "title_verified"}


def test_unverifiable_claim_is_demoted_not_dropped():
    out = apply_trust_tiers({"capacity_l": 60}, TITLE)
    assert out["capacity_l"] == {"value": 60, "source": "inferred"}


def test_inferred_field_is_never_promoted():
    out = apply_trust_tiers({"use_case": ["trekking"]}, TITLE)
    assert out["use_case"] == {"value": ["trekking"], "source": "inferred"}


def test_null_value_carries_null_source():
    out = apply_trust_tiers({"material": None}, TITLE)
    assert out["material"] == {"value": None, "source": None}


def test_fabricated_material_is_demoted():
    # The title says nothing about polyester — it must not reach tier B.
    out = apply_trust_tiers({"material": "polyester"}, TITLE)
    assert out["material"]["source"] == "inferred"


def test_gender_stated_in_title_is_verified():
    out = apply_trust_tiers({"gender": "women"}, "Puma Running Shoes for Women Size 7")
    assert out["gender"]["source"] == "title_verified"
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python -m pytest tests/test_enrich.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.enrich'`.

- [ ] **Step 3: Write `backend/scripts/enrich.py`**

```python
"""Generate descriptions and trust-tiered attributes from source titles.

The source dataset has no description field, so descriptions are generated —
but grounded strictly in the title. A fabricated specification would flow into
a hard filter and produce confidently wrong recommendations
(docs/dataset.md 4.2).

Checkpointed per batch: a rate limit or Ctrl-C resumes from the last completed
batch rather than restarting hundreds of network calls.
"""
import json
import os
import sys
from pathlib import Path

from groq import Groq

from scripts.verify_attributes import TIER_B_FIELDS, verify

BATCH_SIZE = 50
CHECKPOINT_DIR = Path("data/enriched")

PROMPT = """You are cataloguing products for a shopping assistant. For each product you
receive an Amazon India listing title, its category, and its price in INR.

For each product return an object with these fields:
  id            copy the input id exactly
  title_en      the title in natural English. If the input is Hindi, translate it.
                Keep brand names and model numbers VERBATIM - never transliterate them.
  description   2-3 sentences describing the product for a shopper.
  capacity_l    litre capacity ONLY if the title states one, else null
  water_resistant  true ONLY if the title says water resistant/proof, else null
  gender        "men"/"women"/"unisex" ONLY if the title states it, else null
  material      ONLY if the title names a material, else null
  product_type  a short noun for what this is, e.g. "backpack", "kurta", "headphones"
  use_case      list of activities this suits, e.g. ["trekking", "travel"]
  occasion      list of occasions, e.g. ["wedding", "gifting"], or []
  season        list from ["summer","winter","monsoon","all-season"]
  gift_suitable true or false

CRITICAL RULES:
- NEVER invent specifications. No weights, temperature ratings, fill power,
  dimensions, or durability claims unless the title states them.
- If the title does not support a value, return null. Missing data is REQUIRED
  over guessed data.
- description must not assert facts absent from the title. Describe what the
  product is and who it suits, not specifications you cannot see.

Return ONLY a JSON object: {{"products": [ ... ]}}

Products:
{batch}"""


def apply_trust_tiers(raw_attrs: dict, source_title: str) -> dict:
    """Attach provenance to each attribute, verifying tier-B claims.

    An attribute reaches "title_verified" only by passing a code verifier against
    the ORIGINAL title. Failures are demoted to "inferred", where they may rank
    but never exclude (docs/dataset.md 4.1).
    """
    out: dict[str, dict] = {}
    for field, value in raw_attrs.items():
        if value is None or value == []:
            out[field] = {"value": value if value != [] else [], "source": None}
            continue
        if field in TIER_B_FIELDS and verify(field, value, source_title):
            out[field] = {"value": value, "source": "title_verified"}
        else:
            out[field] = {"value": value, "source": "inferred"}
    return out


def _call(client: Groq, batch: list[dict]) -> list[dict]:
    payload = [{"id": p["id"], "title": p["title_original"],
                "category": p["category"], "price": p["price"]} for p in batch]
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user",
                   "content": PROMPT.format(batch=json.dumps(payload, ensure_ascii=False))}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(resp.choices[0].message.content)["products"]


def run(in_path: Path, out_path: Path) -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    products = [json.loads(line) for line in in_path.open(encoding="utf-8")]
    client = Groq(api_key=os.environ["GROQ_API_KEY"])

    batches = [products[i:i + BATCH_SIZE] for i in range(0, len(products), BATCH_SIZE)]
    for n, batch in enumerate(batches):
        ckpt = CHECKPOINT_DIR / f"batch_{n:04d}.json"
        if ckpt.exists():
            continue
        try:
            enriched = _call(client, batch)
        except Exception as exc:  # noqa: BLE001 - checkpoint, then surface
            print(f"batch {n} failed: {exc}", file=sys.stderr)
            raise
        ckpt.write_text(json.dumps(enriched, ensure_ascii=False), encoding="utf-8")
        print(f"  {n + 1}/{len(batches)} batches", file=sys.stderr)

    by_id = {p["id"]: p for p in products}
    written = 0
    with out_path.open("w", encoding="utf-8") as f:
        for ckpt in sorted(CHECKPOINT_DIR.glob("batch_*.json")):
            for item in json.loads(ckpt.read_text(encoding="utf-8")):
                base = by_id.get(item.get("id"))
                if base is None:
                    continue  # model invented an id
                source_title = base["title_original"]
                raw = {k: item.get(k) for k in
                       ("capacity_l", "water_resistant", "gender", "material",
                        "product_type", "use_case", "occasion", "season", "gift_suitable")}
                base["title"] = item.get("title_en") or source_title
                base["description"] = item.get("description") or ""
                base["attributes"] = apply_trust_tiers(raw, source_title)
                f.write(json.dumps(base, ensure_ascii=False) + "\n")
                written += 1
    print(f"wrote {written} enriched products")


if __name__ == "__main__":
    run(Path("data/catalogue.raw.jsonl"), Path("data/catalogue.jsonl"))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_enrich.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Enrich a 30-product sample and review it by hand**

The spec requires manual review before the full run — this is the only check that catches
a model fabricating specifications in prose.

```bash
cd backend && head -30 data/catalogue.raw.jsonl > data/sample.raw.jsonl
GROQ_API_KEY=... python -c "
from pathlib import Path
from scripts import enrich
enrich.CHECKPOINT_DIR = Path('data/enriched_sample')
enrich.run(Path('data/sample.raw.jsonl'), Path('data/sample.jsonl'))
"
python -c "
import json
for l in open('data/sample.jsonl'):
    p=json.loads(l)
    print('---'); print('SRC :', p['title_original'][:90])
    print('DESC:', p['description'])
    print('VER :', {k:v['value'] for k,v in p['attributes'].items() if v['source']=='title_verified'})
"
```

Reject and re-prompt if any description asserts a weight, temperature rating, dimension, or
material not present in the source title.

- [ ] **Step 6: Run the full enrichment**

```bash
cd backend && GROQ_API_KEY=... python scripts/enrich.py
wc -l data/catalogue.jsonl
```

Interruptions are safe — rerun resumes from the last checkpoint.

- [ ] **Step 7: Verify tier discipline held across the whole catalogue**

```bash
cd backend && python -c "
import json, collections
c=collections.Counter()
for l in open('data/catalogue.jsonl'):
    for f,a in json.loads(l)['attributes'].items():
        c[(f, a['source'])] += 1
for k,v in sorted(c.items()): print(f'{k[0]:16s} {str(k[1]):15s} {v}')
"
```

Expected: `use_case`, `season`, `occasion`, `product_type`, `gift_suitable` appear only as
`inferred`. If any shows `title_verified`, `TIER_B_FIELDS` has been widened without a
verifier — a correctness bug, not a cosmetic one.

- [ ] **Step 8: Commit**

```bash
git add backend/scripts/enrich.py backend/tests/test_enrich.py
git commit -m "feat: conservative LLM enrichment with tier-B verification"
```

---

### Task 8: Embeddings with a pinned manifest

**Files:**
- Create: `backend/scripts/build_embeddings.py`
- Test: `backend/tests/test_embeddings_build.py`

**Interfaces:**
- Produces: `data/embeddings.npy` (float16, shape `[N, 768]`, L2-normalised), `data/embeddings.manifest.json`, `data/catalogue.jsonl.gz`; and `scripts.build_embeddings.embedding_text(product: dict) -> str`.

The manifest is what makes a vector-space mismatch impossible to express silently
(spec §3.1). The index refuses to load without a match.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_embeddings_build.py`:

```python
from scripts.build_embeddings import embedding_text

PRODUCT = {
    "title": "Wildcraft 45L Rucksack Water Resistant Trekking Backpack",
    "description": "A 45-litre water-resistant rucksack for multi-day treks.",
    "category": "Rucksacks and Trekking Backpacks",
    "attributes": {
        "use_case": {"value": ["trekking", "hiking"], "source": "inferred"},
        "season": {"value": ["winter"], "source": "inferred"},
        "material": {"value": None, "source": None},
    },
}


def test_embedding_text_includes_title_description_category():
    text = embedding_text(PRODUCT)
    assert "Wildcraft 45L Rucksack" in text
    assert "multi-day treks" in text
    assert "Rucksacks and Trekking Backpacks" in text


def test_embedding_text_includes_attribute_values():
    text = embedding_text(PRODUCT)
    assert "trekking" in text and "winter" in text


def test_embedding_text_omits_null_attributes():
    assert "None" not in embedding_text(PRODUCT)
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python -m pytest tests/test_embeddings_build.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.build_embeddings'`.

- [ ] **Step 3: Write `backend/scripts/build_embeddings.py`**

```python
"""Embed the enriched catalogue and write a pinned manifest.

float16 halves the file with no meaningful effect on cosine similarity;
768 dimensions uses gemini-embedding-001's supported Matryoshka truncation
(docs/dataset.md 5.2).

Vectors are L2-normalised at build time so query-time similarity is a plain
dot product.
"""
import gzip
import json
import os
import shutil
from datetime import date
from pathlib import Path

import numpy as np
from google import genai

MODEL = "gemini-embedding-001"
DIMS = 768
BATCH = 100


def embedding_text(product: dict) -> str:
    """Flatten a product into the text that gets embedded.

    Title carries most of the signal (Amazon titles are long and keyword-dense);
    description and attribute values add the semantics the title lacks.
    """
    parts = [product["title"], product.get("description", ""), product.get("category", "")]
    for attr in product.get("attributes", {}).values():
        value = attr.get("value")
        if value is None or value == []:
            continue
        if isinstance(value, list):
            parts.extend(str(v) for v in value)
        elif isinstance(value, bool):
            continue
        else:
            parts.append(str(value))
    return " | ".join(p for p in parts if p)


def run(in_path: Path, out_dir: Path) -> None:
    products = [json.loads(line) for line in in_path.open(encoding="utf-8")]
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    vectors: list[list[float]] = []
    for i in range(0, len(products), BATCH):
        chunk = [embedding_text(p) for p in products[i:i + BATCH]]
        resp = client.models.embed_content(
            model=MODEL, contents=chunk,
            config={"output_dimensionality": DIMS, "task_type": "RETRIEVAL_DOCUMENT"},
        )
        vectors.extend(e.values for e in resp.embeddings)
        print(f"  embedded {len(vectors)}/{len(products)}")

    matrix = np.asarray(vectors, dtype=np.float32)
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
    np.save(out_dir / "embeddings.npy", matrix.astype(np.float16))

    (out_dir / "embeddings.manifest.json").write_text(json.dumps({
        "model": MODEL, "dims": DIMS, "dtype": "float16",
        "normalised": True, "count": len(products),
        "built": date.today().isoformat(),
    }, indent=2))

    # Row order in embeddings.npy must match line order in the gzipped catalogue.
    with in_path.open("rb") as src, gzip.open(out_dir / "catalogue.jsonl.gz", "wb") as dst:
        shutil.copyfileobj(src, dst)

    print(f"wrote {len(products)} vectors, {DIMS} dims")


if __name__ == "__main__":
    run(Path("data/catalogue.jsonl"), Path("data"))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_embeddings_build.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Build the embeddings**

```bash
cd backend && GEMINI_API_KEY=... python scripts/build_embeddings.py
ls -lh data/embeddings.npy data/catalogue.jsonl.gz
cat data/embeddings.manifest.json
```

Expected: `embeddings.npy` around 30 MB for 20k products, `catalogue.jsonl.gz` around 6 MB.
If `embeddings.npy` exceeds 50 MB, GitHub warns — reduce `DIMS` to 512 and rebuild.

- [ ] **Step 6: Verify row alignment**

```bash
cd backend && python -c "
import gzip, json, numpy as np
m=np.load('data/embeddings.npy')
n=sum(1 for _ in gzip.open('data/catalogue.jsonl.gz','rt',encoding='utf-8'))
print('vectors:', m.shape, 'catalogue rows:', n)
assert m.shape[0]==n, 'ROW MISALIGNMENT — vectors do not match catalogue'
print('aligned OK')
"
```

A misalignment here silently returns the wrong product for every query. This assertion is
the only thing standing between that bug and production.

- [ ] **Step 7: Commit — only if Task 2 cleared the licence**

```bash
git add backend/scripts/build_embeddings.py backend/tests/test_embeddings_build.py
git add backend/data/catalogue.jsonl.gz backend/data/embeddings.npy backend/data/embeddings.manifest.json
git commit -m "feat: build pinned catalogue embeddings with manifest"
```

If `docs/licence-check.md` recorded a restrictive licence, commit only the script and tests
and follow the fallback in dataset.md §1.1.

---

## Phase 2 — Backend core

### Task 9: Schemas

**Files:**
- Create: `backend/app/schemas/__init__.py`, `product.py`, `intent.py`, `response.py`
- Test: `backend/tests/test_schemas.py`

**Interfaces:**
- Produces, imported by every later backend task:
  - `product.Attribute(value: Any, source: Literal["title_verified","inferred"] | None)`
  - `product.Product(id, title, title_original, description, category, price, currency, price_tier, rating, reviews, quality_score, attributes: dict[str, Attribute], image_url, product_url)` with `Product.attr(name) -> Attribute | None` and `Product.verified(name) -> Any | None`
  - `intent.SubNeed(label: str, query: str)`
  - `intent.Assumption(field, value, reason, confidence: Literal["low","medium","high"], editable: bool)`
  - `intent.ShoppingIntent(activity, destination, season, duration_days, budget_max, gender, occasion)` — all optional
  - `intent.IntentResult(intent, sub_needs, assumptions, clarifying_question, confidence)`
  - `response.Candidate(product: Product, similarity: float, sub_need: str, score: float)`
  - `response.Recommendation(product_id, title, price, price_tier, rating, reviews, image_url, product_url, reason)`
  - `response.ResultGroup(label, recommendations, empty_reason: str | None)`
  - `response.RecommendResponse(session_id, intent, assumptions, clarifying_question, groups, relaxations, timings)`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_schemas.py`:

```python
from app.schemas.intent import Assumption, ShoppingIntent, SubNeed
from app.schemas.product import Attribute, Product


def _product(**overrides) -> Product:
    base = dict(
        id="B08XYZ", title="Wildcraft 45L Rucksack Water Resistant Trekking Backpack",
        title_original="Wildcraft 45L Rucksack Water Resistant Trekking Backpack",
        description="A 45-litre rucksack.", category="Backpacks",
        price=3499.0, price_tier="mid", rating=4.3, reviews=212, quality_score=23.1,
        attributes={
            "capacity_l": Attribute(value=45, source="title_verified"),
            "use_case": Attribute(value=["trekking"], source="inferred"),
            "material": Attribute(value=None, source=None),
        },
        image_url="https://m.media-amazon.com/x.jpg",
        product_url="https://www.amazon.in/dp/B08XYZ",
    )
    base.update(overrides)
    return Product(**base)


def test_verified_returns_value_only_for_title_verified():
    p = _product()
    assert p.verified("capacity_l") == 45
    assert p.verified("use_case") is None       # inferred never counts as verified
    assert p.verified("material") is None
    assert p.verified("missing_field") is None


def test_attr_returns_attribute_or_none():
    p = _product()
    assert p.attr("use_case").value == ["trekking"]
    assert p.attr("nope") is None


def test_intent_fields_all_optional():
    i = ShoppingIntent()
    assert i.budget_max is None and i.gender is None


def test_sub_need_requires_label_and_query():
    s = SubNeed(label="Backpack", query="50L trekking rucksack")
    assert s.label == "Backpack"


def test_assumption_defaults_to_editable():
    a = Assumption(field="climate", value="cold-weather likely",
                   reason="high-altitude trek in late October", confidence="medium")
    assert a.editable is True
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python -m pytest tests/test_schemas.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.schemas.product'`.

- [ ] **Step 3: Write `backend/app/schemas/product.py`**

```python
from typing import Any, Literal

from pydantic import BaseModel

TrustSource = Literal["title_verified", "inferred"]


class Attribute(BaseModel):
    """A product attribute with its provenance.

    `source` is what decides whether this attribute may exclude a product:
    "title_verified" may hard-filter, "inferred" may only rank, None means absent
    (docs/dataset.md 4.1).
    """
    value: Any = None
    source: TrustSource | None = None


class Product(BaseModel):
    id: str
    title: str
    title_original: str
    description: str = ""
    category: str
    price: float
    currency: str = "INR"
    price_tier: Literal["budget", "mid", "premium", "luxury"]
    rating: float
    reviews: int
    quality_score: float
    attributes: dict[str, Attribute] = {}
    image_url: str
    product_url: str

    def attr(self, name: str) -> Attribute | None:
        return self.attributes.get(name)

    def verified(self, name: str) -> Any | None:
        """Return the value only if it passed title verification, else None.

        Callers that hard-filter MUST use this rather than `attr`, so an inferred
        value can never exclude a product.
        """
        a = self.attributes.get(name)
        if a is None or a.source != "title_verified":
            return None
        return a.value
```

- [ ] **Step 4: Write `backend/app/schemas/intent.py`**

```python
from typing import Literal

from pydantic import BaseModel, Field


class SubNeed(BaseModel):
    label: str
    query: str


class Assumption(BaseModel):
    field: str
    value: str
    reason: str
    confidence: Literal["low", "medium", "high"] = "medium"
    editable: bool = True


class ShoppingIntent(BaseModel):
    activity: str | None = None
    destination: str | None = None
    season: str | None = None
    duration_days: int | None = None
    budget_max: float | None = None
    gender: Literal["men", "women", "unisex"] | None = None
    occasion: str | None = None

    def merge(self, delta: "ShoppingIntent") -> "ShoppingIntent":
        """Apply a follow-up delta without losing prior context.

        "make it cheaper" sets budget_max and must leave everything else intact,
        so only non-None fields from the delta overwrite.
        """
        merged = self.model_dump()
        for key, value in delta.model_dump().items():
            if value is not None:
                merged[key] = value
        return ShoppingIntent(**merged)


class IntentResult(BaseModel):
    intent: ShoppingIntent = Field(default_factory=ShoppingIntent)
    sub_needs: list[SubNeed] = []
    assumptions: list[Assumption] = []
    clarifying_question: str | None = None
    confidence: float = 0.5
```

- [ ] **Step 5: Write `backend/app/schemas/response.py`**

```python
from typing import Any, Literal

from pydantic import BaseModel

from app.schemas.intent import Assumption, ShoppingIntent
from app.schemas.product import Product


class Candidate(BaseModel):
    product: Product
    similarity: float
    sub_need: str
    score: float = 0.0


class Recommendation(BaseModel):
    product_id: str
    title: str
    price: float
    price_tier: str
    rating: float
    reviews: int
    image_url: str
    product_url: str
    reason: str


class ResultGroup(BaseModel):
    label: str
    recommendations: list[Recommendation] = []
    empty_reason: str | None = None


class RecommendResponse(BaseModel):
    session_id: str
    intent: ShoppingIntent
    assumptions: list[Assumption] = []
    clarifying_question: str | None = None
    groups: list[ResultGroup] = []
    relaxations: list[str] = []
    timings_ms: dict[str, float] = {}


class StreamEvent(BaseModel):
    event: Literal["understood", "searching", "results", "done", "error"]
    data: dict[str, Any]
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd backend && touch app/schemas/__init__.py app/__init__.py
python -m pytest tests/test_schemas.py -v
```

Expected: 5 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas backend/tests/test_schemas.py
git commit -m "feat: add trust-tiered product and intent schemas"
```

---

### Task 10: Catalogue loader and numpy index with manifest verification

**Files:**
- Create: `backend/app/catalogue/__init__.py`, `loader.py`, `index.py`
- Test: `backend/tests/test_index.py`

**Interfaces:**
- Consumes: `app.schemas.product.Product`, `app.config.Settings`.
- Produces:
  - `loader.CatalogueSource` protocol with `load() -> list[Product]`
  - `loader.JsonlCatalogue(path: Path)`
  - `index.CatalogueIndex(products: list[Product], matrix: np.ndarray)` with `search(query_vec: np.ndarray, subset: list[int] | None, top_k: int) -> list[tuple[int, float]]`
  - `index.load_index(data_dir: Path, settings: Settings) -> CatalogueIndex` — raises `ManifestMismatch` when the configured embedding model or dims differ from the manifest

- [ ] **Step 1: Write the failing test**

`backend/tests/test_index.py`:

```python
import gzip
import json

import numpy as np
import pytest

from app.catalogue.index import CatalogueIndex, ManifestMismatch, load_index
from app.catalogue.loader import JsonlCatalogue


def _row(i: int) -> dict:
    return {
        "id": f"B{i}", "title": f"Product {i}", "title_original": f"Product {i}",
        "description": "", "category": "Test", "price": 100.0 + i, "price_tier": "mid",
        "rating": 4.0, "reviews": 10, "quality_score": 9.6, "attributes": {},
        "image_url": "https://x/i.jpg", "product_url": f"https://www.amazon.in/dp/B{i}",
    }


@pytest.fixture
def data_dir(tmp_path):
    with gzip.open(tmp_path / "catalogue.jsonl.gz", "wt", encoding="utf-8") as f:
        for i in range(3):
            f.write(json.dumps(_row(i)) + "\n")
    m = np.eye(3, 4, dtype=np.float16)          # 3 orthogonal unit vectors
    np.save(tmp_path / "embeddings.npy", m)
    (tmp_path / "embeddings.manifest.json").write_text(json.dumps(
        {"model": "gemini-embedding-001", "dims": 4, "count": 3, "normalised": True}))
    return tmp_path


def test_loader_reads_gzipped_jsonl(data_dir):
    products = JsonlCatalogue(data_dir / "catalogue.jsonl.gz").load()
    assert [p.id for p in products] == ["B0", "B1", "B2"]


def test_search_ranks_by_cosine(data_dir):
    products = JsonlCatalogue(data_dir / "catalogue.jsonl.gz").load()
    idx = CatalogueIndex(products, np.load(data_dir / "embeddings.npy"))
    hits = idx.search(np.array([0, 1, 0, 0], dtype=np.float32), None, top_k=2)
    assert hits[0][0] == 1
    assert hits[0][1] == pytest.approx(1.0, abs=1e-3)


def test_search_respects_subset(data_dir):
    products = JsonlCatalogue(data_dir / "catalogue.jsonl.gz").load()
    idx = CatalogueIndex(products, np.load(data_dir / "embeddings.npy"))
    hits = idx.search(np.array([0, 1, 0, 0], dtype=np.float32), subset=[0, 2], top_k=2)
    assert {h[0] for h in hits} == {0, 2}


def test_search_on_empty_subset_returns_nothing(data_dir):
    products = JsonlCatalogue(data_dir / "catalogue.jsonl.gz").load()
    idx = CatalogueIndex(products, np.load(data_dir / "embeddings.npy"))
    assert idx.search(np.array([1, 0, 0, 0], dtype=np.float32), subset=[], top_k=5) == []


def test_load_index_rejects_model_mismatch(data_dir):
    from app.config import Settings
    s = Settings(_env_file=None, embedding_model="some-other-model", embedding_dims=4)
    with pytest.raises(ManifestMismatch, match="some-other-model"):
        load_index(data_dir, s)


def test_load_index_rejects_dims_mismatch(data_dir):
    from app.config import Settings
    s = Settings(_env_file=None, embedding_model="gemini-embedding-001", embedding_dims=768)
    with pytest.raises(ManifestMismatch, match="768"):
        load_index(data_dir, s)
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python -m pytest tests/test_index.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.catalogue.index'`.

- [ ] **Step 3: Write `backend/app/catalogue/loader.py`**

```python
import gzip
import json
from pathlib import Path
from typing import Protocol

from app.schemas.product import Product


class CatalogueSource(Protocol):
    def load(self) -> list[Product]: ...


class JsonlCatalogue:
    """Reads a gzipped JSONL catalogue.

    Line order is significant: it must match row order in embeddings.npy.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[Product]:
        opener = gzip.open if self.path.suffix == ".gz" else open
        with opener(self.path, "rt", encoding="utf-8") as f:
            return [Product.model_validate(json.loads(line)) for line in f if line.strip()]
```

- [ ] **Step 4: Write `backend/app/catalogue/index.py`**

```python
import json
from pathlib import Path

import numpy as np

from app.catalogue.loader import JsonlCatalogue
from app.config import Settings
from app.schemas.product import Product


class ManifestMismatch(RuntimeError):
    """Raised when configured embeddings differ from the built catalogue.

    Failing loudly here is the point: a silent mismatch would put query vectors in
    a different space from the catalogue, cosine would still return plausible
    numbers, and every result would be noise with nothing to debug against
    (spec 3.1).
    """


class CatalogueIndex:
    def __init__(self, products: list[Product], matrix: np.ndarray) -> None:
        if len(products) != matrix.shape[0]:
            raise ManifestMismatch(
                f"row misalignment: {len(products)} products, {matrix.shape[0]} vectors")
        self.products = products
        self.matrix = matrix.astype(np.float32)

    def search(self, query_vec: np.ndarray, subset: list[int] | None,
               top_k: int) -> list[tuple[int, float]]:
        """Return (row_index, similarity) pairs, best first.

        Vectors are L2-normalised at build time, so a dot product is the cosine.
        """
        if subset is not None:
            if not subset:
                return []
            rows = np.asarray(subset, dtype=np.int64)
            sims = self.matrix[rows] @ query_vec
        else:
            rows = np.arange(self.matrix.shape[0])
            sims = self.matrix @ query_vec

        k = min(top_k, sims.shape[0])
        top = np.argpartition(-sims, k - 1)[:k]
        top = top[np.argsort(-sims[top])]
        return [(int(rows[i]), float(sims[i])) for i in top]


def load_index(data_dir: Path, settings: Settings) -> CatalogueIndex:
    manifest = json.loads((data_dir / "embeddings.manifest.json").read_text())

    if manifest["model"] != settings.embedding_model:
        raise ManifestMismatch(
            f"catalogue built with {manifest['model']!r} but configured "
            f"embedding_model is {settings.embedding_model!r}. Rebuild embeddings.")
    if int(manifest["dims"]) != settings.embedding_dims:
        raise ManifestMismatch(
            f"catalogue built with {manifest['dims']} dims but configured "
            f"embedding_dims is {settings.embedding_dims}. Rebuild embeddings.")

    products = JsonlCatalogue(data_dir / "catalogue.jsonl.gz").load()
    matrix = np.load(data_dir / "embeddings.npy")
    return CatalogueIndex(products, matrix)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && touch app/catalogue/__init__.py
python -m pytest tests/test_index.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/catalogue backend/tests/test_index.py
git commit -m "feat: catalogue index with manifest-pinned embedding verification"
```

---

### Task 11: Errors and structured logging

**Files:**
- Create: `backend/app/core/__init__.py`, `errors.py`, `logging.py`
- Test: `backend/tests/test_errors.py`

**Interfaces:**
- Produces:
  - `errors.AppError(code, message, retryable, http_status)` and subclasses `InvalidQuery`, `ProviderUnavailable`, `RateLimited`, `NoResults`, `Internal`
  - `errors.AppError.envelope() -> dict` → `{"error": {"code","message","retryable"}}`
  - `logging.setup_logging()`, `logging.log_stage(request_id: str, stage: str, **fields)`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_errors.py`:

```python
import json

from app.core.errors import NoResults, ProviderUnavailable, RateLimited


def test_envelope_shape():
    e = RateLimited("slow down")
    assert e.envelope() == {
        "error": {"code": "RATE_LIMITED", "message": "slow down", "retryable": True}}


def test_provider_unavailable_is_not_retryable_by_client():
    assert ProviderUnavailable("all providers failed").retryable is False


def test_no_results_is_a_client_visible_200_level_concern():
    assert NoResults("nothing matched").http_status == 200


def test_log_stage_emits_single_json_line(capsys):
    from app.core.logging import log_stage, setup_logging
    setup_logging()
    log_stage("req-1", "intent", duration_ms=812.5, provider="gemini")
    line = capsys.readouterr().err.strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["request_id"] == "req-1"
    assert payload["stage"] == "intent"
    assert payload["provider"] == "gemini"
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python -m pytest tests/test_errors.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.errors'`.

- [ ] **Step 3: Write `backend/app/core/errors.py`**

```python
class AppError(Exception):
    code = "INTERNAL"
    retryable = False
    http_status = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def envelope(self) -> dict:
        return {"error": {"code": self.code, "message": self.message,
                          "retryable": self.retryable}}


class InvalidQuery(AppError):
    code = "INVALID_QUERY"
    http_status = 400


class ProviderUnavailable(AppError):
    """Primary and fallback generation providers both failed."""
    code = "PROVIDER_UNAVAILABLE"
    http_status = 503


class RateLimited(AppError):
    code = "RATE_LIMITED"
    retryable = True
    http_status = 429


class NoResults(AppError):
    """Every sub-need came back empty after relaxation.

    Not an error condition for individual empty groups — those are a normal
    response body (spec 7.2).
    """
    code = "NO_RESULTS"
    http_status = 200


class Internal(AppError):
    pass
```

- [ ] **Step 4: Write `backend/app/core/logging.py`**

```python
import json
import logging
import sys

_LOGGER = logging.getLogger("assistant")


def setup_logging() -> None:
    if _LOGGER.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _LOGGER.addHandler(handler)
    _LOGGER.setLevel(logging.INFO)
    _LOGGER.propagate = False


def log_stage(request_id: str, stage: str, **fields) -> None:
    """One structured JSON line per pipeline stage."""
    _LOGGER.info(json.dumps({"request_id": request_id, "stage": stage, **fields}))
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && touch app/core/__init__.py
python -m pytest tests/test_errors.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core backend/tests/test_errors.py
git commit -m "feat: add error envelope and structured stage logging"
```

---

### Task 12: Providers — generation chain and pinned embeddings

**Files:**
- Create: `backend/app/providers/__init__.py`, `generation.py`, `embedding.py`
- Test: `backend/tests/test_providers.py`

**Interfaces:**
- Consumes: `app.core.errors.ProviderUnavailable`, `app.config.Settings`.
- Produces:
  - `generation.GenerationProvider` protocol: `async generate_json(prompt: str, *, request_id: str) -> dict`, attribute `name: str`
  - `generation.StubGenerationProvider(responses: list[dict])` — deterministic, used by every pipeline test
  - `generation.GeminiGeneration`, `generation.GroqGeneration`
  - `generation.FallbackChain(primary, fallback)` — raises `ProviderUnavailable` when both fail
  - `embedding.EmbeddingProvider` protocol: `async embed(texts: list[str]) -> np.ndarray`
  - `embedding.GeminiEmbedding(api_key, model, dims)`, `embedding.StubEmbedding(dims)`
  - **No embedding fallback exists by design.**

- [ ] **Step 1: Write the failing test**

`backend/tests/test_providers.py`:

```python
import numpy as np
import pytest

from app.core.errors import ProviderUnavailable
from app.providers.embedding import StubEmbedding
from app.providers.generation import FallbackChain, StubGenerationProvider


class _Failing:
    name = "failing"

    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls = 0

    async def generate_json(self, prompt: str, *, request_id: str) -> dict:
        self.calls += 1
        raise self.exc


async def test_stub_returns_queued_responses_in_order():
    stub = StubGenerationProvider([{"a": 1}, {"b": 2}])
    assert await stub.generate_json("x", request_id="r") == {"a": 1}
    assert await stub.generate_json("x", request_id="r") == {"b": 2}


async def test_chain_uses_primary_when_it_works():
    primary = StubGenerationProvider([{"ok": True}])
    fallback = _Failing(RuntimeError("should not be called"))
    chain = FallbackChain(primary, fallback)
    assert await chain.generate_json("x", request_id="r") == {"ok": True}
    assert fallback.calls == 0


async def test_chain_falls_back_once_on_primary_failure():
    primary = _Failing(RuntimeError("429"))
    fallback = StubGenerationProvider([{"rescued": True}])
    chain = FallbackChain(primary, fallback)
    assert await chain.generate_json("x", request_id="r") == {"rescued": True}
    assert primary.calls == 1


async def test_chain_raises_provider_unavailable_when_both_fail():
    chain = FallbackChain(_Failing(RuntimeError("a")), _Failing(RuntimeError("b")))
    with pytest.raises(ProviderUnavailable):
        await chain.generate_json("x", request_id="r")


async def test_chain_with_no_fallback_raises_immediately():
    chain = FallbackChain(_Failing(RuntimeError("a")), None)
    with pytest.raises(ProviderUnavailable):
        await chain.generate_json("x", request_id="r")


async def test_stub_embedding_is_deterministic_and_normalised():
    emb = StubEmbedding(dims=8)
    a = await emb.embed(["trekking backpack"])
    b = await emb.embed(["trekking backpack"])
    assert np.allclose(a, b)
    assert np.isclose(np.linalg.norm(a[0]), 1.0)


async def test_stub_embedding_differs_across_texts():
    emb = StubEmbedding(dims=8)
    out = await emb.embed(["trekking backpack", "wedding sherwani"])
    assert not np.allclose(out[0], out[1])


def test_no_embedding_fallback_chain_exists():
    import app.providers.embedding as m
    assert not hasattr(m, "FallbackChain"), (
        "embedding providers must never fall back — a silent vector-space "
        "swap produces noise with no error (spec 3.1)")
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python -m pytest tests/test_providers.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.providers.generation'`.

- [ ] **Step 3: Write `backend/app/providers/generation.py`**

```python
import json
from typing import Protocol

from app.core.errors import ProviderUnavailable
from app.core.logging import log_stage


class GenerationProvider(Protocol):
    name: str

    async def generate_json(self, prompt: str, *, request_id: str) -> dict: ...


class StubGenerationProvider:
    """Deterministic provider for tests. Makes the whole pipeline testable with
    no network and no API keys, so CI needs no secrets."""

    name = "stub"

    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    async def generate_json(self, prompt: str, *, request_id: str) -> dict:
        self.prompts.append(prompt)
        if not self._responses:
            raise RuntimeError("StubGenerationProvider exhausted")
        return self._responses.pop(0)


class GeminiGeneration:
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash",
                 timeout: float = 30.0) -> None:
        from google import genai
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._timeout = timeout

    async def generate_json(self, prompt: str, *, request_id: str) -> dict:
        resp = await self._client.aio.models.generate_content(
            model=self._model, contents=prompt,
            config={"response_mime_type": "application/json", "temperature": 0.2},
        )
        return json.loads(resp.text)


class GroqGeneration:
    name = "groq"

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile",
                 timeout: float = 30.0) -> None:
        from groq import AsyncGroq
        self._client = AsyncGroq(api_key=api_key, timeout=timeout)
        self._model = model

    async def generate_json(self, prompt: str, *, request_id: str) -> dict:
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        return json.loads(resp.choices[0].message.content)


class FallbackChain:
    """Primary -> one fallback -> ProviderUnavailable.

    Deliberately two providers, not three: each additional provider multiplies
    prompt-compatibility testing across differing structured-output support and
    error semantics (spec 3.2).
    """

    name = "chain"

    def __init__(self, primary: GenerationProvider,
                 fallback: GenerationProvider | None) -> None:
        self.primary = primary
        self.fallback = fallback

    async def generate_json(self, prompt: str, *, request_id: str) -> dict:
        try:
            return await self.primary.generate_json(prompt, request_id=request_id)
        except Exception as exc:  # noqa: BLE001 - any provider failure triggers fallback
            log_stage(request_id, "provider_failover",
                      provider=self.primary.name, error=str(exc)[:200])
            if self.fallback is None:
                raise ProviderUnavailable(f"{self.primary.name} failed: {exc}") from exc

        try:
            return await self.fallback.generate_json(prompt, request_id=request_id)
        except Exception as exc:  # noqa: BLE001
            raise ProviderUnavailable(
                f"both {self.primary.name} and {self.fallback.name} failed: {exc}") from exc
```

- [ ] **Step 4: Write `backend/app/providers/embedding.py`**

```python
"""Embedding providers.

There is deliberately NO fallback chain here. Query vectors must come from the
same model and dimensionality as the catalogue matrix; a dynamic swap would put
them in a different space, cosine would still return plausible numbers, and every
result would be noise with nothing to debug against (spec 3.1).

A missing embedding provider is a hard failure, which is correct: silently wrong
retrieval is worse than a clear error.
"""
import hashlib
from typing import Protocol

import numpy as np


class EmbeddingProvider(Protocol):
    model: str
    dims: int

    async def embed(self, texts: list[str]) -> np.ndarray: ...


class GeminiEmbedding:
    def __init__(self, api_key: str, model: str, dims: int) -> None:
        from google import genai
        self._client = genai.Client(api_key=api_key)
        self.model = model
        self.dims = dims

    async def embed(self, texts: list[str]) -> np.ndarray:
        resp = await self._client.aio.models.embed_content(
            model=self.model, contents=texts,
            config={"output_dimensionality": self.dims, "task_type": "RETRIEVAL_QUERY"},
        )
        matrix = np.asarray([e.values for e in resp.embeddings], dtype=np.float32)
        return matrix / np.linalg.norm(matrix, axis=1, keepdims=True)


class StubEmbedding:
    """Deterministic hash-based vectors for tests.

    Same text always yields the same vector; different texts yield different ones.
    That is all the pipeline tests need.
    """

    model = "stub"

    def __init__(self, dims: int = 768) -> None:
        self.dims = dims

    async def embed(self, texts: list[str]) -> np.ndarray:
        out = np.empty((len(texts), self.dims), dtype=np.float32)
        for i, text in enumerate(texts):
            seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")
            out[i] = np.random.default_rng(seed).standard_normal(self.dims)
        return out / np.linalg.norm(out, axis=1, keepdims=True)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && touch app/providers/__init__.py
python -m pytest tests/test_providers.py -v
```

Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/providers backend/tests/test_providers.py
git commit -m "feat: split generation and embedding providers, no embedding fallback"
```

---

### Task 13: Retrieval — tier-gated hard filters and per-sub-need search

**Files:**
- Create: `backend/app/services/__init__.py`, `backend/app/services/retrieval.py`
- Test: `backend/tests/test_retrieval.py`

**Interfaces:**
- Consumes: `CatalogueIndex`, `ShoppingIntent`, `SubNeed`, `EmbeddingProvider`, `Candidate`.
- Produces:
  - `retrieval.survives(product: Product, intent: ShoppingIntent) -> bool`
  - `retrieval.filter_rows(index, intent) -> tuple[list[int], list[str]]` — returns surviving row indices and relaxation notices
  - `retrieval.retrieve(index, embedder, sub_needs, subset, top_k=8) -> list[Candidate]`

The rule this task enforces: **only tier A and verified tier B may exclude a product.** An
inferred attribute that removed products would let an enrichment mistake make a valid
product unreachable (spec principle 3).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_retrieval.py`:

```python
import numpy as np
import pytest

from app.catalogue.index import CatalogueIndex
from app.providers.embedding import StubEmbedding
from app.schemas.intent import ShoppingIntent, SubNeed
from app.schemas.product import Attribute, Product
from app.services.retrieval import filter_rows, retrieve, survives


def _p(pid: str, price: float, gender: Attribute | None = None) -> Product:
    return Product(
        id=pid, title=f"Product {pid}", title_original=f"Product {pid}", description="",
        category="Test", price=price, price_tier="mid", rating=4.0, reviews=10,
        quality_score=9.6, attributes={"gender": gender} if gender else {},
        image_url="https://x/i.jpg", product_url=f"https://www.amazon.in/dp/{pid}")


def test_unstated_constraints_are_skipped():
    assert survives(_p("A", 99999.0), ShoppingIntent()) is True


def test_budget_excludes_over_max():
    intent = ShoppingIntent(budget_max=3000)
    assert survives(_p("A", 2999.0), intent) is True
    assert survives(_p("B", 3001.0), intent) is False


def test_verified_gender_excludes_mismatch():
    intent = ShoppingIntent(gender="women")
    men = _p("A", 100.0, Attribute(value="men", source="title_verified"))
    assert survives(men, intent) is False


def test_verified_unisex_always_passes_gender():
    intent = ShoppingIntent(gender="women")
    uni = _p("A", 100.0, Attribute(value="unisex", source="title_verified"))
    assert survives(uni, intent) is True


def test_inferred_gender_never_excludes():
    """An enrichment mistake must not make a valid product unreachable."""
    intent = ShoppingIntent(gender="women")
    inferred_men = _p("A", 100.0, Attribute(value="men", source="inferred"))
    assert survives(inferred_men, intent) is True


def test_missing_gender_never_excludes():
    # Gender is unknown for ~50% of the catalogue (docs/dataset.md 3.3).
    assert survives(_p("A", 100.0), ShoppingIntent(gender="women")) is True


def _index(products: list[Product]) -> CatalogueIndex:
    m = np.eye(len(products), 8, dtype=np.float32)
    return CatalogueIndex(products, m)


def test_filter_rows_returns_surviving_indices():
    idx = _index([_p("A", 1000.0), _p("B", 5000.0), _p("C", 2000.0)])
    rows, relaxations = filter_rows(idx, ShoppingIntent(budget_max=2500))
    assert rows == [0, 2]
    assert relaxations == []


def test_filter_rows_relaxes_budget_when_pool_is_empty():
    idx = _index([_p("A", 4000.0), _p("B", 5000.0)])
    rows, relaxations = filter_rows(idx, ShoppingIntent(budget_max=1000))
    assert rows, "relaxation must not leave the pool empty"
    assert len(relaxations) == 1
    assert "1000" in relaxations[0]


async def test_retrieve_returns_candidates_tagged_with_sub_need():
    products = [_p(f"P{i}", 100.0) for i in range(5)]
    idx = _index(products)
    subs = [SubNeed(label="Bags", query="backpack"), SubNeed(label="Shoes", query="boots")]
    cands = await retrieve(idx, StubEmbedding(dims=8), subs, subset=[0, 1, 2, 3, 4], top_k=2)
    assert {c.sub_need for c in cands} == {"Bags", "Shoes"}
    assert len(cands) <= 2 * len(subs)


async def test_retrieve_deduplicates_across_sub_needs():
    products = [_p("SAME", 100.0)]
    idx = CatalogueIndex(products, np.ones((1, 8), dtype=np.float32) / np.sqrt(8))
    subs = [SubNeed(label="A", query="x"), SubNeed(label="B", query="y")]
    cands = await retrieve(idx, StubEmbedding(dims=8), subs, subset=[0], top_k=2)
    assert len(cands) == 1, "the same product must not appear twice"
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python -m pytest tests/test_retrieval.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.retrieval'`.

- [ ] **Step 3: Write `backend/app/services/retrieval.py`**

```python
"""Deterministic filtering and per-sub-need vector retrieval.

The LLM decides WHAT a constraint is; this module decides WHICH rows survive it.
Arithmetic over thousands of rows must be exact and testable, and embeddings do
not encode price - two jackets at Rs 2,000 and Rs 22,000 have near-identical
vectors (spec 5, Stage 2).
"""
from app.catalogue.index import CatalogueIndex
from app.providers.embedding import EmbeddingProvider
from app.schemas.intent import ShoppingIntent, SubNeed
from app.schemas.product import Product
from app.schemas.response import Candidate

BUDGET_RELAXATION_FACTOR = 1.25


def survives(product: Product, intent: ShoppingIntent) -> bool:
    """Hard filter using tier A and verified tier B only.

    Unstated constraints are skipped entirely. Inferred attributes never exclude:
    an enrichment mistake must degrade ranking, not hide products.
    """
    # Tier A - source-grounded
    if intent.budget_max is not None and product.price > intent.budget_max:
        return False

    # Tier B - only when title-verified
    if intent.gender is not None:
        verified_gender = product.verified("gender")
        if verified_gender is not None and verified_gender not in (intent.gender, "unisex"):
            return False

    return True


def filter_rows(index: CatalogueIndex, intent: ShoppingIntent) -> tuple[list[int], list[str]]:
    """Apply hard filters, widening one step rather than returning nothing."""
    rows = [i for i, p in enumerate(index.products) if survives(p, intent)]
    if rows or intent.budget_max is None:
        return rows, []

    relaxed = intent.model_copy(
        update={"budget_max": intent.budget_max * BUDGET_RELAXATION_FACTOR})
    rows = [i for i, p in enumerate(index.products) if survives(p, relaxed)]
    notice = (f"No products under Rs {intent.budget_max:.0f} matched - "
              f"showing options up to Rs {relaxed.budget_max:.0f}.")
    if not rows:
        rows = list(range(len(index.products)))
        notice = f"No products under Rs {intent.budget_max:.0f} matched - budget ignored."
    return rows, [notice]


async def retrieve(index: CatalogueIndex, embedder: EmbeddingProvider,
                   sub_needs: list[SubNeed], subset: list[int],
                   top_k: int = 8) -> list[Candidate]:
    """Retrieve top-k per sub-need, then union and deduplicate.

    Candidate count is at most top_k * len(sub_needs) and is typically lower
    after overlap deduplication (spec 5, Stage 3).
    """
    if not sub_needs:
        return []

    vectors = await embedder.embed([s.query for s in sub_needs])

    best: dict[str, Candidate] = {}
    for sub_need, vec in zip(sub_needs, vectors):
        for row, similarity in index.search(vec, subset, top_k):
            product = index.products[row]
            existing = best.get(product.id)
            if existing is None or similarity > existing.similarity:
                best[product.id] = Candidate(product=product, similarity=similarity,
                                             sub_need=sub_need.label)
    return list(best.values())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && touch app/services/__init__.py
python -m pytest tests/test_retrieval.py -v
```

Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/retrieval.py backend/tests/test_retrieval.py
git commit -m "feat: tier-gated hard filters with relaxation and per-sub-need retrieval"
```

---

### Task 14: Deterministic pre-ranking and diversity

**Files:**
- Create: `backend/app/services/scoring.py`
- Test: `backend/tests/test_scoring.py`

**Interfaces:**
- Consumes: `Candidate`, `ShoppingIntent`.
- Produces:
  - `scoring.WEIGHTS` — a module-level dict, the single place weights live
  - `scoring.score_candidate(candidate, intent, max_quality) -> float`
  - `scoring.prerank(candidates: list[Candidate], intent, per_sub_need: int = 5) -> list[Candidate]`

Deliberately dumb in v1: similarity dominates and everything else is a small bounded
adjustment. There is no relevance-judgement data to fit coefficients on, so tuned weights
would be guesses that silently distort ranking. The eval harness (v2) is what would make
tuning measurable — until then these stay at their defaults (spec §5 Stage 4, §12).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_scoring.py`:

```python
from app.schemas.intent import ShoppingIntent
from app.schemas.product import Attribute, Product
from app.schemas.response import Candidate
from app.services.scoring import WEIGHTS, prerank, score_candidate


def _cand(pid: str, similarity: float, sub_need: str = "Bags", *, title: str | None = None,
          quality: float = 10.0, attrs: dict | None = None) -> Candidate:
    product = Product(
        id=pid, title=title or f"Product {pid}", title_original=title or f"Product {pid}",
        description="", category="Test", price=1000.0, price_tier="mid", rating=4.0,
        reviews=100, quality_score=quality, attributes=attrs or {},
        image_url="https://x/i.jpg", product_url=f"https://www.amazon.in/dp/{pid}")
    return Candidate(product=product, similarity=similarity, sub_need=sub_need)


def test_similarity_dominates_scoring():
    high = score_candidate(_cand("A", 0.9, quality=0.0), ShoppingIntent(), 100.0)
    low = score_candidate(_cand("B", 0.4, quality=100.0), ShoppingIntent(), 100.0)
    assert high > low, "quality must never outweigh a large similarity gap"


def test_quality_breaks_ties():
    a = score_candidate(_cand("A", 0.7, quality=100.0), ShoppingIntent(), 100.0)
    b = score_candidate(_cand("B", 0.7, quality=0.0), ShoppingIntent(), 100.0)
    assert a > b


def test_verified_attribute_match_outweighs_inferred_match():
    intent = ShoppingIntent(activity="trekking")
    verified = _cand("A", 0.7, attrs={"use_case": Attribute(
        value=["trekking"], source="title_verified")})
    inferred = _cand("B", 0.7, attrs={"use_case": Attribute(
        value=["trekking"], source="inferred")})
    assert (score_candidate(verified, intent, 100.0)
            > score_candidate(inferred, intent, 100.0))


def test_weights_keep_adjustments_bounded_below_similarity_range():
    adjustable = WEIGHTS["quality"] + WEIGHTS["verified_attr"] + WEIGHTS["inferred_attr"]
    assert adjustable < 0.5, "combined boosts must not be able to overturn similarity"


def test_prerank_limits_per_sub_need():
    cands = [_cand(f"P{i}", 0.9 - i * 0.01, sub_need="Bags") for i in range(10)]
    assert len(prerank(cands, ShoppingIntent(), per_sub_need=5)) == 5


def test_prerank_keeps_each_sub_need_separately():
    cands = ([_cand(f"A{i}", 0.9, sub_need="Bags") for i in range(6)]
             + [_cand(f"B{i}", 0.5, sub_need="Shoes") for i in range(6)])
    out = prerank(cands, ShoppingIntent(), per_sub_need=3)
    by_need = {}
    for c in out:
        by_need.setdefault(c.sub_need, []).append(c)
    assert len(by_need["Bags"]) == 3
    assert len(by_need["Shoes"]) == 3, "a weak sub-need must not be starved by a strong one"


def test_prerank_penalises_near_duplicates():
    cands = [
        _cand("A", 0.90, title="Boat Rockerz 450 Bluetooth Headphones Black"),
        _cand("B", 0.89, title="Boat Rockerz 450 Bluetooth Headphones Blue"),
        _cand("C", 0.88, title="Sony WH1000XM4 Wireless Headphones Black"),
    ]
    out = prerank(cands, ShoppingIntent(), per_sub_need=2)
    ids = [c.product.id for c in out]
    assert ids[0] == "A"
    assert "C" in ids, "a near-duplicate must not occupy the second slot"
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python -m pytest tests/test_scoring.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.scoring'`.

- [ ] **Step 3: Write `backend/app/services/scoring.py`**

```python
"""Deterministic pre-ranking between vector retrieval and LLM reranking.

Purpose: make the LLM the final semantic judge rather than the entire ranker, and
cut the rerank prompt from 8 candidates per sub-need to 4-5.

Weights are deliberately conservative. Similarity dominates; everything else is a
small bounded adjustment. Without relevance judgements to fit against, tuned
coefficients would be guesses that silently distort ranking and are harder to
debug than plain similarity ordering (spec 5, Stage 4).
"""
from app.schemas.intent import ShoppingIntent
from app.schemas.response import Candidate
from scripts.ingest import variant_key

WEIGHTS = {
    "quality": 0.10,
    "verified_attr": 0.08,
    "inferred_attr": 0.04,
    "duplicate_penalty": 0.15,
}


def _intent_terms(intent: ShoppingIntent) -> set[str]:
    terms = {intent.activity, intent.occasion, intent.season}
    return {t.lower() for t in terms if t}


def _attribute_matches(candidate: Candidate, terms: set[str]) -> tuple[int, int]:
    """Count how many intent terms appear in verified vs inferred attributes."""
    verified = inferred = 0
    for name in ("use_case", "occasion", "season", "product_type"):
        attr = candidate.product.attr(name)
        if attr is None or attr.value in (None, []):
            continue
        values = attr.value if isinstance(attr.value, list) else [attr.value]
        hits = sum(1 for v in values if str(v).lower() in terms)
        if attr.source == "title_verified":
            verified += hits
        else:
            inferred += hits
    return verified, inferred


def score_candidate(candidate: Candidate, intent: ShoppingIntent,
                    max_quality: float) -> float:
    terms = _intent_terms(intent)
    verified, inferred = _attribute_matches(candidate, terms)
    quality = candidate.product.quality_score / max_quality if max_quality > 0 else 0.0

    return (
        candidate.similarity
        + WEIGHTS["quality"] * min(quality, 1.0)
        + WEIGHTS["verified_attr"] * min(verified, 1)
        + WEIGHTS["inferred_attr"] * min(inferred, 1)
    )


def prerank(candidates: list[Candidate], intent: ShoppingIntent,
            per_sub_need: int = 5) -> list[Candidate]:
    """Score, apply a diversity penalty, and keep the top N per sub-need.

    Sub-needs are ranked independently so a strong one cannot starve a weak one -
    every group the user asked for gets its own shot at the LLM.
    """
    if not candidates:
        return []

    max_quality = max(c.product.quality_score for c in candidates) or 1.0
    for c in candidates:
        c.score = score_candidate(c, intent, max_quality)

    by_sub_need: dict[str, list[Candidate]] = {}
    for c in candidates:
        by_sub_need.setdefault(c.sub_need, []).append(c)

    selected: list[Candidate] = []
    for group in by_sub_need.values():
        group.sort(key=lambda c: c.score, reverse=True)
        chosen: list[Candidate] = []
        seen_variants: set[str] = set()
        for c in group:
            if len(chosen) >= per_sub_need:
                break
            key = variant_key(c.product.title)
            if key in seen_variants:
                # Near-duplicate: 35.8% of source rows share a title prefix
                # (docs/dataset.md 3.2). Demote rather than drop, so a sub-need
                # with only variants still returns something.
                c.score -= WEIGHTS["duplicate_penalty"]
                continue
            seen_variants.add(key)
            chosen.append(c)
        selected.extend(chosen)

    return selected
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_scoring.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/scoring.py backend/tests/test_scoring.py
git commit -m "feat: deterministic pre-ranking with bounded weights and diversity"
```

---

### Task 15: Intent extraction and delta merge

**Files:**
- Create: `backend/app/services/intent.py`
- Test: `backend/tests/test_intent.py`

**Interfaces:**
- Consumes: `GenerationProvider`, `IntentResult`, `ShoppingIntent`.
- Produces:
  - `intent.INTENT_PROMPT: str`
  - `intent.extract(provider, query: str, prior: ShoppingIntent | None, *, request_id: str) -> IntentResult`
  - `intent.parse_intent_payload(payload: dict) -> IntentResult` — tolerant parser with one repair path

- [ ] **Step 1: Write the failing test**

`backend/tests/test_intent.py`:

```python
import pytest

from app.core.errors import InvalidQuery
from app.providers.generation import StubGenerationProvider
from app.schemas.intent import ShoppingIntent
from app.services.intent import extract, parse_intent_payload

PAYLOAD = {
    "intent": {"activity": "trekking", "destination": "Hampta Pass",
               "season": "late October", "duration_days": 7,
               "budget_max": None, "gender": None, "occasion": None},
    "sub_needs": [{"label": "Backpack", "query": "50L trekking rucksack"},
                  {"label": "Insulation layer", "query": "warm insulated jacket"}],
    "assumptions": [{"field": "climate", "value": "cold-weather conditions likely",
                     "reason": "high-altitude trek in late October",
                     "confidence": "medium"}],
    "clarifying_question": None,
    "confidence": 0.82,
}


def test_parse_extracts_sub_needs_and_assumptions():
    result = parse_intent_payload(PAYLOAD)
    assert result.intent.activity == "trekking"
    assert [s.label for s in result.sub_needs] == ["Backpack", "Insulation layer"]
    assert result.assumptions[0].confidence == "medium"


def test_parse_tolerates_missing_optional_keys():
    result = parse_intent_payload({"sub_needs": [{"label": "X", "query": "y"}]})
    assert result.clarifying_question is None
    assert result.intent.budget_max is None


def test_parse_drops_malformed_sub_needs_rather_than_failing():
    result = parse_intent_payload({"sub_needs": [{"label": "Good", "query": "ok"},
                                                 {"label": "Missing query"}]})
    assert [s.label for s in result.sub_needs] == ["Good"]


def test_parse_raises_when_no_sub_needs_survive():
    with pytest.raises(InvalidQuery):
        parse_intent_payload({"sub_needs": []})


async def test_extract_calls_provider_and_parses():
    provider = StubGenerationProvider([PAYLOAD])
    result = await extract(provider, "trek to Hampta Pass", None, request_id="r")
    assert result.intent.destination == "Hampta Pass"
    assert "trek to Hampta Pass" in provider.prompts[0]


async def test_extract_merges_delta_onto_prior_intent():
    delta = {"intent": {"budget_max": 3000},
             "sub_needs": [{"label": "Backpack", "query": "cheap rucksack"}]}
    prior = ShoppingIntent(activity="trekking", destination="Hampta Pass",
                           duration_days=7)
    result = await extract(StubGenerationProvider([delta]), "make it cheaper",
                           prior, request_id="r")
    assert result.intent.budget_max == 3000
    assert result.intent.activity == "trekking", "prior context must survive"
    assert result.intent.destination == "Hampta Pass"


async def test_extract_includes_prior_intent_in_prompt():
    provider = StubGenerationProvider([PAYLOAD])
    await extract(provider, "cheaper", ShoppingIntent(activity="trekking"),
                  request_id="r")
    assert "trekking" in provider.prompts[0]
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python -m pytest tests/test_intent.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.intent'`.

- [ ] **Step 3: Write `backend/app/services/intent.py`**

```python
"""Stage 1: turn a natural-language request into structured intent and sub-needs.

Sub-need decomposition is the core AI decision. A single vector for the whole
request is a blurry average - "trekking essentials and clothing" would skew
toward whatever the catalogue holds most of, and a sleeping bag would never
enter the candidate pool. Searching per sub-need retrieves each need on its own
terms, and result groups derive from the request rather than being invented
afterwards (spec 5, Stage 1).
"""
from app.core.errors import InvalidQuery
from app.providers.generation import GenerationProvider
from app.schemas.intent import Assumption, IntentResult, ShoppingIntent, SubNeed

INTENT_PROMPT = """You are a shopping assistant interpreting a customer request.

Customer request:
{query}
{prior_block}
Break the request into distinct shopping sub-needs. Each sub-need becomes its own
product search and its own group of results, so make them specific and disjoint.
A simple request may have only one sub-need.

Return ONLY JSON:
{{
  "intent": {{
    "activity": string or null,
    "destination": string or null,
    "season": string or null,
    "duration_days": integer or null,
    "budget_max": number or null,
    "gender": "men" | "women" | "unisex" | null,
    "occasion": string or null
  }},
  "sub_needs": [{{"label": "Short group heading", "query": "search phrase describing the item"}}],
  "assumptions": [{{"field": "...", "value": "...", "reason": "...", "confidence": "low"|"medium"|"high"}}],
  "clarifying_question": "one question, or null",
  "confidence": 0.0-1.0
}}

RULES:
- budget_max: set ONLY if the customer stated a budget. Never guess one.
- gender: set ONLY if the customer stated who this is for.
- Do NOT assert facts you cannot verify. You have no weather, geography, or
  altitude data. Write "cold-weather conditions likely" with confidence
  "medium", never "sub-zero nights at 4,200 m".
- Every judgement you made that the customer did not state belongs in
  "assumptions", so it can be shown and edited.
- clarifying_question: set ONLY when a critical detail is genuinely unguessable
  (for example a gifting budget, which could be Rs 2,000 or Rs 50,000). Results
  are always returned alongside it, so never treat it as blocking.
"""

PRIOR_BLOCK = """
This is a follow-up. The customer's existing request was:
{prior}

Return ONLY the fields that CHANGE. Omit or null everything else - prior context
is preserved automatically.
"""


def parse_intent_payload(payload: dict) -> IntentResult:
    """Parse provider output tolerantly; drop malformed parts rather than failing."""
    intent = ShoppingIntent.model_validate(payload.get("intent") or {})

    sub_needs: list[SubNeed] = []
    for raw in payload.get("sub_needs") or []:
        if isinstance(raw, dict) and raw.get("label") and raw.get("query"):
            sub_needs.append(SubNeed(label=str(raw["label"]), query=str(raw["query"])))

    if not sub_needs:
        raise InvalidQuery(
            "Could not work out what you're shopping for. Try describing the "
            "occasion or the kind of items you need.")

    assumptions: list[Assumption] = []
    for raw in payload.get("assumptions") or []:
        if not isinstance(raw, dict) or not raw.get("field"):
            continue
        assumptions.append(Assumption(
            field=str(raw["field"]), value=str(raw.get("value", "")),
            reason=str(raw.get("reason", "")),
            confidence=raw.get("confidence") if raw.get("confidence") in
            ("low", "medium", "high") else "medium"))

    return IntentResult(
        intent=intent, sub_needs=sub_needs, assumptions=assumptions,
        clarifying_question=payload.get("clarifying_question") or None,
        confidence=float(payload.get("confidence") or 0.5),
    )


async def extract(provider: GenerationProvider, query: str,
                  prior: ShoppingIntent | None, *, request_id: str) -> IntentResult:
    """Extract intent, merging onto prior intent when this is a follow-up."""
    if not query or not query.strip():
        raise InvalidQuery("Tell me what you're shopping for.")

    prior_block = ""
    if prior is not None:
        stated = {k: v for k, v in prior.model_dump().items() if v is not None}
        if stated:
            prior_block = PRIOR_BLOCK.format(prior=stated)

    payload = await provider.generate_json(
        INTENT_PROMPT.format(query=query.strip(), prior_block=prior_block),
        request_id=request_id)

    result = parse_intent_payload(payload)
    if prior is not None:
        result.intent = prior.merge(result.intent)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_intent.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/intent.py backend/tests/test_intent.py
git commit -m "feat: intent extraction with sub-need decomposition and delta merge"
```

---

### Task 16: LLM reranking with grounded explanations

**Files:**
- Create: `backend/app/services/ranking.py`
- Test: `backend/tests/test_ranking.py`

**Interfaces:**
- Consumes: `GenerationProvider`, `Candidate`, `ShoppingIntent`, `SubNeed`, `ResultGroup`, `Recommendation`.
- Produces:
  - `ranking.RERANK_PROMPT: str`
  - `ranking.build_groups(payload: dict, candidates: list[Candidate], sub_needs: list[SubNeed]) -> list[ResultGroup]`
  - `ranking.rerank(provider, candidates, intent, sub_needs, *, request_id) -> list[ResultGroup]`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_ranking.py`:

```python
from app.providers.generation import StubGenerationProvider
from app.schemas.intent import ShoppingIntent, SubNeed
from app.schemas.product import Product
from app.schemas.response import Candidate
from app.services.ranking import build_groups, rerank


def _cand(pid: str, sub_need: str = "Bags") -> Candidate:
    product = Product(
        id=pid, title=f"Product {pid}", title_original=f"Product {pid}", description="",
        category="Test", price=1000.0, price_tier="mid", rating=4.0, reviews=100,
        quality_score=18.4, attributes={}, image_url="https://x/i.jpg",
        product_url=f"https://www.amazon.in/dp/{pid}")
    return Candidate(product=product, similarity=0.8, sub_need=sub_need)


CANDS = [_cand("A"), _cand("B"), _cand("C", "Shoes")]
SUBS = [SubNeed(label="Bags", query="backpack"), SubNeed(label="Shoes", query="boots")]


def test_build_groups_maps_ids_to_recommendations():
    payload = {"groups": [{"label": "Bags", "picks": [
        {"product_id": "A", "reason": "45L suits a week-long trip"}]}]}
    groups = build_groups(payload, CANDS, SUBS)
    bags = next(g for g in groups if g.label == "Bags")
    assert bags.recommendations[0].product_id == "A"
    assert bags.recommendations[0].reason == "45L suits a week-long trip"
    assert bags.recommendations[0].product_url == "https://www.amazon.in/dp/A"


def test_hallucinated_product_ids_are_dropped():
    payload = {"groups": [{"label": "Bags", "picks": [
        {"product_id": "DOES-NOT-EXIST", "reason": "invented"},
        {"product_id": "A", "reason": "real"}]}]}
    groups = build_groups(payload, CANDS, SUBS)
    ids = [r.product_id for r in groups[0].recommendations]
    assert ids == ["A"], "the model must never be able to invent a product"


def test_missing_group_is_reported_as_empty_not_hidden():
    payload = {"groups": [{"label": "Bags", "picks": [
        {"product_id": "A", "reason": "ok"}]}]}
    groups = build_groups(payload, CANDS, SUBS)
    shoes = next(g for g in groups if g.label == "Shoes")
    assert shoes.recommendations == []
    assert shoes.empty_reason is not None


def test_group_the_model_invented_is_ignored():
    payload = {"groups": [{"label": "Spaceships", "picks": [
        {"product_id": "A", "reason": "no"}]}]}
    groups = build_groups(payload, CANDS, SUBS)
    assert {g.label for g in groups} == {"Bags", "Shoes"}


def test_all_sub_needs_always_appear_in_order():
    groups = build_groups({"groups": []}, CANDS, SUBS)
    assert [g.label for g in groups] == ["Bags", "Shoes"]


async def test_rerank_sends_only_candidate_ids_the_model_may_choose_from():
    provider = StubGenerationProvider([{"groups": [
        {"label": "Bags", "picks": [{"product_id": "A", "reason": "r"}]}]}])
    await rerank(provider, CANDS, ShoppingIntent(), SUBS, request_id="r")
    prompt = provider.prompts[0]
    assert "A" in prompt and "B" in prompt and "C" in prompt


async def test_rerank_returns_empty_groups_when_there_are_no_candidates():
    provider = StubGenerationProvider([{"groups": []}])
    groups = await rerank(provider, [], ShoppingIntent(), SUBS, request_id="r")
    assert all(g.recommendations == [] for g in groups)
    assert all(g.empty_reason for g in groups)
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python -m pytest tests/test_ranking.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.ranking'`.

- [ ] **Step 3: Write `backend/app/services/ranking.py`**

```python
"""Stage 5: LLM chooses final picks per group and explains each one.

Three guards make this safe: every returned product_id is validated against the
candidate pool, explanations may only cite grounded facts, and groups with no
good match are reported rather than hidden (spec 5, Stage 5).
"""
import json

from app.providers.generation import GenerationProvider
from app.schemas.intent import ShoppingIntent, SubNeed
from app.schemas.response import Candidate, Recommendation, ResultGroup

MAX_PICKS_PER_GROUP = 5
EMPTY_REASON = "No suitable match found in the catalogue for this need."

RERANK_PROMPT = """You are a shopping assistant choosing final recommendations.

Customer intent:
{intent}

Groups to fill:
{groups}

Candidate products (you may ONLY choose from these ids):
{candidates}

For each group, choose the 3-5 best candidates and write one sentence explaining
why each suits this customer.

Return ONLY JSON:
{{"groups": [{{"label": "exact group label", "picks": [
   {{"product_id": "id from the list above", "reason": "one sentence"}}]}}]}}

RULES:
- Use ONLY product ids from the candidate list. Never invent one.
- Facts marked "verified" may be stated as fact. Everything else is a judgement -
  phrase it as suitability ("suited to cold-weather trekking"), never as a
  specification ("rated to -12C").
- Never state a weight, temperature rating, or dimension unless it appears in the
  product title.
- If a group has no good candidate, return it with an empty picks list. An honest
  empty group is better than a bad recommendation.
"""


def _candidate_line(c: Candidate) -> str:
    verified = {k: a.value for k, a in c.product.attributes.items()
                if a.source == "title_verified" and a.value is not None}
    parts = [f"id={c.product.id}", f"group={c.sub_need}", f"title={c.product.title}",
             f"price=Rs{c.product.price:.0f}", f"tier={c.product.price_tier}",
             f"rating={c.product.rating}({c.product.reviews})"]
    if verified:
        parts.append(f"verified={json.dumps(verified, ensure_ascii=False)}")
    return " | ".join(parts)


def build_groups(payload: dict, candidates: list[Candidate],
                 sub_needs: list[SubNeed]) -> list[ResultGroup]:
    """Assemble groups, validating every id against the candidate pool.

    Every sub-need appears in the output in its original order, whether or not the
    model returned picks for it - empty groups are reported, not hidden.
    """
    by_id = {c.product.id: c.product for c in candidates}
    picks_by_label: dict[str, list[dict]] = {}
    for raw in payload.get("groups") or []:
        if isinstance(raw, dict) and raw.get("label"):
            picks_by_label[str(raw["label"])] = raw.get("picks") or []

    groups: list[ResultGroup] = []
    for sub_need in sub_needs:
        recommendations: list[Recommendation] = []
        for pick in picks_by_label.get(sub_need.label, []):
            if not isinstance(pick, dict):
                continue
            product = by_id.get(str(pick.get("product_id")))
            if product is None:
                continue  # hallucinated id - dropped
            recommendations.append(Recommendation(
                product_id=product.id, title=product.title, price=product.price,
                price_tier=product.price_tier, rating=product.rating,
                reviews=product.reviews, image_url=product.image_url,
                product_url=product.product_url,
                reason=str(pick.get("reason") or "").strip()))
            if len(recommendations) >= MAX_PICKS_PER_GROUP:
                break

        groups.append(ResultGroup(
            label=sub_need.label, recommendations=recommendations,
            empty_reason=None if recommendations else EMPTY_REASON))
    return groups


async def rerank(provider: GenerationProvider, candidates: list[Candidate],
                 intent: ShoppingIntent, sub_needs: list[SubNeed], *,
                 request_id: str) -> list[ResultGroup]:
    if not candidates:
        return [ResultGroup(label=s.label, recommendations=[], empty_reason=EMPTY_REASON)
                for s in sub_needs]

    stated = {k: v for k, v in intent.model_dump().items() if v is not None}
    payload = await provider.generate_json(
        RERANK_PROMPT.format(
            intent=json.dumps(stated, ensure_ascii=False),
            groups="\n".join(f"- {s.label}: {s.query}" for s in sub_needs),
            candidates="\n".join(_candidate_line(c) for c in candidates),
        ), request_id=request_id)

    return build_groups(payload, candidates, sub_needs)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_ranking.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ranking.py backend/tests/test_ranking.py
git commit -m "feat: LLM rerank with id validation and tier-gated explanations"
```

---

### Task 17: Sessions and the pipeline orchestrator

**Files:**
- Create: `backend/app/services/sessions.py`, `backend/app/services/pipeline.py`
- Test: `backend/tests/test_sessions.py`, `backend/tests/test_pipeline.py`

**Interfaces:**
- Consumes: everything from Tasks 9–16.
- Produces:
  - `sessions.SessionStore(ttl_seconds: int)` with `get(session_id) -> ShoppingIntent | None`, `put(session_id, intent) -> None`, `new_id() -> str`
  - `pipeline.RecommendationPipeline(index, embedder, generator, sessions)` with `async run(query: str, session_id: str | None, *, request_id: str) -> AsyncIterator[StreamEvent]`
  - `pipeline.collect(events) -> RecommendResponse` — drains the generator for the JSON route

One generator, two transports. The JSON route drains it; the streaming route forwards it.
If streaming is cut, the core is untouched (spec §5).

- [ ] **Step 1: Write the failing session test**

`backend/tests/test_sessions.py`:

```python
from app.schemas.intent import ShoppingIntent
from app.services.sessions import SessionStore


def test_put_then_get_round_trips():
    store = SessionStore(ttl_seconds=60)
    sid = store.new_id()
    store.put(sid, ShoppingIntent(activity="trekking"))
    assert store.get(sid).activity == "trekking"


def test_unknown_session_returns_none():
    assert SessionStore(ttl_seconds=60).get("nope") is None


def test_expired_session_returns_none():
    store = SessionStore(ttl_seconds=0)
    sid = store.new_id()
    store.put(sid, ShoppingIntent(activity="trekking"))
    assert store.get(sid) is None


def test_new_id_is_unique():
    store = SessionStore(ttl_seconds=60)
    assert store.new_id() != store.new_id()
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python -m pytest tests/test_sessions.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.sessions'`.

- [ ] **Step 3: Write `backend/app/services/sessions.py`**

```python
"""Process-local session store.

An in-memory TTL dict only works with a single worker: with several, a session
created on worker A is missing on worker B. The deployment therefore runs
--workers 1, and that constraint is documented rather than discovered
(spec 6). Redis is the production path.
"""
import time
import uuid

from app.schemas.intent import ShoppingIntent


class SessionStore:
    def __init__(self, ttl_seconds: int = 1800) -> None:
        self._ttl = ttl_seconds
        self._data: dict[str, tuple[float, ShoppingIntent]] = {}

    def new_id(self) -> str:
        return uuid.uuid4().hex

    def put(self, session_id: str, intent: ShoppingIntent) -> None:
        self._data[session_id] = (time.monotonic(), intent)

    def get(self, session_id: str) -> ShoppingIntent | None:
        entry = self._data.get(session_id)
        if entry is None:
            return None
        stored_at, intent = entry
        if time.monotonic() - stored_at > self._ttl:
            self._data.pop(session_id, None)
            return None
        return intent
```

- [ ] **Step 4: Write the failing pipeline test**

`backend/tests/test_pipeline.py`:

```python
import gzip
import json

import numpy as np
import pytest

from app.catalogue.index import CatalogueIndex
from app.catalogue.loader import JsonlCatalogue
from app.providers.embedding import StubEmbedding
from app.providers.generation import StubGenerationProvider
from app.services.pipeline import RecommendationPipeline, collect
from app.services.sessions import SessionStore

INTENT_PAYLOAD = {
    "intent": {"activity": "trekking", "budget_max": None},
    "sub_needs": [{"label": "Backpack", "query": "trekking rucksack"}],
    "assumptions": [{"field": "climate", "value": "cold-weather conditions likely",
                     "reason": "high-altitude trek", "confidence": "medium"}],
    "clarifying_question": None, "confidence": 0.8,
}


def _row(i: int, price: float = 1000.0) -> dict:
    return {"id": f"B{i}", "title": f"Trekking Backpack {i}",
            "title_original": f"Trekking Backpack {i}", "description": "A rucksack.",
            "category": "Backpacks", "price": price, "price_tier": "mid", "rating": 4.2,
            "reviews": 50, "quality_score": 16.5, "attributes": {},
            "image_url": "https://x/i.jpg", "product_url": f"https://www.amazon.in/dp/B{i}"}


@pytest.fixture
def index(tmp_path):
    with gzip.open(tmp_path / "c.jsonl.gz", "wt", encoding="utf-8") as f:
        for i in range(6):
            f.write(json.dumps(_row(i, price=1000.0 * (i + 1))) + "\n")
    products = JsonlCatalogue(tmp_path / "c.jsonl.gz").load()
    rng = np.random.default_rng(0)
    m = rng.standard_normal((6, 8)).astype(np.float32)
    m /= np.linalg.norm(m, axis=1, keepdims=True)
    return CatalogueIndex(products, m)


def _pipeline(index, rerank_payload=None):
    rerank_payload = rerank_payload or {"groups": [{"label": "Backpack", "picks": [
        {"product_id": "B0", "reason": "Suited to multi-day treks."}]}]}
    return RecommendationPipeline(
        index=index, embedder=StubEmbedding(dims=8),
        generator=StubGenerationProvider([INTENT_PAYLOAD, rerank_payload]),
        sessions=SessionStore(ttl_seconds=60))


async def test_pipeline_emits_stages_in_order(index):
    events = [e async for e in _pipeline(index).run("trek gear", None, request_id="r")]
    assert [e.event for e in events] == ["understood", "searching", "results", "done"]


async def test_understood_event_carries_intent_and_assumptions(index):
    events = [e async for e in _pipeline(index).run("trek gear", None, request_id="r")]
    understood = events[0].data
    assert understood["intent"]["activity"] == "trekking"
    assert understood["assumptions"][0]["confidence"] == "medium"
    assert understood["sub_needs"] == ["Backpack"]


async def test_collect_builds_a_full_response(index):
    events = [e async for e in _pipeline(index).run("trek gear", None, request_id="r")]
    response = collect(events)
    assert response.groups[0].label == "Backpack"
    assert response.groups[0].recommendations[0].product_id == "B0"
    assert response.session_id
    assert "intent" in response.timings_ms and "total" in response.timings_ms


async def test_budget_filter_reaches_the_catalogue(index):
    payload = dict(INTENT_PAYLOAD, intent={"activity": "trekking", "budget_max": 2500})
    pipe = RecommendationPipeline(
        index=index, embedder=StubEmbedding(dims=8),
        generator=StubGenerationProvider([payload, {"groups": []}]),
        sessions=SessionStore(ttl_seconds=60))
    events = [e async for e in pipe.run("cheap trek gear", None, request_id="r")]
    assert events[1].data["candidates"] <= 2, "only B0 and B1 are under Rs 2500"


async def test_session_intent_persists_for_follow_up(index):
    sessions = SessionStore(ttl_seconds=60)
    pipe = RecommendationPipeline(
        index=index, embedder=StubEmbedding(dims=8),
        generator=StubGenerationProvider([INTENT_PAYLOAD, {"groups": []}]),
        sessions=sessions)
    events = [e async for e in pipe.run("trek gear", None, request_id="r")]
    sid = collect(events).session_id
    assert sessions.get(sid).activity == "trekking"


async def test_provider_failure_emits_error_event(index):
    class Boom:
        name = "boom"

        async def generate_json(self, prompt, *, request_id):
            raise RuntimeError("upstream exploded")

    from app.providers.generation import FallbackChain
    pipe = RecommendationPipeline(
        index=index, embedder=StubEmbedding(dims=8),
        generator=FallbackChain(Boom(), None), sessions=SessionStore(ttl_seconds=60))
    events = [e async for e in pipe.run("trek gear", None, request_id="r")]
    assert events[-1].event == "error"
    assert events[-1].data["error"]["code"] == "PROVIDER_UNAVAILABLE"
```

- [ ] **Step 5: Run it to verify it fails**

```bash
cd backend && python -m pytest tests/test_pipeline.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.pipeline'`.

- [ ] **Step 6: Write `backend/app/services/pipeline.py`**

```python
"""The orchestrator: one async generator, two transports.

The streaming route forwards these events; the JSON route drains them via
collect(). Keeping both on one implementation means streaming can be cut under
time pressure without touching the core (spec 5).
"""
import time
from typing import AsyncIterator

from app.catalogue.index import CatalogueIndex
from app.core.errors import AppError, Internal
from app.core.logging import log_stage
from app.providers.embedding import EmbeddingProvider
from app.providers.generation import GenerationProvider
from app.schemas.response import RecommendResponse, ResultGroup, StreamEvent
from app.services import intent as intent_service
from app.services import ranking, retrieval, scoring
from app.services.sessions import SessionStore

RETRIEVE_TOP_K = 8
PRERANK_PER_SUB_NEED = 5


class RecommendationPipeline:
    def __init__(self, index: CatalogueIndex, embedder: EmbeddingProvider,
                 generator: GenerationProvider, sessions: SessionStore) -> None:
        self.index = index
        self.embedder = embedder
        self.generator = generator
        self.sessions = sessions

    async def run(self, query: str, session_id: str | None, *,
                  request_id: str) -> AsyncIterator[StreamEvent]:
        started = time.perf_counter()
        timings: dict[str, float] = {}
        sid = session_id or self.sessions.new_id()

        try:
            # Stage 1 - understand
            t0 = time.perf_counter()
            prior = self.sessions.get(sid) if session_id else None
            result = await intent_service.extract(
                self.generator, query, prior, request_id=request_id)
            self.sessions.put(sid, result.intent)
            timings["intent"] = (time.perf_counter() - t0) * 1000
            log_stage(request_id, "intent", duration_ms=timings["intent"],
                      sub_needs=len(result.sub_needs))

            yield StreamEvent(event="understood", data={
                "session_id": sid,
                "intent": result.intent.model_dump(),
                "assumptions": [a.model_dump() for a in result.assumptions],
                "sub_needs": [s.label for s in result.sub_needs],
                "clarifying_question": result.clarifying_question,
            })

            # Stage 2 + 3 - filter, then retrieve per sub-need
            t0 = time.perf_counter()
            rows, relaxations = retrieval.filter_rows(self.index, result.intent)
            candidates = await retrieval.retrieve(
                self.index, self.embedder, result.sub_needs, rows, RETRIEVE_TOP_K)
            timings["retrieval"] = (time.perf_counter() - t0) * 1000
            log_stage(request_id, "retrieval", duration_ms=timings["retrieval"],
                      pool=len(rows), candidates=len(candidates))

            yield StreamEvent(event="searching", data={
                "candidates": len(candidates), "pool": len(rows),
                "relaxations": relaxations,
            })

            # Stage 4 - deterministic pre-ranking
            t0 = time.perf_counter()
            shortlist = scoring.prerank(candidates, result.intent, PRERANK_PER_SUB_NEED)
            timings["prerank"] = (time.perf_counter() - t0) * 1000

            # Stage 5 - LLM rerank and explain
            t0 = time.perf_counter()
            groups = await ranking.rerank(
                self.generator, shortlist, result.intent, result.sub_needs,
                request_id=request_id)
            timings["rerank"] = (time.perf_counter() - t0) * 1000
            log_stage(request_id, "rerank", duration_ms=timings["rerank"],
                      shortlist=len(shortlist),
                      filled=sum(1 for g in groups if g.recommendations))

            yield StreamEvent(event="results", data={
                "groups": [g.model_dump() for g in groups],
                "relaxations": relaxations,
            })

            timings["total"] = (time.perf_counter() - started) * 1000
            yield StreamEvent(event="done", data={"timings_ms": timings})

        except AppError as exc:
            log_stage(request_id, "error", code=exc.code, message=exc.message)
            yield StreamEvent(event="error", data=exc.envelope())
        except Exception as exc:  # noqa: BLE001 - never leak a traceback to the client
            log_stage(request_id, "error", code="INTERNAL", message=str(exc)[:200])
            yield StreamEvent(event="error", data=Internal("Something went wrong.").envelope())


def collect(events: list[StreamEvent]) -> RecommendResponse:
    """Drain pipeline events into a single JSON response."""
    by_event = {e.event: e.data for e in events}

    if "error" in by_event and "results" not in by_event:
        raise Internal(by_event["error"]["error"]["message"])

    understood = by_event.get("understood", {})
    results = by_event.get("results", {})
    return RecommendResponse(
        session_id=understood.get("session_id", ""),
        intent=understood.get("intent") or {},
        assumptions=understood.get("assumptions") or [],
        clarifying_question=understood.get("clarifying_question"),
        groups=[ResultGroup.model_validate(g) for g in results.get("groups", [])],
        relaxations=results.get("relaxations", []),
        timings_ms=by_event.get("done", {}).get("timings_ms", {}),
    )
```

- [ ] **Step 7: Run both test files to verify they pass**

```bash
cd backend && python -m pytest tests/test_sessions.py tests/test_pipeline.py -v
```

Expected: 4 + 6 = 10 passed.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/sessions.py backend/app/services/pipeline.py
git add backend/tests/test_sessions.py backend/tests/test_pipeline.py
git commit -m "feat: pipeline orchestrator with staged events and session persistence"
```

---

### Task 18: API routes and application wiring

**Files:**
- Create: `backend/app/api/__init__.py`, `deps.py`, `routes_recommend.py`, `backend/app/main.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Produces: `POST /api/recommend`, `POST /api/recommend/stream`, `GET /api/health`; `main.create_app() -> FastAPI`; `deps.get_pipeline()`.

Request body for both recommend endpoints:
```json
{"query": "trekking gear for a week in October", "session_id": "optional-hex"}
```

- [ ] **Step 1: Write the failing test**

`backend/tests/test_api.py`:

```python
import gzip
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.catalogue.index import CatalogueIndex
from app.catalogue.loader import JsonlCatalogue
from app.main import create_app
from app.providers.embedding import StubEmbedding
from app.providers.generation import StubGenerationProvider
from app.services.pipeline import RecommendationPipeline
from app.services.sessions import SessionStore

INTENT_PAYLOAD = {
    "intent": {"activity": "trekking"},
    "sub_needs": [{"label": "Backpack", "query": "trekking rucksack"}],
    "assumptions": [], "clarifying_question": None, "confidence": 0.8,
}
RERANK_PAYLOAD = {"groups": [{"label": "Backpack", "picks": [
    {"product_id": "B0", "reason": "Suited to multi-day treks."}]}]}


@pytest.fixture
def client(tmp_path):
    with gzip.open(tmp_path / "c.jsonl.gz", "wt", encoding="utf-8") as f:
        for i in range(3):
            f.write(json.dumps({
                "id": f"B{i}", "title": f"Trekking Backpack {i}",
                "title_original": f"Trekking Backpack {i}", "description": "A rucksack.",
                "category": "Backpacks", "price": 1000.0, "price_tier": "mid",
                "rating": 4.2, "reviews": 50, "quality_score": 16.5, "attributes": {},
                "image_url": "https://x/i.jpg",
                "product_url": f"https://www.amazon.in/dp/B{i}"}) + "\n")
    products = JsonlCatalogue(tmp_path / "c.jsonl.gz").load()
    m = np.eye(3, 8, dtype=np.float32)
    index = CatalogueIndex(products, m)

    app = create_app(load_catalogue=False)
    app.dependency_overrides[deps.get_pipeline] = lambda: RecommendationPipeline(
        index=index, embedder=StubEmbedding(dims=8),
        generator=StubGenerationProvider([INTENT_PAYLOAD, RERANK_PAYLOAD]),
        sessions=SessionStore(ttl_seconds=60))
    return TestClient(app)


def test_health_reports_readiness(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_recommend_returns_grouped_results(client):
    r = client.post("/api/recommend", json={"query": "trekking gear for a week"})
    assert r.status_code == 200
    body = r.json()
    assert body["groups"][0]["label"] == "Backpack"
    assert body["groups"][0]["recommendations"][0]["product_id"] == "B0"
    assert body["session_id"]


def test_empty_query_returns_error_envelope(client):
    r = client.post("/api/recommend", json={"query": "   "})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_QUERY"


def test_stream_emits_sse_frames(client):
    with client.stream("POST", "/api/recommend/stream",
                       json={"query": "trekking gear"}) as r:
        assert r.status_code == 200
        body = "".join(r.iter_text())
    assert "event: understood" in body
    assert "event: results" in body
    assert "event: done" in body
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python -m pytest tests/test_api.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.main'`.

- [ ] **Step 3: Write `backend/app/api/deps.py`**

```python
from functools import lru_cache

from app.catalogue.index import load_index
from app.config import Settings, get_settings
from app.core.errors import ProviderUnavailable
from app.providers.embedding import GeminiEmbedding
from app.providers.generation import (FallbackChain, GeminiGeneration,
                                      GenerationProvider, GroqGeneration)
from app.services.pipeline import RecommendationPipeline
from app.services.sessions import SessionStore

_sessions: SessionStore | None = None


def _build_generation(settings: Settings) -> GenerationProvider:
    builders = {
        "gemini": lambda: GeminiGeneration(settings.gemini_api_key,
                                           timeout=settings.llm_timeout_seconds),
        "groq": lambda: GroqGeneration(settings.groq_api_key,
                                       timeout=settings.llm_timeout_seconds),
    }
    keys = {"gemini": settings.gemini_api_key, "groq": settings.groq_api_key}

    if not keys.get(settings.generation_primary):
        raise ProviderUnavailable(
            f"no API key configured for primary provider {settings.generation_primary!r}")

    primary = builders[settings.generation_primary]()
    fallback = None
    name = settings.generation_fallback
    if name and name != settings.generation_primary and keys.get(name):
        fallback = builders[name]()
    return FallbackChain(primary, fallback)


@lru_cache
def get_pipeline() -> RecommendationPipeline:
    global _sessions
    settings = get_settings()
    if _sessions is None:
        _sessions = SessionStore(ttl_seconds=settings.session_ttl_seconds)

    # No embedding fallback by design: query vectors must share the catalogue's
    # vector space, and the manifest check enforces it (spec 3.1).
    if not settings.gemini_api_key:
        raise ProviderUnavailable("GEMINI_API_KEY is required for embeddings")

    return RecommendationPipeline(
        index=load_index(settings.data_dir, settings),
        embedder=GeminiEmbedding(settings.gemini_api_key,
                                 settings.embedding_model, settings.embedding_dims),
        generator=_build_generation(settings),
        sessions=_sessions,
    )
```

- [ ] **Step 4: Write `backend/app/api/routes_recommend.py`**

```python
import json
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import get_pipeline
from app.core.errors import AppError, Internal
from app.services.pipeline import RecommendationPipeline, collect

router = APIRouter(prefix="/api")


class RecommendRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.post("/recommend")
async def recommend(body: RecommendRequest,
                    pipeline: RecommendationPipeline = Depends(get_pipeline)):
    request_id = uuid.uuid4().hex[:12]
    events = [e async for e in pipeline.run(body.query, body.session_id,
                                            request_id=request_id)]

    error = next((e for e in events if e.event == "error"), None)
    if error is not None:
        code = error.data["error"]["code"]
        status = {"INVALID_QUERY": 400, "RATE_LIMITED": 429,
                  "PROVIDER_UNAVAILABLE": 503}.get(code, 500)
        return JSONResponse(status_code=status, content=error.data)

    return collect(events).model_dump()


@router.post("/recommend/stream")
async def recommend_stream(body: RecommendRequest,
                           pipeline: RecommendationPipeline = Depends(get_pipeline)):
    """SSE frames over POST.

    Native EventSource is GET-only, and the request body carries a
    natural-language query plus session state - putting that in query parameters
    hits URL length limits and writes user queries into access logs. The client
    uses fetch + ReadableStream instead (spec 7.1).
    """
    request_id = uuid.uuid4().hex[:12]

    async def frames():
        async for event in pipeline.run(body.query, body.session_id,
                                        request_id=request_id):
            payload = json.dumps(event.data, ensure_ascii=False)
            yield f"event: {event.event}\ndata: {payload}\n\n"

    return StreamingResponse(frames(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # stops nginx/proxies buffering the stream
    })
```

- [ ] **Step 5: Write `backend/app/main.py`**

```python
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import deps
from app.api.routes_recommend import router
from app.config import get_settings
from app.core.errors import AppError
from app.core.logging import setup_logging


def create_app(load_catalogue: bool = True) -> FastAPI:
    setup_logging()
    settings = get_settings()
    app = FastAPI(title="Personal Shopping Assistant", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=r"https://.*\.vercel\.app",  # preview deployments
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.envelope())

    app.include_router(router)

    if load_catalogue:
        @app.on_event("startup")
        async def _warm() -> None:
            # Load catalogue and vectors once, not per request. Also fails fast on
            # a manifest mismatch rather than at first query.
            deps.get_pipeline()

    return app


app = create_app()
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd backend && touch app/api/__init__.py
python -m pytest tests/test_api.py -v
```

Expected: 4 passed.

- [ ] **Step 7: Run the whole backend suite**

```bash
cd backend && python -m pytest -v
```

Expected: all tests pass, no network calls, no API keys needed.

- [ ] **Step 8: Start the server against real data and try a real query**

```bash
cd backend && uvicorn app.main:app --reload --workers 1 --port 8000
```

In another terminal:

```bash
curl -s localhost:8000/api/health
curl -s -X POST localhost:8000/api/recommend \
  -H 'content-type: application/json' \
  -d '{"query":"I am going for a trek to Hampta Pass in the last week of October for one week. Please find me trekking essentials and clothing."}' \
  | python -m json.tool | head -60
```

Check the reasons cite grounded facts, and that empty groups say so rather than vanishing.

- [ ] **Step 9: Commit**

```bash
git add backend/app/api backend/app/main.py backend/tests/test_api.py
git commit -m "feat: recommend and streaming endpoints with CORS and error envelope"
```

---

## Phase 3 — Frontend

### Task 19: Frontend scaffold, types, and API client

**Files:**
- Create: `frontend/` (Vite scaffold), `frontend/.env.example`, `frontend/src/types.ts`, `frontend/src/lib/api.ts`
- Test: `frontend/src/lib/api.test.ts`

**Interfaces:**
- Produces:
  - `types.ts`: `Assumption`, `Recommendation`, `ResultGroup`, `RecommendResponse`, `ApiError` — mirroring `app/schemas/response.py`
  - `api.ts`: `recommend(query: string, sessionId?: string): Promise<RecommendResponse>` and `ApiFailure` (thrown, carries `code`)

- [ ] **Step 1: Scaffold Vite and install dependencies**

```bash
cd /Users/soumyagupta/Documents/resume-projects/confluxe
npm create vite@latest frontend -- --template react-ts
cd frontend && npm install
npm install -D tailwindcss@3 postcss autoprefixer vitest
npx tailwindcss init -p
```

- [ ] **Step 2: Configure Tailwind and the API base URL**

`frontend/tailwind.config.js` — set `content: ["./index.html", "./src/**/*.{ts,tsx}"]`.

`frontend/src/index.css` — replace contents with:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

Tailwind is pinned to v3 because these `@tailwind` directives are v3 syntax; v4 uses a
single `@import "tailwindcss"` and a different PostCSS plugin.

`frontend/.env.example`:

```bash
VITE_API_BASE_URL=http://localhost:8000
```

`frontend/vite.config.ts` — add a dev proxy so local development needs no CORS:

```ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:8000" } },
  test: { environment: "node" },
});
```

- [ ] **Step 3: Write `frontend/src/types.ts`**

```ts
// Mirrors backend/app/schemas/response.py. Keep field names identical.

export interface Assumption {
  field: string;
  value: string;
  reason: string;
  confidence: "low" | "medium" | "high";
  editable: boolean;
}

export interface Recommendation {
  product_id: string;
  title: string;
  price: number;
  price_tier: string;
  rating: number;
  reviews: number;
  image_url: string;
  product_url: string;
  reason: string;
}

export interface ResultGroup {
  label: string;
  recommendations: Recommendation[];
  empty_reason: string | null;
}

export interface RecommendResponse {
  session_id: string;
  intent: Record<string, unknown>;
  assumptions: Assumption[];
  clarifying_question: string | null;
  groups: ResultGroup[];
  relaxations: string[];
  timings_ms: Record<string, number>;
}

export interface ApiError {
  error: { code: string; message: string; retryable: boolean };
}
```

- [ ] **Step 4: Write the failing API client test**

`frontend/src/lib/api.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiFailure, recommend } from "./api";

afterEach(() => vi.unstubAllGlobals());

function stubFetch(status: number, body: unknown) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: status < 400,
    status,
    json: async () => body,
  }));
}

describe("recommend", () => {
  it("returns the parsed response on success", async () => {
    stubFetch(200, { session_id: "abc", groups: [], assumptions: [], relaxations: [] });
    const result = await recommend("trekking gear");
    expect(result.session_id).toBe("abc");
  });

  it("sends the session id when one is supplied", async () => {
    stubFetch(200, { session_id: "abc", groups: [] });
    await recommend("cheaper", "sess-1");
    const [, init] = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(JSON.parse(init.body as string).session_id).toBe("sess-1");
  });

  it("throws ApiFailure carrying the error code", async () => {
    stubFetch(400, { error: { code: "INVALID_QUERY", message: "no", retryable: false } });
    await expect(recommend("")).rejects.toThrow(ApiFailure);
    await expect(recommend("")).rejects.toMatchObject({ code: "INVALID_QUERY" });
  });
});
```

- [ ] **Step 5: Run it to verify it fails**

```bash
cd frontend && npx vitest run src/lib/api.test.ts
```

Expected: FAIL — cannot resolve `./api`.

- [ ] **Step 6: Write `frontend/src/lib/api.ts`**

```ts
import type { ApiError, RecommendResponse } from "../types";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiFailure extends Error {
  code: string;
  retryable: boolean;

  constructor(code: string, message: string, retryable: boolean) {
    super(message);
    this.name = "ApiFailure";
    this.code = code;
    this.retryable = retryable;
  }
}

export async function recommend(
  query: string,
  sessionId?: string,
): Promise<RecommendResponse> {
  const response = await fetch(`${BASE}/api/recommend`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ query, session_id: sessionId ?? null }),
  });

  const body = await response.json();
  if (!response.ok) {
    const { error } = body as ApiError;
    throw new ApiFailure(
      error?.code ?? "INTERNAL",
      error?.message ?? "Something went wrong.",
      error?.retryable ?? false,
    );
  }
  return body as RecommendResponse;
}
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
cd frontend && npx vitest run
```

Expected: 3 passed.

- [ ] **Step 8: Commit**

```bash
git add frontend
git commit -m "feat: scaffold frontend with typed API client"
```

---

### Task 20: Recommendation hook and result rendering

**Files:**
- Create: `frontend/src/hooks/useRecommendation.ts`, `frontend/src/components/InputPanel.tsx`, `ProductCard.tsx`, `ResultGroup.tsx`, and rewrite `frontend/src/App.tsx`
- Test: `frontend/src/hooks/useRecommendation.test.ts`

**Interfaces:**
- Consumes: `recommend`, `ApiFailure`, `ResultGroup`, `RecommendResponse`.
- Produces: `useRecommendation()` returning `{ status: "idle"|"loading"|"ready"|"error", response, error, submit(query), refine(query) }`.

- [ ] **Step 1: Write the failing hook test**

`frontend/src/hooks/useRecommendation.test.ts`:

```ts
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useRecommendation } from "./useRecommendation";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return { ...actual, recommend: vi.fn() };
});
const { recommend } = await import("../lib/api");

afterEach(() => vi.clearAllMocks());

const RESPONSE = {
  session_id: "sess-1", intent: {}, assumptions: [], clarifying_question: null,
  groups: [{ label: "Backpack", recommendations: [], empty_reason: "none" }],
  relaxations: [], timings_ms: {},
};

describe("useRecommendation", () => {
  it("starts idle", () => {
    const { result } = renderHook(() => useRecommendation());
    expect(result.current.status).toBe("idle");
  });

  it("moves to ready and stores the response", async () => {
    vi.mocked(recommend).mockResolvedValue(RESPONSE as never);
    const { result } = renderHook(() => useRecommendation());
    await act(async () => { await result.current.submit("trekking gear"); });
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.response?.groups[0].label).toBe("Backpack");
  });

  it("reuses the session id when refining", async () => {
    vi.mocked(recommend).mockResolvedValue(RESPONSE as never);
    const { result } = renderHook(() => useRecommendation());
    await act(async () => { await result.current.submit("trekking gear"); });
    await act(async () => { await result.current.refine("make it cheaper"); });
    expect(vi.mocked(recommend).mock.calls[1]).toEqual(["make it cheaper", "sess-1"]);
  });

  it("captures errors without crashing", async () => {
    const { ApiFailure } = await import("../lib/api");
    vi.mocked(recommend).mockRejectedValue(new ApiFailure("RATE_LIMITED", "slow", true));
    const { result } = renderHook(() => useRecommendation());
    await act(async () => { await result.current.submit("x"); });
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error?.code).toBe("RATE_LIMITED");
  });
});
```

- [ ] **Step 2: Install test dependencies and run to verify it fails**

```bash
cd frontend && npm install -D @testing-library/react @testing-library/dom jsdom
```

Set `test: { environment: "jsdom" }` in `vite.config.ts`, then:

```bash
npx vitest run src/hooks/useRecommendation.test.ts
```

Expected: FAIL — cannot resolve `./useRecommendation`.

- [ ] **Step 3: Write `frontend/src/hooks/useRecommendation.ts`**

```ts
import { useCallback, useRef, useState } from "react";
import { ApiFailure, recommend } from "../lib/api";
import type { RecommendResponse } from "../types";

type Status = "idle" | "loading" | "ready" | "error";

export function useRecommendation() {
  const [status, setStatus] = useState<Status>("idle");
  const [response, setResponse] = useState<RecommendResponse | null>(null);
  const [error, setError] = useState<ApiFailure | null>(null);
  const sessionId = useRef<string | undefined>(undefined);

  const run = useCallback(async (query: string, useSession: boolean) => {
    setStatus("loading");
    setError(null);
    try {
      const result = await recommend(query, useSession ? sessionId.current : undefined);
      sessionId.current = result.session_id;
      setResponse(result);
      setStatus("ready");
    } catch (err) {
      setError(err instanceof ApiFailure
        ? err
        : new ApiFailure("INTERNAL", "Something went wrong.", false));
      setStatus("error");
    }
  }, []);

  const submit = useCallback((query: string) => run(query, false), [run]);
  const refine = useCallback((query: string) => run(query, true), [run]);

  return { status, response, error, submit, refine };
}
```

- [ ] **Step 4: Write `frontend/src/components/ProductCard.tsx`**

```tsx
import type { Recommendation } from "../types";

const INR = new Intl.NumberFormat("en-IN", {
  style: "currency", currency: "INR", maximumFractionDigits: 0,
});

export function ProductCard({ item }: { item: Recommendation }) {
  return (
    <a
      href={item.product_url}
      target="_blank"
      rel="noreferrer noopener"
      className="flex gap-4 rounded-lg border border-slate-200 bg-white p-4 transition hover:border-slate-400"
    >
      <img
        src={item.image_url}
        alt=""
        loading="lazy"
        className="h-24 w-24 shrink-0 rounded object-contain"
      />
      <div className="min-w-0">
        <h3 className="line-clamp-2 text-sm font-medium text-slate-900">{item.title}</h3>
        <div className="mt-1 flex items-center gap-2 text-sm">
          <span className="font-semibold">{INR.format(item.price)}</span>
          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs capitalize text-slate-600">
            {item.price_tier}
          </span>
          {item.reviews > 0 && (
            <span className="text-xs text-slate-500">
              {item.rating.toFixed(1)} ({item.reviews.toLocaleString("en-IN")})
            </span>
          )}
        </div>
        <p className="mt-2 text-sm text-slate-600">{item.reason}</p>
      </div>
    </a>
  );
}
```

- [ ] **Step 5: Write `frontend/src/components/ResultGroup.tsx`**

```tsx
import type { ResultGroup as Group } from "../types";
import { ProductCard } from "./ProductCard";

export function ResultGroup({ group }: { group: Group }) {
  return (
    <section className="mb-8">
      <h2 className="mb-3 text-lg font-semibold text-slate-900">{group.label}</h2>
      {group.recommendations.length === 0 ? (
        // Empty groups are shown, never hidden — an honest gap reads better than
        // a silently missing section (spec 5, Stage 5).
        <p className="rounded-lg border border-dashed border-slate-300 p-4 text-sm text-slate-500">
          {group.empty_reason}
        </p>
      ) : (
        <div className="grid gap-3">
          {group.recommendations.map((item) => (
            <ProductCard key={item.product_id} item={item} />
          ))}
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 6: Write `frontend/src/components/InputPanel.tsx`**

```tsx
import { useState } from "react";

const EXAMPLES = [
  "I am going for a trek to Hampta Pass in the last week of October for one week. Please find me trekking essentials and clothing.",
  "Find me good traditional wear for my friend's wedding in March next year.",
  "I need a premium gifting hamper for my parents' 25th anniversary next month.",
];

export function InputPanel({
  onSubmit, busy,
}: { onSubmit: (query: string) => void; busy: boolean }) {
  const [value, setValue] = useState("");

  return (
    <div>
      <form
        onSubmit={(e) => { e.preventDefault(); if (value.trim()) onSubmit(value.trim()); }}
      >
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          rows={3}
          placeholder="Describe what you're shopping for…"
          className="w-full resize-none rounded-lg border border-slate-300 p-3 text-sm focus:border-slate-500 focus:outline-none"
        />
        <button
          type="submit"
          disabled={busy || !value.trim()}
          className="mt-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
        >
          {busy ? "Thinking…" : "Find products"}
        </button>
      </form>

      <div className="mt-3 flex flex-wrap gap-2">
        {EXAMPLES.map((example) => (
          <button
            key={example}
            onClick={() => { setValue(example); onSubmit(example); }}
            disabled={busy}
            className="rounded-full border border-slate-300 px-3 py-1 text-xs text-slate-600 hover:border-slate-500 disabled:opacity-40"
          >
            {example.slice(0, 42)}…
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Rewrite `frontend/src/App.tsx`**

```tsx
import { InputPanel } from "./components/InputPanel";
import { ResultGroup } from "./components/ResultGroup";
import { useRecommendation } from "./hooks/useRecommendation";

export default function App() {
  const { status, response, error, submit } = useRecommendation();

  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      <h1 className="text-2xl font-semibold text-slate-900">Shopping Assistant</h1>
      <p className="mb-6 mt-1 text-sm text-slate-500">
        Describe what you need. I'll work out the details.
      </p>

      <InputPanel onSubmit={submit} busy={status === "loading"} />

      {status === "error" && (
        <p className="mt-6 rounded-lg bg-red-50 p-4 text-sm text-red-700">
          {error?.message}
        </p>
      )}

      {status === "ready" && response && (
        <div className="mt-8">
          {response.relaxations.map((note) => (
            <p key={note} className="mb-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
              {note}
            </p>
          ))}
          {response.groups.map((group) => (
            <ResultGroup key={group.label} group={group} />
          ))}
        </div>
      )}
    </main>
  );
}
```

- [ ] **Step 8: Run tests to verify they pass**

```bash
cd frontend && npx vitest run
```

Expected: 7 passed (3 from Task 19 + 4 here).

- [ ] **Step 9: Run both servers and check a real query end to end**

```bash
# terminal 1
cd backend && uvicorn app.main:app --reload --workers 1 --port 8000
# terminal 2
cd frontend && npm run dev
```

Open <http://localhost:5173>, click the first example chip, confirm grouped results render
with images, prices, reasons, and working Amazon links.

- [ ] **Step 10: Commit**

```bash
git add frontend/src
git commit -m "feat: recommendation hook and grouped result rendering"
```

---

### Task 21: Assumption chips, clarifying question, and refine bar

**Files:**
- Create: `frontend/src/components/AssumptionChips.tsx`, `frontend/src/components/RefineBar.tsx`
- Modify: `frontend/src/App.tsx`
- Test: `frontend/src/components/AssumptionChips.test.tsx`

**Interfaces:**
- Consumes: `Assumption`, and `refine` from `useRecommendation`.
- Produces: `AssumptionChips({ assumptions, question, onAnswer })`, `RefineBar({ onRefine, busy })`.

The rule this renders: assumptions are visible and editable, and a clarifying question
appears *alongside* results rather than blocking them (spec §6).

- [ ] **Step 1: Write the failing test**

`frontend/src/components/AssumptionChips.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AssumptionChips } from "./AssumptionChips";

const ASSUMPTIONS = [{
  field: "climate", value: "cold-weather conditions likely",
  reason: "high-altitude trek in late October",
  confidence: "medium" as const, editable: true,
}];

describe("AssumptionChips", () => {
  it("shows each assumption with its confidence", () => {
    render(<AssumptionChips assumptions={ASSUMPTIONS} question={null} onAnswer={vi.fn()} />);
    expect(screen.getByText(/cold-weather conditions likely/)).toBeTruthy();
    expect(screen.getByText(/medium/i)).toBeTruthy();
  });

  it("renders nothing when there is nothing to show", () => {
    const { container } = render(
      <AssumptionChips assumptions={[]} question={null} onAnswer={vi.fn()} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows the clarifying question alongside, not instead of, results", () => {
    render(<AssumptionChips assumptions={ASSUMPTIONS} question="What's your budget?"
                            onAnswer={vi.fn()} />);
    expect(screen.getByText("What's your budget?")).toBeTruthy();
    expect(screen.getByText(/cold-weather/)).toBeTruthy();
  });

  it("submits an answer to the clarifying question", async () => {
    const onAnswer = vi.fn();
    render(<AssumptionChips assumptions={[]} question="What's your budget?"
                            onAnswer={onAnswer} />);
    await userEvent.type(screen.getByPlaceholderText(/answer/i), "under 5000");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));
    expect(onAnswer).toHaveBeenCalledWith("under 5000");
  });
});
```

- [ ] **Step 2: Install and run to verify it fails**

```bash
cd frontend && npm install -D @testing-library/user-event
npx vitest run src/components/AssumptionChips.test.tsx
```

Expected: FAIL — cannot resolve `./AssumptionChips`.

- [ ] **Step 3: Write `frontend/src/components/AssumptionChips.tsx`**

```tsx
import { useState } from "react";
import type { Assumption } from "../types";

export function AssumptionChips({
  assumptions, question, onAnswer,
}: {
  assumptions: Assumption[];
  question: string | null;
  onAnswer: (answer: string) => void;
}) {
  const [answer, setAnswer] = useState("");
  if (assumptions.length === 0 && !question) return null;

  return (
    <div className="mb-6 rounded-lg border border-slate-200 bg-slate-50 p-4">
      {assumptions.length > 0 && (
        <>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            What I assumed
          </p>
          <ul className="flex flex-wrap gap-2">
            {assumptions.map((a) => (
              <li
                key={`${a.field}-${a.value}`}
                title={a.reason}
                className="rounded-full border border-slate-300 bg-white px-3 py-1 text-xs text-slate-700"
              >
                {a.value}
                <span className="ml-1.5 text-slate-400">{a.confidence}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      {question && (
        <div className="mt-4 border-t border-slate-200 pt-3">
          <p className="text-sm text-slate-700">{question}</p>
          <form
            className="mt-2 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (answer.trim()) { onAnswer(answer.trim()); setAnswer(""); }
            }}
          >
            <input
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              placeholder="Your answer…"
              className="flex-1 rounded border border-slate-300 px-2 py-1 text-sm"
            />
            <button
              type="submit"
              className="rounded bg-slate-900 px-3 py-1 text-sm text-white"
            >
              Send
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Write `frontend/src/components/RefineBar.tsx`**

```tsx
import { useState } from "react";

const QUICK = ["Make it cheaper", "More premium", "Show more options"];

export function RefineBar({
  onRefine, busy,
}: { onRefine: (query: string) => void; busy: boolean }) {
  const [value, setValue] = useState("");

  return (
    <div className="sticky bottom-0 mt-8 border-t border-slate-200 bg-white/95 py-3 backdrop-blur">
      <div className="mb-2 flex flex-wrap gap-2">
        {QUICK.map((q) => (
          <button
            key={q}
            onClick={() => onRefine(q)}
            disabled={busy}
            className="rounded-full border border-slate-300 px-3 py-1 text-xs text-slate-600 hover:border-slate-500 disabled:opacity-40"
          >
            {q}
          </button>
        ))}
      </div>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (value.trim()) { onRefine(value.trim()); setValue(""); }
        }}
      >
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Refine these results…"
          className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={busy || !value.trim()}
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-40"
        >
          Refine
        </button>
      </form>
    </div>
  );
}
```

- [ ] **Step 5: Wire both into `frontend/src/App.tsx`**

Add the imports, then replace the `status === "ready"` block:

```tsx
import { AssumptionChips } from "./components/AssumptionChips";
import { RefineBar } from "./components/RefineBar";
```

```tsx
{status === "ready" && response && (
  <div className="mt-8">
    <AssumptionChips
      assumptions={response.assumptions}
      question={response.clarifying_question}
      onAnswer={refine}
    />
    {response.relaxations.map((note) => (
      <p key={note} className="mb-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
        {note}
      </p>
    ))}
    {response.groups.map((group) => (
      <ResultGroup key={group.label} group={group} />
    ))}
    <RefineBar onRefine={refine} busy={false} />
  </div>
)}
```

Destructure `refine` from the hook: `const { status, response, error, submit, refine } = useRecommendation();`

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd frontend && npx vitest run
```

Expected: 11 passed.

- [ ] **Step 7: Check refinement end to end**

Run a query, then click "Make it cheaper". The follow-up must preserve prior context — the
same activity and destination, with a budget applied — proving the intent delta merge works
through the session.

- [ ] **Step 8: Commit**

```bash
git add frontend/src
git commit -m "feat: assumption chips, clarifying question, and refinement"
```

---

## Phase 4 — Streaming

### Task 22: Streamed staged reveal

**Files:**
- Modify: `frontend/src/lib/api.ts`, `frontend/src/hooks/useRecommendation.ts`, `frontend/src/App.tsx`
- Test: `frontend/src/lib/stream.test.ts`

**Interfaces:**
- Produces: `api.parseSseFrames(chunk: string): Array<{event: string; data: unknown}>` and
  `api.recommendStream(query, sessionId, handlers): Promise<void>` where `handlers` is
  `{ onUnderstood, onSearching, onResults, onDone, onError }`.

Everything before this task already works. Streaming is additive: if it misbehaves, the
JSON path in Task 19 remains the shipped implementation (spec §7.1).

- [ ] **Step 1: Write the failing parser test**

`frontend/src/lib/stream.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { parseSseFrames } from "./api";

describe("parseSseFrames", () => {
  it("parses a single complete frame", () => {
    const frames = parseSseFrames('event: understood\ndata: {"a":1}\n\n');
    expect(frames).toEqual([{ event: "understood", data: { a: 1 } }]);
  });

  it("parses several frames in one chunk", () => {
    const frames = parseSseFrames(
      'event: searching\ndata: {"candidates":12}\n\nevent: done\ndata: {}\n\n');
    expect(frames.map((f) => f.event)).toEqual(["searching", "done"]);
  });

  it("ignores an incomplete trailing frame", () => {
    expect(parseSseFrames('event: understood\ndata: {"a":1}')).toEqual([]);
  });

  it("skips frames with unparseable data rather than throwing", () => {
    const frames = parseSseFrames("event: results\ndata: {oops\n\nevent: done\ndata: {}\n\n");
    expect(frames.map((f) => f.event)).toEqual(["done"]);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd frontend && npx vitest run src/lib/stream.test.ts
```

Expected: FAIL — `parseSseFrames` is not exported.

- [ ] **Step 3: Add streaming to `frontend/src/lib/api.ts`**

```ts
export interface SseFrame {
  event: string;
  data: unknown;
}

/** Parse complete SSE frames from a buffer. Incomplete trailing frames are ignored
 *  so the caller can retain the remainder for the next chunk. */
export function parseSseFrames(buffer: string): SseFrame[] {
  const frames: SseFrame[] = [];
  for (const block of buffer.split("\n\n")) {
    const eventLine = block.match(/^event:\s*(.+)$/m);
    const dataLine = block.match(/^data:\s*(.+)$/m);
    if (!eventLine || !dataLine) continue;
    try {
      frames.push({ event: eventLine[1].trim(), data: JSON.parse(dataLine[1]) });
    } catch {
      // Malformed payload — skip this frame rather than failing the stream.
    }
  }
  return frames;
}

export interface StreamHandlers {
  onUnderstood?: (data: any) => void;
  onSearching?: (data: any) => void;
  onResults?: (data: any) => void;
  onDone?: (data: any) => void;
  onError?: (error: ApiFailure) => void;
}

/** POST + fetch streaming. Native EventSource is GET-only, and the request body
 *  carries a natural-language query plus session state (spec 7.1). */
export async function recommendStream(
  query: string,
  sessionId: string | undefined,
  handlers: StreamHandlers,
): Promise<void> {
  const response = await fetch(`${BASE}/api/recommend/stream`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ query, session_id: sessionId ?? null }),
  });

  if (!response.ok || !response.body) {
    handlers.onError?.(new ApiFailure("INTERNAL", "Stream failed to start.", true));
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lastBoundary = buffer.lastIndexOf("\n\n");
    if (lastBoundary === -1) continue;
    const complete = buffer.slice(0, lastBoundary + 2);
    buffer = buffer.slice(lastBoundary + 2);

    for (const frame of parseSseFrames(complete)) {
      const data = frame.data as any;
      if (frame.event === "understood") handlers.onUnderstood?.(data);
      else if (frame.event === "searching") handlers.onSearching?.(data);
      else if (frame.event === "results") handlers.onResults?.(data);
      else if (frame.event === "done") handlers.onDone?.(data);
      else if (frame.event === "error") {
        handlers.onError?.(new ApiFailure(
          data.error?.code ?? "INTERNAL",
          data.error?.message ?? "Something went wrong.",
          data.error?.retryable ?? false));
      }
    }
  }
}
```

- [ ] **Step 4: Add a streaming path to `useRecommendation`**

Extend the hook with a `stage` field and a `submitStreaming` action, leaving `submit`
untouched as the fallback:

```ts
type Stage = "idle" | "understanding" | "searching" | "ranking" | "ready" | "error";

// inside useRecommendation, alongside the existing state:
const [stage, setStage] = useState<Stage>("idle");
const [partial, setPartial] = useState<Partial<RecommendResponse> | null>(null);

const submitStreaming = useCallback(async (query: string, useSession = false) => {
  setStage("understanding");
  setError(null);
  setResponse(null);
  await recommendStream(query, useSession ? sessionId.current : undefined, {
    onUnderstood: (data) => {
      sessionId.current = data.session_id;
      setPartial({
        session_id: data.session_id,
        assumptions: data.assumptions,
        clarifying_question: data.clarifying_question,
      } as Partial<RecommendResponse>);
      setStage("searching");
    },
    onSearching: () => setStage("ranking"),
    onResults: (data) => {
      // Functional update: `partial` was set by onUnderstood earlier in this same
      // callback, so reading it from the closure would see the stale value.
      setPartial((current) => {
        setResponse({
          session_id: sessionId.current ?? "",
          intent: {},
          assumptions: current?.assumptions ?? [],
          clarifying_question: current?.clarifying_question ?? null,
          groups: data.groups,
          relaxations: data.relaxations ?? [],
          timings_ms: {},
        } as RecommendResponse);
        return current;
      });
      setStage("ready");
      setStatus("ready");
    },
    onError: (err) => { setError(err); setStage("error"); setStatus("error"); },
  });
}, []);
```

Return `stage`, `partial`, and `submitStreaming` alongside the existing values.

- [ ] **Step 5: Render intermediate state in `App.tsx`**

Switch `InputPanel`'s handler to `submitStreaming`, and render the understanding strip as
soon as it arrives — before results exist:

```tsx
{partial && stage !== "ready" && (
  <div className="mt-8">
    <AssumptionChips
      assumptions={partial.assumptions ?? []}
      question={partial.clarifying_question ?? null}
      onAnswer={refine}
    />
    <p className="text-sm text-slate-500">
      {stage === "searching" ? "Searching the catalogue…" : "Choosing the best matches…"}
    </p>
  </div>
)}
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd frontend && npx vitest run
```

Expected: 15 passed.

- [ ] **Step 7: Verify staged reveal in the browser**

Run a golden query and confirm the assumption chips appear *before* the product cards.
That gap is the whole point of streaming — if both appear together, buffering is defeating
it and `X-Accel-Buffering: no` needs checking on the deployed backend.

- [ ] **Step 8: Commit**

```bash
git add frontend/src
git commit -m "feat: streamed staged reveal over POST with fetch streaming"
```

---

## Phase 5 — Ship

### Task 23: URL validation and the evaluation query set

**Files:**
- Create: `backend/scripts/validate_urls.py`, `backend/eval/queries.yaml`, `backend/data/url_validation.json`
- Test: `backend/tests/test_eval_queries.py`

**Interfaces:**
- Produces: `data/url_validation.json` (a sampled resolvability rate), and `eval/queries.yaml` — golden plus unseen queries. **The harness itself is v2** (spec §11); this task ships the query set so the intent is legible and v2 is a small addition.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_eval_queries.py`:

```python
from pathlib import Path

import yaml

QUERIES = Path(__file__).parent.parent / "eval" / "queries.yaml"


def test_golden_queries_are_the_assignment_examples():
    data = yaml.safe_load(QUERIES.read_text(encoding="utf-8"))
    assert len(data["golden"]) == 3
    joined = " ".join(q["query"] for q in data["golden"]).lower()
    assert "hampta" in joined and "wedding" in joined and "anniversary" in joined


def test_unseen_queries_cover_unrelated_domains():
    data = yaml.safe_load(QUERIES.read_text(encoding="utf-8"))
    assert len(data["unseen"]) >= 7
    domains = {q["domain"] for q in data["unseen"]}
    assert len(domains) >= 5, "unseen queries must span domains, not restate one"


def test_every_query_has_an_id_and_text():
    data = yaml.safe_load(QUERIES.read_text(encoding="utf-8"))
    for q in data["golden"] + data["unseen"]:
        assert q["id"] and q["query"]
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && python -m pytest tests/test_eval_queries.py -v
```

Expected: FAIL — `FileNotFoundError: eval/queries.yaml`.

- [ ] **Step 3: Write `backend/eval/queries.yaml`**

```yaml
# Golden queries are the assignment's examples. Unseen queries exist to show the
# architecture generalises rather than being engineered to pass three known cases
# (spec principle 1). The automated harness that runs these is v2.

golden:
  - id: trek-hampta
    domain: outdoor
    query: >-
      I am going for a trek to Hampta Pass in the last week of October for one
      week. Please find me trekking essentials and clothing.
    expect: multiple groups covering clothing and gear; empty groups are acceptable
      where the catalogue is genuinely thin (sleeping bags, trekking poles)
  - id: wedding-traditional
    domain: apparel
    query: Find me good traditional wear for my friend's wedding in March next year.
    expect: ethnic wear groups; a clarifying question about who it is for is reasonable
  - id: anniversary-gift
    domain: gifting
    query: I need a premium gifting hamper for my parents' 25th anniversary next month.
    expect: several gift categories at the premium or luxury price tier

unseen:
  - id: office-headphones
    domain: electronics
    query: wireless headphones for office calls under Rs 5,000
    expect: budget filter applied as a hard cut; no item above Rs 5,000
  - id: home-workout
    domain: fitness
    query: beginner home workout equipment
    expect: several distinct equipment groups, not one undifferentiated list
  - id: new-apartment-gift
    domain: home
    query: a useful gift for someone moving into a new apartment
    expect: home and kitchen groups; assumptions surfaced about budget
  - id: walking-shoes
    domain: footwear
    query: comfortable shoes for daily walking
    expect: a single well-populated group; simple queries should not be over-decomposed
  - id: wfh-desk
    domain: office
    query: desk accessories for working from home
    expect: multiple small accessory groups
  - id: badminton-beginner
    domain: sports
    query: badminton equipment for a beginner
    expect: racquets and shuttles; beginner framing reflected in price tier
  - id: five-day-travel
    domain: travel
    query: travel essentials for a five-day trip
    expect: luggage and accessories; duration reflected in the assumptions
```

- [ ] **Step 4: Write `backend/scripts/validate_urls.py`**

```python
"""Bounded URL validation over the final catalogue.

Exhaustive validation of ~20k URLs would be slow and abusive toward Amazon, so
this samples. The output supports a claim of "resolvable, spot-checked", never
"all links are live" (docs/dataset.md 5.6).

Note: Amazon returns 200 for delisted products with an "unavailable" body, so
this establishes routing, not availability.
"""
import gzip
import json
import random
import sys
import time
from datetime import date
from pathlib import Path

import httpx

SAMPLE_SIZE = 200
CONCURRENCY = 5
DELAY_SECONDS = 0.3
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")


def run(catalogue: Path, out: Path, sample_size: int = SAMPLE_SIZE) -> None:
    products = [json.loads(line) for line in
                gzip.open(catalogue, "rt", encoding="utf-8")]

    # Stratify by category so the sample is not dominated by the largest ones.
    by_category: dict[str, list[dict]] = {}
    for p in products:
        by_category.setdefault(p["category"], []).append(p)

    rng = random.Random(0)
    per_category = max(1, sample_size // max(len(by_category), 1))
    sample = []
    for group in by_category.values():
        sample.extend(rng.sample(group, min(per_category, len(group))))
    sample = sample[:sample_size]

    results = {"ok": 0, "failed": 0, "failures": []}
    with httpx.Client(headers={"User-Agent": UA}, timeout=15.0,
                      follow_redirects=True) as client:
        for i, product in enumerate(sample):
            try:
                status = client.head(product["product_url"]).status_code
            except httpx.HTTPError as exc:
                status = str(exc)[:60]
            if status == 200:
                results["ok"] += 1
            else:
                results["failed"] += 1
                results["failures"].append({"id": product["id"], "status": status})
            time.sleep(DELAY_SECONDS)
            if (i + 1) % 25 == 0:
                print(f"  {i + 1}/{len(sample)}", file=sys.stderr)

    total = results["ok"] + results["failed"]
    out.write_text(json.dumps({
        "checked": total,
        "catalogue_size": len(products),
        "resolvable": results["ok"],
        "resolvable_rate": round(results["ok"] / total, 4) if total else 0.0,
        "sampled": True,
        "note": "HTTP 200 establishes routing, not product availability.",
        "date": date.today().isoformat(),
        "failures": results["failures"][:20],
    }, indent=2))
    print(f"{results['ok']}/{total} resolvable")


if __name__ == "__main__":
    run(Path("data/catalogue.jsonl.gz"), Path("data/url_validation.json"))
```

- [ ] **Step 5: Run tests, then run validation**

```bash
cd backend && python -m pytest tests/test_eval_queries.py -v
python scripts/validate_urls.py
cat data/url_validation.json
```

Expected: 3 passed. Validation takes roughly a minute for 200 URLs at the configured delay.
Record the rate — it is what the README reports.

- [ ] **Step 6: Run every golden and unseen query by hand**

With both servers running, submit all ten queries from `eval/queries.yaml` through the UI.
For each, check: sub-needs are sensible, no group contains five near-identical products, no
reason states a specification absent from the title, and empty groups read honestly.

This manual pass substitutes for the v2 harness. Note anything that looks wrong — but
resist tuning `scoring.WEIGHTS` from impressions, which is precisely what the harness
exists to prevent (spec §12).

- [ ] **Step 7: Commit**

```bash
git add backend/eval backend/scripts/validate_urls.py backend/tests/test_eval_queries.py
git add backend/data/url_validation.json
git commit -m "feat: add evaluation query set and sampled URL validation"
```

---

### Task 24: README

**Files:**
- Create: `README.md`

The assignment requires setup instructions, architecture overview, design decisions, AI
approach, known limitations, and future improvements.

- [ ] **Step 1: Write `README.md`**

````markdown
# Personal Shopping Assistant

Describe what you need in plain English; get grouped product recommendations with reasons
and links, from a ~20,000-product Amazon India catalogue.

## Setup

**Backend** (Python 3.11)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # add GEMINI_API_KEY and optionally GROQ_API_KEY
uvicorn app.main:app --reload --workers 1 --port 8000
```

**Frontend** (Node 20+)

```bash
cd frontend
npm install
cp .env.example .env
npm run dev               # http://localhost:5173
```

The catalogue and its embeddings are committed, so there is no data preparation step and no
Kaggle account is needed. `GEMINI_API_KEY` is required — it powers both query-time
reasoning and query embeddings.

**Tests**

```bash
cd backend && python -m pytest        # no network, no API keys
cd frontend && npx vitest run
```

## Architecture

```
React SPA ──POST──> FastAPI ──> services/ ──> providers/  (generation, embedding)
                                          └─> catalogue/  (numpy cosine index)
```

Routers handle HTTP only; services never touch `Request`/`Response`. Swapping a generation
provider or a catalogue source touches one file.

### The pipeline

```
query
  ├─ 1. Understand   LLM → structured intent + sub-needs + assumptions
  ├─ 2. Filter       deterministic Python, tier-gated (no AI)
  ├─ 3. Retrieve     top-8 per sub-need, cosine over the embedding matrix
  ├─ 4. Pre-rank     deterministic scoring + diversity → top 4-5 per sub-need (no AI)
  └─ 5. Rerank       LLM → final picks + one-sentence reasons
```

Two LLM calls per query, regardless of request complexity.

## Design decisions

**Sub-need decomposition drives retrieval.** A single vector for "trekking essentials and
clothing" is a blurry average and skews toward whatever the catalogue holds most of. Each
sub-need is retrieved separately, so result groups derive from the request rather than being
invented afterwards.

**The LLM decides what a constraint is; Python decides which rows survive it.** Arithmetic
over thousands of rows must be exact and testable, and embeddings do not encode price — two
jackets at ₹2,000 and ₹22,000 have near-identical vectors.

**A three-tier data-trust model governs filtering.** Source-grounded fields (price, rating,
URL) and title-verified attributes may exclude products. LLM-inferred semantics
(`use_case`, `season`, `occasion`) may only rank them. An enrichment mistake degrades
ranking; it never makes a valid product unreachable.

**Generation and embedding providers are separate protocols.** Generation may fall back
(Gemini → Groq). Embeddings may not: query vectors must share the catalogue's vector space,
so a manifest pins the model and dimensionality and the index refuses to load on mismatch.
A silent swap would return plausible-looking numbers and noise results with nothing to
debug.

**No vector database.** 20k products is a numpy matrix; cosine over 20k × 768 stays viable
past 100k rows.

**The catalogue is sampled query-agnostically.** Stratified across all 214 source
categories, not selected to make the three assignment examples work. Those are evaluation
cases — `backend/eval/queries.yaml` also holds seven unseen queries from unrelated domains.

## AI approach

**Offline.** The source dataset has no description field, so descriptions and attributes are
generated once from product titles and committed. The model may only restate and categorise
what the title already asserts — no invented weights, temperature ratings, or materials.
Anything it claims as explicit is re-checked in code against the source title before it
earns the right to filter.

**Query time.** Gemini 2.5 Flash for intent extraction and final reranking. Everything
between them is deterministic Python. Hallucinated product IDs are validated away against
the candidate pool, so the model can never invent a product.

**Testing.** A stub provider makes the entire pipeline testable with no network and no API
keys.

## Known limitations

- **No real descriptions in the source data.** Descriptions are generated from titles, so
  the assistant reasons at "insulated jacket suited to cold-weather trekking", never "rated
  to −12 °C".
- **Some categories are genuinely sparse.** Sleeping bags, trekking poles, and sleeping mats
  barely exist in the source. Those groups return empty and say so — the honest consequence
  of query-agnostic sampling.
- **Category metadata is noisy.** Sleeping bags are filed under "Small Animals" and first
  aid under "Software", so source categories are used for stratification and price cohorts,
  never as semantic filters.
- **Sessions are process-local**, so the backend runs a single worker.
- **The catalogue is a 2023 snapshot.** Prices and availability drift. URLs are
  spot-checked, not exhaustively validated — see `backend/data/url_validation.json` for the
  sampled rate. HTTP 200 establishes routing, not availability.
- **Pre-ranking weights are unfitted.** Conservative and similarity-dominant. The evaluation
  harness that would justify tuning them is v2, so no aggregate quality or latency figures
  are claimed.
- **Free-tier rate limits.** The fallback chain mitigates but does not eliminate them.

## Future improvements

- Evaluation harness over `eval/queries.yaml` with graded relevance judgements, turning
  recommendation quality into a tracked metric and giving the pre-ranking weights something
  to be fitted on
- Redis-backed sessions and horizontal scaling
- A real vector store past ~100k products
- Learning-to-rank from click-through, replacing LLM reranking in the hot path

## Data

See [ATTRIBUTION.md](ATTRIBUTION.md) and [docs/dataset.md](docs/dataset.md).
````

- [ ] **Step 2: Verify every setup command from a clean checkout**

```bash
cd /tmp && rm -rf readme-check && git clone /Users/soumyagupta/Documents/resume-projects/confluxe readme-check
cd readme-check/backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && python -m pytest -q
```

Tests must pass with no `.env` present. If they do not, the stub-provider isolation has been
broken somewhere.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup, architecture, and limitations"
```

---

### Task 25: Two deployments

**Files:**
- Create: `backend/Dockerfile`, `render.yaml`, `frontend/vercel.json`

**Interfaces:**
- Produces: a public backend URL and a public frontend URL.

- [ ] **Step 1: Write `backend/Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY data ./data

# Single worker: sessions are process-local (spec 6).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
```

`scripts/` is copied deliberately — `app.services.scoring` imports `variant_key` and
`app` imports the tier-B verifiers from there, so the verifiers stay identical offline and
at runtime.

- [ ] **Step 2: Write `render.yaml`**

```yaml
services:
  - type: web
    name: shopping-assistant-api
    runtime: docker
    dockerfilePath: ./backend/Dockerfile
    dockerContext: ./backend
    healthCheckPath: /api/health
    envVars:
      - key: GEMINI_API_KEY
        sync: false
      - key: GROQ_API_KEY
        sync: false
      - key: CORS_ORIGINS
        sync: false
```

- [ ] **Step 3: Write `frontend/vercel.json`**

```json
{
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "framework": "vite",
  "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }]
}
```

- [ ] **Step 4: Deploy the backend and verify it independently**

```bash
curl -s https://<backend-host>/api/health
curl -s -X POST https://<backend-host>/api/recommend \
  -H 'content-type: application/json' \
  -d '{"query":"wireless headphones for office calls under 5000"}' | head -40
```

A `ManifestMismatch` at startup means the committed embeddings and the configured model
disagree — rebuild embeddings rather than loosening the check.

- [ ] **Step 5: Deploy the frontend**

Set `VITE_API_BASE_URL` to the backend URL in Vercel's environment settings, then deploy.
Add the Vercel domain to the backend's `CORS_ORIGINS`. Preview deployments are already
covered by the `allow_origin_regex` in `main.py`.

- [ ] **Step 6: Verify cross-origin streaming — the most likely breakage**

Open the deployed frontend, run a golden query, and watch the Network tab. The
`/api/recommend/stream` response must arrive incrementally, with assumption chips rendering
before product cards.

If it arrives as one block, a proxy is buffering. Confirm the backend sends
`X-Accel-Buffering: no`. If streaming cannot be made to work cross-origin, switch
`InputPanel` back to `submit` (the JSON path) and ship that — a reliable deployed
application beats a broken stream (spec §12.1).

- [ ] **Step 7: Record the cold-start behaviour**

Render's free tier idles out after ~15 minutes, so the first request can take ~50 seconds.
Either note it in the README's setup section or move to Fly, which behaves better. Decide
**before** recording the demo video.

- [ ] **Step 8: Commit**

```bash
git add backend/Dockerfile render.yaml frontend/vercel.json
git commit -m "chore: add deployment configuration for Render and Vercel"
```

---

## Appendix: what is deliberately not built

Recorded so a reviewer can see these were decisions rather than omissions.

| Not built | Why |
|---|---|
| Automated evaluation harness | v2. The query set ships; the runner does not (spec §11). |
| Pre-ranking weight tuning | No relevance judgements to fit against. Guessed weights are worse than plain similarity ordering. |
| Third generation provider | Each provider multiplies prompt-compatibility testing across differing structured-output support. |
| Flipkart as a second catalogue source | Dead product URLs. The `CatalogueSource` protocol keeps the option open. |
| Catalogue browsing UI | Cards link directly to Amazon; a browse endpoint is not a dependency of the recommendation flow. |
| Vector database | 20k products is a numpy matrix. |
| Redis sessions | Single worker is correct at this scale, and the constraint is documented. |
| Tier-2 Devanagari translation at ingest | The Latin pool is ~9× the target, so coverage holds without it. The enrichment prompt already emits `title_en`, so enabling it is a filter change, not new machinery (dataset.md §6, Task 6). |
