"""The orchestrator: one async generator, two transports.

The streaming route forwards these events; the JSON route drains them via
collect(). Keeping both on one implementation means streaming can be cut under
time pressure without touching the core (spec 5).
"""
import time
from typing import AsyncIterator

from app.catalogue.index import CatalogueIndex
from app.core.errors import AppError, Internal
from app.core.logging import log_stage
from app.providers.embedding import EmbeddingProvider
from app.providers.generation import GenerationProvider
from app.schemas.response import RecommendResponse, ResultGroup, StreamEvent
from app.services import intent as intent_service
from app.services import ranking, retrieval, scoring
from app.services.sessions import SessionStore

RETRIEVE_TOP_K = 8
PRERANK_PER_SUB_NEED = 5


class RecommendationPipeline:
    def __init__(self, index: CatalogueIndex, embedder: EmbeddingProvider,
                 generator: GenerationProvider, sessions: SessionStore) -> None:
        self.index = index
        self.embedder = embedder
        self.generator = generator
        self.sessions = sessions

    async def run(self, query: str, session_id: str | None, *,
                  request_id: str) -> AsyncIterator[StreamEvent]:
        started = time.perf_counter()
        timings: dict[str, float] = {}
        sid = session_id or self.sessions.new_id()

        try:
            # Stage 1 - understand
            t0 = time.perf_counter()
            prior_state = self.sessions.get(sid) if session_id else None
            prior_intent = prior_state.intent if prior_state else None
            prior_sub_needs = prior_state.sub_needs if prior_state else None
            history = prior_state.history if prior_state else []
            # A follow-up like "total budget is 10k" is meaningless on its own -
            # sub-need decomposition needs the full conversation so it doesn't
            # invent unrelated categories from an isolated fragment.
            conversation = "\n".join([*history, query])
            result = await intent_service.extract(
                self.generator, conversation, prior_intent, request_id=request_id,
                prior_sub_needs=prior_sub_needs)

            # Clarity gate: skip retrieval when the request is too vague.
            # Two signals (either fires the gate):
            #   - confidence < 0.4  (LLM self-reported; weak on smaller models)
            #   - >= 2 LLM-generated clarifying questions (deterministic backstop)
            # We count questions BEFORE the gender injection that intent.extract()
            # may append — that structural question is not a vagueness signal.
            # Loop protection: stalled_turns tracks consecutive gated turns.
            # After 2 stalls we force generation regardless so the user never
            # gets stuck answering questions forever.
            stalled = prior_state.stalled_turns if prior_state else 0
            llm_question_count = len(result.clarifying_questions) - (
                1 if intent_service.GENDER_CLARIFYING_QUESTION in result.clarifying_questions else 0
            )
            # If the user is responding to a gated turn (stalled > 0), don't
            # re-gate on question count alone — they're actively answering.
            # Only confidence < 0.4 can gate a response-to-gate turn.
            if stalled > 0:
                too_vague = result.confidence < 0.4 and stalled < 2
            else:
                too_vague = (
                    result.confidence < 0.4 or llm_question_count >= 2
                ) and stalled < 2

            if too_vague:
                new_stalled = stalled + 1
            else:
                new_stalled = 0

            self.sessions.put(sid, result.intent, [*history, query], result.sub_needs,
                              stalled_turns=new_stalled)
            timings["intent"] = (time.perf_counter() - t0) * 1000
            log_stage(request_id, "intent", duration_ms=timings["intent"],
                      sub_needs=len(result.sub_needs),
                      awaiting_clarification=too_vague)

            yield StreamEvent(event="understood", data={
                "session_id": sid,
                "intent": result.intent.model_dump(),
                "assumptions": [a.model_dump() for a in result.assumptions],
                "sub_needs": [s.label for s in result.sub_needs],
                "clarifying_questions": result.clarifying_questions,
                "awaiting_clarification": too_vague,
            })

            if too_vague:
                timings["total"] = (time.perf_counter() - started) * 1000
                yield StreamEvent(event="done", data={"timings_ms": timings})
                return

            # Stage 2 + 3 - filter, then retrieve per sub-need
            t0 = time.perf_counter()
            rows, relaxations = retrieval.filter_rows(self.index, result.intent)
            candidates = await retrieval.retrieve(
                self.index, self.embedder, result.sub_needs, rows, RETRIEVE_TOP_K)
            timings["retrieval"] = (time.perf_counter() - t0) * 1000
            log_stage(request_id, "retrieval", duration_ms=timings["retrieval"],
                      pool=len(rows), candidates=len(candidates))

            yield StreamEvent(event="searching", data={
                "candidates": len(candidates), "pool": len(rows),
                "relaxations": relaxations,
            })

            # Stage 4 - deterministic pre-ranking
            t0 = time.perf_counter()
            shortlist = scoring.prerank(candidates, result.intent, PRERANK_PER_SUB_NEED)
            timings["prerank"] = (time.perf_counter() - t0) * 1000

            # Stage 5 - LLM rerank and explain
            t0 = time.perf_counter()
            groups = await ranking.rerank(
                self.generator, shortlist, result.intent, result.sub_needs,
                request_id=request_id)
            timings["rerank"] = (time.perf_counter() - t0) * 1000
            log_stage(request_id, "rerank", duration_ms=timings["rerank"],
                      shortlist=len(shortlist),
                      filled=sum(1 for g in groups if g.recommendations))

            yield StreamEvent(event="results", data={
                "groups": [g.model_dump() for g in groups],
                "relaxations": relaxations,
            })

            timings["total"] = (time.perf_counter() - started) * 1000
            yield StreamEvent(event="done", data={"timings_ms": timings})

        except AppError as exc:
            log_stage(request_id, "error", code=exc.code, message=exc.message)
            yield StreamEvent(event="error", data=exc.envelope())
        except Exception as exc:  # noqa: BLE001 - never leak a traceback to the client
            log_stage(request_id, "error", code="INTERNAL", message=str(exc)[:200])
            yield StreamEvent(event="error",
                              data=Internal("Something went wrong.").envelope())


def collect(events: list[StreamEvent]) -> RecommendResponse:
    """Drain pipeline events into a single JSON response."""
    by_event = {e.event: e.data for e in events}

    if "error" in by_event and "results" not in by_event:
        raise Internal(by_event["error"]["error"]["message"])

    understood = by_event.get("understood", {})
    results = by_event.get("results", {})
    return RecommendResponse(
        session_id=understood.get("session_id", ""),
        intent=understood.get("intent") or {},
        assumptions=understood.get("assumptions") or [],
        clarifying_questions=understood.get("clarifying_questions") or [],
        groups=[ResultGroup.model_validate(g) for g in results.get("groups", [])],
        relaxations=results.get("relaxations", []),
        timings_ms=by_event.get("done", {}).get("timings_ms", {}),
        awaiting_clarification=understood.get("awaiting_clarification", False),
    )
