"""Seed the products table from the mock catalogue.

    python scripts/seed_db.py                  # uses .env DATABASE_URL
    DATABASE_URL=postgresql://... python scripts/seed_db.py

One direction only: data/mock/catalogue.jsonl.gz -> Postgres. The JSONL stays
authoritative (its line order is pinned to the embedding matrix rows), so rerun
this after every scripts/build_mock_catalogue.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg2.extras

from app.catalogue.loader import JsonlCatalogue
from app.config import get_settings
from app.db.mock_db import close_db, get_connection, init_db

UPSERT = """
INSERT INTO products
    (id, title, title_original, description, domain, category, subcategory,
     price, currency, price_tier, rating, reviews, quality_score, attributes,
     image_url, product_url)
VALUES %s
ON CONFLICT (id) DO UPDATE SET
    title          = EXCLUDED.title,
    title_original = EXCLUDED.title_original,
    description    = EXCLUDED.description,
    domain         = EXCLUDED.domain,
    category       = EXCLUDED.category,
    subcategory    = EXCLUDED.subcategory,
    price          = EXCLUDED.price,
    currency       = EXCLUDED.currency,
    price_tier     = EXCLUDED.price_tier,
    rating         = EXCLUDED.rating,
    reviews        = EXCLUDED.reviews,
    quality_score  = EXCLUDED.quality_score,
    attributes     = EXCLUDED.attributes,
    image_url      = EXCLUDED.image_url,
    product_url    = EXCLUDED.product_url
"""


def main() -> None:
    settings = get_settings()
    # DATA_DIR points at data/mock for a mock run and at data/ otherwise, so
    # accept either rather than making the seed depend on which one is set.
    candidates = [settings.data_dir / "catalogue.jsonl.gz",
                  settings.data_dir / "mock" / "catalogue.jsonl.gz"]
    catalogue_path = next((p for p in candidates if p.exists()), None)
    if catalogue_path is None:
        sys.exit(f"Catalogue not found at any of {[str(p) for p in candidates]}. "
                 f"Run scripts/build_mock_catalogue.py first.")

    # Never mask the DSN's own password, but never print it either.
    dsn_host = settings.database_url.rsplit("@", 1)[-1]
    print(f"Connecting to {dsn_host} ...")
    # required=True: there is nothing to degrade to here, so an unreachable
    # database must fail the script rather than report a successful no-op.
    init_db(required=True)

    products = JsonlCatalogue(catalogue_path).load()
    print(f"Seeding {len(products)} products ...")

    rows = [
        (p.id, p.title, p.title_original, p.description, p.domain, p.category,
         p.subcategory, p.price, p.currency, p.price_tier, p.rating, p.reviews,
         p.quality_score,
         psycopg2.extras.Json({k: v.model_dump() for k, v in p.attributes.items()}),
         p.image_url, p.product_url)
        for p in products
    ]

    with get_connection() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, UPSERT, rows, page_size=200)

            # Upsert alone leaves orphans: a product dropped from the catalogue
            # would keep serving from Postgres forever. The table mirrors the
            # JSONL, so anything not in the JSONL does not belong in it.
            cur.execute("DELETE FROM products WHERE NOT (id = ANY(%s))",
                        ([p.id for p in products],))
            deleted = cur.rowcount

            cur.execute("SELECT COUNT(*) AS n FROM products")
            total = cur.fetchone()["n"]
        conn.commit()

    close_db()

    if total != len(products):
        sys.exit(f"Seed mismatch: {len(products)} in catalogue, {total} in table.")
    print(f"Done. {total} products in table"
          + (f", {deleted} stale row(s) removed." if deleted else "."))


if __name__ == "__main__":
    main()
