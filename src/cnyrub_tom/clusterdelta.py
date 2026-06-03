from __future__ import annotations

from collections import defaultdict
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import floor
from pathlib import Path
from typing import Any

from .models import Trade


@dataclass(frozen=True)
class LiveClusterDeltaState:
    status: str
    summary: str
    chart: str
    trade_count: int
    row_count: int


def _parse_trade_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.strip())


def load_trades_csv(path: str | Path, secid: str | None = None) -> list[Trade]:
    trades: list[Trade] = []
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            trade_secid = row.get("secid") or row.get("SECID") or secid or "CNYRUB_TOM"
            if secid and trade_secid != secid:
                continue
            ts_value = row.get("ts") or row.get("TRADETIME") or row.get("tradetime") or ""
            trades.append(Trade(
                tradeno=int(float(row.get("tradeno") or row.get("TRADENO") or len(trades) + 1)),
                secid=trade_secid,
                ts=_parse_trade_ts(ts_value),
                price=float(row.get("price") or row.get("PRICE") or 0),
                quantity=float(row.get("quantity") or row.get("QUANTITY") or 0),
                value=float(row.get("value") or row.get("VALUE") or 0),
                buysell=row.get("buysell") or row.get("BUYSELL"),
                boardid=row.get("boardid") or row.get("BOARDID"),
                source=row.get("source") or "csv-trades",
            ))
    return trades


def _limit_recent_buckets(rows: list[dict[str, Any]], max_buckets: int | None) -> list[dict[str, Any]]:
    if max_buckets is None or max_buckets <= 0:
        return rows
    bucket_starts = sorted({str(row["bucket_start"]) for row in rows})
    allowed = set(bucket_starts[-max_buckets:])
    return [row for row in rows if str(row["bucket_start"]) in allowed]


def _filter_latest_session_trades(trades: list[Trade]) -> list[Trade]:
    if not trades:
        return []
    latest_session_date = max(_normalize_ts(trade.ts).date() for trade in trades)
    return [trade for trade in trades if _normalize_ts(trade.ts).date() == latest_session_date]


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


def build_cumulative_delta_rows(
    trades: list[Trade],
    *,
    bucket_minutes: int = 3,
) -> list[dict[str, Any]]:
    buckets: dict[tuple[datetime, str], dict[str, Any]] = {}
    for trade in sorted(trades, key=lambda item: (item.ts, item.tradeno)):
        start = _bucket_start(trade.ts, bucket_minutes)
        key = (start, trade.secid)
        row = buckets.setdefault(key, {
            "bucket_start": start,
            "bucket_end": start + timedelta(minutes=bucket_minutes),
            "secid": trade.secid,
            "delta": 0.0,
            "last_price": trade.price,
            "volume": 0.0,
            "trade_count": 0,
        })
        side = (trade.buysell or "").upper()
        if side == "B":
            row["delta"] += float(trade.quantity)
        elif side == "S":
            row["delta"] -= float(trade.quantity)
        row["last_price"] = trade.price
        row["volume"] += float(trade.quantity)
        row["trade_count"] += 1

    cumulative = 0.0
    rows: list[dict[str, Any]] = []
    for row in sorted(buckets.values(), key=lambda item: item["bucket_start"]):
        cumulative += float(row["delta"])
        rows.append({
            "bucket_start": row["bucket_start"].isoformat(),
            "bucket_end": row["bucket_end"].isoformat(),
            "secid": row["secid"],
            "delta": row["delta"],
            "cumulative_delta": cumulative,
            "last_price": row["last_price"],
            "volume": row["volume"],
            "trade_count": row["trade_count"],
        })
    return rows


def render_cumulative_delta_chart(rows: list[dict[str, Any]], *, bucket_minutes: int = 3) -> str:
    if not rows:
        return f"Cumulative Delta {bucket_minutes}m: нет сделок"
    lines = [f"Cumulative Delta {bucket_minutes}m", "time | delta | cumulative | last price | volume"]
    for row in rows:
        start_dt = datetime.fromisoformat(str(row["bucket_start"]))
        end_dt = datetime.fromisoformat(str(row["bucket_end"]))
        time_label = f"{start_dt:%H:%M}-{end_dt:%H:%M}"
        lines.append(
            f"{time_label} | delta {_format_qty(float(row['delta']))} | "
            f"cum {_format_qty(float(row['cumulative_delta']))} | price {float(row['last_price']):.3f} | vol {float(row['volume']):.0f}"
        )
    return "\n".join(lines)


def build_volume_profile_rows(trades: list[Trade], *, price_step: float | None = None) -> list[dict[str, Any]]:
    levels: dict[tuple[str, float], dict[str, Any]] = {}
    for trade in sorted(trades, key=lambda item: (item.price, item.ts, item.tradeno)):
        price = _price_bucket(trade.price, price_step)
        key = (trade.secid, price)
        row = levels.setdefault(key, {
            "secid": trade.secid,
            "price": price,
            "buy_qty": 0.0,
            "sell_qty": 0.0,
            "delta": 0.0,
            "volume": 0.0,
            "trade_count": 0,
            "poc": False,
        })
        side = (trade.buysell or "").upper()
        if side == "B":
            row["buy_qty"] += float(trade.quantity)
        elif side == "S":
            row["sell_qty"] += float(trade.quantity)
        row["volume"] += float(trade.quantity)
        row["trade_count"] += 1
        row["delta"] = row["buy_qty"] - row["sell_qty"]
    rows = sorted(levels.values(), key=lambda item: float(item["price"]))
    if rows:
        poc_volume = max(float(row["volume"]) for row in rows)
        for row in rows:
            row["poc"] = float(row["volume"]) == poc_volume
    return rows


def render_volume_profile_chart(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "Volume Profile: нет сделок"
    max_volume = max(float(row["volume"]) for row in rows) or 1.0
    lines = ["Volume Profile", "price | volume | delta | buy | sell | note"]
    for row in sorted(rows, key=lambda item: float(item["price"]), reverse=True):
        bar = "█" * max(1, round(float(row["volume"]) / max_volume * 20))
        note = "POC" if row.get("poc") else ""
        lines.append(
            f"{float(row['price']):.3f} | {float(row['volume']):.0f} {bar} | {_format_qty(float(row['delta']))} | "
            f"{float(row['buy_qty']):.0f} | {float(row['sell_qty']):.0f} | {note}"
        )
    return "\n".join(lines)


def build_trade_alert_rows(
    trades: list[Trade],
    *,
    bucket_minutes: int = 3,
    price_step: float | None = None,
    min_abs_delta: float = 100.0,
    min_volume: float = 150.0,
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    for row in build_cumulative_delta_rows(trades, bucket_minutes=bucket_minutes):
        delta = float(row["delta"])
        if abs(delta) >= min_abs_delta:
            alerts.append({
                "kind": "strong_buy_delta" if delta > 0 else "strong_sell_delta",
                "ts": row["bucket_start"],
                "secid": row["secid"],
                "price": row["last_price"],
                "delta": delta,
                "volume": row["volume"],
                "confidence": min(1.0, abs(delta) / max(min_abs_delta, 1.0)),
                "reason": f"3m delta {_format_qty(delta)} превышает порог {_format_qty(min_abs_delta)}",
            })
    for row in build_volume_profile_rows(trades, price_step=price_step):
        volume = float(row["volume"])
        if volume >= min_volume:
            alerts.append({
                "kind": "high_volume_price",
                "ts": "session",
                "secid": row["secid"],
                "price": row["price"],
                "delta": row["delta"],
                "volume": volume,
                "confidence": min(1.0, volume / max(min_volume, 1.0)),
                "reason": f"цена {float(row['price']):.3f}: объем {volume:.0f} выше порога {min_volume:.0f}",
            })
    return sorted(alerts, key=lambda item: (str(item["ts"]), str(item["kind"]), float(item["price"] or 0)))


def render_trade_alerts(alerts: list[dict[str, Any]]) -> str:
    if not alerts:
        return "События и алерты: спокойно, сильных событий нет"
    lines = ["События и алерты — смотри сюда", "kind | time | price | delta | volume | reason"]
    for alert in alerts:
        lines.append(
            f"{alert['kind']} | {alert['ts']} | {float(alert['price']):.3f} | "
            f"{_format_qty(float(alert['delta']))} | {float(alert['volume']):.0f} | {alert['reason']}"
        )
    return "\n".join(lines)


@dataclass(frozen=True)
class LiveOrderFlowState:
    status: str
    summary: str
    cumulative_chart: str
    volume_profile_chart: str
    alerts: str
    trade_count: int
    alert_count: int


def build_live_order_flow_state(
    trades_csv: str | Path,
    *,
    secid: str | None = None,
    bucket_minutes: int = 3,
    price_step: float | None = None,
    min_abs_delta: float = 100.0,
    min_volume: float = 150.0,
) -> LiveOrderFlowState:
    path = Path(trades_csv)
    if not path.exists():
        return LiveOrderFlowState(
            status="missing",
            summary=f"CSV сделок не найден: {path}",
            cumulative_chart=render_cumulative_delta_chart([], bucket_minutes=bucket_minutes),
            volume_profile_chart=render_volume_profile_chart([]),
            alerts=render_trade_alerts([]),
            trade_count=0,
            alert_count=0,
        )
    try:
        trades = _filter_latest_session_trades(load_trades_csv(path, secid=secid))
        cumulative = build_cumulative_delta_rows(trades, bucket_minutes=bucket_minutes)
        profile = build_volume_profile_rows(trades, price_step=price_step)
        alerts = build_trade_alert_rows(
            trades,
            bucket_minutes=bucket_minutes,
            price_step=price_step,
            min_abs_delta=min_abs_delta,
            min_volume=min_volume,
        )
        mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%H:%M:%S")
        return LiveOrderFlowState(
            status="active" if trades else "empty",
            summary=f"Order Flow: сделок: {len(trades)} · алертов: {len(alerts)} · файл обновлен: {mtime}",
            cumulative_chart=render_cumulative_delta_chart(cumulative, bucket_minutes=bucket_minutes),
            volume_profile_chart=render_volume_profile_chart(profile),
            alerts=render_trade_alerts(alerts),
            trade_count=len(trades),
            alert_count=len(alerts),
        )
    except Exception as exc:
        return LiveOrderFlowState(
            status="error",
            summary=f"Ошибка чтения order flow: {exc}",
            cumulative_chart=render_cumulative_delta_chart([], bucket_minutes=bucket_minutes),
            volume_profile_chart=render_volume_profile_chart([]),
            alerts=render_trade_alerts([]),
            trade_count=0,
            alert_count=0,
        )


def build_live_cluster_delta_state(
    trades_csv: str | Path,
    *,
    secid: str | None = None,
    bucket_minutes: int = 3,
    price_step: float | None = None,
    max_buckets: int | None = None,
) -> LiveClusterDeltaState:
    path = Path(trades_csv)
    if not path.exists():
        return LiveClusterDeltaState(
            status="missing",
            summary=f"CSV сделок не найден: {path}",
            chart=render_cluster_delta_chart([], bucket_minutes=bucket_minutes),
            trade_count=0,
            row_count=0,
        )
    try:
        all_trades = load_trades_csv(path, secid=secid)
        trades = _filter_latest_session_trades(all_trades)
        rows = build_cluster_delta_rows(trades, bucket_minutes=bucket_minutes, price_step=price_step)
        rows = _limit_recent_buckets(rows, max_buckets)
        chart = render_cluster_delta_chart(rows, bucket_minutes=bucket_minutes)
        mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%H:%M:%S")
        total_delta = sum(float(row["delta"]) for row in rows)
        return LiveClusterDeltaState(
            status="active" if rows else "empty",
            summary=f"Live Cluster Delta с начала сессии: сделок: {len(trades)} · строк: {len(rows)} · delta: {_format_qty(total_delta)} · файл обновлен: {mtime}",
            chart=chart,
            trade_count=len(trades),
            row_count=len(rows),
        )
    except Exception as exc:
        return LiveClusterDeltaState(
            status="error",
            summary=f"Ошибка чтения cluster delta: {exc}",
            chart=render_cluster_delta_chart([], bucket_minutes=bucket_minutes),
            trade_count=0,
            row_count=0,
        )
