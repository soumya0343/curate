from app.providers.generation import StubGenerationProvider
from app.schemas.intent import ShoppingIntent, SubNeed
from app.schemas.product import Product
from app.schemas.response import Candidate
from app.services.ranking import build_groups, rerank


def _cand(pid: str, sub_need: str = "Bags") -> Candidate:
    product = Product(
        id=pid, title=f"Product {pid}", title_original=f"Product {pid}", description="",
        category="Test", price=1000.0, price_tier="mid", rating=4.0, reviews=100,
        quality_score=18.4, attributes={}, image_url="https://x/i.jpg",
        product_url=f"https://www.amazon.in/dp/{pid}")
    return Candidate(product=product, similarity=0.8, sub_need=sub_need)


CANDS = [_cand("A"), _cand("B"), _cand("C", "Shoes")]
SUBS = [SubNeed(label="Bags", query="backpack"), SubNeed(label="Shoes", query="boots")]


def test_build_groups_maps_ids_to_recommendations():
    payload = {"groups": [{"label": "Bags", "picks": [
        {"product_id": "A", "reason": "45L suits a week-long trip"}]}]}
    groups = build_groups(payload, CANDS, SUBS)
    bags = next(g for g in groups if g.label == "Bags")
    assert bags.recommendations[0].product_id == "A"
    assert bags.recommendations[0].reason == "45L suits a week-long trip"
    assert bags.recommendations[0].product_url == "https://www.amazon.in/dp/A"


def test_hallucinated_product_ids_are_dropped():
    payload = {"groups": [{"label": "Bags", "picks": [
        {"product_id": "DOES-NOT-EXIST", "reason": "invented"},
        {"product_id": "A", "reason": "real"}]}]}
    groups = build_groups(payload, CANDS, SUBS)
    ids = [r.product_id for r in groups[0].recommendations]
    assert ids == ["A"], "the model must never be able to invent a product"


def test_missing_group_is_reported_as_empty_not_hidden():
    payload = {"groups": [{"label": "Bags", "picks": [
        {"product_id": "A", "reason": "ok"}]}]}
    groups = build_groups(payload, CANDS, SUBS)
    shoes = next(g for g in groups if g.label == "Shoes")
    assert shoes.recommendations == []
    assert shoes.empty_reason is not None


def test_group_the_model_invented_is_ignored():
    payload = {"groups": [{"label": "Spaceships", "picks": [
        {"product_id": "A", "reason": "no"}]}]}
    groups = build_groups(payload, CANDS, SUBS)
    assert {g.label for g in groups} == {"Bags", "Shoes"}


def test_all_sub_needs_always_appear_in_order():
    groups = build_groups({"groups": []}, CANDS, SUBS)
    assert [g.label for g in groups] == ["Bags", "Shoes"]


async def test_rerank_sends_only_candidate_ids_the_model_may_choose_from():
    provider = StubGenerationProvider([{"groups": [
        {"label": "Bags", "picks": [{"product_id": "A", "reason": "r"}]}]}])
    await rerank(provider, CANDS, ShoppingIntent(), SUBS, request_id="r")
    prompt = provider.prompts[0]
    assert "A" in prompt and "B" in prompt and "C" in prompt


async def test_rerank_returns_empty_groups_when_there_are_no_candidates():
    provider = StubGenerationProvider([{"groups": []}])
    groups = await rerank(provider, [], ShoppingIntent(), SUBS, request_id="r")
    assert all(g.recommendations == [] for g in groups)
    assert all(g.empty_reason for g in groups)
