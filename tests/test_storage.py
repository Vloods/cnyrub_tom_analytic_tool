import sqlite3
from datetime import datetime, timezone

from cnyrub_tom.models import OrderBook, OrderLevel
from cnyrub_tom.storage import SnapshotStore


def test_snapshot_store_round_trips_full_orderbook(tmp_path):
    db_path = tmp_path / "snapshots.sqlite"
    store = SnapshotStore(db_path)
    book = OrderBook(
        secid="CNYRUB_TOM",
        ts=datetime(2026, 1, 2, 10, 30, tzinfo=timezone.utc),
        bids=[OrderLevel(price=12.34, quantity=100), OrderLevel(price=12.33, quantity=50)],
        asks=[OrderLevel(price=12.36, quantity=70)],
        source="test",
    )

    snapshot_id = store.save_orderbook(book)
    loaded = list(store.iter_orderbooks(secid="CNYRUB_TOM"))

    assert snapshot_id == 1
    assert loaded == [book]
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("select count(*) from orderbook_levels").fetchone()[0] == 3
