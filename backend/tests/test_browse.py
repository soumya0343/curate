from app.catalogue import browse
from app.schemas.product import Product


def _p(pid: str, *, title: str = "Product", category: str = "Backpacks",
       domain: str | None = None, price: float = 1000.0, price_tier: str = "mid",
       rating: float = 4.0, reviews: int = 10, quality_score: float = 9.6,
       description: str = "") -> Product:
    return Product(
        id=pid, title=title, title_original=title, description=description,
        domain=domain, category=category, price=price, price_tier=price_tier,
        rating=rating, reviews=reviews, quality_score=quality_score,
        image_url="https://x/i.jpg", product_url=f"https://www.amazon.in/dp/{pid}")


def test_filter_by_category():
    products = [_p("A", category="Backpacks"), _p("B", category="Books")]
    assert [p.id for p in browse.filter_products(products, category="Books")] == ["B"]


def test_filter_by_price_tier():
    products = [_p("A", price_tier="budget"), _p("B", price_tier="premium")]
    assert [p.id for p in browse.filter_products(products, price_tier="premium")] == ["B"]


def test_filter_by_price_range():
    products = [_p("A", price=100.0), _p("B", price=500.0), _p("C", price=900.0)]
    result = browse.filter_products(products, min_price=200.0, max_price=800.0)
    assert [p.id for p in result] == ["B"]


def test_search_matches_title_or_description():
    products = [_p("A", title="Trekking Backpack"),
                _p("B", title="Formal Shirt", description="great for a trek")]
    result = browse.filter_products(products, search="trek")
    assert {p.id for p in result} == {"A", "B"}


def test_search_is_case_insensitive():
    products = [_p("A", title="Trekking Backpack")]
    assert len(browse.filter_products(products, search="TREKKING")) == 1


def test_unstated_filters_are_no_ops():
    products = [_p("A"), _p("B")]
    assert browse.filter_products(products) == products


def test_filters_compose():
    products = [
        _p("A", category="Backpacks", price=1000.0),
        _p("B", category="Backpacks", price=5000.0),
        _p("C", category="Books", price=1000.0),
    ]
    result = browse.filter_products(products, category="Backpacks", max_price=2000.0)
    assert [p.id for p in result] == ["A"]


def test_sort_breaks_ties_on_id_ascending_regardless_of_direction():
    """Without a tiebreak, rows sharing a rating order arbitrarily between two
    paginated requests - a product could land on two pages or on none."""
    products = [_p("C", rating=4.2), _p("A", rating=4.2), _p("B", rating=4.2)]
    assert [p.id for p in browse.sort_products(products, "rating", "desc")] == ["A", "B", "C"]
    assert [p.id for p in browse.sort_products(products, "rating", "asc")] == ["A", "B", "C"]


def test_sort_descending_orders_by_the_real_key_first():
    products = [_p("A", price=100.0), _p("B", price=900.0), _p("C", price=500.0)]
    assert [p.id for p in browse.sort_products(products, "price", "desc")] == ["B", "C", "A"]


def test_sort_ascending():
    products = [_p("A", price=900.0), _p("B", price=100.0)]
    assert [p.id for p in browse.sort_products(products, "price", "asc")] == ["B", "A"]


def test_sort_by_title_is_case_insensitive():
    products = [_p("A", title="zebra"), _p("B", title="Apple")]
    assert [p.id for p in browse.sort_products(products, "title", "asc")] == ["B", "A"]


def test_paginate_returns_the_requested_slice():
    products = [_p(str(i)) for i in range(25)]
    page2 = browse.paginate(products, page=2, page_size=10)
    assert [p.id for p in page2] == [str(i) for i in range(10, 20)]


def test_paginate_covers_every_row_exactly_once():
    products = [_p(str(i)) for i in range(7)]
    seen = [p.id for page in (1, 2, 3, 4)
            for p in browse.paginate(products, page=page, page_size=2)]
    assert sorted(seen, key=int) == [str(i) for i in range(7)]


def test_category_counts_are_sorted_and_grouped():
    products = [_p("A", category="Backpacks"), _p("B", category="Books"),
                _p("C", category="Backpacks")]
    assert browse.category_counts(products) == [("Backpacks", 2), ("Books", 1)]


def test_domain_counts_skip_products_with_no_domain():
    products = [_p("A", domain="Outdoor"), _p("B", domain=None), _p("C", domain="Outdoor")]
    assert browse.domain_counts(products) == [("Outdoor", 2)]


def test_find_product_returns_none_when_missing():
    assert browse.find_product([_p("A")], "nope") is None


def test_find_product_returns_the_match():
    products = [_p("A"), _p("B")]
    assert browse.find_product(products, "B").id == "B"
