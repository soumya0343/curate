"""The catalogue browsing router and the pool behind it.

Two layers, because they fail differently. The unit tests drive the router with a
fake cursor and assert on the SQL it emits -- ordering, filters, pagination
arithmetic -- which is where the bugs a live database would not reveal (an
unstable sort reads fine against 3 rows). The integration tests need a real
Postgres and skip without one; they are what proves the schema, the seed and the
row mapping actually agree.
"""
import contextlib
import os

import psycopg2
import pytest
from fastapi.testclient import TestClient

from app.api import routes_catalogue
from app.db import mock_db
from app.main import create_app


# --- fake cursor -------------------------------------------------------

class FakeCursor:
    """Records every statement and replays canned rows."""

    def __init__(self, rows: list[list[dict]]) -> None:
        self.statements: list[tuple[str, list]] = []
        self._rows = list(rows)
        self._current: list[dict] = []

    def execute(self, sql, params=None):
        self.statements.append((" ".join(sql.split()), list(params or [])))
        self._current = self._rows.pop(0) if self._rows else []

    def fetchone(self):
        return self._current[0] if self._current else None

    def fetchall(self):
        return self._current

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def commit(self):
        pass


def install_fake(monkeypatch, rows: list[list[dict]]) -> FakeCursor:
    cursor = FakeCursor(rows)

    @contextlib.contextmanager
    def fake_get_connection():
        yield FakeConnection(cursor)

    monkeypatch.setattr(routes_catalogue, "get_connection", fake_get_connection)
    return cursor


PRODUCT_ROW = {
    "id": "B0MOCK0000", "title": "Wildcraft 45L Rucksack", "category": "Rucksacks",
    "price": 3499.0, "currency": "INR", "price_tier": "mid", "rating": 4.3,
    "reviews": 2871, "image_url": "https://img/x.jpg",
    "product_url": "https://www.amazon.in/dp/B0MOCK0000",
}


@pytest.fixture
def client():
    # load_catalogue=False: no pipeline warm-up and no init_db, so these tests
    # never touch a database unless they open one themselves.
    with TestClient(create_app(load_catalogue=False)) as c:
        yield c


# --- no database -------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_pool():
    """Every test starts with the pool closed; integration tests opt in."""
    mock_db.close_db()
    yield
    mock_db.close_db()


def test_browsing_without_a_database_is_503_not_500(client):
    """The distinction is the whole point of degrading rather than failing to
    boot: recommendation is fine, only browsing is down, and it is retryable."""
    response = client.get("/api/catalogue")
    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "CATALOGUE_UNAVAILABLE",
        "message": response.json()["error"]["message"],
        "retryable": True,
    }


def test_the_app_still_boots_and_serves_when_the_database_is_missing(monkeypatch):
    """init_db must swallow an unreachable database. If it raised, one dead
    router would take the whole API down with it."""
    monkeypatch.setattr(
        mock_db, "get_settings",
        lambda: type("S", (), {"database_url":
                               "postgresql://nobody@127.0.0.1:1/none"})())
    assert mock_db.init_db() is False
    assert mock_db.is_ready() is False


def test_init_db_raises_when_the_caller_requires_a_database(monkeypatch):
    """The seed script has nothing to degrade to, so it must not get a silent
    no-op that reports success."""
    monkeypatch.setattr(
        mock_db, "get_settings",
        lambda: type("S", (), {"database_url":
                               "postgresql://nobody@127.0.0.1:1/none"})())
    with pytest.raises(psycopg2.Error):
        mock_db.init_db(required=True)


# --- query construction ------------------------------------------------

def test_listing_breaks_sort_ties_on_a_unique_column(client, monkeypatch):
    """Without the id tiebreak, two products with the same rating order
    arbitrarily between the count query and the page query, so one can appear on
    two pages while another never appears at all."""
    cursor = install_fake(monkeypatch, [[{"n": 2}], [PRODUCT_ROW]])
    client.get("/api/catalogue")
    page_sql = cursor.statements[1][0]
    assert "ORDER BY rating DESC, id ASC" in page_sql


def test_listing_paginates_with_limit_and_offset(client, monkeypatch):
    cursor = install_fake(monkeypatch, [[{"n": 147}], [PRODUCT_ROW]])
    body = client.get("/api/catalogue?page=3&page_size=20").json()

    assert cursor.statements[1][1][-2:] == [20, 40], "LIMIT 20 OFFSET 40"
    assert (body["total"], body["page"], body["pages"]) == (147, 3, 8)


def test_filters_are_bound_parameters_not_interpolated(client, monkeypatch):
    """A category name is user input and reaches SQL only as a bound value."""
    cursor = install_fake(monkeypatch, [[{"n": 0}], []])
    client.get("/api/catalogue?category=Books&price_tier=budget"
               "&min_price=100&max_price=500&search=atomic")

    sql, params = cursor.statements[0]
    assert "category = %s" in sql and "price_tier = %s" in sql
    assert "price >= %s" in sql and "price <= %s" in sql
    assert params == ["Books", "budget", "%atomic%", "%atomic%", 100.0, 500.0]
    assert "Books" not in sql


def test_an_unlisted_sort_column_is_rejected_before_reaching_sql(client, monkeypatch):
    install_fake(monkeypatch, [[{"n": 0}], []])
    response = client.get("/api/catalogue?sort_by=price;DROP TABLE products")
    assert response.status_code == 422


def test_a_missing_product_is_the_apps_error_envelope(client, monkeypatch):
    """404s from this router must match the shape /api/recommend already uses,
    not FastAPI's default {"detail": ...}."""
    install_fake(monkeypatch, [[]])
    response = client.get("/api/catalogue/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


# --- against a real database -------------------------------------------

def _live_dsn() -> str | None:
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        return None
    try:
        psycopg2.connect(dsn).close()
    except psycopg2.Error:
        return None
    return dsn


live_db = pytest.mark.skipif(
    _live_dsn() is None,
    reason="set TEST_DATABASE_URL to a reachable Postgres to run these")


@pytest.fixture
def seeded(monkeypatch):
    dsn = _live_dsn()
    monkeypatch.setattr(mock_db, "get_settings",
                        lambda: type("S", (), {"database_url": dsn})())
    mock_db.init_db(required=True)
    with mock_db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM products")
            cur.executemany(
                """INSERT INTO products (id, title, title_original, description,
                       category, price, currency, price_tier, rating, reviews,
                       quality_score, attributes, image_url, product_url)
                   VALUES (%s,%s,%s,%s,%s,%s,'INR',%s,%s,%s,%s,'{}'::jsonb,%s,%s)""",
                [(f"B{i}", f"Trekking Backpack {i}", f"Trekking Backpack {i}",
                  "A rucksack.", "Backpacks" if i < 2 else "Books",
                  1000.0 + i, "mid", 4.2, 50, 16.5, "https://img", "https://p")
                 for i in range(4)])
        conn.commit()
    yield
    mock_db.close_db()


@live_db
def test_the_schema_round_trips_a_product(seeded, client):
    body = client.get("/api/catalogue/B0").json()
    assert body["id"] == "B0"
    assert body["price"] == 1000.0, "NUMERIC must come back as a float, not Decimal"
    assert body["attributes"] == {}


@live_db
def test_pagination_covers_every_row_exactly_once(seeded, client):
    """The tiebreak claim, verified end to end: all four rows share a rating."""
    seen = []
    for page in (1, 2):
        seen += [p["id"] for p in
                 client.get(f"/api/catalogue?page={page}&page_size=2").json()["items"]]
    assert sorted(seen) == ["B0", "B1", "B2", "B3"]


@live_db
def test_categories_come_back_with_counts(seeded, client):
    assert client.get("/api/catalogue/categories").json() == [
        {"category": "Backpacks", "count": 2},
        {"category": "Books", "count": 2},
    ]
