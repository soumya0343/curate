import time

from app.schemas.intent import ShoppingIntent, SubNeed
from app.services.sessions import SessionStore


def test_put_then_get_round_trips():
    store = SessionStore(ttl_seconds=60)
    sid = store.new_id()
    store.put(sid, ShoppingIntent(activity="trekking"))
    assert store.get(sid).intent.activity == "trekking"


def test_history_round_trips():
    store = SessionStore(ttl_seconds=60)
    sid = store.new_id()
    store.put(sid, ShoppingIntent(activity="trekking"), ["trek gear", "make it cheaper"])
    assert store.get(sid).history == ["trek gear", "make it cheaper"]


def test_history_defaults_to_empty():
    store = SessionStore(ttl_seconds=60)
    sid = store.new_id()
    store.put(sid, ShoppingIntent(activity="trekking"))
    assert store.get(sid).history == []


def test_sub_needs_round_trip():
    store = SessionStore(ttl_seconds=60)
    sid = store.new_id()
    sub_needs = [SubNeed(label="Footwear", query="boots")]
    store.put(sid, ShoppingIntent(activity="trekking"), ["trek gear"], sub_needs)
    assert store.get(sid).sub_needs == sub_needs


def test_sub_needs_defaults_to_empty():
    store = SessionStore(ttl_seconds=60)
    sid = store.new_id()
    store.put(sid, ShoppingIntent(activity="trekking"))
    assert store.get(sid).sub_needs == []


def test_unknown_session_returns_none():
    assert SessionStore(ttl_seconds=60).get("nope") is None


def test_expired_session_returns_none():
    store = SessionStore(ttl_seconds=0)
    sid = store.new_id()
    store.put(sid, ShoppingIntent(activity="trekking"))
    time.sleep(0.001)  # monotonic() must advance past a zero TTL
    assert store.get(sid) is None


def test_expired_session_is_evicted_not_just_hidden():
    store = SessionStore(ttl_seconds=0)
    sid = store.new_id()
    store.put(sid, ShoppingIntent(activity="trekking"))
    time.sleep(0.001)
    store.get(sid)
    assert sid not in store._data


def test_new_id_is_unique():
    store = SessionStore(ttl_seconds=60)
    assert store.new_id() != store.new_id()
