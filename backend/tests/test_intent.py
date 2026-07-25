import pytest

from app.core.errors import InvalidQuery
from app.providers.generation import StubGenerationProvider
from app.schemas.intent import ShoppingIntent
from app.services.intent import extract, parse_intent_payload

PAYLOAD = {
    "intent": {"activity": "trekking", "destination": "Hampta Pass",
               "season": "late October", "duration_days": 7,
               "budget_max": None, "gender": None, "occasion": None},
    "sub_needs": [{"label": "Backpack", "query": "50L trekking rucksack"},
                  {"label": "Insulation layer", "query": "warm insulated jacket"}],
    "assumptions": [{"field": "climate", "value": "cold-weather conditions likely",
                     "reason": "high-altitude trek in late October",
                     "confidence": "medium"}],
    "clarifying_question": None,
    "confidence": 0.82,
}


def test_parse_extracts_sub_needs_and_assumptions():
    result = parse_intent_payload(PAYLOAD)
    assert result.intent.activity == "trekking"
    assert [s.label for s in result.sub_needs] == ["Backpack", "Insulation layer"]
    assert result.assumptions[0].confidence == "medium"


def test_parse_tolerates_missing_optional_keys():
    result = parse_intent_payload({"sub_needs": [{"label": "X", "query": "y"}]})
    assert result.clarifying_question is None
    assert result.intent.budget_max is None


def test_parse_drops_malformed_sub_needs_rather_than_failing():
    result = parse_intent_payload({"sub_needs": [{"label": "Good", "query": "ok"},
                                                 {"label": "Missing query"}]})
    assert [s.label for s in result.sub_needs] == ["Good"]


def test_parse_raises_when_no_sub_needs_survive():
    with pytest.raises(InvalidQuery):
        parse_intent_payload({"sub_needs": []})


async def test_extract_calls_provider_and_parses():
    provider = StubGenerationProvider([PAYLOAD])
    result = await extract(provider, "trek to Hampta Pass", None, request_id="r")
    assert result.intent.destination == "Hampta Pass"
    assert "trek to Hampta Pass" in provider.prompts[0]


async def test_extract_merges_delta_onto_prior_intent():
    delta = {"intent": {"budget_max": 3000},
             "sub_needs": [{"label": "Backpack", "query": "cheap rucksack"}]}
    prior = ShoppingIntent(activity="trekking", destination="Hampta Pass",
                           duration_days=7)
    result = await extract(StubGenerationProvider([delta]), "make it cheaper",
                           prior, request_id="r")
    assert result.intent.budget_max == 3000
    assert result.intent.activity == "trekking", "prior context must survive"
    assert result.intent.destination == "Hampta Pass"


async def test_extract_includes_prior_intent_in_prompt():
    provider = StubGenerationProvider([PAYLOAD])
    await extract(provider, "cheaper", ShoppingIntent(activity="trekking"),
                  request_id="r")
    assert "trekking" in provider.prompts[0]
