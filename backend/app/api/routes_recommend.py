import json
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import get_pipeline
from app.core.errors import AppError, Internal
from app.services.pipeline import RecommendationPipeline, collect

router = APIRouter(prefix="/api")


class RecommendRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.post("/recommend")
async def recommend(body: RecommendRequest,
                    pipeline: RecommendationPipeline = Depends(get_pipeline)):
    request_id = uuid.uuid4().hex[:12]
    events = [e async for e in pipeline.run(body.query, body.session_id,
                                            request_id=request_id)]

    error = next((e for e in events if e.event == "error"), None)
    if error is not None:
        code = error.data["error"]["code"]
        status = {"INVALID_QUERY": 400, "RATE_LIMITED": 429,
                  "PROVIDER_UNAVAILABLE": 503}.get(code, 500)
        return JSONResponse(status_code=status, content=error.data)

    return collect(events).model_dump()


@router.post("/recommend/stream")
async def recommend_stream(body: RecommendRequest,
                           pipeline: RecommendationPipeline = Depends(get_pipeline)):
    """SSE frames over POST.

    Native EventSource is GET-only, and the request body carries a
    natural-language query plus session state - putting that in query parameters
    hits URL length limits and writes user queries into access logs. The client
    uses fetch + ReadableStream instead (spec 7.1).
    """
    request_id = uuid.uuid4().hex[:12]

    async def frames():
        async for event in pipeline.run(body.query, body.session_id,
                                        request_id=request_id):
            payload = json.dumps(event.data, ensure_ascii=False)
            yield f"event: {event.event}\ndata: {payload}\n\n"

    return StreamingResponse(frames(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # stops nginx/proxies buffering the stream
    })
