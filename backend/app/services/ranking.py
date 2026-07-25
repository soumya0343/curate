"""Stage 5: LLM chooses final picks per group and explains each one.

Three guards make this safe: every returned product_id is validated against the
candidate pool, explanations may only cite grounded facts, and groups with no
good match are reported rather than hidden (spec 5, Stage 5).
"""
import json

from app.providers.generation import GenerationProvider
from app.schemas.intent import ShoppingIntent, SubNeed
from app.schemas.response import Candidate, Recommendation, ResultGroup

MAX_PICKS_PER_GROUP = 5
EMPTY_REASON = "No suitable match found in the catalogue for this need."

RERANK_PROMPT = """You are a shopping assistant choosing final recommendations.

Customer intent:
{intent}

Groups to fill:
{groups}

Candidate products (you may ONLY choose from these ids):
{candidates}

For each group, choose the 3-5 best candidates and write one sentence explaining
why each suits this customer.

Return ONLY JSON:
{{"groups": [{{"label": "exact group label", "picks": [
   {{"product_id": "id from the list above", "reason": "one sentence"}}]}}]}}

RULES:
- Use ONLY product ids from the candidate list. Never invent one.
- Facts marked "verified" may be stated as fact. Everything else is a judgement -
  phrase it as suitability ("suited to cold-weather trekking"), never as a
  specification ("rated to -12C").
- Never state a weight, temperature rating, or dimension unless it appears in the
  product title.
- If a group has no good candidate, return it with an empty picks list. An honest
  empty group is better than a bad recommendation.
"""


def _candidate_line(c: Candidate) -> str:
    verified = {k: a.value for k, a in c.product.attributes.items()
                if a.source == "title_verified" and a.value is not None}
    parts = [f"id={c.product.id}", f"group={c.sub_need}", f"title={c.product.title}",
             f"price=Rs{c.product.price:.0f}", f"tier={c.product.price_tier}",
             f"rating={c.product.rating}({c.product.reviews})"]
    if verified:
        parts.append(f"verified={json.dumps(verified, ensure_ascii=False)}")
    return " | ".join(parts)


def build_groups(payload: dict, candidates: list[Candidate],
                 sub_needs: list[SubNeed]) -> list[ResultGroup]:
    """Assemble groups, validating every id against the candidate pool.

    Every sub-need appears in the output in its original order, whether or not the
    model returned picks for it - empty groups are reported, not hidden.
    """
    by_id = {c.product.id: c.product for c in candidates}
    picks_by_label: dict[str, list[dict]] = {}
    for raw in payload.get("groups") or []:
        if isinstance(raw, dict) and raw.get("label"):
            picks_by_label[str(raw["label"])] = raw.get("picks") or []

    groups: list[ResultGroup] = []
    for sub_need in sub_needs:
        recommendations: list[Recommendation] = []
        for pick in picks_by_label.get(sub_need.label, []):
            if not isinstance(pick, dict):
                continue
            product = by_id.get(str(pick.get("product_id")))
            if product is None:
                continue  # hallucinated id - dropped
            recommendations.append(Recommendation(
                product_id=product.id, title=product.title, price=product.price,
                price_tier=product.price_tier, rating=product.rating,
                reviews=product.reviews, image_url=product.image_url,
                product_url=product.product_url,
                reason=str(pick.get("reason") or "").strip()))
            if len(recommendations) >= MAX_PICKS_PER_GROUP:
                break

        groups.append(ResultGroup(
            label=sub_need.label, recommendations=recommendations,
            empty_reason=None if recommendations else EMPTY_REASON))
    return groups


async def rerank(provider: GenerationProvider, candidates: list[Candidate],
                 intent: ShoppingIntent, sub_needs: list[SubNeed], *,
                 request_id: str) -> list[ResultGroup]:
    if not candidates:
        return [ResultGroup(label=s.label, recommendations=[], empty_reason=EMPTY_REASON)
                for s in sub_needs]

    stated = {k: v for k, v in intent.model_dump().items() if v is not None}
    payload = await provider.generate_json(
        RERANK_PROMPT.format(
            intent=json.dumps(stated, ensure_ascii=False),
            groups="\n".join(f"- {s.label}: {s.query}" for s in sub_needs),
            candidates="\n".join(_candidate_line(c) for c in candidates),
        ), request_id=request_id)

    return build_groups(payload, candidates, sub_needs)
