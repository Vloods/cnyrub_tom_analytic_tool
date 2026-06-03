from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from math import floor
from typing import Any

from .models import Trade


def _normalize_ts(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _bucket_start(ts: datetime, bucket_minutes: int) -> datetime:
    if bucket_minutes <= 0:
        raise ValueError("bucket_minutes must be positive")
    normalized = _normalize_ts(ts).replace(second=0, microsecond=0)
    minute = (normalized.minute // bucket_minutes) * bucket_minutes
    return normalized.replace(minute=minute)


def _price_bucket(price: float, price_step: float | None) -> float:
    if price_step is None or price_step <= 0:
        return round(price, 10)
    # Cluster/footprint rows normally group prices down to the selected tick/step.
    return round(floor((price / price_step) + 1e-9) * price_step, 10)


def build_cluster_delta_rows(
    trades: list[Trade],
    *,
    bucket_minutes: int = 3,
    price_step: float | None = None,
) -> list[dict[str, Any]]:
    buckets: dict[tuple[datetime, str, float], dict[str, Any]] = {}
    for trade in sorted(trades, key=lambda item: (item.ts, item.tradeno)):
        start = _bucket_start(trade.ts, bucket_minutes)
        price = _price_bucket(trade.price, price_step)
        key = (start, trade.secid, price)
        row = buckets.setdefault(key, {
            "bucket_start": start,
            "bucket_end": start + timedelta(minutes=bucket_minutes),
            "secid": trade.secid,
            "price": price,
            "buy_qty": 0.0,
            "sell_qty": 0.0,
            "delta": 0.0,
            "volume": 0.0,
            "trade_count": 0,
        })
        side = (trade.buysell or "").upper()
        if side == "B":
            row["buy_qty"] += float(trade.quantity)
        elif side == "S":
            row["sell_qty"] += float(trade.quantity)
        row["volume"] += float(trade.quantity)
        row["trade_count"] += 1
        row["delta"] = row["buy_qty"] - row["sell_qty"]

    rows: list[dict[str, Any]] = []
    for row in sorted(buckets.values(), key=lambda item: (item["bucket_start"], item["price"])):
        rows.append({
            "bucket_start": row["bucket_start"].isoformat(),
            "bucket_end": row["bucket_end"].isoformat(),
            "secid": row["secid"],
            "price": row["price"],
            "buy_qty": row["buy_qty"],
            "sell_qty": row["sell_qty"],
            "delta": row["delta"],
            "volume": row["volume"],
            "trade_count": row["trade_count"],
        })
    return rows


def _format_qty(value: float) -> str:
    if float(value).is_integer():
        return f"{value:+.0f}"
    return f"{value:+.2f}"


def render_cluster_delta_chart(rows: list[dict[str, Any]], *, bucket_minutes: int = 3) -> str:
    if not rows:
        return f"Cluster Delta {bucket_minutes}m: нет сделок"

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["bucket_start"])].append(row)

    lines = [f"Cluster Delta {bucket_minutes}m", "price | time | delta | buy | sell | volume"]
    for bucket_start in sorted(grouped):
        bucket_rows = sorted(grouped[bucket_start], key=lambda item: float(item["price"]), reverse=True)
        start_dt = datetime.fromisoformat(bucket_start)
        end_dt = datetime.fromisoformat(str(bucket_rows[0]["bucket_end"]))
        time_label = f"{start_dt:%H:%M}-{end_dt:%H:%M}"
        total_delta = sum(float(row["delta"]) for row in bucket_rows)
        lines.append(f"[{time_label}] total delta {_format_qty(total_delta)}")
        for row in bucket_rows:
            lines.append(
                f"{float(row['price']):.3f} | {time_label} | {_format_qty(float(row['delta'])):>8} | "
                f"{float(row['buy_qty']):.0f} | {float(row['sell_qty']):.0f} | {float(row['volume']):.0f}"
            )
    return "\n".join(lines)
