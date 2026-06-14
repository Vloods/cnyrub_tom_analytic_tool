import json
from datetime import datetime, timezone

from cnyrub_tom.providers import FileOrderBookProvider


def test_file_orderbook_provider_reads_quik_export_shape(tmp_path):
    path = tmp_path / "cnyrub_orderbook.json"
    path.write_text(json.dumps({
        "secid": "CNYRUB_TOM",
        "class_code": "CETS",
        "ts": "2026-06-03T20:00:01+00:00",
        "bid": [{"price": "10.85000", "quantity": "1000"}],
        "offer": [{"price": "10.86000", "quantity": "750"}],
    }), encoding="utf-8")

    book = FileOrderBookProvider(path).get_orderbook()

    assert book.secid == "CNYRUB_TOM"
    assert book.ts == datetime(2026, 6, 3, 20, 0, 1, tzinfo=timezone.utc)
    assert [(level.price, level.quantity) for level in book.bids] == [(10.85, 1000.0)]
    assert [(level.price, level.quantity) for level in book.asks] == [(10.86, 750.0)]
    assert book.source == "file-json"


def test_file_orderbook_provider_reads_generic_bids_asks_shape(tmp_path):
    path = tmp_path / "book.json"
    path.write_text(json.dumps({
        "ts": "2026-06-03T20:00:02+00:00",
        "bids": [[10.84, 500]],
        "asks": [[10.87, 300]],
    }), encoding="utf-8")

    book = FileOrderBookProvider(path).get_orderbook("CNYRUB_TOM")

    assert book.secid == "CNYRUB_TOM"
    assert [(level.price, level.quantity) for level in book.bids] == [(10.84, 500.0)]
    assert [(level.price, level.quantity) for level in book.asks] == [(10.87, 300.0)]


def test_file_orderbook_provider_reads_singular_bid_ask_shape(tmp_path):
    path = tmp_path / "book_bid_ask.json"
    path.write_text(json.dumps({
        "ts": "2026-06-03T20:00:03+00:00",
        "bid": [[10.83, 700]],
        "ask": [[10.88, 400]],
    }), encoding="utf-8")

    book = FileOrderBookProvider(path).get_orderbook("CNYRUB_TOM")

    assert [(level.price, level.quantity) for level in book.bids] == [(10.83, 700.0)]
    assert [(level.price, level.quantity) for level in book.asks] == [(10.88, 400.0)]
