"""Key rotation for rate-limited providers.

Free tiers are the constraint this project actually runs into: Gemini and Groq
both cut off well before the work is done, and an offline enrichment pass over
20k products will hit a limit several times. Holding several keys per provider
and advancing on a 429 turns a hard stop into a pause.

TWO RULES, both load-bearing:

1. **Rotate only on rate limits.** A malformed prompt, a bad model name, or a
   revoked key fails identically on every key in the ring. Rotating through
   them would multiply one error into N, bury the real message, and burn every
   key's quota discovering the same thing. Anything that is not a rate limit is
   re-raised on the first attempt.

2. **Rotation is not fallback.** A different key is the same model in the same
   vector space; a different provider is not. That distinction is why key
   rotation is safe for embeddings - where `EmbeddingProvider` must never fall
   back - and provider chaining is not (spec 3.1).
"""
import re
from typing import Awaitable, Callable, Sequence, TypeVar

from app.core.errors import RateLimited
from app.core.logging import log_stage

T = TypeVar("T")

_RATE_LIMIT_TEXT = re.compile(
    r"rate.?limit|quota|resource.?exhausted|too many requests|\b429\b", re.I)


def is_rate_limited(exc: Exception) -> bool:
    """True when an exception looks like a quota or rate-limit refusal.

    Providers disagree on how they say this: an HTTP status on the response, a
    `status_code` attribute, a `code`, or nothing but the message. Checking all
    of them is less brittle than matching on each SDK's exception classes,
    which would also make the SDKs a hard import here.
    """
    for attr in ("status_code", "code", "status"):
        value = getattr(exc, attr, None)
        if value == 429 or str(value) == "429":
            return True

    response = getattr(exc, "response", None)
    if getattr(response, "status_code", None) == 429:
        return True

    return bool(_RATE_LIMIT_TEXT.search(str(exc)))


class KeyRing:
    """An ordered set of interchangeable API keys for one provider."""

    def __init__(self, keys: str | Sequence[str] | None) -> None:
        if keys is None:
            keys = []
        if isinstance(keys, str):
            # A comma in a single credential is always several credentials:
            # no provider issues keys containing one, and putting a list in
            # GEMINI_API_KEY rather than GEMINI_API_KEYS is the obvious thing
            # to do. Treating it as one opaque key sends the whole blob as a
            # bearer token and 401s on every provider at once.
            keys = [keys]
        keys = [part for key in keys for part in str(key).split(",")]

        seen: set[str] = set()
        self._keys: list[str] = []
        for key in keys:
            key = (key or "").strip()
            # Duplicates share a quota, so a ring holding the same key twice
            # would "rotate" onto the limit it just hit.
            if key and key not in seen:
                seen.add(key)
                self._keys.append(key)
        self._index = 0

    def __len__(self) -> int:
        return len(self._keys)

    def __bool__(self) -> bool:
        return bool(self._keys)

    @property
    def current(self) -> str:
        if not self._keys:
            raise RateLimited("no API key configured for this provider")
        return self._keys[self._index]

    def rotate(self) -> None:
        """Advance to the next key, wrapping. Keeps the position across calls so
        a key that just hit its limit is not immediately retried."""
        if self._keys:
            self._index = (self._index + 1) % len(self._keys)


async def call_with_rotation(ring: KeyRing, call: Callable[[str], Awaitable[T]], *,
                             request_id: str, provider: str) -> T:
    """Run `call` with each key in turn, advancing only on rate limits.

    Raises `RateLimited` once every key in the ring has refused - which is the
    signal a provider chain uses to move on, and which the API surfaces as 429
    with `retryable: true` rather than a generic failure.
    """
    if not ring:
        raise RateLimited(f"no API key configured for {provider}")

    last: Exception | None = None
    for attempt in range(len(ring)):
        try:
            return await call(ring.current)
        except Exception as exc:  # noqa: BLE001 - classified immediately below
            if not is_rate_limited(exc):
                raise
            last = exc
            log_stage(request_id, "key_rotation", provider=provider,
                      key_index=attempt, keys=len(ring), error=str(exc)[:160])
            ring.rotate()

    raise RateLimited(
        f"all {len(ring)} {provider} key(s) are rate limited: {str(last)[:200]}")
