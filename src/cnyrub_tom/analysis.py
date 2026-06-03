from __future__ import annotations

from .models import OrderBook, Trade


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


def summarize_trades(trades: list[Trade]) -> dict[str, float | int | str | None]:
    if not trades:
        return {
            "secid": None,
            "trade_count": 0,
            "first_ts": None,
            "last_ts": None,
            "min_price": None,
            "max_price": None,
            "last_price": None,
            "quantity": 0,
            "value": 0,
            "vwap": None,
            "buy_quantity": 0,
            "sell_quantity": 0,
            "side_imbalance": None,
        }
    ordered = sorted(trades, key=lambda trade: (trade.ts, trade.tradeno))
    quantity = sum(trade.quantity for trade in ordered)
    value = sum(trade.value for trade in ordered)
    price_quantity = sum(trade.price * trade.quantity for trade in ordered)
    buy_quantity = sum(trade.quantity for trade in ordered if trade.buysell == "B")
    sell_quantity = sum(trade.quantity for trade in ordered if trade.buysell == "S")
    side_total = buy_quantity + sell_quantity
    return {
        "secid": ordered[0].secid,
        "trade_count": len(ordered),
        "first_ts": ordered[0].ts.isoformat(),
        "last_ts": ordered[-1].ts.isoformat(),
        "min_price": min(trade.price for trade in ordered),
        "max_price": max(trade.price for trade in ordered),
        "last_price": ordered[-1].price,
        "quantity": quantity,
        "value": value,
        "vwap": (price_quantity / quantity) if quantity else None,
        "buy_quantity": buy_quantity,
        "sell_quantity": sell_quantity,
        "side_imbalance": ((buy_quantity - sell_quantity) / side_total) if side_total else None,
    }
