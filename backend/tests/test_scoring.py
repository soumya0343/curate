from app.schemas.intent import ShoppingIntent
from app.schemas.product import Attribute, Product
from app.schemas.response import Candidate
from app.services.scoring import WEIGHTS, prerank, score_candidate


def _cand(pid: str, similarity: float, sub_need: str = "Bags", *, title: str | None = None,
          quality: float = 10.0, attrs: dict | None = None) -> Candidate:
    product = Product(
        id=pid, title=title or f"Product {pid}", title_original=title or f"Product {pid}",
        description="", category="Test", price=1000.0, price_tier="mid", rating=4.0,
        reviews=100, quality_score=quality, attributes=attrs or {},
        image_url="https://x/i.jpg", product_url=f"https://www.amazon.in/dp/{pid}")
    return Candidate(product=product, similarity=similarity, sub_need=sub_need)


def test_similarity_dominates_scoring():
    high = score_candidate(_cand("A", 0.9, quality=0.0), ShoppingIntent(), 100.0)
    low = score_candidate(_cand("B", 0.4, quality=100.0), ShoppingIntent(), 100.0)
    assert high > low, "quality must never outweigh a large similarity gap"


def test_quality_breaks_ties():
    a = score_candidate(_cand("A", 0.7, quality=100.0), ShoppingIntent(), 100.0)
    b = score_candidate(_cand("B", 0.7, quality=0.0), ShoppingIntent(), 100.0)
    assert a > b


def test_verified_attribute_match_outweighs_inferred_match():
    intent = ShoppingIntent(activity="trekking")
    verified = _cand("A", 0.7, attrs={"use_case": Attribute(
        value=["trekking"], source="title_verified")})
    inferred = _cand("B", 0.7, attrs={"use_case": Attribute(
        value=["trekking"], source="inferred")})
    assert (score_candidate(verified, intent, 100.0)
            > score_candidate(inferred, intent, 100.0))


def test_weights_keep_adjustments_bounded_below_similarity_range():
    adjustable = WEIGHTS["quality"] + WEIGHTS["verified_attr"] + WEIGHTS["inferred_attr"]
    assert adjustable < 0.5, "combined boosts must not be able to overturn similarity"


def test_prerank_limits_per_sub_need():
    cands = [_cand(f"P{i}", 0.9 - i * 0.01, sub_need="Bags") for i in range(10)]
    assert len(prerank(cands, ShoppingIntent(), per_sub_need=5)) == 5


def test_prerank_keeps_each_sub_need_separately():
    cands = ([_cand(f"A{i}", 0.9, sub_need="Bags") for i in range(6)]
             + [_cand(f"B{i}", 0.5, sub_need="Shoes") for i in range(6)])
    out = prerank(cands, ShoppingIntent(), per_sub_need=3)
    by_need = {}
    for c in out:
        by_need.setdefault(c.sub_need, []).append(c)
    assert len(by_need["Bags"]) == 3
    assert len(by_need["Shoes"]) == 3, "a weak sub-need must not be starved by a strong one"


def test_prerank_penalises_near_duplicates():
    cands = [
        _cand("A", 0.90, title="Boat Rockerz 450 Bluetooth Headphones Black"),
        _cand("B", 0.89, title="Boat Rockerz 450 Bluetooth Headphones Blue"),
        _cand("C", 0.88, title="Sony WH1000XM4 Wireless Headphones Black"),
    ]
    out = prerank(cands, ShoppingIntent(), per_sub_need=2)
    ids = [c.product.id for c in out]
    assert ids[0] == "A"
    assert "C" in ids, "a near-duplicate must not occupy the second slot"


def test_prerank_returns_variants_when_a_sub_need_has_nothing_else():
    """Demote, never drop: a sub-need of pure variants must still return picks."""
    cands = [
        _cand("A", 0.90, title="Boat Rockerz 450 Bluetooth Headphones Black"),
        _cand("B", 0.89, title="Boat Rockerz 450 Bluetooth Headphones Blue"),
    ]
    out = prerank(cands, ShoppingIntent(), per_sub_need=3)
    assert [c.product.id for c in out] == ["A", "B"]
    assert out[1].score < out[0].score, "the variant is demoted, not removed"
