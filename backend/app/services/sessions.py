"""Process-local session store.

An in-memory TTL dict only works with a single worker: with several, a session
created on worker A is missing on worker B. The deployment therefore runs
--workers 1, and that constraint is documented rather than discovered
(spec 6). Redis is the production path.
"""
import time
import uuid

from app.schemas.intent import ShoppingIntent


class SessionStore:
    def __init__(self, ttl_seconds: int = 1800) -> None:
        self._ttl = ttl_seconds
        self._data: dict[str, tuple[float, ShoppingIntent]] = {}

    def new_id(self) -> str:
        return uuid.uuid4().hex

    def put(self, session_id: str, intent: ShoppingIntent) -> None:
        self._data[session_id] = (time.monotonic(), intent)

    def get(self, session_id: str) -> ShoppingIntent | None:
        entry = self._data.get(session_id)
        if entry is None:
            return None
        stored_at, intent = entry
        if time.monotonic() - stored_at > self._ttl:
            self._data.pop(session_id, None)
            return None
        return intent
