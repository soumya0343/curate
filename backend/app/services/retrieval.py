"""Deterministic filtering and per-sub-need vector retrieval.

The LLM decides WHAT a constraint is; this module decides WHICH rows survive it.
Arithmetic over thousands of rows must be exact and testable, and embeddings do
not encode price - two jackets at Rs 2,000 and Rs 22,000 have near-identical
vectors (spec 5, Stage 2).
"""
from app.catalogue.index import CatalogueIndex
from app.providers.embedding import EmbeddingProvider
from app.schemas.intent import ShoppingIntent, SubNeed
from app.schemas.product import Product
from app.schemas.response import Candidate

BUDGET_RELAXATION_FACTOR = 1.25


def survives(product: Product, intent: ShoppingIntent) -> bool:
    """Hard filter using tier A and verified tier B only.

    Unstated constraints are skipped entirely. Inferred attributes never exclude:
    an enrichment mistake must degrade ranking, not hide products.
    """
    # Tier A - source-grounded
    if intent.budget_max is not None and product.price > intent.budget_max:
        return False

    # Tier B - only when title-verified
    if intent.gender is not None:
        verified_gender = product.verified("gender")
        if verified_gender is not None and verified_gender not in (intent.gender, "unisex"):
            return False

    return True


def filter_rows(index: CatalogueIndex, intent: ShoppingIntent) -> tuple[list[int], list[str]]:
    """Apply hard filters, widening one step rather than returning nothing."""
    rows = [i for i, p in enumerate(index.products) if survives(p, intent)]
    if rows or intent.budget_max is None:
        return rows, []

    relaxed = intent.model_copy(
        update={"budget_max": intent.budget_max * BUDGET_RELAXATION_FACTOR})
    rows = [i for i, p in enumerate(index.products) if survives(p, relaxed)]
    notice = (f"No products under Rs {intent.budget_max:.0f} matched - "
              f"showing options up to Rs {relaxed.budget_max:.0f}.")
    if not rows:
        rows = list(range(len(index.products)))
        notice = f"No products under Rs {intent.budget_max:.0f} matched - budget ignored."
    return rows, [notice]


async def retrieve(index: CatalogueIndex, embedder: EmbeddingProvider,
                   sub_needs: list[SubNeed], subset: list[int],
                   top_k: int = 8) -> list[Candidate]:
    """Retrieve top-k per sub-need, then union and deduplicate.

    Candidate count is at most top_k * len(sub_needs) and is typically lower
    after overlap deduplication (spec 5, Stage 3).
    """
    if not sub_needs:
        return []

    vectors = await embedder.embed([s.query for s in sub_needs])

    best: dict[str, Candidate] = {}
    for sub_need, vec in zip(sub_needs, vectors):
        for row, similarity in index.search(vec, subset, top_k):
            product = index.products[row]
            existing = best.get(product.id)
            if existing is None or similarity > existing.similarity:
                best[product.id] = Candidate(product=product, similarity=similarity,
                                             sub_need=sub_need.label)
    return list(best.values())
