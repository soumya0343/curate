"""Process-local session store.

An in-memory TTL dict only works with a single worker: with several, a session
created on worker A is missing on worker B. The deployment therefore runs
--workers 1, and that constraint is documented rather than discovered
(spec 6). Redis is the production path.
"""
import time
import uuid
from dataclasses import dataclass, field

from app.schemas.intent import ShoppingIntent, SubNeed


@dataclass
class SessionState:
    intent: ShoppingIntent
    # Every query and follow-up answer typed so far, oldest first. A lone
    # follow-up like "total budget is 10k" carries almost no signal for what
    # sub-needs to search - the model needs the whole conversation, not just
    # the newest fragment, or it invents categories from nothing (spec 5).
    history: list[str] = field(default_factory=list)
    # The categories settled on so far. A filter-only follow-up ("i'm a girl
    # and my budget is 5k") re-derives sub_needs from scratch every turn if
    # this isn't kept, and the model can relabel or misclassify a category it
    # already got right (e.g. backpacks sliding into "Trekking Clothing").
    sub_needs: list[SubNeed] = field(default_factory=list)
    # Consecutive turns where the clarity gate fired without retrieval running.
    # Capped at 2 — on the third unclear turn we force generation anyway so the
    # user can never get stuck in an infinite question loop.
    stalled_turns: int = 0


class SessionStore:
    def __init__(self, ttl_seconds: int = 1800) -> None:
        self._ttl = ttl_seconds
        self._data: dict[str, tuple[float, SessionState]] = {}

    def new_id(self) -> str:
        return uuid.uuid4().hex

    def put(self, session_id: str, intent: ShoppingIntent,
            history: list[str] | None = None,
            sub_needs: list[SubNeed] | None = None,
            stalled_turns: int = 0) -> None:
        self._data[session_id] = (
            time.monotonic(),
            SessionState(intent=intent, history=history or [], sub_needs=sub_needs or [],
                         stalled_turns=stalled_turns))

    def get(self, session_id: str) -> SessionState | None:
        entry = self._data.get(session_id)
        if entry is None:
            return None
        stored_at, state = entry
        if time.monotonic() - stored_at > self._ttl:
            self._data.pop(session_id, None)
            return None
        return state
