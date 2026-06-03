from datetime import datetime, timedelta, timezone

from cnyrub_tom.dataset import build_feature_rows, build_label_rows
from cnyrub_tom.models import OrderBook, OrderLevel


def _book(ts: datetime, bid: float, ask: float, bid_qty: float, ask_qty: float) -> OrderBook:
    return OrderBook(
        secid="CNYRUB_TOM",
        ts=ts,
        bids=[OrderLevel(bid, bid_qty), OrderLevel(bid - 0.001, bid_qty / 2)],
        asks=[OrderLevel(ask, ask_qty), OrderLevel(ask + 0.001, ask_qty / 2)],
        source="test",
    )


def test_build_feature_rows_creates_ml_ready_orderbook_features():
    base = datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc)
    books = [
        _book(base, 12.340, 12.350, 1000, 800),
        _book(base + timedelta(seconds=5), 12.342, 12.352, 1500, 700),
    ]

    rows = build_feature_rows(books, levels=(1, 2))

    assert len(rows) == 2
    assert rows[1]["secid"] == "CNYRUB_TOM"
    assert rows[1]["ts"] == "2026-06-03T10:00:05+00:00"
    assert rows[1]["mid"] == 12.347
    assert rows[1]["spread"] == 0.01
    assert rows[1]["bid_depth_1"] == 1500
    assert rows[1]["ask_depth_1"] == 700
    assert rows[1]["bid_depth_2"] == 2250
    assert rows[1]["ask_depth_2"] == 1050
    assert rows[1]["imbalance_1"] > 0
    assert rows[1]["mid_change"] > 0


def test_build_label_rows_labels_future_mid_direction_by_horizon():
    base = datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc)
    books = [
        _book(base, 12.340, 12.350, 1000, 800),
        _book(base + timedelta(seconds=5), 12.345, 12.355, 1000, 800),
        _book(base + timedelta(seconds=10), 12.344, 12.354, 1000, 800),
    ]

    rows = build_label_rows(books, horizon_seconds=5, flat_threshold=0.0005)

    assert len(rows) == 2
    assert rows[0]["label"] == "up"
    assert rows[0]["future_return"] > 0
    assert rows[1]["label"] == "down"
    assert rows[1]["horizon_sec"] == 5
