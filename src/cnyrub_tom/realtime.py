from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .analysis import summarize_orderbook
from .models import OrderBook
from .providers import FileOrderBookProvider
from .storage import SnapshotStore


@dataclass(frozen=True)
class PatternState:
    advantage: str
    pattern: str
    confidence: float
    explanation: list[str]


@dataclass(frozen=True)
class DashboardState:
    db_status: str
    db_error: str | None
    db_path: str
    snapshot_count: int
    latest_snapshot_id: int | None
    latest_snapshot_ts: str | None
    last_snapshot_age_sec: float | None
    quik_status: str
    quik_path: str | None
    quik_age_sec: float | None
    secid: str | None
    best_bid: float | None
    best_ask: float | None
    spread: float | None
    mid: float | None
    bid_qty: float | None
    ask_qty: float | None
    imbalance: float | None
    advantage: str
    pattern: str
    confidence: float
    explanation: list[str]


def classify_market_pattern(books: list[OrderBook], *, levels: int = 10) -> PatternState:
    ordered = sorted(books, key=lambda book: book.ts)
    if not ordered:
        return PatternState("unknown", "no_data", 0.0, ["нет snapshots стакана"])

    rows = [summarize_orderbook(book, levels=levels) for book in ordered]
    latest = rows[-1]
    imbalance = _as_float(latest.get("imbalance"))
    bid_qty = _as_float(latest.get("bid_qty")) or 0.0
    ask_qty = _as_float(latest.get("ask_qty")) or 0.0
    mid_values = [_as_float(row.get("mid")) for row in rows]
    valid_mids = [value for value in mid_values if value is not None]

    if imbalance is None:
        return PatternState("unknown", "no_data", 0.0, ["недостаточно уровней bid/ask"])

    if imbalance >= 0.25:
        advantage = "buyer"
        explanation = ["bid depth выше ask depth"]
    elif imbalance <= -0.25:
        advantage = "seller"
        explanation = ["ask depth выше bid depth"]
    else:
        advantage = "balance"
        explanation = ["баланс bid/ask без сильного перекоса"]

    mid_change = 0.0
    mid_range = 0.0
    if len(valid_mids) >= 2:
        mid_change = valid_mids[-1] - valid_mids[0]
        mid_range = max(valid_mids) - min(valid_mids)

    latest_mid = valid_mids[-1] if valid_mids else None
    narrow_range = latest_mid is not None and mid_range <= max(0.002, latest_mid * 0.0002)
    pressure_threshold = max(0.001, (latest_mid or 0) * 0.00015)

    if advantage == "buyer" and narrow_range and len(ordered) >= 5:
        pattern = "buyer_accumulation"
        explanation.append("цена стоит в узком диапазоне")
        confidence = _confidence(abs(imbalance), bid_qty, ask_qty, range_bonus=0.25)
    elif advantage == "seller" and narrow_range and len(ordered) >= 5:
        pattern = "seller_accumulation"
        explanation.append("цена стоит в узком диапазоне")
        confidence = _confidence(abs(imbalance), ask_qty, bid_qty, range_bonus=0.25)
    elif mid_change > pressure_threshold and advantage in {"buyer", "balance"}:
        pattern = "up_impulse" if advantage == "buyer" else "up_move"
        explanation.append("mid растет в текущем окне")
        confidence = _confidence(abs(imbalance), bid_qty, ask_qty, range_bonus=0.1)
    elif mid_change < -pressure_threshold and advantage in {"seller", "balance"}:
        pattern = "down_impulse" if advantage == "seller" else "down_move"
        explanation.append("mid падает в текущем окне")
        confidence = _confidence(abs(imbalance), ask_qty, bid_qty, range_bonus=0.1)
    elif advantage == "buyer":
        pattern = "buyer_pressure"
        confidence = _confidence(abs(imbalance), bid_qty, ask_qty)
    elif advantage == "seller":
        pattern = "seller_pressure"
        confidence = _confidence(abs(imbalance), ask_qty, bid_qty)
    else:
        pattern = "balance"
        confidence = 0.35

    return PatternState(advantage, pattern, round(confidence, 4), explanation)


def build_dashboard_state(
    db_path: str | Path,
    *,
    orderbook_path: str | Path | None = None,
    now: datetime | None = None,
    levels: int = 10,
    pattern_window: int = 20,
) -> DashboardState:
    db_path = Path(db_path)
    now = now or datetime.now().astimezone()
    quik_status, quik_age = _quik_status(orderbook_path, now)
    live_book = _read_live_orderbook(orderbook_path)

    if not db_path.exists():
        if live_book is not None:
            pattern = classify_market_pattern([live_book], levels=levels)
            summary = summarize_orderbook(live_book, levels=levels)
            return DashboardState(
                db_status="missing",
                db_error=None,
                db_path=str(db_path),
                snapshot_count=0,
                latest_snapshot_id=None,
                latest_snapshot_ts=live_book.ts.isoformat(),
                last_snapshot_age_sec=None,
                quik_status=quik_status,
                quik_path=str(orderbook_path) if orderbook_path else None,
                quik_age_sec=quik_age,
                secid=live_book.secid,
                best_bid=_as_float(summary.get("best_bid")),
                best_ask=_as_float(summary.get("best_ask")),
                spread=_rounded(summary.get("spread")),
                mid=_rounded(summary.get("mid")),
                bid_qty=_as_float(summary.get("bid_qty")),
                ask_qty=_as_float(summary.get("ask_qty")),
                imbalance=_rounded(summary.get("imbalance"), digits=6),
                advantage=pattern.advantage,
                pattern=pattern.pattern,
                confidence=pattern.confidence,
                explanation=["показываю bid/ask из текущего QUIK JSON; база еще не записана", *pattern.explanation],
            )
        return DashboardState(
            db_status="missing",
            db_error=None,
            db_path=str(db_path),
            snapshot_count=0,
            latest_snapshot_id=None,
            latest_snapshot_ts=None,
            last_snapshot_age_sec=None,
            quik_status=quik_status,
            quik_path=str(orderbook_path) if orderbook_path else None,
            quik_age_sec=quik_age,
            secid=None,
            best_bid=None,
            best_ask=None,
            spread=None,
            mid=None,
            bid_qty=None,
            ask_qty=None,
            imbalance=None,
            advantage="unknown",
            pattern="no_data",
            confidence=0.0,
            explanation=["база данных не найдена"],
        )

    try:
        store = SnapshotStore(db_path)
        snapshot_count = store.snapshot_count()
        latest = store.latest_snapshot_meta()
        books = store.latest_orderbooks(limit=pattern_window)
    except Exception as exc:  # pragma: no cover - defensive for Windows/SQLite runtime issues
        return DashboardState(
            db_status="error",
            db_error=str(exc),
            db_path=str(db_path),
            snapshot_count=0,
            latest_snapshot_id=None,
            latest_snapshot_ts=None,
            last_snapshot_age_sec=None,
            quik_status=quik_status,
            quik_path=str(orderbook_path) if orderbook_path else None,
            quik_age_sec=quik_age,
            secid=None,
            best_bid=None,
            best_ask=None,
            spread=None,
            mid=None,
            bid_qty=None,
            ask_qty=None,
            imbalance=None,
            advantage="unknown",
            pattern="no_data",
            confidence=0.0,
            explanation=["ошибка чтения базы данных"],
        )

    if not books or latest is None:
        if live_book is not None:
            pattern = classify_market_pattern([live_book], levels=levels)
            summary = summarize_orderbook(live_book, levels=levels)
            latest_ts = live_book.ts.isoformat()
            age = None
            secid = live_book.secid
            latest_id = None
        else:
            pattern = PatternState("unknown", "no_data", 0.0, ["в базе нет snapshots"])
            summary: dict[str, float | int | str | None] = {}
            latest_ts = None
            age = None
            secid = None
            latest_id = None
    else:
        pattern = classify_market_pattern(books, levels=levels)
        summary = summarize_orderbook(books[-1], levels=levels)
        latest_id, secid, latest_ts_dt = latest
        latest_ts = latest_ts_dt.isoformat()
        age = max(0.0, (now - latest_ts_dt).total_seconds()) if _same_tz(now, latest_ts_dt) else None

    return DashboardState(
        db_status="connected",
        db_error=None,
        db_path=str(db_path),
        snapshot_count=snapshot_count,
        latest_snapshot_id=latest_id,
        latest_snapshot_ts=latest_ts,
        last_snapshot_age_sec=round(age, 3) if age is not None else None,
        quik_status=quik_status,
        quik_path=str(orderbook_path) if orderbook_path else None,
        quik_age_sec=quik_age,
        secid=secid,
        best_bid=_as_float(summary.get("best_bid")),
        best_ask=_as_float(summary.get("best_ask")),
        spread=_rounded(summary.get("spread")),
        mid=_rounded(summary.get("mid")),
        bid_qty=_as_float(summary.get("bid_qty")),
        ask_qty=_as_float(summary.get("ask_qty")),
        imbalance=_rounded(summary.get("imbalance"), digits=6),
        advantage=pattern.advantage,
        pattern=pattern.pattern,
        confidence=pattern.confidence,
        explanation=pattern.explanation,
    )


def _read_live_orderbook(orderbook_path: str | Path | None) -> OrderBook | None:
    if orderbook_path is None:
        return None
    path = Path(orderbook_path)
    if not path.exists():
        return None
    try:
        return FileOrderBookProvider(path).get_orderbook()
    except Exception:
        return None


def _quik_status(orderbook_path: str | Path | None, now: datetime) -> tuple[str, float | None]:
    if orderbook_path is None:
        return "not_configured", None
    path = Path(orderbook_path)
    if not path.exists():
        return "missing", None
    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=now.tzinfo)
    age = max(0.0, (now - modified).total_seconds())
    return ("active" if age <= 5 else "stale"), round(age, 3)


def _same_tz(left: datetime, right: datetime) -> bool:
    return (left.tzinfo is None and right.tzinfo is None) or (left.tzinfo is not None and right.tzinfo is not None)


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _rounded(value: object, *, digits: int = 10) -> float | None:
    number = _as_float(value)
    return None if number is None else round(number, digits)


def _confidence(imbalance_strength: float, dominant_qty: float, passive_qty: float, *, range_bonus: float = 0.0) -> float:
    total = dominant_qty + passive_qty
    depth_score = (dominant_qty / total) if total else 0.0
    return min(1.0, 0.25 + imbalance_strength * 0.55 + depth_score * 0.2 + range_bonus)
