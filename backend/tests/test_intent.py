import pytest

from app.core.errors import InvalidQuery
from app.providers.generation import StubGenerationProvider
from app.schemas.intent import ShoppingIntent, SubNeed
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
    "clarifying_questions": [],
    "confidence": 0.82,
}


def test_parse_extracts_sub_needs_and_assumptions():
    result = parse_intent_payload(PAYLOAD)
    assert result.intent.activity == "trekking"
    assert [s.label for s in result.sub_needs] == ["Backpack", "Insulation layer"]
    assert result.assumptions[0].confidence == "medium"


def test_parse_tolerates_missing_optional_keys():
    result = parse_intent_payload({"sub_needs": [{"label": "X", "query": "y"}]})
    assert result.clarifying_questions == []
    assert result.intent.budget_max is None


def test_parse_drops_malformed_sub_needs_rather_than_failing():
    result = parse_intent_payload({"sub_needs": [{"label": "Good", "query": "ok"},
                                                 {"label": "Missing query"}]})
    assert [s.label for s in result.sub_needs] == ["Good"]


def test_parse_raises_when_no_sub_needs_survive():
    with pytest.raises(InvalidQuery):
        parse_intent_payload({"sub_needs": []})


def test_parse_allows_empty_sub_needs_for_follow_ups():
    result = parse_intent_payload({"sub_needs": []}, allow_empty_sub_needs=True)
    assert result.sub_needs == []


@pytest.mark.parametrize("raw_gender,expected", [
    ("male", "men"), ("Male", "men"), ("female", "women"),
    ("unisex", "unisex"), ("nonbinary", None), (None, None),
])
def test_parse_normalizes_gender_aliases_instead_of_raising(raw_gender, expected):
    payload = {**PAYLOAD, "intent": {**PAYLOAD["intent"], "gender": raw_gender}}
    result = parse_intent_payload(payload)
    assert result.intent.gender == expected


def test_parse_drops_non_string_assumption_values():
    payload = {**PAYLOAD, "assumptions": [
        {"field": "bogus", "value": True, "reason": "stray flag", "confidence": "low"},
        {"field": "climate", "value": "cold-weather conditions likely",
         "reason": "high-altitude trek", "confidence": "medium"},
    ]}
    result = parse_intent_payload(payload)
    assert [a.field for a in result.assumptions] == ["climate"]


async def test_extract_calls_provider_and_parses():
    provider = StubGenerationProvider([PAYLOAD])
    result = await extract(provider, "trek to Hampta Pass", None, request_id="r")
    assert result.intent.destination == "Hampta Pass"
    assert "trek to Hampta Pass" in provider.prompts[0]


async def test_extract_defaults_unstated_gender_to_unisex_and_asks():
    """Gender left unstated must never silently skew toward one gender -
    default to unisex and surface a question, rather than picking one."""
    provider = StubGenerationProvider([PAYLOAD])  # PAYLOAD's gender is None
    result = await extract(provider, "trek to Hampta Pass", None, request_id="r")
    assert result.intent.gender == "unisex"
    assert any(a.field == "gender" and a.value == "unisex" for a in result.assumptions)
    assert "Who is this for — men, women, or unisex?" in result.clarifying_questions


async def test_extract_does_not_override_stated_gender():
    payload = {**PAYLOAD, "intent": {**PAYLOAD["intent"], "gender": "women"}}
    result = await extract(StubGenerationProvider([payload]), "trek to Hampta Pass",
                           None, request_id="r")
    assert result.intent.gender == "women"
    assert not any(a.field == "gender" for a in result.assumptions)


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


async def test_extract_keeps_prior_sub_needs_when_followup_returns_none():
    """A filter-only follow-up ("i'm a girl and my budget is 5k") must not
    relabel or drop categories already established earlier in the conversation."""
    filter_only = {"intent": {"budget_max": 5000, "gender": "women"}, "sub_needs": []}
    prior = ShoppingIntent(activity="trekking", destination="Hampta Pass")
    prior_sub_needs = [SubNeed(label="Trekking Footwear", query="hiking boots"),
                       SubNeed(label="Clothing for cold weather", query="thermal jacket")]

    result = await extract(StubGenerationProvider([filter_only]), "i'm a girl and my budget is 5k",
                           prior, request_id="r", prior_sub_needs=prior_sub_needs)

    assert result.sub_needs == prior_sub_needs
    assert result.intent.budget_max == 5000
    assert result.intent.gender == "women"


async def test_extract_includes_prior_sub_needs_in_prompt():
    provider = StubGenerationProvider([PAYLOAD])
    await extract(provider, "cheaper", ShoppingIntent(activity="trekking"),
                  request_id="r", prior_sub_needs=[SubNeed(label="Footwear", query="boots")])
    assert "Footwear" in provider.prompts[0]
