"""Deterministic pre-ranking between vector retrieval and LLM reranking.

Purpose: make the LLM the final semantic judge rather than the entire ranker, and
cut the rerank prompt from 8 candidates per sub-need to 4-5.

Weights are deliberately conservative. Similarity dominates; everything else is a
small bounded adjustment. Without relevance judgements to fit against, tuned
coefficients would be guesses that silently distort ranking and are harder to
debug than plain similarity ordering (spec 5, Stage 4).
"""
from app.core.text import variant_key
from app.schemas.intent import ShoppingIntent
from app.schemas.response import Candidate

WEIGHTS = {
    "quality": 0.10,
    "verified_attr": 0.08,
    "inferred_attr": 0.04,
    "duplicate_penalty": 0.15,
}


def _intent_terms(intent: ShoppingIntent) -> set[str]:
    terms = {intent.activity, intent.occasion, intent.season}
    return {t.lower() for t in terms if t}


def _attribute_matches(candidate: Candidate, terms: set[str]) -> tuple[int, int]:
    """Count how many intent terms appear in verified vs inferred attributes."""
    verified = inferred = 0
    for name in ("use_case", "occasion", "season", "product_type"):
        attr = candidate.product.attr(name)
        if attr is None or attr.value in (None, []):
            continue
        values = attr.value if isinstance(attr.value, list) else [attr.value]
        hits = sum(1 for v in values if str(v).lower() in terms)
        if attr.source == "title_verified":
            verified += hits
        else:
            inferred += hits
    return verified, inferred


def score_candidate(candidate: Candidate, intent: ShoppingIntent,
                    max_quality: float) -> float:
    terms = _intent_terms(intent)
    verified, inferred = _attribute_matches(candidate, terms)
    quality = candidate.product.quality_score / max_quality if max_quality > 0 else 0.0

    return (
        candidate.similarity
        + WEIGHTS["quality"] * min(quality, 1.0)
        + WEIGHTS["verified_attr"] * min(verified, 1)
        + WEIGHTS["inferred_attr"] * min(inferred, 1)
    )


def prerank(candidates: list[Candidate], intent: ShoppingIntent,
            per_sub_need: int = 5) -> list[Candidate]:
    """Score, apply a diversity penalty, and keep the top N per sub-need.

    Sub-needs are ranked independently so a strong one cannot starve a weak one -
    every group the user asked for gets its own shot at the LLM.
    """
    if not candidates:
        return []

    max_quality = max(c.product.quality_score for c in candidates) or 1.0
    for c in candidates:
        c.score = score_candidate(c, intent, max_quality)

    by_sub_need: dict[str, list[Candidate]] = {}
    for c in candidates:
        by_sub_need.setdefault(c.sub_need, []).append(c)

    selected: list[Candidate] = []
    for group in by_sub_need.values():
        group.sort(key=lambda c: c.score, reverse=True)
        chosen: list[Candidate] = []
        demoted: list[Candidate] = []
        seen_variants: set[str] = set()

        for c in group:
            if len(chosen) >= per_sub_need:
                break
            key = variant_key(c.product.title)
            if key in seen_variants:
                # Near-duplicate: 35.8% of source rows share a title prefix
                # (docs/dataset.md 3.2). Demote rather than drop, so a sub-need
                # holding nothing but variants still returns something.
                c.score -= WEIGHTS["duplicate_penalty"]
                demoted.append(c)
                continue
            seen_variants.add(key)
            chosen.append(c)

        if len(chosen) < per_sub_need:
            demoted.sort(key=lambda c: c.score, reverse=True)
            chosen.extend(demoted[: per_sub_need - len(chosen)])
        selected.extend(chosen)

    return selected
