import numpy as np
import pytest

from app.core.errors import ProviderUnavailable
from app.providers.embedding import StubEmbedding
from app.providers.generation import FallbackChain, StubGenerationProvider


class _Failing:
    name = "failing"

    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls = 0

    async def generate_json(self, prompt: str, *, request_id: str) -> dict:
        self.calls += 1
        raise self.exc


async def test_stub_returns_queued_responses_in_order():
    stub = StubGenerationProvider([{"a": 1}, {"b": 2}])
    assert await stub.generate_json("x", request_id="r") == {"a": 1}
    assert await stub.generate_json("x", request_id="r") == {"b": 2}


async def test_chain_uses_primary_when_it_works():
    primary = StubGenerationProvider([{"ok": True}])
    fallback = _Failing(RuntimeError("should not be called"))
    chain = FallbackChain(primary, fallback)
    assert await chain.generate_json("x", request_id="r") == {"ok": True}
    assert fallback.calls == 0


async def test_chain_falls_back_once_on_primary_failure():
    primary = _Failing(RuntimeError("429"))
    fallback = StubGenerationProvider([{"rescued": True}])
    chain = FallbackChain(primary, fallback)
    assert await chain.generate_json("x", request_id="r") == {"rescued": True}
    assert primary.calls == 1


async def test_chain_raises_provider_unavailable_when_both_fail():
    chain = FallbackChain(_Failing(RuntimeError("a")), _Failing(RuntimeError("b")))
    with pytest.raises(ProviderUnavailable):
        await chain.generate_json("x", request_id="r")


async def test_chain_with_no_fallback_raises_immediately():
    chain = FallbackChain(_Failing(RuntimeError("a")), None)
    with pytest.raises(ProviderUnavailable):
        await chain.generate_json("x", request_id="r")


async def test_stub_embedding_is_deterministic_and_normalised():
    emb = StubEmbedding(dims=8)
    a = await emb.embed(["trekking backpack"])
    b = await emb.embed(["trekking backpack"])
    assert np.allclose(a, b)
    assert np.isclose(np.linalg.norm(a[0]), 1.0)


async def test_stub_embedding_differs_across_texts():
    emb = StubEmbedding(dims=8)
    out = await emb.embed(["trekking backpack", "wedding sherwani"])
    assert not np.allclose(out[0], out[1])


def test_no_embedding_fallback_chain_exists():
    import app.providers.embedding as m
    assert not hasattr(m, "FallbackChain"), (
        "embedding providers must never fall back — a silent vector-space "
        "swap produces noise with no error (spec 3.1)")
