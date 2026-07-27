"""Postgres connection pool for the mock catalogue.

Local dev:  DATABASE_URL=postgresql://user:pass@localhost:5432/catalogue
Supabase:   DATABASE_URL=postgresql://postgres:[password]@db.[ref].supabase.co:5432/postgres

The catalogue table is a browsable mirror of `data/mock/catalogue.jsonl.gz`, not a
second source of truth. The JSONL plus its embedding matrix stay authoritative --
they are what the recommendation pipeline reads, and row order there is pinned to
the vector rows. `scripts/seed_db.py` is the one direction data moves: JSONL ->
Postgres. Nothing writes back.
"""
import logging
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2.pool import PoolError, ThreadedConnectionPool

from app.config import get_settings
from app.core.errors import CatalogueUnavailable

logger = logging.getLogger(__name__)

_pool: ThreadedConnectionPool | None = None

# Sized to FastAPI's sync-route threadpool rather than to expected traffic: every
# route in routes_catalogue.py is a `def`, so Starlette runs it in a worker thread
# and each concurrent request holds a connection for its whole body.
POOL_SIZE = 10

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS products (
    id             TEXT PRIMARY KEY,
    title          TEXT NOT NULL,
    title_original TEXT NOT NULL,
    description    TEXT,
    domain         TEXT,
    category       TEXT NOT NULL,
    subcategory    TEXT,
    price          NUMERIC NOT NULL,
    currency       TEXT NOT NULL DEFAULT 'INR',
    price_tier     TEXT NOT NULL,
    rating         NUMERIC NOT NULL,
    reviews        INTEGER NOT NULL,
    quality_score  NUMERIC NOT NULL,
    attributes     JSONB NOT NULL DEFAULT '{}'::jsonb,
    image_url      TEXT,
    product_url    TEXT
);

-- CREATE TABLE IF NOT EXISTS is a no-op against a table created by an earlier
-- version of this schema, so it would leave the new columns missing and both
-- the seed script and the indexes below would fail on them. Adding them
-- explicitly, BEFORE anything references them, is what makes startup safe on
-- an already-seeded database.
ALTER TABLE products ADD COLUMN IF NOT EXISTS title_original TEXT;
ALTER TABLE products ADD COLUMN IF NOT EXISTS attributes JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE products ADD COLUMN IF NOT EXISTS domain TEXT;
ALTER TABLE products ADD COLUMN IF NOT EXISTS subcategory TEXT;
UPDATE products SET title_original = title WHERE title_original IS NULL;
ALTER TABLE products ALTER COLUMN title_original SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_products_category   ON products(category);
CREATE INDEX IF NOT EXISTS idx_products_price_tier ON products(price_tier);
CREATE INDEX IF NOT EXISTS idx_products_domain     ON products(domain);
"""


def init_db(required: bool = False) -> bool:
    """Open the connection pool. Called once at startup and by the seed script.

    Returns whether the pool is open. With `required=False` an unreachable
    database is logged and swallowed: recommendation serves from the JSONL index
    and needs no Postgres at all, so refusing to boot would take down the whole
    API to protect one router. Catalogue routes then answer 503 (which is what
    they mean) instead of 500. The seed script passes `required=True`, where
    there is nothing to degrade to.
    """
    global _pool
    if _pool is not None:
        return True

    dsn = get_settings().database_url
    try:
        # minconn == maxconn on purpose. psycopg2 only returns a connection to
        # the pool while `len(pool) < minconn`; past that, putconn *closes* it.
        # With minconn=1 the pool would retain exactly one connection and open a
        # fresh one per request, which is the cost pooling exists to avoid.
        _pool = ThreadedConnectionPool(
            minconn=POOL_SIZE,
            maxconn=POOL_SIZE,
            dsn=dsn,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
        # Ensure table exists (idempotent). A schema error here (e.g. a hand-
        # edited database this DDL doesn't expect) must degrade the same way an
        # unreachable database does - recommendation reads the JSONL index and
        # needs no Postgres at all, so this may not crash the whole app either.
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(CREATE_TABLE)
            conn.commit()
    except psycopg2.Error as exc:
        if _pool is not None:
            _pool.closeall()
        _pool = None
        if required:
            raise
        logger.warning("catalogue database unavailable, browsing disabled: %s",
                       str(exc).strip())
        return False

    return True


def is_ready() -> bool:
    return _pool is not None


def close_db() -> None:
    """Close every pooled connection. Called on shutdown and between tests."""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


@contextmanager
def get_connection():
    """Check out a pooled connection, returning it on the way out.

    Raises CatalogueUnavailable rather than RuntimeError when the pool is closed
    or exhausted, so the failure travels through the app's normal error envelope
    instead of surfacing as an unhandled 500.
    """
    if _pool is None:
        raise CatalogueUnavailable(
            "Catalogue database is not connected. Check DATABASE_URL and run "
            "scripts/seed_db.py.")
    try:
        conn = _pool.getconn()
    except PoolError as exc:
        raise CatalogueUnavailable(f"Catalogue database is busy: {exc}") from exc
    try:
        yield conn
    finally:
        _pool.putconn(conn)
