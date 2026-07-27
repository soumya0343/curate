"""Build the real catalogue from the Kaggle-derived, offline-enriched dataset.

Source: `data/enriched.csv` — Amazon India Products 2023 (asaniczka, ODC-By
v1.0, see ATTRIBUTION.md), translated/categorised/attribute-enriched outside
this repo, in the shape docs/dataset.md and docs/taxonomy.md designed for.

WHAT THIS DOES. Maps each CSV row onto `Product` (app/schemas/product.py) with
no schema changes: fields the model already has a slot for are copied
directly; everything else becomes a trust-tier `attributes` entry, re-verified
against `title_original` with the same `scripts/verify_attributes.verify()`
gate the mock catalogue uses (docs/dataset.md 4.1) — a field is tier B
("title_verified") only if the source title actually supports it, tier C
("inferred") otherwise. Then writes the same three files
`build_mock_catalogue.py` does, via the shared `scripts/catalogue_build`, into
`data/` (not `data/mock/`) — that's what `Settings.data_dir` already defaults
to, so the app picks this up with zero config changes, and `data/mock/` is
untouched as the permanent no-credentials fallback (`DATA_DIR=data/mock`).

Rows with no `category` are dropped (logged) — `category` is required on
`Product` and inventing one would misrepresent a field docs/dataset.md marks
as still pending title-inference for those rows.

Run:
    cd backend && python scripts/ingest_enriched.py --embedder hashing   # smoke test, no key
    cd backend && python scripts/ingest_enriched.py --embedder gemini    # real run, needs GEMINI_API_KEY
"""
import collections
import csv
import sys
from pathlib import Path

# `python scripts/ingest_enriched.py` puts scripts/ on sys.path, not the
# backend root, so `app` and `scripts` are both unimportable without this.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.product import Product  # noqa: E402
from scripts import catalogue_build  # noqa: E402
from scripts.verify_attributes import TIER_B_FIELDS  # noqa: E402

DIMS = 256
CSV_PATH = Path("data/enriched.csv")
OUT_DIR = Path("data")

# Every enrichment column that isn't a direct Product field, and therefore
# becomes a trust-tier `attributes` entry. Declared here (not inferred from
# the CSV header) so the mapping is legible without reading the CSV: adding a
# column this ingest doesn't yet handle is a visible diff here, not a silent
# no-op.
ATTRIBUTE_FIELDS = (
    "brand", "product_type", "gender", "use_case", "occasion", "season",
    "age_group", "material", "capacity_l", "capacity_ml", "weight_kg",
    "screen_size_in", "pack_count", "water_resistant", "wireless",
    "rechargeable", "gift_suitable",
)


def _str(v: str) -> str | None:
    return v if v else None


def _float(v: str) -> float | None:
    return float(v) if v else None


def _int(v: str) -> int | None:
    return int(float(v)) if v else None


def _bool(v: str) -> bool | None:
    return v.strip().lower() == "true" if v else None


def _list(v: str) -> list[str]:
    return [x for x in v.split("|") if x] if v else []


_ATTRIBUTE_PARSERS = {
    "brand": _str, "product_type": _str, "gender": _str,
    "use_case": _list, "occasion": _list, "season": _str, "age_group": _str,
    "material": _str, "capacity_l": _float, "capacity_ml": _float,
    "weight_kg": _float, "screen_size_in": _float, "pack_count": _int,
    "water_resistant": _bool, "wireless": _bool, "rechargeable": _bool,
    "gift_suitable": _bool,
}


def raw_attributes(row: dict) -> dict:
    return {field: _ATTRIBUTE_PARSERS[field](row[field]) for field in ATTRIBUTE_FIELDS}


def build_product(row: dict) -> dict | None:
    """One CSV row -> one Product-shaped dict, or None if it must be dropped."""
    if not row["category"]:
        return None

    attributes = catalogue_build.apply_trust_tiers(
        raw_attributes(row), row["title_original"], TIER_B_FIELDS)

    return {
        "id": row["asin"],
        "title": row["title_en"],
        "title_original": row["title_original"],
        "description": row["description"],
        "domain": _str(row["domain"]),
        "category": row["category"],
        "subcategory": _str(row["subcategory"]),
        "price": float(row["price_inr"]),
        "currency": "INR",
        "price_tier": row["price_tier"],
        "rating": float(row["rating"]),
        "reviews": int(float(row["rating_count"])),
        "quality_score": float(row["quality_score"]),
        "attributes": attributes,
        "image_url": row["imgUrl"],
        "product_url": row["productURL"],
    }


def build(csv_path: Path) -> list[dict]:
    products: list[dict] = []
    dropped = 0
    with csv_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            product = build_product(row)
            if product is None:
                dropped += 1
                continue
            # Fail fast on a malformed row rather than shipping a catalogue
            # entry the app's own loader would later reject.
            Product.model_validate(product)
            products.append(product)

    if dropped:
        print(f"dropped {dropped} rows with no category "
              f"(category_source=pending_title_inference)")
    return products


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embedder", choices=["hashing", "gemini", "jina"], default="hashing",
                         help="hashing needs no key; gemini/jina need "
                              "GEMINI_API_KEY/JINA_API_KEY and give real semantic "
                              "retrieval (jina's free tier has far more headroom)")
    parser.add_argument("--csv", type=Path, default=CSV_PATH)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    catalogue = build(args.csv)
    catalogue_build.write(
        catalogue, args.out, dims=DIMS, embedder=args.embedder, synthetic=False,
        note=("Derived from the Amazon India Products 2023 dataset (asaniczka, "
              "ODC-By v1.0) via offline enrichment. See ATTRIBUTION.md."))

    tiers = collections.Counter(p["price_tier"] for p in catalogue)
    domains = collections.Counter(p["domain"] for p in catalogue)
    print(f"wrote {len(catalogue)} products across {len(domains)} domains "
          f"to {args.out} ({args.embedder} embeddings)")
    print(f"price tiers: {dict(tiers)}")
