import json
from datetime import datetime, timedelta, timezone

from cnyrub_tom.models import OrderBook, OrderLevel
from cnyrub_tom.realtime import build_dashboard_state, classify_market_pattern
from cnyrub_tom.storage import SnapshotStore


def _book(ts: datetime, bid_qty: float, ask_qty: float, bid: float = 12.34, ask: float = 12.35) -> OrderBook:
    return OrderBook(
        secid="CNYRUB_TOM",
        ts=ts,
        bids=[OrderLevel(bid, bid_qty), OrderLevel(bid - 0.001, bid_qty / 2)],
        asks=[OrderLevel(ask, ask_qty), OrderLevel(ask + 0.001, ask_qty / 2)],
        source="test",
    )


def test_classify_market_pattern_detects_buyer_accumulation_in_narrow_range():
    base = datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc)
    books = [
        _book(base + timedelta(seconds=i), bid_qty=9000 + i * 50, ask_qty=3000, bid=12.34, ask=12.35)
        for i in range(8)
    ]

    state = classify_market_pattern(books, levels=2)

    assert state.advantage == "buyer"
    assert state.pattern == "buyer_accumulation"
    assert state.confidence >= 0.6
    assert "узком диапазоне" in " ".join(state.explanation)


def test_build_dashboard_state_reports_connected_database_and_latest_metrics(tmp_path):
    db_path = tmp_path / "orderbook.sqlite"
    store = SnapshotStore(db_path)
    base = datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc)
    first_id = store.save_orderbook(_book(base, bid_qty=5000, ask_qty=4000, bid=12.34, ask=12.35))
    second_id = store.save_orderbook(_book(base + timedelta(seconds=1), bid_qty=9000, ask_qty=3000, bid=12.341, ask=12.351))

    state = build_dashboard_state(
        db_path,
        orderbook_path=tmp_path / "missing.json",
        now=base + timedelta(seconds=2),
        levels=2,
        pattern_window=5,
    )

    assert state.db_status == "connected"
    assert state.snapshot_count == 2
    assert state.latest_snapshot_id == second_id
    assert state.last_snapshot_age_sec == 1.0
    assert state.quik_status == "missing"
    assert state.best_bid == 12.341
    assert state.best_ask == 12.351
    assert state.advantage == "buyer"
    assert state.imbalance > 0
    assert state.pattern in {"buyer_accumulation", "buyer_pressure"}


def test_build_dashboard_state_reports_missing_database(tmp_path):
    state = build_dashboard_state(tmp_path / "missing.sqlite", orderbook_path=None)

    assert state.db_status == "missing"
    assert state.snapshot_count == 0
    assert state.pattern == "no_data"


def test_build_dashboard_state_uses_live_quik_json_bid_ask_when_database_missing(tmp_path):
    orderbook_path = tmp_path / "cnyrub_tom_orderbook.json"
    orderbook_path.write_text(json.dumps({
        "secid": "CNYRUB_TOM",
        "ts": "2026-06-03T10:00:00+00:00",
        "bid": [{"price": "12.340", "quantity": "5000"}],
        "offer": [{"price": "12.350", "quantity": "3000"}],
    }), encoding="utf-8")

    state = build_dashboard_state(
        tmp_path / "missing.sqlite",
        orderbook_path=orderbook_path,
        now=datetime.fromtimestamp(orderbook_path.stat().st_mtime, tz=timezone.utc),
        levels=1,
    )

    assert state.db_status == "missing"
    assert state.quik_status == "active"
    assert state.best_bid == 12.34
    assert state.best_ask == 12.35
    assert state.spread == 0.01
    assert state.bid_qty == 5000
    assert state.ask_qty == 3000
    assert state.advantage == "buyer"
