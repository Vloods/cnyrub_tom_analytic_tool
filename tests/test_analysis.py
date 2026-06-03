from datetime import datetime, timezone

from cnyrub_tom.models import OrderBook, OrderLevel
from cnyrub_tom.analysis import summarize_orderbook


def test_summarize_orderbook_computes_spread_mid_and_imbalances():
    book = OrderBook(
        secid="CNYRUB_TOM",
        ts=datetime(2026, 1, 2, 10, 30, tzinfo=timezone.utc),
        bids=[OrderLevel(price=12.34, quantity=100), OrderLevel(price=12.33, quantity=50)],
        asks=[OrderLevel(price=12.36, quantity=70), OrderLevel(price=12.37, quantity=30)],
    )

    summary = summarize_orderbook(book, levels=2)

    assert summary["best_bid"] == 12.34
    assert summary["best_ask"] == 12.36
    assert round(summary["spread"], 8) == 0.02
    assert summary["mid"] == 12.35
    assert summary["bid_qty"] == 150
    assert summary["ask_qty"] == 100
    assert summary["imbalance"] == 0.2
