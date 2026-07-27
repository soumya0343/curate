"""The catalogue browsing router, over an in-memory product list.

app/catalogue/browse.py carries the filter/sort/pagination logic and is unit
tested directly in test_browse.py. This file is the thin HTTP layer on top:
query-param parsing, response shape, and error envelopes.
"""
import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.main import create_app
from app.schemas.product import Attribute, Product


def _p(pid: str, *, title: str = "Wildcraft 45L Rucksack", category: str = "Backpacks",
       domain: str | None = None, price: float = 3499.0, price_tier: str = "mid",
       rating: float = 4.3, reviews: int = 2871, quality_score: float = 16.5,
       attributes: dict | None = None) -> Product:
    return Product(
        id=pid, title=title, title_original=title, description="A rucksack.",
        domain=domain, category=category, price=price, price_tier=price_tier,
        rating=rating, reviews=reviews, quality_score=quality_score,
        attributes=attributes or {}, image_url="https://img/x.jpg",
        product_url=f"https://www.amazon.in/dp/{pid}")


@pytest.fixture
def client():
    app = create_app(load_catalogue=False)
    yield TestClient(app), app
    app.dependency_overrides.clear()


def _with_products(client, products: list[Product]) -> TestClient:
    test_client, app = client
    app.dependency_overrides[deps.get_products] = lambda: products
    return test_client


def test_listing_returns_every_product_when_unfiltered(client):
    c = _with_products(client, [_p("B0"), _p("B1")])
    body = c.get("/api/catalogue").json()
    assert body["total"] == 2
    assert {item["id"] for item in body["items"]} == {"B0", "B1"}


def test_listing_paginates(client):
    c = _with_products(client, [_p(f"B{i}") for i in range(25)])
    body = c.get("/api/catalogue?page=2&page_size=10").json()
    assert (body["total"], body["page"], body["pages"]) == (25, 2, 3)
    assert len(body["items"]) == 10


def test_listing_filters_by_category(client):
    c = _with_products(client, [_p("B0", category="Backpacks"), _p("B1", category="Books")])
    body = c.get("/api/catalogue?category=Books").json()
    assert [item["id"] for item in body["items"]] == ["B1"]


def test_listing_filters_by_search(client):
    c = _with_products(client, [_p("B0", title="Trekking Backpack"), _p("B1", title="Shirt")])
    body = c.get("/api/catalogue?search=trek").json()
    assert [item["id"] for item in body["items"]] == ["B0"]


def test_an_unlisted_sort_column_is_rejected_before_reaching_the_router(client):
    c = _with_products(client, [_p("B0")])
    response = c.get("/api/catalogue?sort_by=price;DROP TABLE products")
    assert response.status_code == 422


def test_listing_breaks_sort_ties_deterministically(client):
    """Two products tied on the default sort column (rating) must still come
    back in a stable, deterministic order - not whatever the list happened to
    be in."""
    c = _with_products(client, [_p("B2", rating=4.2), _p("B0", rating=4.2), _p("B1", rating=4.2)])
    body = c.get("/api/catalogue").json()
    assert [item["id"] for item in body["items"]] == ["B0", "B1", "B2"]


def test_a_missing_product_is_the_apps_error_envelope(client):
    """404s from this router must match the shape /api/recommend already uses,
    not FastAPI's default {"detail": ...}."""
    c = _with_products(client, [_p("B0")])
    response = c.get("/api/catalogue/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_product_detail_includes_attribute_provenance(client):
    c = _with_products(client, [_p("B0", attributes={
        "gender": Attribute(value="unisex", source="title_verified")})])
    body = c.get("/api/catalogue/B0").json()
    assert body["id"] == "B0"
    assert body["attributes"]["gender"] == {"value": "unisex", "source": "title_verified"}


def test_categories_come_back_with_counts(client):
    c = _with_products(client, [
        _p("B0", category="Backpacks"), _p("B1", category="Backpacks"),
        _p("B2", category="Books")])
    assert c.get("/api/catalogue/categories").json() == [
        {"category": "Backpacks", "count": 2},
        {"category": "Books", "count": 1},
    ]


def test_domains_skip_products_with_no_domain(client):
    c = _with_products(client, [
        _p("B0", domain="Outdoor"), _p("B1", domain=None)])
    assert c.get("/api/catalogue/domains").json() == [{"domain": "Outdoor", "count": 1}]


def test_catalogue_browsing_needs_no_database(client):
    """The whole point of dropping Postgres: browsing reads the same in-memory
    list recommendation does, so there is no second store to be unavailable."""
    c = _with_products(client, [_p("B0")])
    assert c.get("/api/catalogue").status_code == 200
