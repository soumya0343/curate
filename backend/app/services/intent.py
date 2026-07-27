"""Stage 1: turn a natural-language request into structured intent and sub-needs.

Sub-need decomposition is the core AI decision. A single vector for the whole
request is a blurry average - "trekking essentials and clothing" would skew
toward whatever the catalogue holds most of, and a sleeping bag would never
enter the candidate pool. Searching per sub-need retrieves each need on its own
terms, and result groups derive from the request rather than being invented
afterwards (spec 5, Stage 1).
"""
from app.core.errors import InvalidQuery
from app.providers.generation import GenerationProvider
from app.schemas.intent import Assumption, IntentResult, ShoppingIntent, SubNeed

INTENT_PROMPT = """You are a shopping assistant interpreting a customer request.

Customer request:
{query}
{prior_block}
Break the request into distinct shopping sub-needs. Each sub-need becomes its own
product search and its own group of results, so make them specific and disjoint.
A simple request may have only one sub-need.

Return ONLY JSON:
{{
  "intent": {{
    "activity": string or null,
    "destination": string or null,
    "season": string or null,
    "duration_days": integer or null,
    "budget_max": number or null,
    "gender": "men" | "women" | "unisex" | null,
    "occasion": string or null
  }},
  "sub_needs": [{{"label": "Short group heading", "query": "search phrase describing the item"}}],
  "assumptions": [{{"field": "...", "value": "...", "reason": "...", "confidence": "low"|"medium"|"high"}}],
  "clarifying_questions": ["question 1", "question 2", ...],
  "confidence": 0.0-1.0
}}

RULES:
- budget_max: set ONLY if the customer stated a budget. Never guess one.
- gender: set ONLY if the customer stated who this is for.
- Do NOT assert facts you cannot verify. You have no weather, geography, or
  altitude data. Write "cold-weather conditions likely" with confidence
  "medium", never "sub-zero nights at 4,200 m".
- Every judgement you made that the customer did not state belongs in
  "assumptions", so it can be shown and edited.
- clarifying_questions: 0 to 3 questions, only for details that are genuinely
  unguessable (for example a gifting budget, which could be Rs 2,000 or
  Rs 50,000). Empty list if nothing needs asking. Results are always returned
  alongside them, so never treat these as blocking.
"""

PRIOR_BLOCK = """
This is a follow-up. The customer's existing request was:
{prior}

Return ONLY the fields that CHANGE. Omit or null everything else - prior context
is preserved automatically.
"""


def parse_intent_payload(payload: dict) -> IntentResult:
    """Parse provider output tolerantly; drop malformed parts rather than failing."""
    intent = ShoppingIntent.model_validate(payload.get("intent") or {})

    sub_needs: list[SubNeed] = []
    for raw in payload.get("sub_needs") or []:
        if isinstance(raw, dict) and raw.get("label") and raw.get("query"):
            sub_needs.append(SubNeed(label=str(raw["label"]), query=str(raw["query"])))

    if not sub_needs:
        raise InvalidQuery(
            "Could not work out what you're shopping for. Try describing the "
            "occasion or the kind of items you need.")

    assumptions: list[Assumption] = []
    for raw in payload.get("assumptions") or []:
        if not isinstance(raw, dict) or not raw.get("field"):
            continue
        assumptions.append(Assumption(
            field=str(raw["field"]), value=str(raw.get("value", "")),
            reason=str(raw.get("reason", "")),
            confidence=raw.get("confidence") if raw.get("confidence") in
            ("low", "medium", "high") else "medium"))

    clarifying_questions = [
        str(q).strip() for q in (payload.get("clarifying_questions") or [])
        if str(q).strip()
    ][:3]

    return IntentResult(
        intent=intent, sub_needs=sub_needs, assumptions=assumptions,
        clarifying_questions=clarifying_questions,
        confidence=float(payload.get("confidence") or 0.5),
    )


async def extract(provider: GenerationProvider, query: str,
                  prior: ShoppingIntent | None, *, request_id: str) -> IntentResult:
    """Extract intent, merging onto prior intent when this is a follow-up."""
    if not query or not query.strip():
        raise InvalidQuery("Tell me what you're shopping for.")

    prior_block = ""
    if prior is not None:
        stated = {k: v for k, v in prior.model_dump().items() if v is not None}
        if stated:
            prior_block = PRIOR_BLOCK.format(prior=stated)

    payload = await provider.generate_json(
        INTENT_PROMPT.format(query=query.strip(), prior_block=prior_block),
        request_id=request_id)

    result = parse_intent_payload(payload)
    if prior is not None:
        result.intent = prior.merge(result.intent)
    return result
