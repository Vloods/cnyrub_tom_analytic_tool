from __future__ import annotations

from .models import OrderBook


def summarize_orderbook(book: OrderBook, levels: int = 10) -> dict[str, float | int | str | None]:
    bids = book.bids[:levels]
    asks = book.asks[:levels]
    best_bid = bids[0].price if bids else None
    best_ask = asks[0].price if asks else None
    bid_qty = sum(level.quantity for level in bids)
    ask_qty = sum(level.quantity for level in asks)
    total_qty = bid_qty + ask_qty
    spread = (best_ask - best_bid) if best_bid is not None and best_ask is not None else None
    mid = ((best_bid + best_ask) / 2) if best_bid is not None and best_ask is not None else None
    imbalance = ((bid_qty - ask_qty) / total_qty) if total_qty else None
    return {
        "secid": book.secid,
        "ts": book.ts.isoformat(),
        "levels": levels,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": spread,
        "mid": mid,
        "bid_qty": bid_qty,
        "ask_qty": ask_qty,
        "imbalance": imbalance,
    }
