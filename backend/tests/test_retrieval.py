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
