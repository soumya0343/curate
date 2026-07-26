import gzip
import json
import re

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.catalogue.index import CatalogueIndex
from app.catalogue.loader import JsonlCatalogue
from app.main import create_app
from app.providers.embedding import StubEmbedding
from app.providers.generation import (FallbackChain, GenerationProvider,
                                      StubGenerationProvider)
from app.services.pipeline import RecommendationPipeline
from app.services.sessions import SessionStore

INTENT_PAYLOAD = {
    "intent": {"activity": "trekking"},
    "sub_needs": [{"label": "Backpack", "query": "trekking rucksack"}],
    "assumptions": [], "clarifying_question": None, "confidence": 0.8,
}
RERANK_PAYLOAD = {"groups": [{"label": "Backpack", "picks": [
    {"product_id": "B0", "reason": "Suited to multi-day treks."}]}]}


@pytest.fixture
def client(tmp_path):
    with gzip.open(tmp_path / "c.jsonl.gz", "wt", encoding="utf-8") as f:
        for i in range(3):
            f.write(json.dumps({
                "id": f"B{i}", "title": f"Trekking Backpack {i}",
                "title_original": f"Trekking Backpack {i}", "description": "A rucksack.",
                "category": "Backpacks", "price": 1000.0, "price_tier": "mid",
                "rating": 4.2, "reviews": 50, "quality_score": 16.5, "attributes": {},
                "image_url": "https://x/i.jpg",
                "product_url": f"https://www.amazon.in/dp/B{i}"}) + "\n")
    products = JsonlCatalogue(tmp_path / "c.jsonl.gz").load()
    m = np.eye(3, 8, dtype=np.float32)
    index = CatalogueIndex(products, m)

    app = create_app(load_catalogue=False)
    app.dependency_overrides[deps.get_pipeline] = lambda: RecommendationPipeline(
        index=index, embedder=StubEmbedding(dims=8),
        generator=StubGenerationProvider([INTENT_PAYLOAD, RERANK_PAYLOAD]),
        sessions=SessionStore(ttl_seconds=60))
    return TestClient(app)


def test_health_reports_readiness(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_recommend_returns_grouped_results(client):
    r = client.post("/api/recommend", json={"query": "trekking gear for a week"})
    assert r.status_code == 200
    body = r.json()
    assert body["groups"][0]["label"] == "Backpack"
    assert body["groups"][0]["recommendations"][0]["product_id"] == "B0"
    assert body["session_id"]


def test_empty_query_returns_error_envelope(client):
    r = client.post("/api/recommend", json={"query": "   "})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_QUERY"


def test_stream_emits_sse_frames(client):
    with client.stream("POST", "/api/recommend/stream",
                       json={"query": "trekking gear"}) as r:
        assert r.status_code == 200
        body = "".join(r.iter_text())
    assert "event: understood" in body
    assert "event: results" in body
    assert "event: done" in body


# --- Additional tests (not in the plan's Step 1 listing) ------------------
#
# These exercise session persistence across two calls, the exact wire shape of
# SSE frames, and the error envelope produced when every generation provider
# fails.


def _build_index(tmp_path):
    """Same three-product catalogue as the `client` fixture, built fresh so
    each test gets its own tmp_path-backed files."""
    with gzip.open(tmp_path / "c.jsonl.gz", "wt", encoding="utf-8") as f:
        for i in range(3):
            f.write(json.dumps({
                "id": f"B{i}", "title": f"Trekking Backpack {i}",
                "title_original": f"Trekking Backpack {i}", "description": "A rucksack.",
                "category": "Backpacks", "price": 1000.0, "price_tier": "mid",
                "rating": 4.2, "reviews": 50, "quality_score": 16.5, "attributes": {},
                "image_url": "https://x/i.jpg",
                "product_url": f"https://www.amazon.in/dp/B{i}"}) + "\n")
    products = JsonlCatalogue(tmp_path / "c.jsonl.gz").load()
    m = np.eye(3, 8, dtype=np.float32)
    return CatalogueIndex(products, m)


def _client_with_generator(tmp_path, generator: GenerationProvider) -> TestClient:
    app = create_app(load_catalogue=False)
    app.dependency_overrides[deps.get_pipeline] = lambda: RecommendationPipeline(
        index=_build_index(tmp_path), embedder=StubEmbedding(dims=8),
        generator=generator, sessions=SessionStore(ttl_seconds=60))
    return TestClient(app)


def test_recommend_session_round_trip(tmp_path):
    """A second call carrying the first call's session_id gets that same
    session_id echoed back (StubGenerationProvider needs two payloads per
    run: one for intent extraction, one for rerank)."""
    generator = StubGenerationProvider(
        [INTENT_PAYLOAD, RERANK_PAYLOAD, INTENT_PAYLOAD, RERANK_PAYLOAD])
    session_client = _client_with_generator(tmp_path, generator)

    first = session_client.post("/api/recommend",
                                json={"query": "trekking gear for a week"})
    assert first.status_code == 200
    session_id = first.json()["session_id"]
    assert session_id

    second = session_client.post(
        "/api/recommend",
        json={"query": "something warmer too", "session_id": session_id})
    assert second.status_code == 200
    assert second.json()["session_id"] == session_id


_SSE_FRAME = re.compile(r"^event: (?P<event>[a-zA-Z_]+)\ndata: (?P<data>.+)$",
                        re.DOTALL)


def test_stream_frames_are_well_formed_sse(client):
    with client.stream("POST", "/api/recommend/stream",
                       json={"query": "trekking gear"}) as r:
        assert r.status_code == 200
        body = "".join(r.iter_text())

    frames = [f for f in body.split("\n\n") if f]
    assert frames, "expected at least one SSE frame"
    for frame in frames:
        match = _SSE_FRAME.match(frame)
        assert match, f"frame does not match 'event: <name>\\ndata: <json>\\n\\n': {frame!r}"
        json.loads(match.group("data"))


class _RaisingProvider:
    """Stand-in generation provider that always fails, to exercise the
    FallbackChain(primary, None) -> ProviderUnavailable path."""

    name = "always-fails"

    async def generate_json(self, prompt: str, *, request_id: str) -> dict:
        raise RuntimeError("provider exploded")


def test_provider_failure_returns_503_error_envelope(tmp_path):
    generator = FallbackChain(_RaisingProvider(), None)
    failing_client = _client_with_generator(tmp_path, generator)

    r = failing_client.post("/api/recommend", json={"query": "trekking gear"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"


class _RateLimitedProvider:
    """Every key on every provider refused on quota."""

    name = "limited"

    async def generate_json(self, prompt: str, *, request_id: str) -> dict:
        raise RuntimeError("429 rate limit reached for model")


def test_exhausted_rate_limits_return_429_and_are_marked_retryable(tmp_path):
    """A quota pause and a broken provider are different answers: one says come
    back shortly, the other says this is not going to work."""
    generator = FallbackChain(_RateLimitedProvider(), _RateLimitedProvider())
    limited_client = _client_with_generator(tmp_path, generator)

    r = limited_client.post("/api/recommend", json={"query": "trekking gear"})
    assert r.status_code == 429
    body = r.json()["error"]
    assert body["code"] == "RATE_LIMITED"
    assert body["retryable"] is True
