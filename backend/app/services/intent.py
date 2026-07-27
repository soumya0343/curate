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
- sub_needs: return [] when the customer is only narrowing a filter (budget,
  gender, size, style preference) for categories already established earlier
  in the conversation - the app keeps the existing categories automatically.
  Only return sub_needs when the customer is asking for a genuinely NEW
  category of item not already covered (e.g. "I need other trek items also").
- For a FIRST-time request, sub_needs must never be empty as long as there is
  ANY shopping context to work from (a destination, activity, or occasion) -
  even if no item type was named. Infer one broad best-guess category (e.g.
  "i'm going to Manali" -> {{"label": "Travel Essentials", "query": "travel
  essentials for a Manali trip"}}) and ask what they actually need via
  clarifying_questions. Only return [] if the request gives NOTHING to search
  for at all (no destination, activity, or occasion of any kind).
"""

PRIOR_BLOCK = """
This is a follow-up conversation. The customer request above is the full
exchange so far, oldest message first.

The customer's previously extracted intent was:
{prior}

The categories already being searched are:
{prior_sub_needs}

For the "intent" object only, return ONLY the fields that CHANGE. Omit or null
everything else - prior context is preserved automatically. Leave "sub_needs"
as [] unless this message asks for a category not in the list above.
"""


GENDER_ALIASES = {
    "men": "men", "man": "men", "male": "men", "mens": "men",
    "women": "women", "woman": "women", "female": "women", "womens": "women",
    "unisex": "unisex", "any": "unisex", "both": "unisex",
}

GENDER_CLARIFYING_QUESTION = "Who is this for — men, women, or unisex?"


def _normalize_intent_payload(raw: dict) -> dict:
    """Coerce provider quirks (e.g. "male" instead of "men") rather than letting
    an out-of-enum value raise and 500 the whole turn."""
    raw = dict(raw)
    gender = raw.get("gender")
    if gender is not None:
        raw["gender"] = GENDER_ALIASES.get(str(gender).strip().lower())
    return raw


def parse_intent_payload(payload: dict, *, allow_empty_sub_needs: bool = False) -> IntentResult:
    """Parse provider output tolerantly; drop malformed parts rather than failing."""
    intent = ShoppingIntent.model_validate(_normalize_intent_payload(payload.get("intent") or {}))

    sub_needs: list[SubNeed] = []
    for raw in payload.get("sub_needs") or []:
        if isinstance(raw, dict) and raw.get("label") and raw.get("query"):
            sub_needs.append(SubNeed(label=str(raw["label"]), query=str(raw["query"])))

    if not sub_needs and not allow_empty_sub_needs:
        raise InvalidQuery(
            "Could not work out what you're shopping for. Try describing the "
            "occasion or the kind of items you need.")

    assumptions: list[Assumption] = []
    for raw in payload.get("assumptions") or []:
        if not isinstance(raw, dict) or not raw.get("field"):
            continue
        value = raw.get("value")
        if isinstance(value, bool) or value is None:
            continue  # not a displayable value - the model emitted a stray flag
        value = str(value).strip()
        if not value:
            continue
        assumptions.append(Assumption(
            field=str(raw["field"]), value=value,
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
                  prior: ShoppingIntent | None, *, request_id: str,
                  prior_sub_needs: list[SubNeed] | None = None) -> IntentResult:
    """Extract intent, merging onto prior intent when this is a follow-up.

    A follow-up that only narrows a filter ("i'm a girl and my budget is 5k")
    returns no sub_needs of its own - the categories from prior_sub_needs carry
    forward unchanged, so a filter-only turn can't relabel or misclassify a
    category the model already got right.
    """
    if not query or not query.strip():
        raise InvalidQuery("Tell me what you're shopping for.")

    prior_block = ""
    if prior is not None:
        stated = {k: v for k, v in prior.model_dump().items() if v is not None}
        if stated:
            prior_block = PRIOR_BLOCK.format(
                prior=stated,
                prior_sub_needs=[s.label for s in prior_sub_needs or []])

    payload = await provider.generate_json(
        INTENT_PROMPT.format(query=query.strip(), prior_block=prior_block),
        request_id=request_id)

    result = parse_intent_payload(payload, allow_empty_sub_needs=prior is not None)
    if prior is not None:
        result.intent = prior.merge(result.intent)
        if not result.sub_needs:
            result.sub_needs = prior_sub_needs or []

    # Gender left unstated must never silently skew toward whichever gender the
    # catalogue or embeddings happen to rank higher - default to unisex (which
    # the retrieval filter treats as "exclude men-only/women-only verified
    # items") and ask, rather than showing one gender's products by accident.
    if result.intent.gender is None:
        result.intent.gender = "unisex"
        result.assumptions.append(Assumption(
            field="gender", value="unisex",
            reason="not stated - defaulting to unisex rather than skewing toward one gender",
            confidence="low"))
        if GENDER_CLARIFYING_QUESTION not in result.clarifying_questions:
            result.clarifying_questions = (
                result.clarifying_questions + [GENDER_CLARIFYING_QUESTION])[:3]

    return result
