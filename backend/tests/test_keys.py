import httpx
import pytest

from app.config import Settings
from app.core.errors import ProviderUnavailable, RateLimited
from app.providers.generation import (CerebrasGeneration, FallbackChain,
                                      StubGenerationProvider, parse_json_response)
from app.providers.keys import KeyRing, call_with_rotation, is_rate_limited


class _RateLimit(Exception):
    status_code = 429


# --- classification ----------------------------------------------------

@pytest.mark.parametrize("exc", [
    _RateLimit("slow down"),
    RuntimeError("429 Too Many Requests"),
    RuntimeError("RESOURCE_EXHAUSTED: quota exceeded for this project"),
    RuntimeError("Rate limit reached for model"),
])
def test_rate_limits_are_recognised_across_provider_dialects(exc):
    assert is_rate_limited(exc)


@pytest.mark.parametrize("exc", [
    RuntimeError("invalid api key"),
    ValueError("model not found: llama-9"),
    RuntimeError("400 Bad Request: prompt too long"),
])
def test_other_failures_are_not_rate_limits(exc):
    assert not is_rate_limited(exc)


def test_http_429_on_a_response_object_is_recognised():
    request = httpx.Request("POST", "https://example.test")
    response = httpx.Response(429, request=request)
    exc = httpx.HTTPStatusError("rejected", request=request, response=response)
    assert is_rate_limited(exc)


# --- the ring ----------------------------------------------------------

def test_ring_drops_duplicates_and_blanks():
    ring = KeyRing(["a", "  ", "b", "a", ""])
    assert len(ring) == 2, "duplicate keys share one quota, so rotating onto one is pointless"


def test_ring_accepts_a_bare_string():
    assert len(KeyRing("only-one")) == 1


def test_ring_wraps_around():
    ring = KeyRing(["a", "b"])
    assert ring.current == "a"
    ring.rotate()
    assert ring.current == "b"
    ring.rotate()
    assert ring.current == "a"


def test_empty_ring_is_falsy_and_refuses_to_hand_out_a_key():
    ring = KeyRing([])
    assert not ring
    with pytest.raises(RateLimited):
        _ = ring.current


# --- rotation ----------------------------------------------------------

async def test_rotation_moves_to_the_next_key_on_a_rate_limit():
    used: list[str] = []

    async def call(key: str) -> str:
        used.append(key)
        if key == "a":
            raise _RateLimit("limit")
        return "ok"

    result = await call_with_rotation(KeyRing(["a", "b"]), call,
                                      request_id="r", provider="test")
    assert result == "ok"
    assert used == ["a", "b"]


async def test_rotation_stops_once_every_key_is_limited():
    async def call(key: str):
        raise _RateLimit("limit")

    with pytest.raises(RateLimited):
        await call_with_rotation(KeyRing(["a", "b", "c"]), call,
                                 request_id="r", provider="test")


async def test_a_non_rate_limit_error_burns_only_one_key():
    """A bad prompt or revoked credential fails identically on every key.
    Rotating would multiply one error into N and hide the real message."""
    used: list[str] = []

    async def call(key: str):
        used.append(key)
        raise ValueError("model not found")

    with pytest.raises(ValueError):
        await call_with_rotation(KeyRing(["a", "b", "c"]), call,
                                 request_id="r", provider="test")
    assert used == ["a"]


async def test_rotation_resumes_from_where_it_stopped():
    """A key that just hit its limit must not be the first one tried next time."""
    ring = KeyRing(["a", "b"])
    calls: list[str] = []

    async def flaky(key: str):
        calls.append(key)
        if key == "a":
            raise _RateLimit("limit")
        return "ok"

    await call_with_rotation(ring, flaky, request_id="r", provider="test")
    await call_with_rotation(ring, flaky, request_id="r", provider="test")
    assert calls == ["a", "b", "b"]


# --- the chain ---------------------------------------------------------

class _Failing:
    def __init__(self, name: str, exc: Exception) -> None:
        self.name = name
        self.exc = exc
        self.calls = 0

    async def generate_json(self, prompt: str, *, request_id: str) -> dict:
        self.calls += 1
        raise self.exc


async def test_chain_of_three_falls_through_in_order():
    first = _Failing("first", _RateLimit("limit"))
    second = _Failing("second", RuntimeError("boom"))
    third = StubGenerationProvider([{"rescued": True}])

    chain = FallbackChain(first, second, third)
    assert await chain.generate_json("x", request_id="r") == {"rescued": True}
    assert (first.calls, second.calls) == (1, 1)


async def test_chain_reports_rate_limiting_as_429_not_503():
    """`RateLimited` is retryable and `ProviderUnavailable` is not - a client
    can act on that difference, so the distinction must survive the chain."""
    chain = FallbackChain(_Failing("a", _RateLimit("limit")),
                          _Failing("b", _RateLimit("limit")))
    with pytest.raises(RateLimited) as excinfo:
        await chain.generate_json("x", request_id="r")
    assert excinfo.value.retryable is True


async def test_one_hard_failure_makes_the_whole_chain_unavailable():
    chain = FallbackChain(_Failing("a", _RateLimit("limit")),
                          _Failing("b", RuntimeError("bad request")))
    with pytest.raises(ProviderUnavailable):
        await chain.generate_json("x", request_id="r")


def test_chain_needs_at_least_one_provider():
    with pytest.raises(ValueError):
        FallbackChain(None)


# --- tolerant JSON -----------------------------------------------------

def test_parses_plain_json():
    assert parse_json_response('{"a": 1}') == {"a": 1}


def test_parses_fenced_json():
    assert parse_json_response('```json\n{"a": 1}\n```') == {"a": 1}


def test_parses_json_with_a_preamble():
    assert parse_json_response('Sure, here you go:\n{"a": 1}') == {"a": 1}


def test_unparseable_text_still_raises():
    with pytest.raises(ValueError):
        parse_json_response("no json here at all")


# --- cerebras ----------------------------------------------------------

async def test_cerebras_posts_openai_shaped_request_and_rotates(monkeypatch):
    seen: list[tuple[str, dict]] = []

    class _Client:
        def __init__(self, *a, **kw) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a) -> None:
            return None

        async def post(self, url, headers, json):
            seen.append((headers["Authorization"], json))
            request = httpx.Request("POST", url)
            if headers["Authorization"].endswith("key1"):
                return httpx.Response(429, request=request, json={"error": "limit"})
            return httpx.Response(200, request=request, json={
                "choices": [{"message": {"content": '{"groups": []}'}}]})

    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    provider = CerebrasGeneration(["key1", "key2"], model="llama-3.3-70b")
    assert await provider.generate_json("prompt", request_id="r") == {"groups": []}

    assert [auth for auth, _ in seen] == ["Bearer key1", "Bearer key2"]
    _, body = seen[-1]
    assert body["model"] == "llama-3.3-70b"
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"] == [{"role": "user", "content": "prompt"}]


# --- settings ----------------------------------------------------------

def test_keys_for_merges_singular_and_plural(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "one")
    monkeypatch.setenv("GEMINI_API_KEYS", "two, three")
    assert Settings().keys_for("gemini") == ["one", "two", "three"]


def test_generation_chain_overrides_primary_and_fallback(monkeypatch):
    monkeypatch.setenv("GENERATION_CHAIN", "gemini,cerebras,groq")
    assert Settings().generation_order() == ["gemini", "cerebras", "groq"]


def test_legacy_primary_and_fallback_still_work():
    settings = Settings(_env_file=None)
    assert settings.generation_order() == ["gemini", "groq"]
