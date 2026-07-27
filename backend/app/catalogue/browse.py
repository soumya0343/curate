"""Catalogue browsing: filter, sort and paginate over the same in-memory
product list app/services/retrieval.py already searches.

There used to be a second store here (Postgres, seeded one-way from this same
JSONL) because a hand-rolled filter/sort/pagination over a Python list felt
like reinventing what SQL does natively. At this catalogue's size (thousands
of rows, read-only, no per-request writes) that tradeoff doesn't hold: the
whole list already lives in process memory for recommendation, a second
store cannot mirror it any more freshly than just reading it directly, and
a list comprehension plus a sort over a few thousand rows costs microseconds
- there's nothing here for a database to be faster at. One data source is
simpler to reason about than two kept in sync.
"""
from typing import Literal

from app.schemas.product import Product

PriceTier = Literal["budget", "mid", "premium", "luxury"]
SortBy = Literal["price", "rating", "reviews", "quality_score", "title"]

_SORT_KEYS = {
    "price": lambda p: p.price,
    "rating": lambda p: p.rating,
    "reviews": lambda p: p.reviews,
    "quality_score": lambda p: p.quality_score,
    "title": lambda p: p.title.lower(),
}


def filter_products(
    products: list[Product],
    *,
    domain: str | None = None,
    category: str | None = None,
    price_tier: PriceTier | None = None,
    search: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
) -> list[Product]:
    result = products
    if domain is not None:
        result = [p for p in result if p.domain == domain]
    if category is not None:
        result = [p for p in result if p.category == category]
    if price_tier is not None:
        result = [p for p in result if p.price_tier == price_tier]
    if search:
        needle = search.lower()
        result = [p for p in result
                  if needle in p.title.lower() or needle in (p.description or "").lower()]
    if min_price is not None:
        result = [p for p in result if p.price >= min_price]
    if max_price is not None:
        result = [p for p in result if p.price <= max_price]
    return result


def sort_products(products: list[Product], sort_by: SortBy,
                   order: Literal["asc", "desc"]) -> list[Product]:
    """Sort by `sort_by`, breaking ties on `id` ascending.

    Ratings and quality scores tie constantly at this catalogue size. Without a
    deterministic tiebreak, two equally-rated products would order arbitrarily
    between one paginated request and the next, so a product could appear on
    two pages or on none. Python's sort is stable, so sorting by id first and
    then doing a second stable sort on the real key keeps tied rows in
    ascending-id order regardless of `order` - it does not undo the stability
    the way negating a string key or reversing after the fact would.
    """
    by_id = sorted(products, key=lambda p: p.id)
    return sorted(by_id, key=_SORT_KEYS[sort_by], reverse=(order == "desc"))


def paginate(products: list[Product], page: int, page_size: int) -> list[Product]:
    start = (page - 1) * page_size
    return products[start: start + page_size]


def category_counts(products: list[Product]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for p in products:
        counts[p.category] = counts.get(p.category, 0) + 1
    return sorted(counts.items())


def domain_counts(products: list[Product]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for p in products:
        if p.domain:
            counts[p.domain] = counts.get(p.domain, 0) + 1
    return sorted(counts.items())


def find_product(products: list[Product], product_id: str) -> Product | None:
    for p in products:
        if p.id == product_id:
            return p
    return None
