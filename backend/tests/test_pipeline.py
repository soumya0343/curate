import gzip
import json

import numpy as np
import pytest

from app.catalogue.index import CatalogueIndex
from app.catalogue.loader import JsonlCatalogue
from app.providers.embedding import StubEmbedding
from app.providers.generation import StubGenerationProvider
from app.services.pipeline import RecommendationPipeline, collect
from app.services.sessions import SessionStore

INTENT_PAYLOAD = {
    "intent": {"activity": "trekking", "budget_max": None},
    "sub_needs": [{"label": "Backpack", "query": "trekking rucksack"}],
    "assumptions": [{"field": "climate", "value": "cold-weather conditions likely",
                     "reason": "high-altitude trek", "confidence": "medium"}],
    "clarifying_question": None, "confidence": 0.8,
}


def _row(i: int, price: float = 1000.0) -> dict:
    return {"id": f"B{i}", "title": f"Trekking Backpack {i}",
            "title_original": f"Trekking Backpack {i}", "description": "A rucksack.",
            "category": "Backpacks", "price": price, "price_tier": "mid", "rating": 4.2,
            "reviews": 50, "quality_score": 16.5, "attributes": {},
            "image_url": "https://x/i.jpg", "product_url": f"https://www.amazon.in/dp/B{i}"}


@pytest.fixture
def index(tmp_path):
    with gzip.open(tmp_path / "c.jsonl.gz", "wt", encoding="utf-8") as f:
        for i in range(6):
            f.write(json.dumps(_row(i, price=1000.0 * (i + 1))) + "\n")
    products = JsonlCatalogue(tmp_path / "c.jsonl.gz").load()
    rng = np.random.default_rng(0)
    m = rng.standard_normal((6, 8)).astype(np.float32)
    m /= np.linalg.norm(m, axis=1, keepdims=True)
    return CatalogueIndex(products, m)


def _pipeline(index, rerank_payload=None):
    rerank_payload = rerank_payload or {"groups": [{"label": "Backpack", "picks": [
        {"product_id": "B0", "reason": "Suited to multi-day treks."}]}]}
    return RecommendationPipeline(
        index=index, embedder=StubEmbedding(dims=8),
        generator=StubGenerationProvider([INTENT_PAYLOAD, rerank_payload]),
        sessions=SessionStore(ttl_seconds=60))


async def test_pipeline_emits_stages_in_order(index):
    events = [e async for e in _pipeline(index).run("trek gear", None, request_id="r")]
    assert [e.event for e in events] == ["understood", "searching", "results", "done"]


async def test_understood_event_carries_intent_and_assumptions(index):
    events = [e async for e in _pipeline(index).run("trek gear", None, request_id="r")]
    understood = events[0].data
    assert understood["intent"]["activity"] == "trekking"
    assert understood["assumptions"][0]["confidence"] == "medium"
    assert understood["sub_needs"] == ["Backpack"]


async def test_collect_builds_a_full_response(index):
    events = [e async for e in _pipeline(index).run("trek gear", None, request_id="r")]
    response = collect(events)
    assert response.groups[0].label == "Backpack"
    assert response.groups[0].recommendations[0].product_id == "B0"
    assert response.session_id
    assert "intent" in response.timings_ms and "total" in response.timings_ms


async def test_budget_filter_reaches_the_catalogue(index):
    payload = dict(INTENT_PAYLOAD, intent={"activity": "trekking", "budget_max": 2500})
    pipe = RecommendationPipeline(
        index=index, embedder=StubEmbedding(dims=8),
        generator=StubGenerationProvider([payload, {"groups": []}]),
        sessions=SessionStore(ttl_seconds=60))
    events = [e async for e in pipe.run("cheap trek gear", None, request_id="r")]
    assert events[1].data["candidates"] <= 2, "only B0 and B1 are under Rs 2500"


async def test_session_intent_persists_for_follow_up(index):
    sessions = SessionStore(ttl_seconds=60)
    pipe = RecommendationPipeline(
        index=index, embedder=StubEmbedding(dims=8),
        generator=StubGenerationProvider([INTENT_PAYLOAD, {"groups": []}]),
        sessions=sessions)
    events = [e async for e in pipe.run("trek gear", None, request_id="r")]
    sid = collect(events).session_id
    assert sessions.get(sid).activity == "trekking"


async def test_follow_up_merges_onto_prior_intent(index):
    """A refinement carries prior context: 'make it cheaper' must keep the activity."""
    sessions = SessionStore(ttl_seconds=60)
    first = RecommendationPipeline(
        index=index, embedder=StubEmbedding(dims=8),
        generator=StubGenerationProvider([INTENT_PAYLOAD, {"groups": []}]),
        sessions=sessions)
    sid = collect([e async for e in first.run("trek gear", None,
                                              request_id="r")]).session_id

    delta = {"intent": {"budget_max": 3000},
             "sub_needs": [{"label": "Backpack", "query": "cheap rucksack"}],
             "assumptions": [], "clarifying_question": None, "confidence": 0.7}
    second = RecommendationPipeline(
        index=index, embedder=StubEmbedding(dims=8),
        generator=StubGenerationProvider([delta, {"groups": []}]),
        sessions=sessions)
    events = [e async for e in second.run("make it cheaper", sid, request_id="r2")]

    merged = events[0].data["intent"]
    assert merged["budget_max"] == 3000
    assert merged["activity"] == "trekking", "prior intent must survive the delta"
    assert events[0].data["session_id"] == sid


async def test_empty_group_is_reported_not_hidden(index):
    """The model returning no picks must still yield the group, with a reason."""
    pipe = _pipeline(index, rerank_payload={"groups": []})
    events = [e async for e in pipe.run("trek gear", None, request_id="r")]
    group = collect(events).groups[0]
    assert group.label == "Backpack"
    assert group.recommendations == []
    assert group.empty_reason


async def test_provider_failure_emits_error_event(index):
    class Boom:
        name = "boom"

        async def generate_json(self, prompt, *, request_id):
            raise RuntimeError("upstream exploded")

    from app.providers.generation import FallbackChain
    pipe = RecommendationPipeline(
        index=index, embedder=StubEmbedding(dims=8),
        generator=FallbackChain(Boom(), None), sessions=SessionStore(ttl_seconds=60))
    events = [e async for e in pipe.run("trek gear", None, request_id="r")]
    assert events[-1].event == "error"
    assert events[-1].data["error"]["code"] == "PROVIDER_UNAVAILABLE"


async def test_unexpected_exception_never_leaks_internals(index):
    class Leaky:
        name = "leaky"

        async def generate_json(self, prompt, *, request_id):
            raise ValueError("connection string postgres://user:hunter2@host")

    pipe = RecommendationPipeline(
        index=index, embedder=StubEmbedding(dims=8), generator=Leaky(),
        sessions=SessionStore(ttl_seconds=60))
    events = [e async for e in pipe.run("trek gear", None, request_id="r")]
    assert events[-1].event == "error"
    assert events[-1].data["error"]["code"] == "INTERNAL"
    assert "hunter2" not in json.dumps(events[-1].data)
