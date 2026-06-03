from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class Quote:
    secid: str
    ts: datetime
    last: float | None = None
    bid: float | None = None
    ask: float | None = None
    high: float | None = None
    low: float | None = None
    open: float | None = None
    volume: float | None = None
    value: float | None = None
    seqnum: int | None = None
    source: str = "moex-iss"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Candle:
    begin: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    value: float | None = None


@dataclass(frozen=True)
class Trade:
    tradeno: int
    secid: str
    ts: datetime
    price: float
    quantity: float
    value: float
    buysell: str | None = None
    boardid: str | None = None
    source: str = "moex-iss-trades"


@dataclass(frozen=True)
class OrderLevel:
    price: float
    quantity: float


@dataclass(frozen=True)
class OrderBook:
    secid: str
    ts: datetime
    bids: list[OrderLevel]
    asks: list[OrderLevel]
    source: str = "unknown"

    def __post_init__(self) -> None:
        # Normalize ordering; callers can pass any iterable/list order.
        object.__setattr__(self, "bids", sorted(list(self.bids), key=lambda level: level.price, reverse=True))
        object.__setattr__(self, "asks", sorted(list(self.asks), key=lambda level: level.price))


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
