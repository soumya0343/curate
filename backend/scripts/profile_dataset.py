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
