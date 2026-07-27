from typing import Any, Literal

from pydantic import BaseModel

from app.schemas.intent import Assumption, ShoppingIntent
from app.schemas.product import Product


class Candidate(BaseModel):
    product: Product
    similarity: float
    sub_need: str
    score: float = 0.0


class Recommendation(BaseModel):
    product_id: str
    title: str
    price: float
    price_tier: str
    rating: float
    reviews: int
    image_url: str
    product_url: str
    reason: str


class ResultGroup(BaseModel):
    label: str
    recommendations: list[Recommendation] = []
    empty_reason: str | None = None
    fallback_note: str | None = None


class RecommendResponse(BaseModel):
    session_id: str
    intent: ShoppingIntent
    assumptions: list[Assumption] = []
    clarifying_questions: list[str] = []
    groups: list[ResultGroup] = []
    relaxations: list[str] = []
    timings_ms: dict[str, float] = {}
    awaiting_clarification: bool = False


class StreamEvent(BaseModel):
    event: Literal["understood", "searching", "results", "done", "error"]
    data: dict[str, Any]
