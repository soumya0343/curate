"""URL validation over the catalogue, split into two independent modes.

1. `assert_structure` — pure, offline, no network. The source dataset's
   `productURL` is *derived from* `asin` for 100% of 1,589,160 rows, so the
   structural invariant (product_url == f"https://www.amazon.in/dp/{id}") is
   the real guarantee here. This is free to run and catches malformed ids or
   duplicate ids deterministically, every time, for the whole catalogue.

2. `run` — a sampled, live network check (opt-in only, see below). Exhaustive
   validation of ~20k+ URLs would be slow and abusive toward Amazon, so this
   samples, stratified by category, with a polite delay between requests.

   IMPORTANT: Amazon returns HTTP 200 for delisted products with an
   "unavailable" body, so a 200 here establishes routing, not availability.
   Never read the output of `run` as a claim that "all links are live" — at
   most it supports "resolvable, spot-checked" (docs/dataset.md 5.6).

The default `__main__` entry point runs `assert_structure` only, against
whatever catalogue is available, and makes no network request. `run` is only
reachable behind an explicit `--network` flag, because there is currently no
real catalogue — only synthetic mock data with fabricated ASINs — and a live
status-code sweep against those would be meaningless and, since the target
would be the real amazon.in, rude to Amazon.
"""
import argparse
import gzip
import json
import random
import sys
import time
from datetime import date
from pathlib import Path

import httpx

SAMPLE_SIZE = 200
DELAY_SECONDS = 0.3  # sequential with a pause; concurrency would trip bot defences
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")


def assert_structure(products: list[dict]) -> dict:
    """Offline structural check: no network, no I/O beyond what's passed in.

    For every product, asserts:
    - `product_url == f"https://www.amazon.in/dp/{id}"`
    - ids are unique across the list
    - `image_url` is a non-empty https URL

    Returns a summary dict: {"checked": n, "malformed": [...], "duplicate_ids": [...]}
    where "malformed" lists ids whose product_url or image_url failed the
    invariant, and "duplicate_ids" lists ids that appeared more than once.
    """
    seen: dict[str, int] = {}
    malformed: list[str] = []
    duplicate_ids: list[str] = []

    for product in products:
        pid = product.get("id")
        seen[pid] = seen.get(pid, 0) + 1

        expected_url = f"https://www.amazon.in/dp/{pid}"
        image_url = product.get("image_url")

        ok = product.get("product_url") == expected_url
        ok = ok and isinstance(image_url, str) and image_url.startswith("https://") \
            and len(image_url) > len("https://")

        if not ok:
            malformed.append(pid)

    for pid, count in seen.items():
        if count > 1:
            duplicate_ids.append(pid)

    return {
        "checked": len(products),
        "malformed": malformed,
        "duplicate_ids": duplicate_ids,
    }


def run(catalogue: Path, out: Path, sample_size: int = SAMPLE_SIZE) -> None:
    """Sampled, live network check. Opt-in only — see module docstring."""
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


def _load_catalogue(catalogue: Path) -> list[dict]:
    if not catalogue.exists():
        return []
    with gzip.open(catalogue, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate catalogue product URLs. Default: offline "
                     "structural check only, no network call.")
    parser.add_argument("--catalogue", type=Path,
                         default=Path("data/catalogue.jsonl.gz"),
                         help="Path to the gzipped JSONL catalogue.")
    parser.add_argument("--out", type=Path,
                         default=Path("data/url_validation.json"),
                         help="Where to write the --network sample report.")
    parser.add_argument("--sample-size", type=int, default=SAMPLE_SIZE,
                         help="Number of products to sample for --network.")
    parser.add_argument("--network", action="store_true",
                         help="Opt in to the live, sampled network check "
                              "against real URLs (see module docstring for "
                              "why this is not the default).")
    args = parser.parse_args()

    if args.network:
        run(args.catalogue, args.out, args.sample_size)
        return

    products = _load_catalogue(args.catalogue)
    summary = assert_structure(products)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
