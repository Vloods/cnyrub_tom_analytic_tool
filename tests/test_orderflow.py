from datetime import datetime, timedelta, timezone

from cnyrub_tom import cli
from cnyrub_tom.models import OrderBook, OrderLevel
from cnyrub_tom.orderflow import detect_accumulation_zones, orderflow_rows
from cnyrub_tom.storage import SnapshotStore


def _book(second: int, bid: float, ask: float, bid_qty: float, ask_qty: float) -> OrderBook:
    return OrderBook(
        secid="CNYRUB_TOM",
        ts=datetime(2026, 6, 3, 10, 0, second, tzinfo=timezone.utc),
        bids=[OrderLevel(bid, bid_qty), OrderLevel(bid - 0.0005, bid_qty / 2)],
        asks=[OrderLevel(ask, ask_qty), OrderLevel(ask + 0.0005, ask_qty / 2)],
        source="fixture",
    )


def test_orderflow_rows_include_mid_spread_depth_and_imbalance():
    rows = orderflow_rows([_book(0, 12.4800, 12.4810, 100, 60)], levels=2)

    assert rows == [{
        "secid": "CNYRUB_TOM",
        "ts": "2026-06-03T10:00:00+00:00",
        "best_bid": 12.48,
        "best_ask": 12.481,
        "spread": 0.0009999999999994458,
        "mid": 12.4805,
        "bid_qty": 150,
        "ask_qty": 90,
        "imbalance": 0.25,
        "mid_change": 0,
        "bid_qty_change": 0,
        "ask_qty_change": 0,
    }]


def test_detect_accumulation_finds_narrow_high_volume_buy_zone():
    books = [
        _book(0, 12.4800, 12.4810, 300, 80),
        _book(10, 12.4801, 12.4811, 320, 90),
        _book(20, 12.4800, 12.4810, 350, 85),
        _book(30, 12.4801, 12.4811, 330, 95),
    ]

    zones = detect_accumulation_zones(
        books,
        levels=2,
        window=4,
        min_snapshots=4,
        max_mid_range=0.001,
        min_total_depth=500,
        imbalance_threshold=0.35,
    )

    assert len(zones) == 1
    zone = zones[0]
    assert zone.kind == "buy_accumulation"
    assert zone.secid == "CNYRUB_TOM"
    assert zone.start_ts == books[0].ts
    assert zone.end_ts == books[-1].ts
    assert zone.mid_low == 12.4805
    assert zone.mid_high == 12.4806
    assert zone.avg_imbalance > 0.55
    assert zone.confidence > 0.7


def test_detect_accumulation_ignores_wide_moving_price():
    start = datetime(2026, 6, 3, 10, 0, tzinfo=timezone.utc)
    books = []
    for index in range(5):
        bid = 12.4800 + index * 0.004
        books.append(OrderBook(
            secid="CNYRUB_TOM",
            ts=start + timedelta(seconds=index * 10),
            bids=[OrderLevel(bid, 500)],
            asks=[OrderLevel(bid + 0.001, 500)],
        ))

    assert detect_accumulation_zones(books, window=4, max_mid_range=0.001, min_total_depth=500) == []


def test_detect_accumulation_cli_writes_csv(tmp_path, capsys):
    db_path = tmp_path / "orderbook.sqlite"
    output = tmp_path / "zones.csv"
    store = SnapshotStore(db_path)
    for book in [
        _book(0, 12.4800, 12.4810, 300, 80),
        _book(10, 12.4801, 12.4811, 320, 90),
        _book(20, 12.4800, 12.4810, 350, 85),
        _book(30, 12.4801, 12.4811, 330, 95),
    ]:
        store.save_orderbook(book)

    result = cli.main([
        "detect-accumulation",
        "--db",
        str(db_path),
        "--levels",
        "2",
        "--window",
        "4",
        "--min-snapshots",
        "4",
        "--max-mid-range",
        "0.001",
        "--min-total-depth",
        "500",
        "--imbalance-threshold",
        "0.35",
        "--output",
        str(output),
    ])

    assert result == 0
    assert "saved 1 accumulation zones" in capsys.readouterr().out
    content = output.read_text(encoding="utf-8")
    assert "kind,start_ts,end_ts" in content
    assert "buy_accumulation" in content
