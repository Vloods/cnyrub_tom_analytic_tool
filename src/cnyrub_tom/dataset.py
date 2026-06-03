from __future__ import annotations

from datetime import timedelta
from typing import Iterable

from .analysis import summarize_orderbook
from .models import OrderBook


def build_feature_rows(books: Iterable[OrderBook], *, levels: tuple[int, ...] = (1, 5, 10)) -> list[dict[str, float | int | str | None]]:
    ordered = sorted(books, key=lambda book: book.ts)
    rows: list[dict[str, float | int | str | None]] = []
    previous_mid: float | None = None
    previous_spread: float | None = None
    for book in ordered:
        row: dict[str, float | int | str | None] = {
            "secid": book.secid,
            "ts": book.ts.isoformat(),
        }
        summary = summarize_orderbook(book, levels=max(levels) if levels else 10)
        mid = _rounded(summary["mid"])
        spread = _rounded(summary["spread"])
        row["best_bid"] = _rounded(summary["best_bid"])
        row["best_ask"] = _rounded(summary["best_ask"])
        row["mid"] = mid
        row["spread"] = spread
        row["mid_change"] = None if previous_mid is None or mid is None else _round(mid - previous_mid)
        row["spread_change"] = None if previous_spread is None or spread is None else _round(spread - previous_spread)
        for depth in levels:
            depth_summary = summarize_orderbook(book, levels=depth)
            row[f"bid_depth_{depth}"] = _rounded(depth_summary["bid_qty"])
            row[f"ask_depth_{depth}"] = _rounded(depth_summary["ask_qty"])
            row[f"imbalance_{depth}"] = _rounded(depth_summary["imbalance"], digits=6)
        rows.append(row)
        previous_mid = mid
        previous_spread = spread
    return rows


def build_label_rows(
    books: Iterable[OrderBook],
    *,
    horizon_seconds: int = 5,
    flat_threshold: float = 0.0,
) -> list[dict[str, float | int | str | None]]:
    ordered = sorted(books, key=lambda book: book.ts)
    mids = [(book, _rounded(summarize_orderbook(book, levels=1)["mid"])) for book in ordered]
    rows: list[dict[str, float | int | str | None]] = []
    for index, (book, mid) in enumerate(mids):
        if mid is None:
            continue
        target_ts = book.ts + timedelta(seconds=horizon_seconds)
        future = next(((candidate, future_mid) for candidate, future_mid in mids[index + 1:] if candidate.ts >= target_ts and future_mid is not None), None)
        if future is None:
            continue
        future_book, future_mid = future
        assert future_mid is not None
        future_return = _round(future_mid - mid)
        if future_return > flat_threshold:
            label = "up"
        elif future_return < -flat_threshold:
            label = "down"
        else:
            label = "flat"
        rows.append({
            "secid": book.secid,
            "ts": book.ts.isoformat(),
            "horizon_sec": horizon_seconds,
            "mid": mid,
            "future_ts": future_book.ts.isoformat(),
            "future_mid": future_mid,
            "future_return": future_return,
            "label": label,
        })
    return rows


def _rounded(value: object, *, digits: int = 10) -> float | None:
    if value is None:
        return None
    return _round(float(value), digits=digits)


def _round(value: float, *, digits: int = 10) -> float:
    return round(value, digits)
