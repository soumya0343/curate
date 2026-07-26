from pathlib import Path

import yaml

QUERIES = Path(__file__).parent.parent / "eval" / "queries.yaml"


def test_golden_queries_are_the_assignment_examples():
    data = yaml.safe_load(QUERIES.read_text(encoding="utf-8"))
    assert len(data["golden"]) == 3
    joined = " ".join(q["query"] for q in data["golden"]).lower()
    assert "hampta" in joined and "wedding" in joined and "anniversary" in joined


def test_unseen_queries_cover_unrelated_domains():
    data = yaml.safe_load(QUERIES.read_text(encoding="utf-8"))
    assert len(data["unseen"]) >= 7
    domains = {q["domain"] for q in data["unseen"]}
    assert len(domains) >= 5, "unseen queries must span domains, not restate one"


def test_every_query_has_an_id_and_text():
    data = yaml.safe_load(QUERIES.read_text(encoding="utf-8"))
    for q in data["golden"] + data["unseen"]:
        assert q["id"] and q["query"]


def test_every_query_id_is_unique():
    data = yaml.safe_load(QUERIES.read_text(encoding="utf-8"))
    ids = [q["id"] for q in data["golden"] + data["unseen"]]
    assert len(ids) == len(set(ids)), "query ids must be unique across golden and unseen"


def test_every_unseen_query_has_a_domain_and_expect():
    data = yaml.safe_load(QUERIES.read_text(encoding="utf-8"))
    for q in data["unseen"]:
        assert q.get("domain"), f"{q.get('id')} is missing domain"
        assert q.get("expect"), f"{q.get('id')} is missing expect"


def test_golden_queries_carry_the_three_assignment_scenarios():
    data = yaml.safe_load(QUERIES.read_text(encoding="utf-8"))
    by_id = {q["id"]: q for q in data["golden"]}

    assert "trek-hampta" in by_id
    trek = by_id["trek-hampta"]
    assert "hampta" in trek["query"].lower()
    assert trek["domain"] == "outdoor"

    assert "wedding-traditional" in by_id
    wedding = by_id["wedding-traditional"]
    assert "wedding" in wedding["query"].lower()
    assert wedding["domain"] == "apparel"

    assert "anniversary-gift" in by_id
    anniversary = by_id["anniversary-gift"]
    assert "anniversary" in anniversary["query"].lower()
    assert anniversary["domain"] == "gifting"
