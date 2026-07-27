"""Catalogue browsing endpoints.

Reads the same in-memory product list app/services/retrieval.py searches for
recommendation (app/catalogue/browse.py) - not a second store. See that
module's docstring for why a separate database was dropped.
"""
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import get_products
from app.catalogue import browse
from app.core.errors import NotFound
from app.schemas.product import Product

router = APIRouter(prefix="/api/catalogue", tags=["catalogue"])

PriceTier = Literal["budget", "mid", "premium", "luxury"]
SortBy = Literal["price", "rating", "reviews", "quality_score", "title"]


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


def _to_summary(p: Product) -> ProductSummary:
    return ProductSummary(
        id=p.id, title=p.title, domain=p.domain, category=p.category,
        subcategory=p.subcategory, price=p.price, currency=p.currency,
        price_tier=p.price_tier, rating=p.rating, reviews=p.reviews,
        image_url=p.image_url, product_url=p.product_url)


def _to_detail(p: Product) -> ProductDetail:
    return ProductDetail(
        **_to_summary(p).model_dump(),
        description=p.description, quality_score=p.quality_score,
        attributes={k: v.model_dump() for k, v in p.attributes.items()})


@router.get("", response_model=CatalogueResponse)
def list_products(
    products: list[Product] = Depends(get_products),
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
    filtered = browse.filter_products(
        products, domain=domain, category=category, price_tier=price_tier,
        search=search, min_price=min_price, max_price=max_price)
    ordered = browse.sort_products(filtered, sort_by, order)
    page_items = browse.paginate(ordered, page, page_size)

    total = len(ordered)
    return CatalogueResponse(
        total=total, page=page, page_size=page_size,
        pages=(total + page_size - 1) // page_size,
        items=[_to_summary(p) for p in page_items])


@router.get("/categories", response_model=list[CategoryCount])
def list_categories(products: list[Product] = Depends(get_products)):
    """Categories with their product counts, for building browse navigation."""
    return [CategoryCount(category=c, count=n) for c, n in browse.category_counts(products)]


@router.get("/domains", response_model=list[DomainCount])
def list_domains(products: list[Product] = Depends(get_products)):
    """Top-level domains with their product counts, one level above category."""
    return [DomainCount(domain=d, count=n) for d, n in browse.domain_counts(products)]


@router.get("/{product_id}", response_model=ProductDetail)
def get_product(product_id: str, products: list[Product] = Depends(get_products)):
    product = browse.find_product(products, product_id)
    if product is None:
        raise NotFound(f"Product '{product_id}' not found.")
    return _to_detail(product)
