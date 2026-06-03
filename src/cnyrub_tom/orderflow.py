from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from .analysis import summarize_orderbook
from .models import OrderBook


@dataclass(frozen=True)
class AccumulationZone:
    secid: str
    kind: str
    start_ts: datetime
    end_ts: datetime
    snapshots: int
    mid_low: float
    mid_high: float
    mid_range: float
    avg_mid: float
    avg_spread: float
    avg_bid_qty: float
    avg_ask_qty: float
    avg_total_depth: float
    avg_imbalance: float
    confidence: float
    reason: str

    def to_row(self) -> dict[str, str | int | float]:
        row = asdict(self)
        row["start_ts"] = self.start_ts.isoformat()
        row["end_ts"] = self.end_ts.isoformat()
        return row


def orderflow_rows(books: list[OrderBook], levels: int = 10) -> list[dict[str, float | int | str | None]]:
    rows: list[dict[str, float | int | str | None]] = []
    previous_mid: float | None = None
    previous_bid_qty: float | None = None
    previous_ask_qty: float | None = None
    for book in sorted(books, key=lambda item: item.ts):
        summary = summarize_orderbook(book, levels=levels)
        mid = _as_float(summary["mid"])
        bid_qty = _as_float(summary["bid_qty"])
        ask_qty = _as_float(summary["ask_qty"])
        rows.append({
            "secid": book.secid,
            "ts": book.ts.isoformat(),
            "best_bid": summary["best_bid"],
            "best_ask": summary["best_ask"],
            "spread": summary["spread"],
            "mid": mid,
            "bid_qty": bid_qty,
            "ask_qty": ask_qty,
            "imbalance": summary["imbalance"],
            "mid_change": 0 if previous_mid is None or mid is None else mid - previous_mid,
            "bid_qty_change": 0 if previous_bid_qty is None or bid_qty is None else bid_qty - previous_bid_qty,
            "ask_qty_change": 0 if previous_ask_qty is None or ask_qty is None else ask_qty - previous_ask_qty,
        })
        previous_mid = mid
        previous_bid_qty = bid_qty
        previous_ask_qty = ask_qty
    return rows


def detect_accumulation_zones(
    books: list[OrderBook],
    *,
    levels: int = 10,
    window: int = 20,
    min_snapshots: int = 5,
    max_mid_range: float = 0.002,
    min_total_depth: float = 1000,
    imbalance_threshold: float = 0.25,
) -> list[AccumulationZone]:
    ordered = sorted(books, key=lambda item: item.ts)
    if len(ordered) < min_snapshots:
        return []
    window = max(window, min_snapshots)
    zones: list[AccumulationZone] = []
    index = 0
    while index <= len(ordered) - min_snapshots:
        candidate: AccumulationZone | None = None
        candidate_end = index
        max_end = min(len(ordered), index + window)
        for end in range(index + min_snapshots, max_end + 1):
            maybe = _zone_from_window(
                ordered[index:end],
                levels=levels,
                max_mid_range=max_mid_range,
                min_total_depth=min_total_depth,
                imbalance_threshold=imbalance_threshold,
            )
            if maybe is not None:
                candidate = maybe
                candidate_end = end
        if candidate is not None:
            zones.append(candidate)
            index = max(candidate_end, index + 1)
        else:
            index += 1
    return zones


def _zone_from_window(
    books: list[OrderBook],
    *,
    levels: int,
    max_mid_range: float,
    min_total_depth: float,
    imbalance_threshold: float,
) -> AccumulationZone | None:
    rows = orderflow_rows(books, levels=levels)
    mids = [_as_float(row["mid"]) for row in rows]
    spreads = [_as_float(row["spread"]) for row in rows]
    bid_quantities = [_as_float(row["bid_qty"]) for row in rows]
    ask_quantities = [_as_float(row["ask_qty"]) for row in rows]
    imbalances = [_as_float(row["imbalance"]) for row in rows]
    values = mids + spreads + bid_quantities + ask_quantities + imbalances
    if any(value is None for value in values):
        return None
    mid_values = _non_none(mids)
    spread_values = _non_none(spreads)
    bid_values = _non_none(bid_quantities)
    ask_values = _non_none(ask_quantities)
    imbalance_values = _non_none(imbalances)
    mid_low = min(mid_values)
    mid_high = max(mid_values)
    mid_range = mid_high - mid_low
    avg_bid_qty = sum(bid_values) / len(bid_values)
    avg_ask_qty = sum(ask_values) / len(ask_values)
    avg_total_depth = avg_bid_qty + avg_ask_qty
    avg_imbalance = sum(imbalance_values) / len(imbalance_values)
    if mid_range > max_mid_range or avg_total_depth < min_total_depth:
        return None
    if avg_imbalance >= imbalance_threshold:
        kind = "buy_accumulation"
        side_reason = "bid depth dominates and price stays in a narrow range"
    elif avg_imbalance <= -imbalance_threshold:
        kind = "sell_accumulation"
        side_reason = "ask depth dominates and price stays in a narrow range"
    else:
        kind = "neutral_accumulation"
        side_reason = "large depth is trapped in a narrow range without a clear side imbalance"
    range_score = _clamp(1 - (mid_range / max_mid_range if max_mid_range else 0), 0, 1)
    depth_score = _clamp(avg_total_depth / (min_total_depth * 2), 0, 1) if min_total_depth else 1
    imbalance_score = _clamp(abs(avg_imbalance), 0, 1)
    confidence = round(_clamp(0.45 * range_score + 0.35 * depth_score + 0.20 * imbalance_score, 0, 1), 4)
    return AccumulationZone(
        secid=books[0].secid,
        kind=kind,
        start_ts=books[0].ts,
        end_ts=books[-1].ts,
        snapshots=len(books),
        mid_low=round(mid_low, 10),
        mid_high=round(mid_high, 10),
        mid_range=round(mid_range, 10),
        avg_mid=round(sum(mid_values) / len(mid_values), 10),
        avg_spread=round(sum(spread_values) / len(spread_values), 10),
        avg_bid_qty=round(avg_bid_qty, 10),
        avg_ask_qty=round(avg_ask_qty, 10),
        avg_total_depth=round(avg_total_depth, 10),
        avg_imbalance=round(avg_imbalance, 10),
        confidence=confidence,
        reason=side_reason,
    )


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _non_none(values: list[float | None]) -> list[float]:
    return [value for value in values if value is not None]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
