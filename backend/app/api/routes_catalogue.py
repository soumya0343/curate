"""Catalogue browsing endpoints backed by Postgres.

Browsing only. Recommendation reads the JSONL index instead (see app/db/mock_db.py
on why these are separate), so nothing here is on the /api/recommend path and a
database outage costs browsing, not the product.
"""
from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.core.errors import NotFound
from app.db.mock_db import get_connection

router = APIRouter(prefix="/api/catalogue", tags=["catalogue"])

PriceTier = Literal["budget", "mid", "premium", "luxury"]
SortBy = Literal["price", "rating", "reviews", "quality_score", "title"]

# Whitelist, not a passthrough: sort_by is interpolated into the SQL string
# because a column name cannot be a bound parameter. Literal[] rejects anything
# unlisted at the FastAPI layer and this dict is the second gate.
SORT_COLUMNS: dict[str, str] = {
    "price": "price",
    "rating": "rating",
    "reviews": "reviews",
    "quality_score": "quality_score",
    "title": "title",
}


class ProductSummary(BaseModel):
    id: str
    title: str
    domain: str | None = None
    category: str
    subcategory: str | None = None
    price: float
    currency: str
    price_tier: str
    rating: float
    reviews: int
    image_url: str | None
    product_url: str | None


class ProductDetail(ProductSummary):
    description: str | None
    quality_score: float
    attributes: dict[str, Any] = {}


class CatalogueResponse(BaseModel):
    total: int
    page: int
    page_size: int
    pages: int
    items: list[ProductSummary]


class CategoryCount(BaseModel):
    category: str
    count: int


class DomainCount(BaseModel):
    domain: str
    count: int


@router.get("", response_model=CatalogueResponse)
def list_products(
    domain: str | None = Query(None),
    category: str | None = Query(None),
    price_tier: PriceTier | None = Query(None),
    search: str | None = Query(None, description="Substring match on title or description"),
    min_price: float | None = Query(None, ge=0),
    max_price: float | None = Query(None, ge=0),
    sort_by: SortBy = Query("rating"),
    order: Literal["asc", "desc"] = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    conditions: list[str] = []
    params: list = []

    if domain:
        conditions.append("domain = %s")
        params.append(domain)
    if category:
        conditions.append("category = %s")
        params.append(category)
    if price_tier:
        conditions.append("price_tier = %s")
        params.append(price_tier)
    if search:
        conditions.append("(title ILIKE %s OR description ILIKE %s)")
        params.extend([f"%{search}%"] * 2)
    if min_price is not None:
        conditions.append("price >= %s")
        params.append(min_price)
    if max_price is not None:
        conditions.append("price <= %s")
        params.append(max_price)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sort_col = SORT_COLUMNS[sort_by]
    direction = "DESC" if order == "desc" else "ASC"
    offset = (page - 1) * page_size

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS n FROM products {where}", params)
            total = cur.fetchone()["n"]

            # `, id` is not decoration: ties on the sort column otherwise order
            # arbitrarily between the two queries a paginated client makes, so a
            # product can appear on page 2 having already appeared on page 1, or
            # be skipped entirely. Ratings tie constantly at this catalogue size.
            cur.execute(
                f"""SELECT id, title, domain, category, subcategory, price, currency,
                           price_tier, rating, reviews, image_url, product_url
                    FROM products {where}
                    ORDER BY {sort_col} {direction}, id ASC
                    LIMIT %s OFFSET %s""",
                params + [page_size, offset],
            )
            items = [ProductSummary(**row) for row in cur.fetchall()]

    return CatalogueResponse(
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size,
        items=items,
    )


@router.get("/categories", response_model=list[CategoryCount])
def list_categories():
    """Categories with their product counts, for building browse navigation."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT category, COUNT(*) AS count
                           FROM products GROUP BY category ORDER BY category""")
            return [CategoryCount(**row) for row in cur.fetchall()]


@router.get("/domains", response_model=list[DomainCount])
def list_domains():
    """Top-level domains with their product counts, one level above category."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT domain, COUNT(*) AS count
                           FROM products WHERE domain IS NOT NULL
                           GROUP BY domain ORDER BY domain""")
            return [DomainCount(**row) for row in cur.fetchall()]


@router.get("/{product_id}", response_model=ProductDetail)
def get_product(product_id: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, title, description, domain, category, subcategory, price,
                          currency, price_tier, rating, reviews, quality_score, attributes,
                          image_url, product_url
                   FROM products WHERE id = %s""",
                (product_id,),
            )
            row = cur.fetchone()
    if row is None:
        raise NotFound(f"Product '{product_id}' not found.")
    return ProductDetail(**row)
