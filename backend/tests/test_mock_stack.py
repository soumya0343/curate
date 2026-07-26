"""The keyless stack: hashing embeddings, the rule-based generator, and the
synthetic catalogue they run against.

These are fixtures, not products, so the bar is narrow: the vector space must be
shared between build and query time, the generator must stay inside what its
candidates actually state, and the built artifacts must satisfy the same
manifest contract the real pipeline does.
"""
import gzip
import json

import numpy as np
import pytest

from app.catalogue.index import CatalogueIndex, ManifestMismatch, load_index
from app.catalogue.loader import JsonlCatalogue
from app.config import Settings
from app.providers.embedding import HashingEmbedding
from app.providers.generation import MockGeneration
from app.services import intent as intent_service
from app.services.pipeline import RecommendationPipeline, collect
from app.services.sessions import SessionStore
from scripts import build_mock_catalogue as builder

TREK_QUERY = ("I am going for a trek to Hampta Pass in the last week of October "
              "for one week. Please find me trekking essentials and clothing.")


# --- hashing embeddings ------------------------------------------------

def test_hashing_embedding_is_deterministic():
    a = HashingEmbedding(dims=64).encode(["trekking backpack"])
    b = HashingEmbedding(dims=64).encode(["trekking backpack"])
    assert np.allclose(a, b), "build time and query time must agree exactly"


def test_hashing_embedding_rows_are_unit_length():
    m = HashingEmbedding(dims=64).encode(["a trekking backpack", "wireless headphones"])
    assert np.allclose(np.linalg.norm(m, axis=1), 1.0)


def test_hashing_embedding_carries_lexical_signal():
    """The whole reason this exists rather than StubEmbedding's noise."""
    e = HashingEmbedding(dims=256)
    query, related, unrelated = e.encode([
        "trekking backpack", "Wildcraft 45L Trekking Backpack", "Yonex Shuttlecock"])
    assert query @ related > query @ unrelated


def test_stopword_only_text_is_a_zero_row_not_a_crash():
    m = HashingEmbedding(dims=32).encode(["the and of for"])
    assert np.allclose(m, 0.0), "no tokens left, so it matches nothing"


# --- rule-based generation ---------------------------------------------

async def _intent(query: str):
    provider = MockGeneration()
    payload = await provider.generate_json(
        intent_service.INTENT_PROMPT.format(query=query, prior_block=""),
        request_id="t")
    return intent_service.parse_intent_payload(payload)


async def test_mock_intent_output_survives_the_real_parser():
    result = await _intent(TREK_QUERY)
    assert result.intent.activity == "trekking"
    assert len(result.sub_needs) > 1, "a multi-part request decomposes"


async def test_mock_intent_reads_a_stated_budget():
    result = await _intent("wireless headphones for office calls under Rs 5,000")
    assert result.intent.budget_max == 5000.0


async def test_mock_intent_never_invents_a_budget():
    result = await _intent("beginner home workout equipment")
    assert result.intent.budget_max is None
    assert any(a.field == "budget" for a in result.assumptions), (
        "an unstated budget is an assumption to surface, not a silent default")


async def test_unrecognised_request_searches_it_verbatim():
    result = await _intent("something for my aquarium")
    assert len(result.sub_needs) == 1
    assert "aquarium" in result.sub_needs[0].query


async def test_mock_rerank_reasons_cite_only_what_the_candidate_states():
    prompt = ("Candidate products (you may ONLY choose from these ids):\n"
              "id=B1 | group=Backpacks | title=Wildcraft 45L Rucksack | price=Rs3499 "
              '| tier=premium | rating=4.3(2871) | verified={"capacity_l": 45}')
    payload = await MockGeneration().generate_json(prompt, request_id="t")
    reason = payload["groups"][0]["picks"][0]["reason"]

    assert "Rs3499" in reason and "premium" in reason and "capacity l: 45" in reason
    for invented in ("temperature", "-12", "waterproof", "grams", "warranty"):
        assert invented not in reason.lower()


async def test_mock_rerank_only_returns_ids_it_was_given():
    prompt = ("Candidate products (you may ONLY choose from these ids):\n"
              "id=B1 | group=Bags | title=A bag | price=Rs100 | tier=budget | rating=4.0(1)")
    payload = await MockGeneration().generate_json(prompt, request_id="t")
    ids = [p["product_id"] for g in payload["groups"] for p in g["picks"]]
    assert ids == ["B1"]


# --- the synthetic catalogue -------------------------------------------

@pytest.fixture(scope="module")
def mock_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("mock")
    builder.write(builder.build(), out, dims=builder.DIMS)
    return out


def test_build_writes_the_three_artifacts(mock_dir):
    for name in ("catalogue.jsonl.gz", "embeddings.npy", "embeddings.manifest.json"):
        assert (mock_dir / name).exists()


def test_catalogue_rows_align_with_matrix_rows(mock_dir):
    """Line order in the JSONL is row order in the matrix - a silent
    misalignment would attach every explanation to the wrong product."""
    products = JsonlCatalogue(mock_dir / "catalogue.jsonl.gz").load()
    matrix = np.load(mock_dir / "embeddings.npy")
    assert len(products) == matrix.shape[0]
    assert matrix.dtype == np.float16


def test_manifest_pins_the_model_that_built_it(mock_dir):
    manifest = json.loads((mock_dir / "embeddings.manifest.json").read_text())
    assert manifest["model"] == HashingEmbedding.model
    assert manifest["dims"] == builder.DIMS
    assert manifest["synthetic"] is True, "must be labelled as fabricated data"


def test_load_index_accepts_matching_settings(mock_dir):
    index = load_index(mock_dir, Settings(_env_file=None,
                                          embedding_model=HashingEmbedding.model,
                                          embedding_dims=builder.DIMS))
    assert len(index.products) > 50


def test_load_index_refuses_a_different_model(mock_dir):
    with pytest.raises(ManifestMismatch):
        load_index(mock_dir, Settings(_env_file=None,
                                      embedding_model="gemini-embedding-001",
                                      embedding_dims=builder.DIMS))


def test_no_attribute_is_verified_unless_the_title_says_so(mock_dir):
    """The fixture is built through the production verifiers, so a tier
    violation here is a real bug rather than a fixture quirk."""
    for line in gzip.open(mock_dir / "catalogue.jsonl.gz", "rt", encoding="utf-8"):
        product = json.loads(line)
        for field in ("product_type", "use_case", "season", "occasion", "gift_suitable"):
            assert product["attributes"][field]["source"] != "title_verified"
        gender = product["attributes"]["gender"]
        if gender["source"] == "title_verified":
            assert gender["value"] in product["title"].lower()


def test_price_tiers_are_cohort_relative(mock_dir):
    products = [json.loads(l) for l in
                gzip.open(mock_dir / "catalogue.jsonl.gz", "rt", encoding="utf-8")]
    assert {p["price_tier"] for p in products} == {"budget", "mid", "premium", "luxury"}


def test_mock_products_link_to_a_search_not_a_fabricated_asin(mock_dir):
    """The real catalogue's invariant is `product_url == /dp/{asin}`, checked by
    `scripts/validate_urls.assert_structure`. Mock ASINs are invented, so that
    URL would 404 on every card. Linking to an Amazon search for the title
    resolves to something real, which is the honest option for fabricated data —
    and it is why the structural check must not be pointed at this catalogue."""
    for line in gzip.open(mock_dir / "catalogue.jsonl.gz", "rt", encoding="utf-8"):
        product = json.loads(line)
        assert product["product_url"].startswith("https://www.amazon.in/s?k=")
        assert product["id"] not in product["product_url"]


# --- end to end, no keys ------------------------------------------------

@pytest.fixture(scope="module")
def mock_index(mock_dir):
    products = JsonlCatalogue(mock_dir / "catalogue.jsonl.gz").load()
    return CatalogueIndex(products, np.load(mock_dir / "embeddings.npy"))


def _pipeline(index):
    return RecommendationPipeline(
        index=index, embedder=HashingEmbedding(dims=builder.DIMS),
        generator=MockGeneration(), sessions=SessionStore(ttl_seconds=60))


async def test_full_pipeline_runs_without_any_api_key(mock_index):
    events = [e async for e in _pipeline(mock_index).run(TREK_QUERY, None,
                                                         request_id="t")]
    response = collect(events)
    assert len(response.groups) > 1
    assert any(g.recommendations for g in response.groups)


async def test_retrieval_puts_the_right_products_in_the_right_group(mock_index):
    events = [e async for e in _pipeline(mock_index).run(TREK_QUERY, None,
                                                         request_id="t")]
    groups = {g.label: g for g in collect(events).groups}
    backpacks = " ".join(r.title.lower() for r in groups["Backpacks"].recommendations)
    assert "backpack" in backpacks or "rucksack" in backpacks


async def test_stated_budget_excludes_dearer_products(mock_index):
    query = "wireless headphones for office calls under Rs 5,000"
    events = [e async for e in _pipeline(mock_index).run(query, None, request_id="t")]
    response = collect(events)
    prices = [r.price for g in response.groups for r in g.recommendations]
    assert prices, "expected at least one recommendation"
    assert max(prices) <= 5000.0
