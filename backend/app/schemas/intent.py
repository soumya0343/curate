from typing import Literal

from pydantic import BaseModel, Field


class SubNeed(BaseModel):
    label: str
    query: str


class Assumption(BaseModel):
    field: str
    value: str
    reason: str
    confidence: Literal["low", "medium", "high"] = "medium"
    editable: bool = True


class ShoppingIntent(BaseModel):
    activity: str | None = None
    destination: str | None = None
    season: str | None = None
    duration_days: int | None = None
    budget_max: float | None = None
    gender: Literal["men", "women", "unisex"] | None = None
    occasion: str | None = None

    def merge(self, delta: "ShoppingIntent") -> "ShoppingIntent":
        """Apply a follow-up delta without losing prior context.

        "make it cheaper" sets budget_max and must leave everything else intact,
        so only non-None fields from the delta overwrite.
        """
        merged = self.model_dump()
        for key, value in delta.model_dump().items():
            if value is not None:
                merged[key] = value
        return ShoppingIntent(**merged)


class IntentResult(BaseModel):
    intent: ShoppingIntent = Field(default_factory=ShoppingIntent)
    sub_needs: list[SubNeed] = []
    assumptions: list[Assumption] = []
    clarifying_questions: list[str] = []
    confidence: float = 0.5
